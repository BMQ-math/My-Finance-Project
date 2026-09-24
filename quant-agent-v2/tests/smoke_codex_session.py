#!/usr/bin/env python3
"""LIVE CLI demonstration, not a mock. Keeps its disposable workspace and evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.codex_session import CodexSession, SessionError

BASE_TESTS = '''import unittest
from mean import mean

class MeanTests(unittest.TestCase):
    def test_single(self):
        self.assertEqual(mean([10]), 10)

    def test_three(self):
        self.assertEqual(mean([2, 4, 6]), 4)
'''
EMPTY_TEST = '''
    def test_empty(self):
        with self.assertRaises(ValueError):
            mean([])
'''
END = '\nif __name__ == "__main__":\n    unittest.main(verbosity=2)\n'


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def run_tests(workspace, evidence, label):
    result = subprocess.run([sys.executable, '-B', 'test_mean.py'], cwd=workspace,
                            capture_output=True, text=True, timeout=30)
    (evidence / f'{label}.txt').write_text(result.stdout + result.stderr)
    return result.returncode


def verify_turn(result, workspace, evidence, label, expected):
    check((workspace / 'test_mean.py').read_bytes() == expected, 'Worker altered fixed tests')
    check(run_tests(workspace, evidence, label + '-independent') == 0,
          'Independent tests failed')
    commands = [(i, e['item']) for i, e in enumerate(result.events)
                if e.get('type') == 'item.completed'
                and e.get('item', {}).get('type') == 'command_execution']
    tests = [(i, item) for i, item in commands if 'test_mean.py' in item.get('command', '')]
    failures = [(i, item) for i, item in tests if item.get('exit_code') not in (None, 0)
                and 'FAILED' in item.get('aggregated_output', '')]
    passes = [(i, item) for i, item in tests if item.get('exit_code') == 0
              and 'OK' in item.get('aggregated_output', '')]
    check(failures and passes and failures[0][0] < passes[-1][0],
          'Missing runtime command evidence of failing then passing tests')
    edits = [i for i, e in enumerate(result.events)
             if e.get('item', {}).get('type') == 'file_change']
    check(not edits or failures[0][0] < min(edits), 'Worker edited before observing failure')
    tracked = subprocess.run(['git', 'diff', '--name-only'], cwd=workspace,
                             capture_output=True, text=True, check=True).stdout.splitlines()
    check(set(tracked) <= {'mean.py', 'test_mean.py'}, 'Unexpected tracked file change')
    extra = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'], cwd=workspace,
                           capture_output=True, text=True, check=True).stdout.splitlines()
    check(not extra, f'Unexpected new files: {extra}')
    (evidence / f'{label}-mean.py').write_bytes((workspace / 'mean.py').read_bytes())
    diff = subprocess.run(['git', 'diff', '--', 'mean.py'], cwd=workspace,
                          capture_output=True, text=True, check=True).stdout
    (evidence / f'{label}.diff').write_text(diff)
    return {'session_id': result.session_id, 'resumed_from': result.resumed_from,
            'tests_sha256': hashlib.sha256(expected).hexdigest(),
            'failure_event_index': failures[0][0], 'pass_event_index': passes[-1][0],
            'requested': result.requested_settings, 'runtime': result.runtime_settings,
            'usage': result.usage, 'elapsed_seconds': result.elapsed_seconds}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New directory for preserved evidence')
    parser.add_argument('--timeout', type=float, default=180, help='Bound per worker turn')
    args = parser.parse_args()
    evidence = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='quant-codex-smoke-'))
    if args.output:
        evidence.mkdir(parents=True, exist_ok=False)
    workspace = evidence / 'workspace'
    workspace.mkdir()
    print(f'Live evidence: {evidence}', flush=True)
    summary = {'status': 'started', 'evidence': str(evidence), 'turns': []}
    try:
        config = tomllib.loads((ROOT / 'config.toml').read_text())
        # Only the demo overrides the sandbox; model/reasoning come from existing setup.
        config['session'] = {'sandbox': 'workspace-write', 'approve_for_me': False}
        config.setdefault('budgets', {})['timeout_seconds'] = args.timeout
        session = CodexSession.from_config(config, workdir=workspace)
        (workspace / 'mean.py').write_text('def mean(values):\n    return sum(values) / (len(values) - 1)\n')
        expected = (BASE_TESTS + END).encode()
        (workspace / 'test_mean.py').write_bytes(expected)
        (evidence / 'start-tests.py').write_bytes(expected)
        subprocess.run(['git', 'init', '-q', str(workspace)], check=True)
        subprocess.run(['git', 'add', 'mean.py', 'test_mean.py'], cwd=workspace, check=True)
        subprocess.run(['git', '-c', 'user.name=Smoke Test', '-c', 'user.email=smoke@localhost',
                        '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Fixed test fixture'],
                       cwd=workspace, check=True)
        check(run_tests(workspace, evidence, 'baseline') != 0, 'Broken fixture unexpectedly passed')
        test_command = shlex.join([sys.executable, '-B', 'test_mean.py'])
        prompt = (f'Work only in this small repository. First run `{test_command}` BEFORE any editing. '
                  'Inspect the actual failing output, fix only mean.py, then run that exact command again. '
                  'Do not modify, replace, or remove test_mean.py or add other files. '
                  'Use your command execution and file editing tools. Do not delegate. '
                  'Preserve the fixed tests. Summarize the observed failure and repair.')
        (evidence / 'start-prompt.txt').write_text(prompt)
        first = session.start(prompt, key='smoke', event_log=evidence / 'start.jsonl')
        (evidence / 'session-id.txt').write_text(first.session_id + '\n')
        summary['turns'].append(verify_turn(first, workspace, evidence, 'start', expected))
        (evidence / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        expected = (BASE_TESTS + EMPTY_TEST + END).encode()
        (workspace / 'test_mean.py').write_bytes(expected)
        (evidence / 'resume-tests.py').write_bytes(expected)
        check(run_tests(workspace, evidence, 'before-resume') != 0, 'New requirement unexpectedly passed')
        prompt = (f'The driver added a fixed test: mean([]) must raise ValueError. '
                  f'First run `{test_command}` before editing and inspect its failure. '
                  'Change only mean.py to meet that requirement while preserving both existing passing tests. '
                  f'Do not alter or remove tests or add files. Rerun `{test_command}` after repair. '
                  'Use actual tools, do not delegate, and summarize results.')
        (evidence / 'resume-prompt.txt').write_text(prompt)
        # Read the persisted exact ID, and use a fresh wrapper to demonstrate durable resume.
        session = CodexSession.from_config(config, workdir=workspace)
        resumed = session.resume((evidence / 'session-id.txt').read_text().strip(), prompt,
                                 event_log=evidence / 'resume.jsonl')
        check(resumed.session_id == first.session_id, 'Resume changed the session ID')
        summary['turns'].append(verify_turn(resumed, workspace, evidence, 'resume', expected))
        summary['status'] = 'passed'
    except (SessionError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        summary.update(status='failed', error=str(exc))
        if isinstance(exc, SessionError) and exc.result:
            summary['failed_turn_result'] = exc.result.result_log
    finally:
        (evidence / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
