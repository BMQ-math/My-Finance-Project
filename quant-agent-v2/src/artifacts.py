"""Durable inputs, snapshots, event streams, and evidence records."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_.-]+")


@dataclass(frozen=True)
class EvidenceRecord:
    role: str
    claim: str
    source: str = ""
    confidence: str = "unknown"
    observed_at: str = ""


class ArtifactStore:
    def __init__(self, root: Path, run_id: str | None = None) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = self.safe_name(run_id or stamp)
        self.run_dir = root.resolve() / self.run_id
        self._lock = threading.Lock()

    @staticmethod
    def safe_name(value: str) -> str:
        result = _SAFE_NAME.sub("-", value).strip(".-")
        if not result:
            raise ValueError("artifact name must contain at least one safe character")
        return result

    def initialize(self, manifest: dict[str, Any], question: str) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=False)
        (self.run_dir / "inputs").mkdir()
        (self.run_dir / "snapshots").mkdir()
        (self.run_dir / "events").mkdir()
        self.write_json("manifest.json", manifest)
        self.write_text("inputs/question.md", question)

    def write_snapshot(self, role: str, text: str) -> Path:
        return self.write_text(f"snapshots/{self.safe_name(role)}.md", text)

    def event_log(self, role: str) -> Path:
        return self.run_dir / "events" / f"{self.safe_name(role)}.jsonl"

    def append_evidence(self, record: EvidenceRecord) -> Path:
        path = self.run_dir / "evidence.jsonl"
        line = json.dumps(asdict(record), sort_keys=True) + "\n"
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
        return path

    def write_json(self, relative_path: str, value: Any) -> Path:
        return self.write_text(relative_path, json.dumps(value, indent=2, sort_keys=True) + "\n")

    def write_text(self, relative_path: str, value: str) -> Path:
        target = self._resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=target.parent, delete=False
            ) as handle:
                handle.write(value)
                temporary = Path(handle.name)
            os.replace(temporary, target)
        return target

    def _resolve(self, relative_path: str) -> Path:
        candidate = (self.run_dir / relative_path).resolve()
        if not candidate.is_relative_to(self.run_dir.resolve()):
            raise ValueError(f"artifact path escapes run directory: {relative_path}")
        return candidate
