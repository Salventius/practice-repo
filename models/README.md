# Sweet equity valuation models

Read the full guide first: [`docs/sweet-equity-valuation-guide.md`](../docs/sweet-equity-valuation-guide.md)
— it explains the deal structure, how each input is sourced from the
transaction documents, what every parameter does, and how to review a model
built this way.

## Files

| File | Method | Handles | Requires |
|---|---|---|---|
| `black_scholes_opm.py` | Closed-form Option Pricing Method | Plain waterfalls, fixed exit date; includes backsolve calibration and sensitivities | Standard library only |
| `monte_carlo_sweet_equity.py` | Risk-neutral Monte Carlo | MoM ratchets, exit-timing distributions, leaver haircuts; validates itself against the OPM | `numpy` |

## Run

```bash
python3 models/black_scholes_opm.py
pip install numpy && python3 models/monte_carlo_sweet_equity.py
```

Both scripts price the same worked example (guide §7): €250m equity value,
€200m shareholder loans @ 10% PIK, €30m prefs @ 8%, ordinaries split 85/15,
4-year horizon, 45% volatility. The Monte Carlo's plain case must match the
Black-Scholes number within its standard error — that reconciliation is the
first thing to check in any simulation model you review.

## Adapting to a real deal

1. Transcribe the funds flow statement into the `StripInstrument` list and the
   ordinary split (every instrument, exact faces, documented PIK rates and
   compounding).
2. Set `V0`, `T`, `r`, `sigma`, `q`, DLOM per the guide's parameter sections
   (§5.2), with sources documented.
3. Rewrite `waterfall_management_payoff` to follow the shareholders' agreement
   line by line (ratchet drafting varies — check what the MoM/IRR test is
   measured on).
4. Run the OPM reconciliation, the sum-to-V0 check, and the sensitivity grid.
