"""Reproduce the analysis using Python's standard library only.

Usage: python3 analyze_returns.py /absolute/path/to/returns.csv
Outputs are written alongside this script; the input is read only.
"""

import argparse
import csv
import hashlib
import io
import json
from decimal import Decimal, localcontext
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if reader.fieldnames != ["period", "return"]:
        raise ValueError("Expected period,return columns")
    observations = [(int(row["period"]), Decimal(row["return"])) for row in reader]
    if [period for period, _ in observations] != list(range(1, 6)):
        raise ValueError("Expected five observations in period order 1 through 5")
    if any(not r.is_finite() or r < -1 for _, r in observations):
        raise ValueError("Returns must be finite and at least -1")

    with localcontext() as context:
        context.prec = 50
        wealth = peak = Decimal(1)
        max_drawdown = Decimal(0)
        peak_period = max_peak_period = max_trough_period = 0
        rows = [(0, "", "1", "1", "0")]
        for period, r in observations:
            wealth *= 1 + r
            if wealth > peak:
                peak = wealth
                peak_period = period
            drawdown = (peak - wealth) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_peak_period = peak_period
                max_trough_period = period
            rows.append((period, str(r), str(wealth), str(peak), str(drawdown)))
        cumulative = wealth - 1
        mean = sum((r for _, r in observations), Decimal(0)) / len(observations)
        pct = lambda value: format(value * 100, "f").rstrip("0").rstrip(".")
        evidence = {
            "input_filename": args.input.name,
            "input_sha256": hashlib.sha256(raw).hexdigest(),
            "return_units": "decimal fractional returns per period",
            "observation_count": len(observations),
            "initial_wealth": "1",
            "terminal_wealth": str(wealth),
            "cumulative_compounded_return": str(cumulative),
            "arithmetic_mean_return_per_period": str(mean),
            "maximum_drawdown_loss_magnitude": str(max_drawdown),
            "maximum_drawdown_peak_period": max_peak_period,
            "maximum_drawdown_trough_period": max_trough_period,
            "numeric_encoding": "Decimal values serialized as strings",
        }

        output = Path(__file__).resolve().parent
        with (output / "wealth_path.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["period", "return", "wealth", "running_peak", "drawdown_loss_magnitude"])
            writer.writerows(rows)
        (output / "metrics.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

        table = "\n".join(f"| {p} | {r or '—'} | {w} | {d} |" for p, r, w, _, d in rows)
        report = f"""# Arithmetic average and compounded growth

The five supplied returns are interpreted as fractional returns: 10%, −10%, 5%, 2%, and −3%, in the CSV's period order. Starting wealth is 1; gains and losses remain invested with no cash flows.

| Period | Return (fraction) | Wealth | Drawdown (fraction) |
| --- | --- | --- | --- |
{table}

Terminal wealth is **{wealth}**, so the cumulative compounded return is **{pct(cumulative)}%** over all five periods. The arithmetic mean return is **{pct(mean)}% per period**. The maximum peak-to-trough proportional drawdown is **{pct(max_drawdown)}%**, a nonnegative loss magnitude, from wealth 1.10 at period {max_peak_period} to 0.9900 at period {max_trough_period}.

Calculations use W₀ = 1 and Wₜ = Wₜ₋₁(1 + rₜ). Cumulative return is W₅/W₀ − 1 = ∏(1 + rₜ) − 1. Arithmetic mean is Σrₜ/5 = 0.04/5 = 0.008. Drawdown at each observation is (Pₜ − Wₜ)/Pₜ, where Pₜ = max(W₀, …, Wₜ); the reported maximum includes initial wealth in the peak calculation.

The arithmetic mean summarizes the five individual percentage returns equally. Compounded growth multiplies their wealth factors, because each return acts on the wealth remaining after the preceding period. They describe different time horizons: a per-period average versus the total change over five periods. Summing the returns gives 4%, but actual compounded growth is 2.84813%. For example, +10% followed by −10% leaves 1 × 1.10 × 0.90 = 0.99, despite those two returns averaging zero. Replacing every return with the arithmetic mean would change the wealth path and its final value.

These are five artificial observations, not evidence about a market strategy. No annualization or profitability inference is made. Drawdown is measured only at the supplied period boundaries; no within-period path is available.

## Reproduction and evidence

Run `python3 analyze_returns.py /absolute/path/to/returns.csv` with the authorized input. The script uses only Python's standard library, reads the input without changing it, and writes this report, `wealth_path.csv`, and `metrics.json` beside the script. Decimal arithmetic uses 50-digit precision; all displayed calculations for this input are exact terminating decimals. The JSON records the input SHA-256 hash and central quantities as decimal strings.

In the supplied environment, the default `python3` launcher failed because developer tools were unavailable. Execution succeeded with `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3` and the authorized input at `/Users/baimingqiao/Documents/ChatGPT/Trading/pair-check-20260924-013848/run-retry-20260924-020505/inputs/files/0001/returns.csv`. No packages or tools were installed.

The researcher executed the script and checked the resulting wealth path and metrics against the stated formulas. This is researcher verification, not independent review. Independent recomputation in the Critic's own scratch space remains the Critic's responsibility; no independent verification is claimed here.
"""
        (output / "report.md").write_text(report, encoding="utf-8")
        print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
