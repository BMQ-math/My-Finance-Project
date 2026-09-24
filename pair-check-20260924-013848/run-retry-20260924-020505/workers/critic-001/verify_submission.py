"""Independent exact-rational verification; standard library only."""
import csv
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import subprocess
import sys

ROOT = Path('/Users/baimingqiao/Documents/ChatGPT/Trading/pair-check-20260924-013848/run-retry-20260924-020505/snapshots/submission-001-1bb3ae96')
HERE = Path(__file__).resolve().parent
source = ROOT / 'inputs/files/0001/returns.csv'
with source.open(newline='') as f:
    observations = list(csv.DictReader(f))
returns = [Fraction(row['return']) for row in observations]
wealth = [Fraction(1)]
for r in returns:
    wealth.append(wealth[-1] * (1 + r))
peaks = [max(wealth[:i + 1]) for i in range(len(wealth))]
drawdowns = [1 - w / p for w, p in zip(wealth, peaks)]
# Exhaustively examine every ordered peak/trough candidate independently.
loss, peak_period, trough_period = max(
    (1 - wealth[j] / wealth[i], i, j)
    for i in range(len(wealth)) for j in range(i, len(wealth))
)
metrics = json.loads((ROOT / 'artifacts/metrics.json').read_text())
expected = {
    'initial_wealth': wealth[0],
    'terminal_wealth': wealth[-1],
    'cumulative_compounded_return': wealth[-1] / wealth[0] - 1,
    'arithmetic_mean_return_per_period': sum(returns) / len(returns),
    'maximum_drawdown_loss_magnitude': loss,
}
for key, value in expected.items():
    assert Fraction(metrics[key]) == value, key
assert metrics['observation_count'] == len(returns) == 5
assert [int(row['period']) for row in observations] == list(range(1, 6))
assert metrics['maximum_drawdown_peak_period'] == peak_period == 1
assert metrics['maximum_drawdown_trough_period'] == trough_period == 2
assert max(drawdowns) == loss
assert metrics['input_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
with (ROOT / 'artifacts/wealth_path.csv').open(newline='') as f:
    submitted = list(csv.DictReader(f))
assert len(submitted) == len(wealth)
for i, row in enumerate(submitted):
    assert int(row['period']) == i
    assert Fraction(row['wealth']) == wealth[i]
    assert Fraction(row['running_peak']) == peaks[i]
    assert Fraction(row['drawdown_loss_magnitude']) == drawdowns[i]
    assert row['return'] == '' if i == 0 else Fraction(row['return']) == returns[i-1]
assert sum(returns) == Fraction('0.04')
assert (1 + returns[0]) * (1 + returns[1]) == Fraction('0.99')
constant_mean_terminal = (1 + expected['arithmetic_mean_return_per_period']) ** 5
assert constant_mean_terminal != wealth[-1]

manifest = json.loads((ROOT / 'manifest.json').read_text())
for name, digest in manifest['hashes'].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name

# Execute a copy only, so the frozen submission is never modified.
rerun = HERE / 'reproduction'
rerun.mkdir(exist_ok=True)
script = rerun / 'analyze_returns.py'
script.write_bytes((ROOT / 'artifacts/analyze_returns.py').read_bytes())
run = subprocess.run([sys.executable, str(script), str(source)],
                     capture_output=True, text=True, check=True)
(HERE / 'reproduction_stdout.txt').write_text(run.stdout, encoding='utf-8')
assert not run.stderr
for name in ['metrics.json', 'wealth_path.csv', 'report.md']:
    assert (rerun / name).read_bytes() == (ROOT / 'artifacts' / name).read_bytes(), name

result = {
    'arithmetic': 'Exact rational arithmetic using fractions.Fraction',
    'wealth_path_fractions': [str(w) for w in wealth],
    'running_peaks_fractions': [str(p) for p in peaks],
    'drawdown_loss_fractions': [str(d) for d in drawdowns],
    'metrics_fractions': {k: str(v) for k, v in expected.items()},
    'maximum_drawdown_peak_period': peak_period,
    'maximum_drawdown_trough_period': trough_period,
    'constant_mean_terminal_fraction': str(constant_mean_terminal),
    'all_submitted_numeric_values_match': True,
    'all_manifest_file_digests_match': True,
    'reproduced_artifacts_byte_identical': ['metrics.json', 'wealth_path.csv', 'report.md'],
}
(HERE / 'verification_results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
