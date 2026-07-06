# Sweet equity valuation models

**New to the topic? Start with the beginner set** — the Word guide
[`docs/Sweet_Equity_Valuation_Guide.docx`](../docs/Sweet_Equity_Valuation_Guide.docx)
and the live Excel model
[`Sweet_Equity_Valuation_Model.xlsx`](Sweet_Equity_Valuation_Model.xlsx)
(no macros; open sheet "1. Start here"). They share one worked example: a
5-class structure (€180m shareholder loans @10% PIK → €30m prefs @8% → €10m
management rollover notes @10% → A ordinaries 85% → B sweet equity 15%, MoM
ratchet to 20%), pot V0 = €240m.

The markdown guide
[`docs/sweet-equity-valuation-guide.md`](../docs/sweet-equity-valuation-guide.md)
is the more technical practitioner edition, and the Python scripts below use
its simpler 2-instrument example — same methods, different worked numbers.

## Files

| File | Method | Handles | Requires |
|---|---|---|---|
| `Sweet_Equity_Valuation_Model.xlsx` | OPM + 10,000-path Monte Carlo in native Excel formulas | The full 5-class waterfall, ratchet, exit-timing distribution, sensitivity grid, payoff chart | Excel only |
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
