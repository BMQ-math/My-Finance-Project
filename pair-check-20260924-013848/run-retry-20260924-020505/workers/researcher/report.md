# Arithmetic average and compounded growth

The five supplied returns are interpreted as fractional returns: 10%, −10%, 5%, 2%, and −3%, in the CSV's period order. Starting wealth is 1; gains and losses remain invested with no cash flows.

| Period | Return (fraction) | Wealth | Drawdown (fraction) |
| --- | --- | --- | --- |
| 0 | — | 1 | 0 |
| 1 | 0.10 | 1.10 | 0 |
| 2 | -0.10 | 0.9900 | 0.10 |
| 3 | 0.05 | 1.039500 | 0.0550 |
| 4 | 0.02 | 1.06029000 | 0.036100 |
| 5 | -0.03 | 1.0284813000 | 0.06501700 |

Terminal wealth is **1.0284813000**, so the cumulative compounded return is **2.84813%** over all five periods. The arithmetic mean return is **0.8% per period**. The maximum peak-to-trough proportional drawdown is **10%**, a nonnegative loss magnitude, from wealth 1.10 at period 1 to 0.9900 at period 2.

Calculations use W₀ = 1 and Wₜ = Wₜ₋₁(1 + rₜ). Cumulative return is W₅/W₀ − 1 = ∏(1 + rₜ) − 1. Arithmetic mean is Σrₜ/5 = 0.04/5 = 0.008. Drawdown at each observation is (Pₜ − Wₜ)/Pₜ, where Pₜ = max(W₀, …, Wₜ); the reported maximum includes initial wealth in the peak calculation.

The arithmetic mean summarizes the five individual percentage returns equally. Compounded growth multiplies their wealth factors, because each return acts on the wealth remaining after the preceding period. They describe different time horizons: a per-period average versus the total change over five periods. Summing the returns gives 4%, but actual compounded growth is 2.84813%. For example, +10% followed by −10% leaves 1 × 1.10 × 0.90 = 0.99, despite those two returns averaging zero. Replacing every return with the arithmetic mean would change the wealth path and its final value.

These are five artificial observations, not evidence about a market strategy. No annualization or profitability inference is made. Drawdown is measured only at the supplied period boundaries; no within-period path is available.

## Reproduction and evidence

Run `python3 analyze_returns.py /absolute/path/to/returns.csv` with the authorized input. The script uses only Python's standard library, reads the input without changing it, and writes this report, `wealth_path.csv`, and `metrics.json` beside the script. Decimal arithmetic uses 50-digit precision; all displayed calculations for this input are exact terminating decimals. The JSON records the input SHA-256 hash and central quantities as decimal strings.

In the supplied environment, the default `python3` launcher failed because developer tools were unavailable. Execution succeeded with `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3` and the authorized input at `/Users/baimingqiao/Documents/ChatGPT/Trading/pair-check-20260924-013848/run-retry-20260924-020505/inputs/files/0001/returns.csv`. No packages or tools were installed.

The researcher executed the script and checked the resulting wealth path and metrics against the stated formulas. This is researcher verification, not independent review. Independent recomputation in the Critic's own scratch space remains the Critic's responsibility; no independent verification is claimed here.
