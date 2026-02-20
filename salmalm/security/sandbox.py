"""SalmAlm Sandboxing — Docker container or subprocess isolation.

Provides SandboxManager that auto-detects Docker availability and falls back
to subprocess-based isolation. Pure stdlib, no external packages.

Modes:
  - docker: Full container isolation (--network none, resource limits)
  - subprocess: Best-effort isolation (temp dir, env cleanup, dangerous cmd blocking)
  - off: No sandboxing (direct execution)
  - auto: Docker if available, else subprocess
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from salmalm.security.crypto import log

# Default config path
_CONFIG_DIR = Path.home() / ".salmalm"
_CONFIG_FILE = _CONFIG_DIR / "sandbox.json"

_DEFAULT_CONFIG: Dict[str, Any] = {
    "mode": "auto",
    "docker": {
        "image": "python:3.12-slim",
        "network": "none",
        "workspaceAccess": "none",
        "timeoutSeconds": 300,
        "binds": [],
    },
    "subprocess": {
        "isolateEnv": True,
        "blockDangerousCommands": True,
    },
}

# Dangerous command patterns (subprocess mode)
_DANGEROUS_PATTERNS: List[str] = [
    r"\brm\s+(-\w*)?r\w*\s+/\s*$",  # rm -rf /
    r"\brm\s+(-\w*)?r\w*\s+/\*",    # rm -rf /*
    r"\bsudo\b",
    r"\bsu\s+-?\s*$",
    r"\bmkfs\b",
    r"\bdd\s+.*of=/dev/",
    r"\b:(){ :|:& };:",              # fork bomb
    r"\bchmod\s+(-\w+\s+)?777\s+/",
    r"\bchown\s+.*\s+/",
    r"\b>\s*/dev/sd",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\binit\s+[06]",
    r"\bhalt\b",
    r"\bpoweroff\b",
]


class SandboxResult:
    """Result from a sandboxed execution."""

    __slots__ = ("stdout", "stderr", "returncode", "timed_out", "mode")

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0,
                 timed_out: bool = False, mode: str = "off"):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.timed_out = timed_out
        self.mode = mode

    def __repr__(self) -> str:
        return (f"SandboxResult(mode={self.mode!r}, rc={self.returncode}, "
                f"timed_out={self.timed_out})")

    @property
    def output(self) -> str:
        """Combined output suitable for display."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"[stderr]: {self.stderr}")
        if self.returncode != 0:
            parts.append(f"[exit code]: {self.returncode}")
        if self.timed_out:
            parts.append("[timed out]")
        return "\n".join(parts) or "(no output)"


class SandboxManager:
    """Manages sandboxed command execution.

    Auto-detects Docker and falls back to subprocess isolation.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or self._load_config()
        self._docker_available: Optional[bool] = None
        self._mode: Optional[str] = None

    # ── Config ──────────────────────────────────────────────

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        """Load sandbox config from ~/.salmalm/sandbox.json or defaults."""
        from salmalm.config_manager import ConfigManager
        user_cfg = ConfigManager.load('sandbox')
        if not user_cfg:
            return dict(_DEFAULT_CONFIG)
        try:
            cfg = dict(_DEFAULT_CONFIG)
            for section in ("docker", "subprocess"):
                if section in user_cfg:
                    merged = dict(cfg.get(section, {}))
                    merged.update(user_cfg[section])
                    cfg[section] = merged
            if "mode" in user_cfg:
                cfg["mode"] = user_cfg["mode"]
            return cfg
        except Exception as e:
            log.warning(f"Failed to load sandbox config: {e}")
        return dict(_DEFAULT_CONFIG)

    def save_config(self) -> None:
        """Persist current config to disk."""
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w") as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    # ── Docker detection ────────────────────────────────────

    def _detect_docker(self) -> bool:
        """Check if Docker is available and functional."""
        if self._docker_available is not None:
            return self._docker_available
        try:
            # Check docker binary
            r = subprocess.run(["which", "docker"], capture_output=True, timeout=5)
            if r.returncode != 0:
                self._docker_available = False
                return False
            # Check docker daemon
            r = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
            self._docker_available = r.returncode == 0
        except Exception:
            self._docker_available = False
        return self._docker_available  # type: ignore[return-value]

    @property
    def mode(self) -> str:
        """Resolved execution mode."""
        if self._mode is not None:
            return self._mode
        configured = self._config.get("mode", "auto")
        if configured == "auto":
            self._mode = "docker" if self._detect_docker() else "subprocess"
        elif configured == "docker":
            self._mode = "docker" if self._detect_docker() else "subprocess"
        elif configured in ("subprocess", "off"):
            self._mode = configured
        else:
            self._mode = "subprocess"
        log.info(f"[SANDBOX] Mode resolved: {self._mode}")
        return self._mode

    # ── Dangerous command check ─────────────────────────────

    @staticmethod
    def is_dangerous(command: str) -> Tuple[bool, str]:
        """Check if a command matches dangerous patterns."""
        cmd = command.strip()
        for pattern in _DANGEROUS_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return True, f"Blocked dangerous pattern: {pattern}"
        return False, ""

    # ── Execution ───────────────────────────────────────────

    def run(self, command: str, timeout: Optional[int] = None,
            workspace: Optional[str] = None, env: Optional[Dict[str, str]] = None,
            sandbox: bool = True) -> SandboxResult:
        """Execute a command in the appropriate sandbox.

        Args:
            command: Shell command to run.
            timeout: Override timeout in seconds.
            workspace: Working directory (for subprocess mode).
            env: Additional environment variables.
            sandbox: If False, run without sandboxing regardless of config.
        """
        if not sandbox or self.mode == "off":
            return self._run_direct(command, timeout or 30, workspace, env)
        if self.mode == "docker":
            return self._run_docker(command, timeout, workspace, env)
        return self._run_subprocess(command, timeout, workspace, env)

    def _run_direct(self, command: str, timeout: int, workspace: Optional[str],
                    env: Optional[Dict[str, str]]) -> SandboxResult:
        """Run without sandboxing."""
        try:
            full_env = dict(os.environ)
            if env:
                full_env.update(env)
            r = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=workspace, env=full_env,
            )
            return SandboxResult(r.stdout, r.stderr, r.returncode, mode="off")
        except subprocess.TimeoutExpired:
            return SandboxResult(timed_out=True, returncode=-1, mode="off")
        except Exception as e:
            return SandboxResult(stderr=str(e), returncode=-1, mode="off")

    def _run_subprocess(self, command: str, timeout: Optional[int],
                        workspace: Optional[str],
                        env: Optional[Dict[str, str]]) -> SandboxResult:
        """Run in subprocess sandbox with isolation."""
        sp_cfg = self._config.get("subprocess", {})

        # Dangerous command check
        if sp_cfg.get("blockDangerousCommands", True):
            dangerous, reason = self.is_dangerous(command)
            if dangerous:
                return SandboxResult(stderr=reason, returncode=-1, mode="subprocess")

        effective_timeout = timeout or 30
        tmpdir = None

        try:
            # Create isolated temp directory
            tmpdir = tempfile.mkdtemp(prefix="salmalm_sandbox_")

            # Build isolated environment
            if sp_cfg.get("isolateEnv", True):
                safe_env: Dict[str, str] = {
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "HOME": tmpdir,
                    "TMPDIR": tmpdir,
                    "LANG": os.environ.get("LANG", "C.UTF-8"),
                    "TERM": "dumb",
                }
            else:
                safe_env = dict(os.environ)

            if env:
                safe_env.update(env)

            cwd = workspace or tmpdir

            r = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=effective_timeout, cwd=cwd, env=safe_env,
            )
            return SandboxResult(r.stdout, r.stderr, r.returncode, mode="subprocess")

        except subprocess.TimeoutExpired:
            return SandboxResult(timed_out=True, returncode=-1, mode="subprocess")
        except Exception as e:
            return SandboxResult(stderr=str(e), returncode=-1, mode="subprocess")
        finally:
            if tmpdir:
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass

    def _run_docker(self, command: str, timeout: Optional[int],
                    workspace: Optional[str],
                    env: Optional[Dict[str, str]]) -> SandboxResult:
        """Run in Docker container sandbox."""
        dcfg = self._config.get("docker", {})
        image = dcfg.get("image", "python:3.12-slim")
        network = dcfg.get("network", "none")
        ws_access = dcfg.get("workspaceAccess", "none")
        effective_timeout = timeout or dcfg.get("timeoutSeconds", 300)
        binds: List[str] = list(dcfg.get("binds", []))

        docker_cmd = [
            "docker", "run", "--rm",
            f"--network={network}",
            "--memory=512m",
            "--cpus=1",
            "--pids-limit=100",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=100m",
        ]

        # Workspace mount
        if workspace and ws_access in ("ro", "rw"):
            docker_cmd.extend(["-v", f"{workspace}:/workspace:{ws_access}"])
            docker_cmd.extend(["-w", "/workspace"])

        # Custom binds
        for bind in binds:
            docker_cmd.extend(["-v", bind])

        # Environment
        if env:
            for k, v in env.items():
                docker_cmd.extend(["-e", f"{k}={v}"])

        docker_cmd.extend([image, "sh", "-c", command])

        try:
            r = subprocess.run(
                docker_cmd, capture_output=True, text=True,
                timeout=effective_timeout,
            )
            return SandboxResult(r.stdout, r.stderr, r.returncode, mode="docker")
        except subprocess.TimeoutExpired:
            return SandboxResult(timed_out=True, returncode=-1, mode="docker")
        except Exception as e:
            # Docker failed, fall back to subprocess
            log.warning(f"Docker execution failed ({e}), falling back to subprocess")
            return self._run_subprocess(command, timeout, workspace, env)

    # ── Tool interface ──────────────────────────────────────

    def exec_command(self, command: str, timeout: int = 30,
                     sandbox: bool = True) -> str:
        """Execute command and return formatted output string.

        This is the main interface for the exec tool integration.
        """
        result = self.run(command, timeout=timeout, sandbox=sandbox)
        return result.output


# Module-level singleton
sandbox_manager = SandboxManager()
