"""Monte Carlo simulation for sweet equity valuation.

Handles the features the closed-form Black-Scholes OPM cannot:
  - a performance ratchet on the sponsor's money multiple (MoM),
  - uncertain exit timing (a distribution over holding periods),
  - leaver / forfeiture probability weighting.

Method (see docs/sweet-equity-valuation-guide.md §6):
  1. draw exit time and terminal equity value per path under the RISK-NEUTRAL
     measure (GBM: drift r - q, discount at r);
  2. run each path through the full contractual waterfall;
  3. discount and average; report standard errors;
  4. reconcile the plain (no-ratchet, fixed-T) case to the Black-Scholes OPM.

Requires numpy. Run: python3 models/monte_carlo_sweet_equity.py
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from black_scholes_opm import StripInstrument, build_waterfall, opm_allocate


# ----------------------------------------------------------------------------
# Deal terms (transcribed from the SHA / articles / funds flow)
# ----------------------------------------------------------------------------

@dataclass
class DealTerms:
    V0: float = 250.0                    # total equity value today
    r: float = 0.03                      # risk-free rate (matches horizon, currency)
    sigma: float = 0.45                  # volatility of the underlying (equity value)
    q: float = 0.0                       # cash leakage before exit (0 = fully PIK)

    strip: list[StripInstrument] = field(default_factory=lambda: [
        StripInstrument("Shareholder loans", face=200.0, pik_rate=0.10),
        StripInstrument("Preference shares", face=30.0, pik_rate=0.08),
    ])

    # Ordinary shares: base split, ratcheting up for management if the
    # sponsor's MoM at exit reaches the trigger (per the MIP term sheet).
    mgmt_ord_base: float = 0.15
    mgmt_ord_ratcheted: float = 0.20
    ratchet_mom_trigger: float = 2.5     # sponsor MoM >= 2.5x -> ratchet applies
    sponsor_cost: float = 247.0          # sponsor total invested (loans+prefs+ords)

    # Exit timing distribution (evidence: fund life, sponsor hold strategy)
    exit_times: tuple[float, ...] = (3.0, 4.0, 5.0)
    exit_probs: tuple[float, ...] = (0.30, 0.40, 0.30)

    management_cost: float = 3.0         # price management paid for its ordinaries
    leaver_haircut: float = 0.0          # e.g. 0.05 = 5% expected forfeiture
    dlom: float = 0.15                   # marketability discount on the sweet equity


def waterfall_management_payoff(VT: np.ndarray, T: np.ndarray, d: DealTerms
                                ) -> tuple[np.ndarray, np.ndarray]:
    """Distribute exit proceeds VT (per path, at path-specific exit time T).

    Returns (management proceeds, sponsor proceeds) per path. This function IS
    the legal waterfall — extend it line by line as the documents require.
    """
    remaining = VT.copy()
    sponsor = np.zeros_like(VT)

    # 1) Strip instruments in rank order, balances accreted to each path's exit
    for inst in d.strip:
        balance = inst.face * (1.0 + inst.pik_rate) ** T
        paid = np.minimum(remaining, balance)
        sponsor += paid                       # strip is held by the sponsor
        remaining -= paid

    # 2) Ordinary shares. Ratchet depends on sponsor MoM, which depends on the
    #    ordinary split itself -> solve the circularity per the documents.
    #    Typical drafting (used here): test the trigger on the BASE split.
    residual = remaining
    sponsor_base = sponsor + (1.0 - d.mgmt_ord_base) * residual
    mom_base = sponsor_base / d.sponsor_cost
    ratchet_on = mom_base >= d.ratchet_mom_trigger

    mgmt_pct = np.where(ratchet_on, d.mgmt_ord_ratcheted, d.mgmt_ord_base)
    mgmt = mgmt_pct * residual
    sponsor = sponsor + (1.0 - mgmt_pct) * residual
    return mgmt, sponsor


# ----------------------------------------------------------------------------
# Simulation engine
# ----------------------------------------------------------------------------

def simulate(d: DealTerms, n_paths: int = 200_000, seed: int = 42,
             fixed_T: float | None = None, use_ratchet: bool = True):
    """Risk-neutral Monte Carlo. Returns dict of results.

    fixed_T / use_ratchet=False give the degenerate case that must reconcile
    to the closed-form OPM (the key validation of the engine).
    """
    rng = np.random.default_rng(seed)

    # Exit times per path
    if fixed_T is not None:
        T = np.full(n_paths, fixed_T)
    else:
        T = rng.choice(d.exit_times, size=n_paths, p=d.exit_probs)

    # Antithetic variates: pair each normal draw with its negative
    half = n_paths // 2
    z_half = rng.standard_normal(half)
    Z = np.concatenate([z_half, -z_half])
    T = T[: 2 * half]

    # GBM terminal value, risk-neutral drift (note the Ito -sigma^2/2 term)
    VT = d.V0 * np.exp((d.r - d.q - 0.5 * d.sigma**2) * T
                       + d.sigma * np.sqrt(T) * Z)

    if not use_ratchet:
        # Plain waterfall at the base split (OPM-reconcilable case)
        d = replace(d, ratchet_mom_trigger=float("inf"))
    mgmt, sponsor = waterfall_management_payoff(VT, T, d)

    df = np.exp(-d.r * T)
    disc_mgmt = df * mgmt
    disc_total = df * VT

    value = disc_mgmt.mean() * (1.0 - d.leaver_haircut)
    return {
        "mgmt_value_marketable": value,
        "mgmt_value_after_dlom": value * (1.0 - d.dlom),
        "std_error": disc_mgmt.std(ddof=1) / np.sqrt(len(disc_mgmt)),
        "recon_total": disc_total.mean(),       # should ~= V0 when q = 0
        "p_worthless": float((mgmt <= 0).mean()),
        "p_ge_cost": float((mgmt >= d.management_cost).mean()),
        "percentiles": np.percentile(mgmt, [25, 50, 75, 90, 99]),
    }


def example() -> None:
    d = DealTerms()

    # --- 1) Validation: fixed T, no ratchet, must match Black-Scholes OPM ----
    mc = simulate(d, fixed_T=4.0, use_ratchet=False)
    tranches = build_waterfall(d.strip, {"inst": 1 - d.mgmt_ord_base,
                                         "mgmt": d.mgmt_ord_base}, 4.0)
    opm = opm_allocate(d.V0, tranches, 4.0, d.r, d.sigma, d.q)["mgmt"]
    print("Validation (fixed T=4, no ratchet):")
    print(f"  Monte Carlo sweet equity : {mc['mgmt_value_marketable']:7.2f}"
          f"  (std err {mc['std_error']:.3f})")
    print(f"  Black-Scholes OPM        : {opm:7.2f}")
    print(f"  Total value recon        : {mc['recon_total']:7.2f}  vs V0 = {d.V0:.2f}")

    # --- 2) Full model: exit-timing distribution + MoM ratchet ---------------
    mc = simulate(d)
    print("\nFull model (exit distribution 3/4/5y, MoM 2.5x ratchet 15%->20%):")
    print(f"  Sweet equity, marketable : {mc['mgmt_value_marketable']:7.2f}"
          f"  (std err {mc['std_error']:.3f})")
    print(f"  After {d.dlom:.0%} DLOM           : {mc['mgmt_value_after_dlom']:7.2f}")
    print(f"  P(sweet equity worthless): {mc['p_worthless']:7.1%}")
    print(f"  P(payoff >= {d.management_cost:.0f}m cost)    : {mc['p_ge_cost']:7.1%}")
    print(f"  Payoff percentiles 25/50/75/90/99: "
          + " ".join(f"{p:.1f}" for p in mc["percentiles"]))

    # --- 3) Sensitivities -----------------------------------------------------
    print("\nSweet equity (after DLOM) sensitivity to volatility:")
    for s in (0.35, 0.45, 0.55):
        d2 = DealTerms(sigma=s)
        r2 = simulate(d2)
        print(f"  sigma={s:.0%}: {r2['mgmt_value_after_dlom']:6.2f}")


if __name__ == "__main__":
    example()
