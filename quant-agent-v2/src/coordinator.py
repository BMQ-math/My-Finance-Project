"""Workflow orchestration for role-based quantitative research."""

from __future__ import annotations

import concurrent.futures
import hashlib
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.artifacts import ArtifactStore, EvidenceRecord
from src.codex_session import CodexSession
from src.permissions import PermissionBoundary


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"configuration not found: {path}")
    with path.open("rb") as handle:
        config = tomllib.load(handle)
    workers = int(config.get("concurrency", {}).get("max_workers", 1))
    if workers < 1:
        raise ValueError("concurrency.max_workers must be at least 1")
    return config


class Coordinator:
    def __init__(self, project_root: Path, config: dict[str, Any]) -> None:
        self.project_root = project_root.resolve()
        self.config = config
        self.roles_dir = self.project_root / "roles"
        self.permissions = PermissionBoundary.from_config(self.project_root, config)
        self.sessions = CodexSession.from_config(config, workdir=self.project_root)

    def run(self, question_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
        if not question_path.is_file():
            raise FileNotFoundError(f"question not found: {question_path}")
        question = question_path.read_text(encoding="utf-8").strip()
        if not question:
            raise ValueError("question file is empty")

        run_id = self._run_id(question)
        artifacts_root = self.project_root / self.config.get("artifacts", {}).get(
            "root", ".quant/runs"
        )
        store = ArtifactStore(artifacts_root, run_id)
        workflow = self.config.get("workflow", {})
        parallel_roles = list(workflow.get("parallel_roles", ["explorer", "researcher"]))
        review_role = str(workflow.get("review_role", "critic"))
        final_role = str(workflow.get("final_role", "synthesizer"))
        roles = parallel_roles + [review_role, final_role]
        prompts = {role: self._role_prompt(role, question) for role in roles}

        branch = self.permissions.current_branch()
        for role in roles:
            self.permissions.assert_branch_allowed(role, branch)
        store.initialize(
            {
                "run_id": run_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "question_path": str(question_path),
                "branch": branch,
                "roles": roles,
                "dry_run": dry_run,
            },
            question,
        )

        if dry_run:
            for role, prompt in prompts.items():
                store.write_text(f"inputs/{role}-prompt.md", prompt)
            store.write_json("summary.json", {"status": "dry-run", "roles": roles})
            return {"run_id": run_id, "run_dir": str(store.run_dir), "status": "dry-run"}

        max_workers = int(self.config.get("concurrency", {}).get("max_workers", 1))
        findings: dict[str, str] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self._execute_role, role, prompts[role], store): role
                for role in parallel_roles
            }
            for future in concurrent.futures.as_completed(futures):
                role = futures[future]
                findings[role] = future.result()

        review_prompt = self._role_prompt(review_role, question, findings)
        findings[review_role] = self._execute_role(review_role, review_prompt, store)
        final_prompt = self._role_prompt(final_role, question, findings)
        findings[final_role] = self._execute_role(final_role, final_prompt, store)

        summary = {
            "run_id": run_id,
            "run_dir": str(store.run_dir),
            "status": "completed",
            "final_artifact": str(store.run_dir / "snapshots" / f"{final_role}.md"),
        }
        store.write_json("summary.json", summary)
        return summary

    def _execute_role(self, role: str, prompt: str, store: ArtifactStore) -> str:
        result = self.sessions.start(prompt, key=role, event_log=store.event_log(role))
        output = result.final_message.strip()
        if not output:
            raise ValueError(f"role {role!r} returned no final message")
        store.write_snapshot(role, output)
        store.append_evidence(
            EvidenceRecord(
                role=role,
                claim=f"Role output recorded for session {result.session_id or 'unknown'}",
                source=str(store.event_log(role)),
                confidence="recorded",
                observed_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        return output

    def _role_prompt(
        self, role: str, question: str, prior_findings: dict[str, str] | None = None
    ) -> str:
        role_path = self.roles_dir / f"{role}.md"
        if not role_path.is_file():
            raise FileNotFoundError(f"role prompt not found: {role_path}")
        instructions = role_path.read_text(encoding="utf-8").strip()
        parts = [instructions, "# Research question", question]
        if prior_findings:
            context = "\n\n".join(
                f"## {name}\n{text}" for name, text in sorted(prior_findings.items())
            )
            limit = int(self.config.get("budgets", {}).get("max_context_chars", 60000))
            parts.extend(["# Prior team findings", context[:limit]])
        parts.append(
            "Work only within the configured sandbox. Return the requested memo as your final message."
        )
        return "\n\n".join(parts) + "\n"

    @staticmethod
    def _run_id(question: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        digest = hashlib.sha256(question.encode("utf-8")).hexdigest()[:8]
        return f"{stamp}-{digest}"
