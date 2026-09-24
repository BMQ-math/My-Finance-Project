from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.permissions import PermissionBoundary, RolePolicy


class PermissionBoundaryTests(unittest.TestCase):
    def test_branch_and_path_policies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            boundary = PermissionBoundary(
                root,
                {"researcher": RolePolicy(("research/*",), (Path("artifacts"),))},
            )
            boundary.assert_branch_allowed("researcher", "research/momentum")
            boundary.assert_path_allowed("researcher", root / "artifacts" / "memo.md")

            with self.assertRaises(PermissionError):
                boundary.assert_branch_allowed("researcher", "main")
            with self.assertRaises(PermissionError):
                boundary.assert_path_allowed("researcher", root / "config.toml")


if __name__ == "__main__":
    unittest.main()
