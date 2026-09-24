from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.artifacts import ArtifactStore, EvidenceRecord


class ArtifactStoreTests(unittest.TestCase):
    def test_writes_run_files_and_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory), "test-run")
            store.initialize({"status": "created"}, "question")
            store.write_snapshot("explorer", "answer")
            store.append_evidence(EvidenceRecord(role="explorer", claim="recorded"))

            self.assertEqual(
                (store.run_dir / "snapshots" / "explorer.md").read_text(), "answer"
            )
            self.assertTrue((store.run_dir / "evidence.jsonl").is_file())
            with self.assertRaises(ValueError):
                store.write_text("../escape.txt", "no")


if __name__ == "__main__":
    unittest.main()
