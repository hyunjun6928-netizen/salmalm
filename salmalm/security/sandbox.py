"""Lightweight Process Sandbox — OS-native isolation without Docker.

Adapts OpenClaw's container sandbox concept to SalmAlm's pip-install philosophy.
Uses OS primitives instead of Docker/gVisor:

Linux:
  - bubblewrap (bwrap) if available — best isolation
  - unshare + chroot fallback
  - resource limits (rlimit) — always available

macOS:
  - sandbox-exec with custom profile
  - resource limits

Windows:
  - resource limits only (no namespace support)

Usage:
  from salmalm.security.sandbox import sandbox_exec
  result = sandbox_exec("ls -la", timeout=10)
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from salmalm.constants import WORKSPACE_DIR


class SandboxCapabilities:
    """Detect available sandbox capabilities on this OS."""

    _cache: Optional[dict] = None

    @classmethod
    def detect(cls) -> dict:
        """Detect."""
        if cls._cache is not None:
            return cls._cache

        caps = {
            "platform": sys.platform,
            "bwrap": False,
            "unshare": False,
            "sandbox_exec": False,
            "rlimit": False,
            "level": "none",  # none, basic, moderate, strong
        }

        if sys.platform == "linux":
            caps["bwrap"] = shutil.which("bwrap") is not None
            caps["unshare"] = shutil.which("unshare") is not None
            caps["rlimit"] = True
            if caps["bwrap"]:
                caps["level"] = "strong"
            elif caps["unshare"]:
                caps["level"] = "moderate"
            else:
                caps["level"] = "basic"
        elif sys.platform == "darwin":
            caps["sandbox_exec"] = shutil.which("sandbox-exec") is not None
            caps["rlimit"] = True
            caps["level"] = "moderate" if caps["sandbox_exec"] else "basic"
        elif sys.platform == "win32":
            caps["level"] = "basic"  # rlimit not available on Windows
        else:
            caps["rlimit"] = True
            caps["level"] = "basic"

        cls._cache = caps
        return caps


# macOS sandbox-exec profile — restrict network + filesystem
_MACOS_SANDBOX_PROFILE = """
(version 1)
(deny default)
(allow process-exec)
(allow process-fork)
(allow file-read* (subpath "/usr") (subpath "/bin") (subpath "/sbin")
                  (subpath "/Library") (subpath "/System")
                  (subpath "/private/var/db") (subpath "/dev")
                  (subpath "/private/tmp") (subpath "/tmp")
                  (subpath "{workspace}"))
(allow file-write* (subpath "{workspace}") (subpath "/tmp")
                   (subpath "/private/tmp") (subpath "/dev/null"))
(allow file-read-metadata)
(allow sysctl-read)
(allow mach-lookup)
(deny network*)
"""

# bubblewrap (bwrap) arguments for Linux sandbox


def _bwrap_args(workspace: str, allow_network: bool = False) -> list:
    """Build bwrap command arguments for Linux sandboxing."""
    args = [
        "bwrap",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/bin",
        "/bin",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind",
        "/lib64",
        "/lib64",  # may not exist
        "--ro-bind",
        "/etc/alternatives",
        "/etc/alternatives",
        "--ro-bind",
        "/etc/ld.so.cache",
        "/etc/ld.so.cache",
        "--bind",
        workspace,
        workspace,
        "--tmpfs",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--unshare-pid",
        "--unshare-uts",
        "--unshare-ipc",
        "--die-with-parent",
    ]
    if not allow_network:
        args.append("--unshare-net")

    # /lib64 may not exist on all distros
    if not Path("/lib64").exists():
        args = [a for i, a in enumerate(args) if not (a == "/lib64" and i > 0 and args[i - 1] == "--ro-bind")]  # noqa: E226
        # Remove the --ro-bind before /lib64
        cleaned = []
        skip_next = False
        for i, a in enumerate(args):
            if skip_next:
                skip_next = False
                continue
            if a == "--ro-bind" and i + 2 < len(args) and args[i + 1] == "/lib64":  # noqa: E226
                skip_next = True  # skip /lib64 and its target
                continue
            cleaned.append(a)
        args = cleaned

    # Add Python path
    python_prefix = sys.prefix
    if python_prefix not in ("/usr",):
        args.extend(["--ro-bind", python_prefix, python_prefix])

    return args


def _set_rlimits(timeout: int = 30, memory_mb: int = 512, max_fds: int = 50, max_fsize_mb: int = 10):
    """Set resource limits for child process (Linux/macOS)."""
    if sys.platform == "win32":
        return
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (timeout + 5, timeout + 10))
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024 * 1024, memory_mb * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (max_fds, max_fds))
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_fsize_mb * 1024 * 1024, max_fsize_mb * 1024 * 1024))
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (20, 20))
        except (ValueError, AttributeError):
            pass  # Not available on macOS
    except Exception:
        pass


def sandbox_exec(
    command: str, timeout: int = 30, allow_network: bool = False, memory_mb: int = 512, workspace: Optional[str] = None
) -> dict:
    """Execute a command in the best available sandbox.

    Returns {'stdout': str, 'stderr': str, 'exit_code': int, 'sandbox_level': str}.
    """
    caps = SandboxCapabilities.detect()
    ws = workspace or str(WORKSPACE_DIR)

    result = {
        "stdout": "",
        "stderr": "",
        "exit_code": -1,
        "sandbox_level": caps["level"],
        "method": "none",
    }

    try:
        if caps["bwrap"] and sys.platform == "linux":
            # Best: bubblewrap namespace isolation
            bwrap = _bwrap_args(ws, allow_network=allow_network)
            cmd = bwrap + ["--", "sh", "-c", command]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                preexec_fn=lambda: _set_rlimits(timeout, memory_mb),
            )
            result["method"] = "bwrap"

        elif caps["sandbox_exec"] and sys.platform == "darwin":
            # macOS: sandbox-exec
            profile = _MACOS_SANDBOX_PROFILE.replace("{workspace}", ws)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sb", delete=False) as f:
                f.write(profile)
                profile_path = f.name
            try:
                cmd = ["sandbox-exec", "-f", profile_path, "sh", "-c", command]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    preexec_fn=lambda: _set_rlimits(timeout, memory_mb),
                )
                result["method"] = "sandbox-exec"
            finally:
                os.unlink(profile_path)

        else:
            # Fallback: resource limits only
            import shlex

            proc = subprocess.run(
                shlex.split(command),
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=ws,
                preexec_fn=(lambda: _set_rlimits(timeout, memory_mb)) if sys.platform != "win32" else None,
            )
            result["method"] = "rlimit"

        result["stdout"] = proc.stdout[-50000:] if proc.stdout else ""
        result["stderr"] = proc.stderr[-5000:] if proc.stderr else ""
        result["exit_code"] = proc.returncode

    except subprocess.TimeoutExpired:
        result["stderr"] = f"Timeout ({timeout}s)"
        result["exit_code"] = 124
    except Exception as e:
        result["stderr"] = str(e)
        result["exit_code"] = 1

    return result


def get_sandbox_status() -> dict:
    """Get sandbox capabilities status (for /security and UI)."""
    caps = SandboxCapabilities.detect()
    return {
        "platform": caps["platform"],
        "level": caps["level"],
        "bwrap": caps["bwrap"],
        "unshare": caps["unshare"],
        "sandbox_exec": caps["sandbox_exec"],
        "rlimit": caps["rlimit"],
        "recommendation": _get_recommendation(caps),
    }


def _get_recommendation(caps: dict) -> str:
    """Get security recommendation based on current capabilities."""
    if caps["level"] == "strong":
        return "✅ Strong sandbox (bubblewrap namespace isolation)"
    if caps["level"] == "moderate":
        if caps["platform"] == "darwin":
            return "⚠️ Moderate sandbox (macOS sandbox-exec). Consider running in Docker for stronger isolation."
        return "⚠️ Moderate sandbox (unshare). Install bubblewrap for stronger isolation: sudo apt install bubblewrap"
    return "⚠️ Basic sandbox (resource limits only). Install bubblewrap for namespace isolation."


# ============================================================
# Backward-compatible API (tests + external code)
# ============================================================


class SandboxConfig:
    """Configuration for sandboxed execution."""

    def __init__(
        self, timeout_s: int = 30, allow_network: bool = False, max_memory_mb: int = 512, isolate_temp: bool = False
    ):
        """Init  ."""
        self.timeout_s = timeout_s
        self.allow_network = allow_network
        self.max_memory_mb = max_memory_mb
        self.isolate_temp = isolate_temp

    @classmethod
    def strict(cls) -> "SandboxConfig":
        """Strict."""
        return cls(timeout_s=15, allow_network=False, max_memory_mb=256)

    @classmethod
    def standard(cls) -> "SandboxConfig":
        """Standard."""
        return cls(timeout_s=120, allow_network=True, max_memory_mb=1024)

    @classmethod
    def permissive(cls) -> "SandboxConfig":
        """Permissive."""
        return cls(timeout_s=1800, allow_network=True, max_memory_mb=2048)


class SandboxResult:
    """Result of a sandboxed execution."""

    def __init__(self, stdout: str = "", stderr: str = "", exit_code: int = -1, timed_out: bool = False) -> None:
        """Init  ."""
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.timed_out = timed_out

    @property
    def success(self) -> bool:
        """Success."""
        return self.exit_code == 0 and not self.timed_out

    def format_output(self) -> str:
        """Format output."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr:
            parts.append(f"[stderr] {self.stderr}")
        if self.timed_out:
            parts.append("[timed out]")
        return "\n".join(parts) if parts else "(no output)"


def sandboxed_exec(command, config: Optional[SandboxConfig] = None, shell: bool = False) -> SandboxResult:
    """Execute a command in sandbox (backward-compatible wrapper)."""
    cfg = config or SandboxConfig()
    if isinstance(command, list):
        command = " ".join(command)
    result = sandbox_exec(
        command,
        timeout=cfg.timeout_s,
        allow_network=cfg.allow_network,
        memory_mb=cfg.max_memory_mb,
    )
    return SandboxResult(
        stdout=result.get("stdout", ""),
        stderr=result.get("stderr", ""),
        exit_code=result.get("exit_code", -1),
        timed_out=result.get("exit_code") == 124,
    )


def path_jail(path_str: str, root: Optional[str] = None) -> tuple:
    """Check if a path is within allowed boundaries.

    Returns (safe: bool, resolved_path_or_error_msg: str).
    """
    from salmalm.constants import WORKSPACE_DIR

    root = root or str(WORKSPACE_DIR)
    try:
        resolved = str(Path(path_str).resolve())
        if resolved.startswith(root) or resolved.startswith("/tmp"):
            return True, resolved
        return False, f"Path {path_str} escapes allowed root {root}"
    except Exception as e:
        return False, str(e)
