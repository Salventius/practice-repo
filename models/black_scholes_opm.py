"""Black-Scholes Option Pricing Method (OPM) for sweet equity valuation.

Values each class in a private-equity capital structure as a portfolio of
call-spreads on total equity value, per the waterfall in the shareholders'
agreement. See docs/sweet-equity-valuation-guide.md for the theory and the
meaning/sourcing of every parameter.

Pure standard library — runnable anywhere with `python3 models/black_scholes_opm.py`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ----------------------------------------------------------------------------
# Black-Scholes call
# ----------------------------------------------------------------------------

def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0) -> float:
    """European call on underlying S, strike K, maturity T (years),
    risk-free rate r, volatility sigma, leakage/dividend yield q.

    K is the breakpoint measured AT EXIT (already accreted for PIK yield);
    it is therefore a fixed strike in the Black-Scholes sense.
    """
    if K <= 0.0:
        # A claim on everything above zero is the whole (leakage-adjusted) pot.
        return S * math.exp(-q * T)
    if T <= 0.0 or sigma <= 0.0:
        return max(S - K, 0.0)
    sqrt_t = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return S * math.exp(-q * T) * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)


# ----------------------------------------------------------------------------
# Capital structure -> breakpoints
# ----------------------------------------------------------------------------

@dataclass
class StripInstrument:
    """A yield-bearing instrument senior to the ordinary shares.

    face:      amount invested at completion (from the funds flow statement)
    pik_rate:  annual accruing yield (from the loan note instrument / articles)
    holder:    class label the proceeds are attributed to
    """
    name: str
    face: float
    pik_rate: float
    holder: str = "institution"

    def balance_at(self, t: float) -> float:
        # Annual compounding; switch to the instrument's documented convention
        # (e.g. quarterly: face * (1 + rate/4) ** (4 * t)) if it differs.
        return self.face * (1.0 + self.pik_rate) ** t


@dataclass
class Tranche:
    """One interval of the waterfall: from `lower` upwards (until the next
    tranche's lower bound), each class receives `sharing[class]` of every
    marginal unit of exit proceeds. Sharing percentages must sum to 1."""
    lower: float
    sharing: dict[str, float]


def build_waterfall(strip: list[StripInstrument], ordinary_split: dict[str, float],
                    T: float) -> list[Tranche]:
    """Standard structure: strip instruments repaid in rank order (list order),
    then ordinaries share the residual. Breakpoints are accreted to exit."""
    tranches: list[Tranche] = []
    cumulative = 0.0
    for inst in strip:
        tranches.append(Tranche(lower=cumulative, sharing={inst.holder: 1.0}))
        cumulative += inst.balance_at(T)
    tranches.append(Tranche(lower=cumulative, sharing=dict(ordinary_split)))
    return tranches


# ----------------------------------------------------------------------------
# OPM allocation
# ----------------------------------------------------------------------------

def opm_allocate(V0: float, tranches: list[Tranche], T: float, r: float,
                 sigma: float, q: float = 0.0) -> dict[str, float]:
    """Allocate today's total equity value V0 across classes.

    Value of a tranche = C(lower) - C(upper): a call-spread between its
    breakpoints. Class values sum to V0 by construction (q = 0 case).
    """
    values: dict[str, float] = {}
    for i, tranche in enumerate(tranches):
        c_lower = bs_call(V0, tranche.lower, T, r, sigma, q)
        c_upper = (bs_call(V0, tranches[i + 1].lower, T, r, sigma, q)
                   if i + 1 < len(tranches) else 0.0)
        spread = c_lower - c_upper
        for holder, pct in tranche.sharing.items():
            values[holder] = values.get(holder, 0.0) + pct * spread
    return values


def backsolve_equity_value(target_class: str, target_value: float,
                           tranches_builder, T: float, r: float, sigma: float,
                           q: float = 0.0, lo: float = 1e-6, hi: float = 1e5,
                           tol: float = 1e-8) -> float:
    """Calibrate V0 so the model value of `target_class` equals what was
    actually paid for it in the transaction (the 'backsolve').

    tranches_builder: callable V0-independent here, but passed as a builder in
    case breakpoints ever depend on V0 (e.g. %-of-equity hurdles).
    Uses bisection: class values are increasing in V0.
    """
    def f(v0: float) -> float:
        return opm_allocate(v0, tranches_builder(), T, r, sigma, q)[target_class] - target_value

    f_lo, f_hi = f(lo), f(hi)
    if f_lo > 0 or f_hi < 0:
        raise ValueError("target value not bracketed; widen [lo, hi]")
    while hi - lo > tol * max(1.0, hi):
        mid = 0.5 * (lo + hi)
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ----------------------------------------------------------------------------
# Worked example (matches docs/sweet-equity-valuation-guide.md §7)
# ----------------------------------------------------------------------------

def example() -> None:
    # --- Inputs (all amounts in €m), sourced per the guide -------------------
    V0 = 250.0        # total equity value today (funds flow: 500 EV - 250 bank debt)
    T = 4.0           # expected hold (sponsor IC papers / fund life)
    r = 0.03          # 4y government yield, EUR
    sigma = 0.45      # re-levered equity vol from listed comparables
    q = 0.0           # fully PIK structure: no cash leakage before exit
    dlom = 0.15       # protective-put based marketability discount

    strip = [
        StripInstrument("Shareholder loans", face=200.0, pik_rate=0.10),
        StripInstrument("Preference shares", face=30.0, pik_rate=0.08),
    ]
    ordinary_split = {"institution_ords": 0.85, "management_sweet": 0.15}
    management_cost = 3.0  # what management paid for its ordinaries

    tranches = build_waterfall(strip, ordinary_split, T)

    print("Breakpoints at exit (accreted):")
    for tr in tranches:
        print(f"  from {tr.lower:8.1f}  ->  {tr.sharing}")

    values = opm_allocate(V0, tranches, T, r, sigma, q)
    total = sum(values.values())
    print(f"\nOPM allocation of V0 = {V0:.1f}:")
    for holder, v in values.items():
        print(f"  {holder:18s} {v:8.2f}")
    print(f"  {'TOTAL':18s} {total:8.2f}   (must equal V0 -> check: "
          f"{'OK' if abs(total - V0) < 1e-6 else 'FAIL'})")

    sweet = values["management_sweet"]
    print(f"\nSweet equity, marketable basis : {sweet:6.2f}")
    print(f"Sweet equity, after {dlom:.0%} DLOM : {sweet * (1 - dlom):6.2f}")
    print(f"Management cost                : {management_cost:6.2f}")
    intrinsic = max(V0 - tranches[-1].lower, 0.0) * ordinary_split["management_sweet"]
    print(f"Naive intrinsic value          : {intrinsic:6.2f}   "
          "(why option pricing is required)")

    # --- Backsolve demo: calibrate V0 from the sponsor's package -------------
    # Suppose the sponsor's whole package (loans + prefs + its ordinaries)
    # traded at its 247.0 cost at completion; solve the implied V0.
    def sponsor_value(v0: float) -> float:
        vals = opm_allocate(v0, tranches, T, r, sigma, q)
        return vals["institution"] + vals["institution_ords"]

    target = 247.0
    lo, hi = 1.0, 2000.0
    while hi - lo > 1e-8 * hi:
        mid = 0.5 * (lo + hi)
        if sponsor_value(mid) < target:
            lo = mid
        else:
            hi = mid
    v0_implied = 0.5 * (lo + hi)
    print(f"\nBacksolve: V0 implied by sponsor paying {target:.1f} for its "
          f"package = {v0_implied:.2f}")

    # --- Sensitivities (always present these in a report) --------------------
    print("\nSweet equity (marketable) sensitivity:")
    print("        " + "".join(f"  T={t:.0f}y " for t in (3, 4, 5)))
    for s in (0.35, 0.45, 0.55):
        row = f"  s={s:.0%}"
        for t in (3.0, 4.0, 5.0):
            trs = build_waterfall(strip, ordinary_split, t)
            v = opm_allocate(V0, trs, t, r, s, q)["management_sweet"]
            row += f"  {v:6.2f}"
        print(row)


if __name__ == "__main__":
    example()
