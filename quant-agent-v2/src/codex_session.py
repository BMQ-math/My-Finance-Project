"""Small, standard-library adapter for persistent, tool-enabled Codex CLI turns."""
from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import tempfile
import threading
import time
import tomllib
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from src.permissions import WorkerPolicy


class SessionError(RuntimeError):
    """A failed turn; result contains any partial telemetry and log paths."""

    def __init__(self, message: str, result: SessionResult | None = None):
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class SessionResult:
    session_id: str | None
    final_message: str
    events: tuple[dict[str, Any], ...]
    returncode: int | None
    turn_status: str
    process_status: str
    requested_settings: dict[str, Any]
    runtime_settings: dict[str, Any]
    usage: dict[str, Any] | None
    elapsed_seconds: float
    event_log: str
    stderr_log: str
    result_log: str
    command: list[str]
    resumed_from: str | None
    error: str | None


class CodexSession:
    def __init__(self, *, workdir: Path, model: str = "",
                 reasoning_effort: str | None = None, sandbox: str = "workspace-write",
                 approve_for_me: bool = False, timeout_seconds: float = 900,
                 worker_policy: WorkerPolicy | None = None,
                 developer_instructions: str | None = None):
        self.workdir = workdir.resolve(strict=True)
        if not self.workdir.is_dir():
            raise SessionError(f"Not a working directory: {self.workdir}")
        if not model or not reasoning_effort:
            path = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
            try:
                config = tomllib.loads(path.read_text())
            except (OSError, ValueError) as exc:
                raise SessionError(f"Explicit model/reasoning configuration missing: {path}: {exc}") from exc
            if config.get("profile"):
                raise SessionError("Set explicit model and reasoning; automatic profile resolution is unsupported")
            model = model or config.get("model")
            reasoning_effort = reasoning_effort or config.get("model_reasoning_effort")
        if not isinstance(model, str) or not model.strip():
            raise SessionError("Missing explicit model.name or CLI model configuration")
        if not isinstance(reasoning_effort, str) or not reasoning_effort.strip():
            raise SessionError("Missing explicit model.reasoning_effort or CLI model_reasoning_effort")
        if sandbox not in {"read-only", "workspace-write"}:
            raise ValueError("Only read-only and workspace-write sandboxes are supported")
        if approve_for_me and sandbox != "workspace-write":
            raise ValueError("approve_for_me requires workspace-write")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive and finite")
        self.model, self.reasoning_effort = model, reasoning_effort
        self.sandbox, self.approve_for_me = sandbox, approve_for_me
        self.timeout_seconds = timeout_seconds
        if worker_policy and (approve_for_me or worker_policy.workspace.resolve() != self.workdir):
            raise ValueError("A worker policy requires matching cwd and approval_policy=never")
        self.worker_policy = worker_policy
        self.developer_instructions = developer_instructions
        self._processes: dict[str, subprocess.Popen] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, config: dict[str, Any], *, workdir: Path) -> CodexSession:
        return cls(workdir=workdir, model=config.get("model", {}).get("name", ""),
                   reasoning_effort=config.get("model", {}).get("reasoning_effort"),
                   sandbox=config.get("session", {}).get("sandbox", "workspace-write"),
                   approve_for_me=config.get("session", {}).get("approve_for_me", False),
                   timeout_seconds=config.get("budgets", {}).get("timeout_seconds", 900))

    def start(self, prompt: str, *, key: str | None = None,
              event_log: Path | None = None) -> SessionResult:
        return self._run(prompt, key=key or str(uuid.uuid4()), event_log=event_log)

    def resume(self, session_id: str, prompt: str, *, key: str | None = None,
               event_log: Path | None = None) -> SessionResult:
        # Accept exact runtime UUIDs only, never names or implicit --last selection.
        try:
            uuid.UUID(session_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("resume requires an exact session UUID") from exc
        return self._run(prompt, key=key or session_id, event_log=event_log,
                         session_id=session_id)

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        # start_new_session creates an isolated group, never target the parent group.
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                # Kill remaining descendants even if the leader exits on SIGTERM.
                # Do not reap the leader during this short grace period.
                time.sleep(0.2)
            except ProcessLookupError:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                # macOS can deny signaling a group whose last member has exited.
                if process.poll() is None:
                    raise
            process.wait(timeout=2)

    def stop(self, key: str) -> bool:
        with self._lock:
            process = self._processes.get(key)
            if process is None or process.poll() is not None:
                return False
            self._cancelled.add(key)
            self._terminate(process)
            return True

    def _command(self, session_id: str | None) -> list[str]:
        args = ["codex", "exec"]
        if self.worker_policy:
            args.extend(self.worker_policy.cli_args())
        else:
            args.extend(["--sandbox", self.sandbox])
        args += ["-c", 'approval_policy="never"', "--model", self.model,
                "-c", "model_reasoning_effort=" + json.dumps(self.reasoning_effort)]
        if self.developer_instructions is not None:
            args += ["-c", "developer_instructions=" + json.dumps(self.developer_instructions)]
        if self.approve_for_me:
            args.append("--approve-for-me")
        if session_id:
            args += ["resume", "--json", session_id, "-"]
        else:
            args += ["--json", "--color", "never", "-"]
        return args

    def _run(self, prompt: str, *, key: str, event_log: Path | None,
             session_id: str | None = None) -> SessionResult:
        if event_log is None:
            event_log = Path(tempfile.mkdtemp(prefix="codex-turn-")) / "events.jsonl"
        event_log = event_log.resolve()
        event_log.parent.mkdir(parents=True, exist_ok=True)
        stderr_log = event_log.with_suffix(".stderr.log")
        result_log = event_log.with_suffix(".result.json")
        command = self._command(session_id)
        started = time.monotonic()
        process = None
        error = None
        status = "exited"
        interrupted = False
        with self._lock:
            if key in self._processes:
                raise SessionError(f"session key is already active: {key}")
            # Exclusive files prevent accidentally overwriting evidence from an earlier turn.
            out = event_log.open("xb")
            try:
                err = stderr_log.open("xb")
            except BaseException:
                out.close()
                raise
            try:
                process = subprocess.Popen(command, cwd=self.workdir, stdin=subprocess.PIPE,
                                           stdout=out, stderr=err, start_new_session=True)
                self._processes[key] = process
            except OSError as exc:
                error, status = str(exc), "launch_failed"
        try:
            if process is not None:
                try:
                    process.communicate(prompt.encode(), timeout=self.timeout_seconds)
                    if self.worker_policy:
                        # A completed pair turn must not leave writers in its owned
                        # process group. Do not promote artifacts if cleanup is needed.
                        try:
                            os.killpg(process.pid, 0)
                        except ProcessLookupError:
                            pass
                        else:
                            os.killpg(process.pid, signal.SIGTERM)
                            time.sleep(0.2)
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            status, error = "unfinished_processes", "Turn left child processes running; artifacts were not accepted"
                except subprocess.TimeoutExpired:
                    status, error = "timed_out", f"Timeout after {self.timeout_seconds}s"
                    self._terminate(process)
                except KeyboardInterrupt:
                    interrupted = True
                    status, error = "cancelled", "Interrupted by caller"
                    self._terminate(process)
                except OSError as exc:
                    status, error = "io_failed", str(exc)
                    self._terminate(process)
        finally:
            if process and process.stdin:
                process.stdin.close()
            out.close()
            err.close()
            with self._lock:
                self._processes.pop(key, None)
                if key in self._cancelled:
                    status, error = "cancelled", "Cancelled by stop()"
                    self._cancelled.remove(key)
        events = tuple(self._parse_events(event_log.read_text(errors="replace").splitlines()))
        turn_status = "unknown"
        runtime = {"model": None, "reasoning_effort": None, "sandbox": None}
        usage = None
        for event in events:
            kind = event.get("type")
            if kind in {"turn.completed", "turn.failed"}:
                turn_status = kind.split(".")[1]
                usage = event.get("usage", usage)
            # Only structured runtime metadata, never agent prose or requested flags.
            if kind in {"thread.started", "session.started", "turn.started", "turn_context"}:
                data = event.get("payload", event)
                if not isinstance(data, dict):
                    continue
                for target, names in {"model": ("model",),
                                      "reasoning_effort": ("reasoning_effort", "model_reasoning_effort"),
                                      "sandbox": ("sandbox", "sandbox_mode")}.items():
                    for name in names:
                        if name in data:
                            runtime[target] = data[name]
        actual_id = self._session_id(events)
        code = process.returncode if process else None
        if not error and (code != 0 or turn_status != "completed" or not actual_id):
            error = f"Codex exit={code}, turn={turn_status}, session={actual_id}; see logs"
        if session_id and actual_id != session_id:
            error = error or f"Resume session mismatch: requested {session_id}, reported {actual_id}"
        tool_error = self._tool_initialization_error(events)
        if tool_error:
            # The CLI can finish a turn despite unavailable tools. Report the cause
            # before the pair controller tries to collect a nonexistent submission.
            error = f"Codex tool initialization failed: {tool_error}" + (f"; {error}" if error else "")
        requested = {"model": self.model, "reasoning_effort": self.reasoning_effort,
                     "sandbox": self.sandbox,
                     "approval_policy": "auto-review" if self.approve_for_me else "never"}
        if self.worker_policy:
            requested["sandbox"] = None
            requested["permission_profile"] = "quant_pair"
            requested["tool_policy"] = self.worker_policy.overrides()
        result = SessionResult(actual_id, self._final_message(events), events, code,
                               turn_status, status, requested,
                               runtime, usage, time.monotonic() - started, str(event_log),
                               str(stderr_log), str(result_log), command, session_id, error)
        result_log.write_text(json.dumps(asdict(result), indent=2) + "\n")
        if interrupted:
            raise KeyboardInterrupt
        if error:
            raise SessionError(error, result)
        return result

    @staticmethod
    def _tool_initialization_error(events: Iterable[dict[str, Any]]) -> str | None:
        """Recognize this execution-blocking diagnostic, not arbitrary warnings/prose."""
        diagnostic = "code mode is unavailable because code-mode host is disabled"
        for event in events:
            candidates = []
            if event.get("type") in {"error", "warning"}:
                candidates.append(event)
            if event.get("type") == "turn.failed":
                candidates.append(event.get("error"))
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") in {"error", "warning"}:
                candidates.append(item)
            for candidate in candidates:
                if isinstance(candidate, dict):
                    message = candidate.get("message") or candidate.get("text")
                    if isinstance(message, str) and diagnostic in message.casefold():
                        return message
        return None

    @staticmethod
    def _parse_events(lines: Iterable[str]) -> Iterable[dict[str, Any]]:
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = None
            yield event if isinstance(event, dict) else {"type": "unparsed", "text": line}

    @staticmethod
    def _session_id(events: Iterable[dict[str, Any]]) -> str | None:
        for event in events:
            if event.get("type") == "thread.started":
                return event.get("thread_id") or event.get("session_id")
        return None

    @staticmethod
    def _final_message(events: tuple[dict[str, Any], ...]) -> str:
        for event in reversed(events):
            item = event.get("item", {})
            if event.get("type") == "item.completed" and isinstance(item, dict):
                if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                    return item["text"]
        return ""
