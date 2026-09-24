# Step 5 — General-purpose Researcher–Critic pair

Implementation only. **This implementation has not been tested or live-validated in this task.** No tests, worker sessions, demonstrations, datasets, or research runs were created or executed. Existing tests and historical evidence were left intact. Permission enforcement and CLI integration require separately authorized validation before relying on isolation.

## Entry point

From the project root, the existing `quant` launcher now dispatches only the single pair. Supply your own question and inputs. Placeholders below describe syntax; they are not an example research task.

```sh
./quant run QUESTION_FILE --run-dir NEW_RUN_DIRECTORY
./quant run QUESTION_FILE --input AUTHORIZED_FILE --input ANOTHER_AUTHORIZED_FILE --run-dir NEW_RUN_DIRECTORY --timeout SECONDS --max-reviews COUNT
./quant status RUN_DIRECTORY
./quant resume RUN_DIRECTORY
./quant stop RUN_DIRECTORY
./quant runs
```

Alternatively use `.venv/bin/python run.py` in place of `./quant`. Use `./quant --config CONFIG_TOML run ...` for a different project configuration. `--config` comes before the subcommand. Status, resume, and stop use the saved run record, not current configuration or edited role files.

`QUESTION_FILE` is UTF-8. `--input` authorizes one local regular file and is repeatable. The coordinator copies those files; original locations are recorded privately. Directories, symlinks, hard links, and credential-like reserved filenames are rejected. Explicitly enumerate required input files. `NEW_RUN_DIRECTORY` must not exist; its final component must use letters, digits, dots, underscores, or hyphens. `runs` lists directories under configured `artifacts.root`; an explicitly placed run elsewhere is accessed by its path.

The old launcher's default momentum question, all-role `run`, and arbitrary `resume SESSION_ID PROMPT` dispatch are no longer exposed. Existing coordinator/role scaffolding and Step 4 scripts remain on disk; the pair entry point does not invoke that orchestration. The default CodexSession command behavior used by Step 4 remains available when no worker policy is supplied.

## Workflow and interfaces

The coordinator freezes the original question, authorized input copies, resolved settings, editable role texts, and full developer-instruction text in a new run. Role files are explicitly loaded and passed using Codex `developer_instructions`; a Markdown filename alone has no prompt priority. Task text remains a separate user prompt. The provider's system instructions are not replaced.

The Researcher starts a fresh tool-enabled Codex session in `workers/researcher/`. The coordinator never executes a program returned in a model message. The Researcher chooses its methods, artifacts, report filename, and investigations according to the actual question.

At submission the Researcher writes **`submission.json`**, a general interchange inventory with exactly these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `report` | string | Relative path to a nonempty UTF-8 research report |
| `artifacts` | array of objects | Each object has `path` and a nonempty `description`; include the report |

Artifact paths identify individual files within the Researcher's workspace. They must be unique, relative POSIX paths without `.`/`..` traversal, symlinks, hard links, or reserved credential/configuration paths. The inventory itself is collected separately. No script, table, numeric schema, or calculation is required by the controller.

After the CLI reports turn completion, the wrapper checks for remaining processes in its owned process group, and the controller refuses outstanding command events. Files are checked for changes during collection. The coordinator copies only inventory-listed artifacts and authorized input copies into a new snapshot, creates its own manifest and SHA-256 hashes, and marks the files read-only. Tool permissions, rather than file modes alone, restrict access. The controller checks recorded snapshot hashes and file sets before and after subsequent worker turns.

A fresh Critic session receives the original question and complete frozen evidence files. Its only writable directory is its own `workers/critic-NNN/` verification workspace. It receives no Researcher transcript or working records. Independent checking is a role responsibility: the coordinator records checks and command events but does not decide whether a domain calculation is correct.

The Critic writes a separate readable UTF-8 review and **`review.json`** with exactly these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `verdict` | string | `pass`, `revise`, or `reject` |
| `report` | string | Relative path to the readable review, separate from `review.json` |
| `findings` | array of strings | Specific findings; required for revise/reject |
| `required_repairs` | array of strings | Actionable repairs; required for revise, empty for pass |
| `checks` | nonempty array of strings | What the Critic actually checked |
| `unchecked` | array of strings | Material items it did not check |
| `verification_artifacts` | array of strings | Relative paths to any verification evidence it produced; may be empty |

Missing, malformed, incomplete, oversized, or unsafe output is an operational failure, never an invented scientific rejection. The coordinator archives readable/raw reviews and verification artifacts, attaches actual command events, and binds the review to the snapshot ID and manifest hash mechanically. Models do not transcribe identifiers or hashes.

A `revise` routes the exact reviewed snapshot and actual Critic feedback to the original Researcher using its stored UUID. The next submission has a separate snapshot; the next Critic starts another fresh session. Only earlier findings are given as a checklist to the next Critic. A first-review pass ends the run immediately. Pass concerns supported scope, not a positive effect or profitable strategy.

## Configuration

Existing `[model]` resolution is reused: nonempty project values take precedence, otherwise CodexSession requires explicit local CLI configuration. The established request is `gpt-6-astra` with project `high` reasoning. The implementation does not guess a model or substitute one. Settings are resolved and saved when the run is created; later resumes use that saved configuration.

| `[pair]` option | Default | Meaning |
| --- | --- | --- |
| `timeout_seconds` | 900 | Wall time bound per worker turn |
| `max_reviews` | 2 | Total Critic reviews, hence at most one revision by default |
| `max_artifacts` | 256 | Maximum submitted artifact or authorized input count |
| `max_artifact_bytes` | 67108864 | Maximum individual file size |
| `max_submission_bytes` | 268435456 | Maximum total submission, verification, or authorized input payload |

`--timeout` and `--max-reviews` override those options for a new run. The pair runs one turn at a time. It ignores the legacy multi-role workflow, concurrency, and sandbox sections. Review and artifact limits must be positive integers; the timeout must be positive and finite. Large inventories are not truncated; limits cause explicit failure.

Each raw turn result retains requested settings separately from runtime metadata, plus elapsed time, usage fields, status, and event/stderr paths. Unknown runtime fields remain `null`. Resumed-session usage counters are not summed or assumed incremental. The current wrapper does not collect RAM or CPU measurements.

## Access policy

The pair adds `WorkerPolicy` to the existing permissions module and retains `PermissionBoundary` for coordinator-side path validation. The wrapper's optional `worker_policy` selects native Codex permission profiles **without** legacy `--sandbox` or approval-bypass flags. Default Step 4 wrapper calls still use their original sandbox arguments.

A pair profile grants minimal OS/interpreter reads, reads of the exact authorized evidence, and writes only under the current worker workspace. The run record, project implementation, other workers, events/prompts, and Codex credential/session directories are denied to worker tools. The CLI process itself keeps its existing ChatGPT authentication and session storage; `CODEX_HOME` and credentials are not copied or relocated. There is no API-key backend or authentication setup.

User tool configuration is excluded with `--ignore-user-config` after model/reasoning resolution. The role-specific invocation explicitly disables inherited apps/plugins/MCP configuration, browser/computer tools, memory injection/generation, host skill discovery, hooks, shell snapshots, and delegation. Project instructions are disabled; coordinator-owned workspace markers stop ancestor discovery. Workers are marked untrusted so project configuration cannot replace the intended policy. Shell commands receive a minimal environment and a workspace-local temporary directory. Tool network access and web search are disabled. Consequently this milestone supports local authorized evidence; it is not an online browsing agent or a package-installation workflow.

Launch checks require macOS/Linux, Codex CLI 0.156.1 or newer, and existing ChatGPT login. Nonempty known system configuration layers are refused pending an isolation audit. Strict CLI configuration and native sandbox failures stop execution; there is no fallback to weaker sandboxing. Managed configurations may also reject these settings. These compatibility checks are not proof that the effective boundary is correct: the saved `isolation.validated` remains `null`. No permission-denial test has been run in this build-only task.

This relies on the installed CLI's native tool restrictions, not a separate container or OS user. Host-owner edits are outside that boundary. Background or detached jobs are prohibited in the worker protocol; owned process-group cleanup does not constitute a general supervisor for a process that deliberately detaches. Broader runtimes or dependencies may need explicitly designed read grants and later validation.

Permission-profile configuration is based on [official OpenAI documentation](https://learn.chatgpt.com/docs/permissions); the role mechanism uses [additional developer instructions](https://learn.chatgpt.com/docs/config-file/config-reference).

## Records and recovery

Each run retains:

- `state.json` and `summary.json`, with latest attempt, last completed/reviewed/passing submission, unresolved findings, session identities, and failures tracked separately;
- `FINAL_REPORT.md`, generated deterministically from state, with submission and review links;
- frozen question/inputs, private source references, loaded roles, full developer instructions, resolved settings, task prompts, and requested tool policies;
- raw per-turn JSONL, stderr, and result metadata;
- each whitelisted submission snapshot, hash manifest, review, and verification output;
- private worker workspaces, including partial outputs when a turn fails.

A run holds an exclusive coordinator lock. It writes an in-flight marker **before** launching each worker. Safe resume continues only a persisted, known checkpoint with no uncertain worker; it never uses `--last`, re-resolves a session by name, or silently retries a failed review. Changing code/configuration is not a repair for an uncertain run record.

`stop` writes a cooperative cancellation request. The active coordinator polls it and calls `CodexSession.stop` only for its own current process key. It never kills arbitrary PIDs from a saved file. A stop between phases preserves a resumable checkpoint. A stop during a turn, timeout, launch failure, malformed submission/review, or abrupt loss with an in-flight marker blocks automatic resume; inspect evidence before explicitly creating a new run. Orphaned processes from a killed coordinator are not signaled by `stop` from another process.

`resume` clears a prior stop request only after confirming a safe checkpoint. Terminal states (`passed`, `rejected`, `review_limit`) are returned without launching anything. Later failures preserve earlier submissions/reviews and never promote an unreviewed submission. Uncertain artifacts remain available for inspection.

The run/ resume exit code is 0 for a passing review, 1 for recorded nonpass/failure/stopped outcomes, and 2 for launcher/configuration errors. Status and stop return 0 when their request succeeds. A scientific pass and successful isolation validation are separate concepts; this build has no test or live-validation claim.

## Files changed

- `src/research_pair.py`: inventory/snapshot/review controller and durable checkpoints.
- `src/permissions.py`: worker permission-profile construction and launch compatibility checks, alongside existing path utilities.
- `src/codex_session.py`: optional worker policies, explicit developer instructions, and pair-only process-group completion checks.
- `roles/researcher.md`, `roles/critic.md`: simple editable role text from the replacement specification.
- `run.py`, `config.toml`: pair entry point and bounded settings.
- `STEP5.md`: this documentation.

Testing and live validation are deferred to a separate instruction.
