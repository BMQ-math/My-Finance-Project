"""Role-level branch and workspace write boundaries."""

from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RolePolicy:
    branches: tuple[str, ...]
    writable_paths: tuple[Path, ...]


class PermissionBoundary:
    def __init__(self, repo_root: Path, policies: dict[str, RolePolicy]) -> None:
        self.repo_root = repo_root.resolve()
        self.policies = policies

    @classmethod
    def from_config(cls, repo_root: Path, config: dict[str, Any]) -> "PermissionBoundary":
        raw = config.get("permissions", {})
        policies = {
            role: RolePolicy(
                branches=tuple(values.get("branches", [])),
                writable_paths=tuple(Path(path) for path in values.get("writable_paths", [])),
            )
            for role, values in raw.items()
        }
        return cls(repo_root, policies)

    def current_branch(self) -> str:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise PermissionError(result.stderr.strip() or "unable to determine the Git branch")
        return result.stdout.strip() or "DETACHED_HEAD"

    def assert_branch_allowed(self, role: str, branch: str | None = None) -> None:
        policy = self._policy(role)
        candidate = branch or self.current_branch()
        if not any(fnmatch.fnmatchcase(candidate, pattern) for pattern in policy.branches):
            raise PermissionError(f"role {role!r} is not allowed on branch {candidate!r}")

    def assert_path_allowed(self, role: str, path: Path) -> None:
        policy = self._policy(role)
        candidate = path.resolve()
        allowed_roots = [(self.repo_root / item).resolve() for item in policy.writable_paths]
        if not any(candidate == root or candidate.is_relative_to(root) for root in allowed_roots):
            raise PermissionError(f"role {role!r} cannot write {candidate}")

    def _policy(self, role: str) -> RolePolicy:
        try:
            return self.policies[role]
        except KeyError as exc:
            raise PermissionError(f"no permission policy configured for role {role!r}") from exc


def _toml_value(value: Any) -> str:
    """Encode the small subset used by CLI -c overrides, without shell quoting."""
    if isinstance(value, dict):
        return "{" + ", ".join(f"{json.dumps(k)} = {_toml_value(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return json.dumps(value)


@dataclass(frozen=True)
class WorkerPolicy:
    """Native tool sandbox policy; the host CLI keeps its normal auth/state access.

    This is separate from PermissionBoundary's coordinator-side path checks.
    It deliberately does not extend :workspace (which grants shared temp writes).
    """

    workspace: Path
    readable: tuple[Path, ...]
    private_roots: tuple[Path, ...]
    protected: tuple[Path, ...] = ()

    def overrides(self) -> dict[str, Any]:
        workspace = self.workspace.resolve()
        filesystem = {":minimal": "read", str(Path(sys.base_prefix).resolve()): "read"}
        for path in self.private_roots:
            filesystem[str(path.resolve())] = "deny"
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
        filesystem[str(codex_home)] = "deny"
        filesystem[str(Path.home() / ".codex")] = "deny"
        filesystem[str(workspace)] = "write"
        for path in self.readable + self.protected:
            filesystem[str(path.resolve())] = "read"
        for name in (".git", ".codex", ".agents"):
            filesystem[str(workspace / name)] = "deny"
        filesystem[str(workspace / ".pair-workspace")] = "read"
        values = {
            "default_permissions": "quant_pair",
            "permissions.quant_pair": {"filesystem": filesystem, "network": {"enabled": False}},
            "approval_policy": "never",
            "forced_login_method": "chatgpt",
            "project_doc_max_bytes": 0,
            "project_doc_fallback_filenames": [],
            "project_root_markers": [".pair-workspace"],
            f"projects.{json.dumps(str(workspace))}.trust_level": "untrusted",
            "memories.use_memories": False,
            "memories.generate_memories": False,
            "mcp_servers": {},
            "web_search": "disabled",
            "shell_environment_policy.inherit": "none",
            "shell_environment_policy.experimental_use_profile": False,
            "shell_environment_policy.set": {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:" + str(Path(sys.executable).resolve().parent),
                "TMPDIR": str(workspace / ".tmp"),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        }
        for feature in ("apps", "plugins", "remote_plugin", "memories", "multi_agent", "multi_agent_v2",
                        "hooks", "shell_snapshot", "browser_use", "browser_use_external",
                        "computer_use", "image_generation", "workspace_dependencies"):
            values[f"features.{feature}"] = False
        # Local tool execution needs this host; it does not grant broader tool permissions.
        values["features.code_mode_host"] = True
        values["features.skip_host_skill_discovery"] = True
        return values

    def cli_args(self) -> list[str]:
        # Resolve model/reasoning before ignoring user tool configuration. Auth is unaffected.
        args = ["--ignore-user-config", "--strict-config", "--skip-git-repo-check"]
        for key, value in self.overrides().items():
            args += ["-c", f"{key}={_toml_value(value)}"]
        return args

    @staticmethod
    def require_support() -> None:
        """Launch-time compatibility checks, with no model call or security fallback."""
        import re

        if sys.platform not in {"darwin", "linux"}:
            raise PermissionError("The pair supports native permission profiles on macOS/Linux only")
        version = subprocess.run(["codex", "--version"], capture_output=True, text=True,
                                 check=True, timeout=10).stdout
        match = re.search(r"codex-cli (\d+)\.(\d+)\.(\d+)", version)
        if not match or tuple(map(int, match.groups())) < (0, 156, 1):
            raise PermissionError("The pair requires Codex CLI 0.156.1+ permission-profile support")
        # --ignore-user-config excludes user legacy sandbox settings. Refuse system
        # layers that could override profiles or inject external tools/instructions.
        for path in (Path("/etc/codex/config.toml"),
                     Path("/Library/Application Support/Codex/config.toml")):
            if path.exists() and tomllib.loads(path.read_text()):
                raise PermissionError(f"System configuration needs an isolation audit before pair use: {path}")
        login = subprocess.run(["codex", "login", "status"], capture_output=True, text=True,
                               timeout=10)
        if login.returncode or "Logged in using ChatGPT" not in login.stdout + login.stderr:
            raise PermissionError("Existing ChatGPT CLI login required; authentication was not changed")
