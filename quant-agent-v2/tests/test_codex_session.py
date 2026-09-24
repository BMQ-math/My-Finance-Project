"""OFFLINE tests: synthetic events and local Python subprocesses, no Codex calls."""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from src.codex_session import CodexSession, SessionError

ID = '12345678-1234-4234-9234-123456789012'
EVENTS = [
    {'type': 'thread.started', 'thread_id': ID},
    {'type': 'turn.started'},
    {'type': 'item.completed', 'item': {'type': 'command_execution', 'command': 'python test.py',
                                      'exit_code': 0, 'aggregated_output': 'OK'}},
    {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'finished'}},
    {'type': 'turn.completed', 'usage': {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 5}},
]


class CodexSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.session = CodexSession(workdir=self.root, model='explicit-test-model',
                                    reasoning_effort='high', timeout_seconds=2)
        self.log = self.root / 'events.jsonl'

    def run_synthetic(self, events=EVENTS, *, exit_code=0, resume=None):
        script = f'import sys; print({json.dumps(chr(10).join(json.dumps(e) for e in events))}); print("diagnostic", file=sys.stderr); sys.exit({exit_code})'
        with patch.object(self.session, '_command', return_value=[sys.executable, '-c', script]):
            if resume:
                return self.session.resume(resume, 'follow-up', event_log=self.log)
            return self.session.start('prompt', event_log=self.log)

    def test_success_keeps_requested_distinct_from_unknown_runtime(self):
        result = self.run_synthetic()
        self.assertEqual(result.session_id, ID)
        self.assertEqual(result.final_message, 'finished')
        self.assertEqual(result.turn_status, 'completed')
        self.assertEqual(result.runtime_settings, dict(model=None, reasoning_effort=None, sandbox=None))
        self.assertEqual(result.requested_settings['model'], 'explicit-test-model')
        self.assertEqual(result.usage['input_tokens'], 100)
        self.assertIn('diagnostic', Path(result.stderr_log).read_text())
        self.assertGreater(result.elapsed_seconds, 0)
        self.assertTrue(Path(result.result_log).exists())

    def test_runtime_metadata(self):
        events = [dict(EVENTS[0], model='reported-model', reasoning_effort='medium')] + EVENTS[1:]
        result = self.run_synthetic(events)
        self.assertEqual(result.runtime_settings['model'], 'reported-model')
        self.assertEqual(result.runtime_settings['reasoning_effort'], 'medium')

    def test_malformed_and_unknown_events_retained(self):
        events = list(CodexSession._parse_events(['', 'bad', '[]', '{"type":"future"}']))
        self.assertEqual([e['type'] for e in events], ['unparsed', 'unparsed', 'future'])

    def test_nonzero_exit_preserves_partial_logs(self):
        with self.assertRaises(SessionError) as ctx:
            self.run_synthetic(EVENTS[:3], exit_code=7)
        self.assertEqual(ctx.exception.result.returncode, 7)
        self.assertEqual(ctx.exception.result.session_id, ID)
        self.assertIsNone(ctx.exception.result.usage)
        self.assertIn('command_execution', self.log.read_text())

    def test_failed_turn_even_with_zero_exit(self):
        with self.assertRaises(SessionError) as ctx:
            self.run_synthetic(EVENTS[:1] + [{'type': 'turn.failed', 'error': {'message': 'failed'}}])
        self.assertEqual(ctx.exception.result.turn_status, 'failed')

    def test_missing_terminal_event_is_not_success(self):
        with self.assertRaises(SessionError):
            self.run_synthetic(EVENTS[:-1])

    def test_launch_failure_records_result(self):
        with patch('src.codex_session.subprocess.Popen', side_effect=FileNotFoundError('codex absent')):
            with self.assertRaises(SessionError) as ctx:
                self.session.start('prompt', event_log=self.log)
        self.assertEqual(ctx.exception.result.process_status, 'launch_failed')
        self.assertIsNone(ctx.exception.result.returncode)
        self.assertTrue(Path(ctx.exception.result.result_log).exists())

    def test_timeout_retains_partial_output_and_stops_owned_child(self):
        self.session.timeout_seconds = 0.2
        script = 'import time; print(\'{"type":"thread.started","thread_id":"' + ID + '"}\', flush=True); time.sleep(60)'
        with patch.object(self.session, '_command', return_value=[sys.executable, '-c', script]):
            with self.assertRaises(SessionError) as ctx:
                self.session.start('prompt', key='slow', event_log=self.log)
        self.assertEqual(ctx.exception.result.process_status, 'timed_out')
        self.assertEqual(ctx.exception.result.session_id, ID)
        self.assertFalse(self.session.stop('slow'))

    def test_stop_only_owned_key_and_duplicate_key_rejected(self):
        failures = []
        script = 'import time; print("ready", flush=True); time.sleep(60)'
        def run():
            try:
                self.session.start('prompt', key='active', event_log=self.log)
            except SessionError as exc:
                failures.append(exc)
        with patch.object(self.session, '_command', return_value=[sys.executable, '-c', script]):
            thread = threading.Thread(target=run)
            thread.start()
            try:
                deadline = time.monotonic() + 2
                while not self.log.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertFalse(self.session.stop('unowned'))
                with self.assertRaisesRegex(SessionError, 'already active'):
                    self.session.start('another', key='active', event_log=self.root / 'other.jsonl')
                self.assertTrue(self.session.stop('active'))
            finally:
                thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures[0].result.process_status, 'cancelled')
        self.assertFalse((self.root / 'other.jsonl').exists())

    def test_timeout_kills_descendant_that_ignores_sigterm(self):
        heartbeat = self.root / 'heartbeat'
        child = ('import signal,time; from pathlib import Path; '
                 'signal.signal(signal.SIGTERM, signal.SIG_IGN); '
                 f'p=Path({str(heartbeat)!r}); '
                 '\nwhile True:\n p.write_text(str(time.monotonic())); time.sleep(0.02)')
        parent = ('import subprocess,sys,time; '
                  f'subprocess.Popen([sys.executable,"-c",{child!r}]); '
                  'time.sleep(60)')
        self.session.timeout_seconds = 0.5
        with patch.object(self.session, '_command', return_value=[sys.executable, '-c', parent]):
            with self.assertRaises(SessionError):
                self.session.start('prompt', event_log=self.log)
        self.assertTrue(heartbeat.exists())
        last = heartbeat.read_text()
        time.sleep(0.15)
        self.assertEqual(heartbeat.read_text(), last)

    def test_resume_exact_id_and_sandbox_command(self):
        command = self.session._command(ID)
        self.assertEqual(command[command.index('resume') + 1:], ['--json', ID, '-'])
        self.assertEqual(command[command.index('--sandbox') + 1], 'workspace-write')
        self.assertNotIn('--last', command)
        self.assertNotIn('--ephemeral', command)
        result = self.run_synthetic(resume=ID)
        self.assertEqual(result.resumed_from, result.session_id)
        with self.assertRaises(ValueError):
            self.session.resume('--last', 'prompt')

    def test_resume_id_mismatch_fails(self):
        with self.assertRaisesRegex(SessionError, 'mismatch'):
            self.run_synthetic(resume='aaaaaaaa-1234-4234-9234-123456789012')

    def test_missing_explicit_configuration_blocks(self):
        with patch.dict('os.environ', {'CODEX_HOME': str(self.root)}):
            with self.assertRaisesRegex(SessionError, 'configuration missing'):
                CodexSession(workdir=self.root)

    def test_log_overwrite_refused(self):
        self.log.write_text('previous evidence')
        with self.assertRaises(FileExistsError):
            self.session.start('prompt', event_log=self.log)
        self.assertEqual(self.log.read_text(), 'previous evidence')


if __name__ == '__main__':
    unittest.main()
