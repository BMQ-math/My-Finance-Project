# Step 4: one persistent Codex worker

Implemented only the CLI session wrapper and its offline/live tests. Existing role and coordinator files are outside this milestone.

## Repeat in Terminal

Requires Python 3.11+, Git, and the existing ChatGPT-authenticated `codex` CLI on PATH. No API key or new dependencies.

```sh
cd /Users/baimingqiao/Documents/ChatGPT/Trading/quant-agent-v2
python3 tests/smoke_codex_session.py --timeout 180
```

The command creates and prints a unique disposable Git workspace under the system temporary directory and **preserves** it and its evidence. Optional `--output /absolute/path/to/new-directory` stores evidence in a chosen, previously nonexistent directory. Each of the two turns has its own 180-second timeout.

The driver creates broken `mean.py` and fixed `unittest` tests, verifies baseline failure, starts one worker, independently checks its repair and test bytes, saves the runtime session UUID, adds the empty-input requirement, and resumes that exact UUID using a new wrapper instance. It verifies runtime command failure/pass evidence, unchanged test bytes, independent test success, and the resumed thread ID. Only the driver adds tests. No orchestration is invoked.

Artifacts include raw JSONL, stderr, per-turn result JSON, prompts, fixed test snapshots, independent test output, code snapshots/diffs, `session-id.txt`, and `summary.json`. `null` telemetry means unknown. Model statements in the worker's prose are not runtime metadata. Final snapshots verify test integrity; they do not claim to detect a temporary edit that a worker subsequently undoes.

## Interface

`CodexSession(workdir=..., model=..., reasoning_effort=..., sandbox="workspace-write")` exposes `start(prompt, event_log=...)`, `resume(exact_uuid, prompt, event_log=...)`, and `stop(key)`. Calls raise `SessionError` on launch, timeout, nonzero exit, incomplete/failed turn, missing ID, or resume-ID mismatch. `SessionError.result` retains partial telemetry when a process launch was attempted. Logs stream directly to exclusive files and survive failure; omitted log paths create a preserved temporary directory.

Both start and resume use actual `codex exec` with workspace-write sandboxing and command/file tools. Sandbox/model/reasoning options are passed before the `resume` subcommand. Approval is `never` for the demo: sandbox restrictions remain enforced, and unapproved operations fail. Cancellation signals only the dedicated process group created for the owned CLI. Neither `--last` nor `--ephemeral` is used.

Configuration resolution uses nonempty project model/reasoning values first, then explicit values in `$CODEX_HOME/config.toml` (default `~/.codex/config.toml`). Missing values fail rather than select a default model. Profile inheritance requires explicit values. The demo overrides only sandbox, approval behavior, and timeout; it leaves project configuration untouched.

## Validation in this Codex task

- Installed CLI: `codex-cli 0.149.1`; `codex login status`: `Logged in using ChatGPT`. Inspected both `codex exec --help` and `codex exec resume --help`.
- Requested model: `gpt-6-astra`, resolved from local CLI configuration. Requested reasoning: `high`, explicitly set in project `config.toml` (overrides the local CLI's `medium`).
- Live attempt: `.quant/step4-live/`. Baseline independently observed `ZeroDivisionError` for `[10]` and `6.0 != 4` for `[2,4,6]`.
- Child CLI exited 1 before any JSONL events: state database was read-only, followed by `failed to initialize in-process app-server client: Operation not permitted (os error 1)`. No live session ID, repair, passing worker tests, or resume was observed. Runtime model/reasoning and token usage are unknown. Authentication and security were not changed. Run the Terminal command above to complete live validation outside this host restriction.

Offline tests use synthetic events and local Python helper processes, **not live model results**:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The implementation follows the installed CLI syntax; structured events and persistent resume are also described in [official OpenAI documentation](https://learn.chatgpt.com/docs/non-interactive-mode).
