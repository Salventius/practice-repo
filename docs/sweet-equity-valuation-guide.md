# Sweet Equity Valuation — A Complete Practitioner's Guide

*From deal documents to a working Black-Scholes / Monte Carlo model, with every
parameter explained: what it is, where it comes from, how it moves the result,
and why it belongs in the model.*

This guide accompanies two runnable reference models in this repository:

- [`models/black_scholes_opm.py`](../models/black_scholes_opm.py) — the Option
  Pricing Method (OPM): closed-form Black-Scholes allocation of equity value
  across the waterfall, plus a calibration ("backsolve") routine.
- [`models/monte_carlo_sweet_equity.py`](../models/monte_carlo_sweet_equity.py)
  — a Monte Carlo simulation handling the features Black-Scholes cannot
  (ratchets, uncertain exit timing, leaver adjustments).

---

## 1. What is sweet equity, and why is it an option?

In a private equity buyout, the financial sponsor (the "institution") typically
does **not** invest all of its money in ordinary shares. A typical structure:

```
Enterprise value                          €500m
  Bank / external debt                    €250m   ← senior, contractual
  ─────────────────────────────────────────────
  Total equity funding                    €250m
    Shareholder loans / loan notes        €200m   ← institution, 10% PIK yield
    Preference shares                      €30m   ← institution, fixed accruing dividend
    Ordinary shares                        €20m
       Institution (85%)                   €17m
       Management ("sweet equity", 15%)     €3m
```

The institution puts ~92% of its money into yield-bearing instruments (the
**"institutional strip"**) and only a small slice into ordinary shares.
Management, by contrast, invests **only** (or mostly) in ordinary shares. This
is what makes management's equity "sweet": for €3m, management gets 15% of all
value **above** the strip — far more upside per euro invested than the
institution gets. The ratio of effective price-per-ordinary-share paid by the
institution versus management is called the **envy ratio**.

The economic consequence is the key insight of the whole exercise:

> **The ordinary shares only receive proceeds after the strip (plus all its
> accrued yield) is repaid. Their payoff at exit is
> `max(Exit equity value − Strip balance at exit, 0) × ownership %` —
> exactly the payoff of a call option on the company's equity value, struck at
> the strip balance.**

That is why sweet equity is valued with option-pricing techniques
(Black-Scholes or Monte Carlo) rather than by naïve pro-rata allocation:

- **Pro-rata / "current value" allocation** (equity value minus strip, split by
  ownership) values only *intrinsic* value. If the strip exceeds today's equity
  value, it says the sweet equity is worth zero — clearly wrong, since the
  shares still carry the whole upside of the business over a 3–5 year hold.
- **Option pricing** captures both intrinsic value *and* the **time value** of
  the leveraged claim — the value of volatility over the holding period.

### Why the valuation matters (the typical assignments)

- **At entry (tax)**: managers must generally acquire their shares at market
  value or face income tax on the discount (UK: employment-related securities /
  HMRC practice; Netherlands: *lucratief belang* analysis; US: §409A-style
  fair-market-value support). The valuation demonstrates the price paid was
  arm's length.
- **Financial reporting**: IFRS 2 / ASC 718 grant-date fair value if the
  arrangement is (partly) share-based payment.
- **Ongoing / exit reviews**: fund NAV reporting (IPEV guidelines), disputes,
  or — as in your case — a **review** of someone else's valuation, where you
  test each input and the mechanics.

---

## 2. Deal structure vocabulary you must know

| Term | Meaning | Why it matters for the model |
|---|---|---|
| **Institutional strip** | The sponsor's package of shareholder loans + preference shares (+ its ordinary shares) | The loans/prefs define the option **strikes** (breakpoints) |
| **PIK yield** | "Payment in kind" — interest/dividend that accrues and compounds instead of being paid in cash | Strikes **grow over time**; longer hold = higher hurdle for the sweet equity |
| **Sweet equity** | Management's ordinary shares, bought at ordinary-share price while the sponsor's money is mostly in the strip | The asset being valued |
| **Envy ratio** | (Sponsor € per 1% of ordinaries) ÷ (Management € per 1% of ordinaries) | Sanity check on "sweetness"; typically 2–5× in mid-market deals |
| **Hurdle** | Value the equity must exceed before ordinaries participate | = sum of strip balances at exit = the option strike |
| **Ratchet** | Management's ordinary % steps up (or down) if the sponsor achieves a return threshold (MoM or IRR) | Path-dependent payoff → usually forces **Monte Carlo** |
| **Good/bad leaver** | Manager leaving early forfeits shares or sells back at cost/market depending on circumstances | Reduces value; handled as probability-weighted haircut or vesting schedule |
| **Waterfall** | The contractual order in which exit proceeds are distributed | The model **is** the waterfall wrapped in a distribution of exit values |
| **MoM / IRR** | Money multiple / internal rate of return of the sponsor | Ratchet triggers; also used in sanity checks |

---

## 3. From documents to model inputs

You build the entire model from the transaction documents. Map them like this:

| Document | What you extract |
|---|---|
| **Funds flow / sources & uses statement** (completion) | The opening capital structure: exact amounts invested per instrument per party — your day-one strip faces and ordinary splits. The single most load-bearing document. |
| **Shareholders' agreement (SHA) / investment agreement** | Ranking of instruments, exit provisions, drag/tag, leaver provisions, transfer restrictions, ratchet terms |
| **Articles of association / share class terms** | Legal waterfall: liquidation preference of each class, dividend/coupon rates, compounding convention (annual? quarterly?), participation rights |
| **Loan note instruments** | Face, PIK rate, compounding, redemption ranking, any cash-pay element |
| **Management equity term sheet / MIP rules** | Vesting, hurdle shares, ratchet schedule, strike prices of any options |
| **SPA + financial model / business plan** | Enterprise value at the transaction, projections (context for exit horizon and sanity checks) |
| **Bank facility agreements** | External debt amount and terms — needed if you model enterprise value rather than equity value |
| **IM / lender presentations, comparable company data** | Volatility comparables, exit horizon evidence |

**The first artefact you build is a capitalisation table with ranking**: for
each instrument — holder, face amount at completion, yield, compounding, rank.
Everything else in the model derives from it.

---

## 4. The waterfall and breakpoints

At exit, equity proceeds `V_T` (equity value after repaying external bank debt)
are distributed in rank order. With the example structure above and a 4-year
hold:

1. Shareholder loans: €200m compounding at 10% → balance at exit
   `200 × 1.10⁴ = €292.8m`
2. Preference shares: €30m at 8% → `30 × 1.08⁴ = €40.8m`
3. Ordinary shares: everything above `292.8 + 40.8 = €333.6m`, split 85/15.

The **breakpoints** are the cumulative claim levels at which the *marginal*
allocation of one extra euro of proceeds changes:

| Interval of `V_T` | Who gets the marginal euro |
|---|---|
| €0 – €292.8m | Shareholder loans (institution) 100% |
| €292.8m – €333.6m | Preference shares (institution) 100% |
| above €333.6m | Ordinaries: institution 85%, management 15% |

Each interval's payoff to a class is a **call spread**: the payoff between two
strikes. That observation converts the whole waterfall into a portfolio of call
options — the Option Pricing Method.

> **Critical detail — breakpoints are measured at exit, including accrued
> yield.** A very common error in models under review is using day-one face
> values (€230m) instead of accreted balances (€333.6m) as strikes. The PIK
> accrual is precisely what makes long holds expensive for sweet equity.

---

## 5. The Black-Scholes OPM

### 5.1 Mechanics

Model the total equity value `V` as following geometric Brownian motion. The
value of a claim on everything **above** breakpoint `B` at time `T` is a
European call `C(V₀, B, T, r, σ, q)`:

```
C = V₀·e^(−qT)·N(d₁) − B·e^(−rT)·N(d₂)
d₁ = [ln(V₀/B) + (r − q + σ²/2)T] / (σ√T)
d₂ = d₁ − σ√T
```

The value of each class is a sum of call-spreads:

```
Value(class c) = Σᵢ  shareᵢ(c) × [ C(Bᵢ) − C(Bᵢ₊₁) ]
```

where `shareᵢ(c)` is class *c*'s marginal share in interval *i*, `C(B₀=0) = V₀`
and the top interval has no upper call. By construction the class values sum
exactly to `V₀` — your first arithmetic check on any model.

The sweet equity in the example is simply
`15% × C(V₀, K = 333.6, T = 4, r, σ)` (single breakpoint above which management
participates).

### 5.2 Every parameter, explained

#### `V₀` — the underlying: total equity value today
- **What**: the value of *all* equity instruments combined (shareholder loans +
  prefs + ordinaries), i.e. enterprise value minus external net debt. This is
  the "stock price" in Black-Scholes.
- **Source**: at or near the transaction date, the **transaction itself** is the
  best evidence — total equity funding in the funds flow. Later, re-derive from
  a market approach (EBITDA × multiple − net debt) and/or DCF.
- **Influence**: the single biggest driver. Sweet equity is a leveraged,
  usually near- or out-of-the-money claim, so its value is **convex** in `V₀`:
  a 10% rise in `V₀` can raise sweet equity value by 30%+.
- **Why included**: it is the asset the option is written on.
- **Modelling choice to be aware of**: you can instead model **enterprise
  value** as the underlying and put bank debt as the first breakpoint. Then you
  must use **asset volatility**, not equity volatility (see σ below). Modelling
  post-bank-debt equity value with equity volatility is the more common
  practical choice; both are valid **if the volatility is consistent with the
  chosen underlying**.

#### `Bᵢ` — the strikes: breakpoints at exit
- **What**: cumulative accreted claim balances at the assumed exit date (see §4).
- **Source**: pure arithmetic from the cap table — faces, PIK rates,
  compounding convention, projected to `T`. Read the compounding convention in
  the instrument (annual vs quarterly compounding on 10% over 4 years differs
  by ~2% of face).
- **Influence**: higher strikes → sweet equity further out of the money → lower
  value, more of it being time value. Because strikes grow at the PIK rate,
  **the strike races the underlying**: if the PIK rate exceeds the risk-neutral
  drift, waiting hurts the ordinaries.
- **Why included**: they encode the contractual subordination that defines
  sweet equity.

#### `σ` — volatility
- **What**: annualised volatility of the *underlying you chose* (equity value
  or EV) over the holding period.
- **Source**: listed comparable companies. Standard process:
  1. take comparables' historical (or option-implied) **equity** volatilities
     over a window matching `T`;
  2. **de-lever** each to asset volatility, e.g.
     `σ_asset ≈ σ_equity × E/(E+D)` (or a Merton-consistent de-levering);
  3. take a representative asset vol for the sector;
  4. **re-lever** at the subject's own leverage if your underlying is equity
     value: `σ_equity ≈ σ_asset × (E+D)/E` using the subject's bank debt.
  Buyout targets are highly levered, so subject equity vols of 35–60% from
  sector asset vols of 20–30% are normal.
- **Influence**: more volatility → more time value → **more value shifts from
  the strip to the sweet equity** (option holders love volatility; the strip is
  effectively short that option). For out-of-the-money sweet equity, value is
  strongly increasing and roughly linear-to-convex in σ. This is usually the
  most contested and most judgmental input — always show a sensitivity.
- **Why included**: it is the parameter that gives the out-of-the-money claim
  its value; without it you are back to naïve intrinsic-value allocation.

#### `T` — time to exit
- **What**: expected time until a liquidity event (sale, IPO) crystallises the
  waterfall.
- **Source**: sponsor's stated hold strategy (IC papers, IM), fund life and the
  fund's age, sector norms. Typical PE hold: 3–5 years.
- **Influence**: **two-sided**, unlike a plain option. Longer `T` gives more
  time value (helps sweet equity) **but** also more PIK accrual on the strikes
  (hurts it). Which effect wins depends on PIK rate vs `r` and moneyness — test
  it, don't assume. This interaction is a classic review point.
- **Why included**: option value and strike accretion both depend on the
  horizon; the waterfall only bites at exit.

#### `r` — risk-free rate
- **What**: continuously-compounded government yield matching `T` and the
  **currency of the cash flows**.
- **Source**: government bond/swap curve at the valuation date.
- **Influence**: modest. Higher `r` raises risk-neutral drift (helps calls) and
  lowers the PV of strikes — both push sweet equity value up slightly.
- **Why included**: option pricing works under the risk-neutral measure, where
  the underlying drifts at `r` and payoffs are discounted at `r`. **You do not
  use a WACC or an expected equity return anywhere in the model** — risk
  adjustment happens through the measure change, not the discount rate. Mixing
  a real-world drift with risk-free discounting is one of the most common fatal
  errors in reviewed models.

#### `q` — leakage / dividend yield
- **What**: rate at which value leaves the modelled underlying before exit —
  cash dividends, cash-pay interest on instruments *inside* the underlying.
- **Source**: the instruments and dividend policy. In a standard buyout with
  fully PIK strip and no dividends, `q = 0` (all value stays in the pot and is
  distributed at exit).
- **Influence**: leakage lowers the terminal underlying → hurts the junior
  claims most.
- **Why included**: standard Black-Scholes assumes no leakage; if the documents
  provide for cash coupons or sweeps, ignoring them overstates ordinary-share
  value.

#### DLOM — discount for lack of marketability
- **What**: a discount applied **to the sweet equity value** (not to `V₀`)
  reflecting that a minority manager cannot sell: transfer restrictions,
  drag/tag only, no market.
- **Source/technique**: protective-put estimators (Chaffe: an at-the-money put
  over the restriction period; Finnerty's average-strike put) or restricted
  stock studies. Typical outcomes 10–30% depending on `σ` and `T`.
- **Influence**: direct multiplicative reduction of the concluded value.
- **Why included / review flags**: a marketable-basis option value overstates
  what a hypothetical buyer would pay for a locked-up minority stake. But watch
  for **double counting** (a DLOM on top of assumptions that already embed
  illiquidity) and for DLOMs applied to the *whole* equity value rather than
  the interest being valued.

### 5.3 Calibration ("backsolve")

At or shortly after the transaction date, the strongest evidence is the deal
itself: the sponsor paid a known price for a known package. The **backsolve**
inverts the OPM: solve for the `V₀` (and/or σ) that makes the model value of
the sponsor's package equal what the sponsor actually paid. Then read off the
sweet equity value from the same calibrated model. This anchors the model to a
real arm's-length trade and is expected practice under IPEV and in tax work.
`black_scholes_opm.py` implements this with a bisection solve.

### 5.4 What Black-Scholes cannot do

The closed form requires: a single known exit date, breakpoints that depend
only on time (not on the path), and payoffs that are piecewise-linear in `V_T`.
It breaks when the documents contain:

- **ratchets** triggered on sponsor **IRR** (depends on exit timing *and*
  value) or MoM cliffs (piecewise but state-dependent splits — still OK in
  closed form if MoM maps to a `V_T` threshold, but messy);
- **uncertain exit timing** that you want to model as a distribution;
- **leaver/vesting** interacting with time;
- interim **refinancings / dividend recaps**;
- caps, catch-ups with non-linear kinks that are easier to just simulate.

That is what Monte Carlo is for.

---

## 6. Monte Carlo simulation

### 6.1 Why it's used and what it is

Monte Carlo makes no attempt at a closed form. It:

1. draws many (e.g. 200,000) random exit scenarios for the underlying,
2. runs each scenario through the **full contractual waterfall** — however
   complicated — to get management's payoff in that scenario,
3. discounts and averages.

Because step 2 is just code implementing the legal documents, *any* feature the
SHA can invent (ratchets, IRR hurdles, leaver haircuts, caps) is handled by
construction. The price is sampling noise and the need to verify convergence.

### 6.2 The engine, piece by piece

**Terminal value draw (GBM under the risk-neutral measure):**

```
V_T = V₀ · exp( (r − q − σ²/2)·T + σ·√T · Z ),   Z ~ N(0,1)
```

Every parameter has exactly the same meaning, source, and influence as in
§5.2 — Monte Carlo with a plain waterfall and fixed `T` must reproduce the
Black-Scholes OPM to within sampling error. **Run that reconciliation; it is
the single best test of a simulation model.** The `(−σ²/2)` term is the Itô
correction ensuring the *expected* value grows at `r − q`; forgetting it biases
values upward — another review classic.

**Risk-neutral, again**: drift at `r`, discount at `e^(−rT)`. If the model
under review simulates at a "management case" growth rate or a WACC drift and
discounts at anything else, the valuation has no theoretical basis. (A
real-world simulation can be a legitimate *supplementary* exhibit — e.g. "what
is the probability management's shares pay ≥2× cost" — but not the fair value.)

**Exit timing**: instead of fixed `T`, draw exit time per path from a
distribution (e.g. 30% year 3, 40% year 4, 30% year 5, per sponsor evidence).
Strikes are accreted to *each path's own exit date* — this couples the hurdle
to the horizon correctly, which no single-`T` closed form can.

**The waterfall function**: a direct transcription of the documents. Per path:
repay strip balances in rank order, apply the ordinary split, apply the ratchet
rule (e.g. "management ordinary share steps 15% → 20% if sponsor MoM ≥ 2.5×",
computing sponsor MoM from that path's own proceeds and timing), output
management's proceeds.

**Leaver / vesting adjustments**: probability-weight the payoff for forfeiture
risk, or model a vesting fraction as a function of exit time. Keep it explicit
and separately switchable — reviewers should be able to see value with and
without it.

**Convergence and variance reduction**: report the standard error
(`std/√n`); use **antithetic variates** (pair every `Z` with `−Z`) — nearly
free and cuts variance materially for monotone payoffs; fix the random **seed**
for reproducibility.

**DLOM**: applied to the simulated marketable value at the end, exactly as in
the OPM.

### 6.3 Outputs a good MC model should show

- Management (sweet equity) value, per class, with standard errors;
- Reconciliation: Σ discounted class values = `V₀` (no-leakage case);
- Degenerate-case check against Black-Scholes OPM;
- Distribution diagnostics: probability sweet equity finishes worthless,
  P(payoff ≥ cost), percentiles;
- Sensitivities on σ, `T`, `V₀` (and ratchet thresholds if present).

---

## 7. Worked example (matches the code)

Structure: `V₀ = €250m`; SHL €200m @ 10% PIK; prefs €30m @ 8%; ordinaries split
85/15; `T = 4y`; `r = 3%`; `σ = 45%`; `q = 0`; management paid €3m for its
ordinaries; ratchet to 20% if sponsor MoM ≥ 2.5× (MC only); DLOM 15%.

Running `python3 models/black_scholes_opm.py` and
`python3 models/monte_carlo_sweet_equity.py` reproduces, approximately:

- Breakpoints at exit: €292.8m (SHL) and €333.6m (SHL+prefs).
- OPM sweet equity (no ratchet, marketable): ≈ **€11.0m** for the 15%
  (≈ €9.4m after the 15% DLOM) —
  i.e. management's €3m buys something worth well over cost on a marketable
  basis *because of time value*, even though intrinsic value at `V₀ = 250` is
  **zero** (250 < 333.6). This is the essence of why option models are
  mandatory here.
- Monte Carlo without ratchet matches the OPM within the standard error;
  adding the ratchet and exit-timing distribution moves the number; the 15%
  DLOM then applies.
- Note the envy: management holds 15% of ordinaries for €3m; the sponsor holds
  85% for €17m — proportionate. The sweetness is not in the ordinary split
  but in the fact that the sponsor's *other* €230m earns only a fixed yield
  while ordinaries take all residual upside.

---

## 8. Reviewer's checklist (common errors, in rough order of frequency)

**Mechanics**
- [ ] Do the OPM class values **sum exactly to V₀**? (They must, absent leakage.)
- [ ] Are breakpoints **accreted to exit** at documented rates and compounding —
      not day-one faces?
- [ ] Does the MC **reconcile to Black-Scholes** in the plain-waterfall case?
- [ ] Itô correction present in the GBM? Seed fixed? Standard error disclosed
      and small relative to the answer?

**Measure-consistency**
- [ ] Risk-neutral drift `r` **and** risk-free discounting — no WACC, no
      business-plan growth as drift?
- [ ] Volatility consistent with the underlying (asset vol ↔ EV; re-levered
      equity vol ↔ equity value)? Term of vol ≈ `T`?

**Inputs**
- [ ] `V₀` calibrated/backsolved to the transaction (if near deal date), or
      supported by multiples/DCF (if later)?
- [ ] `T` evidenced (fund life, IC papers), and sensitivity shown given the
      two-sided effect?
- [ ] Cash leakage (`q`) consistent with instrument cash-pay terms?
- [ ] All instruments in the funds flow appear in the waterfall (no missing
      pref class, no forgotten management loan notes)?

**Terms**
- [ ] Ratchet, leaver, vesting, and any hurdle shares actually modelled — or
      their exclusion justified?
- [ ] IRR-based triggers handled path-consistently (need MC, not closed form)?

**Adjustments & conclusion**
- [ ] DLOM method disclosed, applied to the subject interest only, no double
      count?
- [ ] Envy ratio computed and benchmarked; conclusion sanity-checked against
      management's price paid and against P(worthless) from the MC?
- [ ] Sensitivity table on σ and `T` presented?

---

## 9. Suggested further reading

- IPEV Valuation Guidelines (allocation of enterprise value across classes).
- AICPA guide *Valuation of Privately-Held-Company Equity Securities Issued as
  Compensation* (the "Cheap Stock" guide) — canonical OPM/backsolve reference.
- Hull, *Options, Futures and Other Derivatives* — Black-Scholes and Monte
  Carlo foundations.
- Chaffe (1993) and Finnerty (2012) papers on put-based DLOM estimators.
