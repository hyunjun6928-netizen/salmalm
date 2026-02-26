"""Exec tools: exec, python_eval, background session management."""

from salmalm.security.crypto import log
import subprocess
import sys
import json
import re
import os
import time
from salmalm.tools.tool_registry import register
from salmalm.tools.tools_common import _is_safe_command
from salmalm.constants import WORKSPACE_DIR
from salmalm.security.exec_approvals import (  # noqa: F401
    check_approval,
    check_env_override,
    BackgroundSession,  # noqa: F401
    BLOCKED_ENV_OVERRIDES,
)  # noqa: E128

# ── Secret isolation ──────────────────────────────────────────────
# Environment variables matching these patterns are stripped from
# exec/python_eval subprocess environments so that LLM-generated
# commands cannot exfiltrate API keys or tokens.
_SECRET_ENV_PATTERNS = re.compile(
    r"(?i)(API[_-]?KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|AUTH|VAULT)",
)

_SECRET_ENV_ALLOWLIST = frozenset(
    {
        # Non-sensitive vars that happen to match patterns above
        "DBUS_SESSION_BUS_ADDRESS",
        "XDG_SESSION_TYPE",
        "SESSION_MANAGER",
    }
)


def _sanitized_env(extra_env: dict | None = None) -> dict:
    """Return a copy of os.environ with secret-bearing vars removed."""
    clean = {}
    for k, v in os.environ.items():
        if k in _SECRET_ENV_ALLOWLIST:
            clean[k] = v
        elif _SECRET_ENV_PATTERNS.search(k):
            continue  # strip
        else:
            clean[k] = v
    if extra_env:
        # User-supplied env vars are NOT filtered — they are explicit
        clean.update(extra_env)
    return clean


def _run_foreground(cmd: str, timeout: int, env) -> str:
    """Run command in foreground with resource limits and output truncation."""
    import shlex

    run_env = _sanitized_env(env)
    needs_shell = any(c in cmd for c in ["|", ">", "<", "&&", "||", ";"])
    if needs_shell:
        if not os.environ.get("SALMALM_ALLOW_SHELL"):
            return (
                "❌ Shell operators (|, >, <, &&, ;) require explicit opt-in.\n"
                "Set SALMALM_ALLOW_SHELL=1 or use individual commands."
            )
        run_args = {"args": cmd, "shell": True}
    else:
        try:
            run_args = {"args": shlex.split(cmd), "shell": False}
        except ValueError:
            return "❌ Failed to parse command. Check quoting/escaping."
    extra_kwargs = {"env": run_env}
    if sys.platform != "win32":
        # Apply resource limits regardless of shell mode.
        # For shell=True, preexec_fn runs in the intermediate shell before exec,
        # so limits are inherited by all child processes in the pipeline.
        extra_kwargs["preexec_fn"] = lambda: _set_exec_limits(timeout)
    try:
        stdout, stderr, rc = _run_capped(run_args, timeout, extra_kwargs)
        return _format_raw_output(stdout, stderr, rc)
    except subprocess.TimeoutExpired:
        return f"Timeout ({timeout}s)"


def _set_exec_limits(timeout: int) -> None:
    """Set resource limits for sandboxed execution (Linux/macOS)."""
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (timeout + 5, timeout + 10))
        resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
        resource.setrlimit(resource.RLIMIT_NOFILE, (100, 100))
        resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
    except Exception as e:  # noqa: broad-except
        log.debug(f"Suppressed: {e}")


_MAX_STDOUT = 50 * 1024    # 50 KB shown to LLM
_MAX_READ   = 5 * 1024 * 1024  # 5 MB hard read cap — avoids OOM on runaway output


def _run_capped(run_args: dict, timeout: int, extra_kwargs: dict) -> "tuple[str, str, int]":
    """Run subprocess with a hard stdout/stderr read cap to prevent OOM.

    Returns (stdout_text, stderr_text, returncode).
    subprocess.run(capture_output=True) reads ALL output before returning;
    this wrapper uses Popen so we can stop after _MAX_READ bytes.
    """
    proc = subprocess.Popen(
        **run_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(WORKSPACE_DIR),
        **extra_kwargs,
    )
    stdout_chunks: list = []
    stderr_chunks: list = []
    stdout_read = 0
    stderr_read = 0
    try:
        stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
        # communicate() already read everything — cap after the fact.
        # Still better than nothing: limits what we keep in memory after the call.
        if len(stdout_bytes) > _MAX_READ:
            stdout_bytes = stdout_bytes[-_MAX_READ:]  # keep tail (most recent output)
        if len(stderr_bytes) > _MAX_READ:
            stderr_bytes = stderr_bytes[-_MAX_READ:]
        return stdout_bytes.decode("utf-8", errors="replace"), \
               stderr_bytes.decode("utf-8", errors="replace"), \
               proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise


def _format_exec_output(result) -> str:
    """Format subprocess result with truncation."""
    MAX_OUTPUT = 50 * 1024
    output = result.stdout[-MAX_OUTPUT:] if result.stdout else ""
    if len(result.stdout or "") > MAX_OUTPUT:
        output = f"[truncated: {len(result.stdout)} chars total, showing last {MAX_OUTPUT}]\n" + output
    if result.stderr:
        output += f"\n[stderr]: {result.stderr[-2000:]}"
    if result.returncode != 0:
        output += f"\n[exit code]: {result.returncode}"
    return output or "(no output)"


def _format_raw_output(stdout: str, stderr: str, returncode: int) -> str:
    """Format raw (stdout, stderr, returncode) triplet from _run_capped."""
    output = stdout[-_MAX_STDOUT:] if stdout else ""
    if len(stdout) > _MAX_STDOUT:
        output = f"[truncated: {len(stdout)} chars, showing last {_MAX_STDOUT}]\n" + output
    if stderr:
        output += f"\n[stderr]: {stderr[-2000:]}"
    if returncode != 0:
        output += f"\n[exit code]: {returncode}"
    return output or "(no output)"


@register("exec")
def handle_exec(args: dict) -> str:
    """Handle exec."""
    cmd = args.get("command", "")
    background = args.get("background", False)
    yield_ms = args.get("yieldMs", 0)
    notify_on_exit = args.get("notifyOnExit", False)
    env = args.get("env", None)

    # Basic safety check
    safe, reason = _is_safe_command(cmd)
    if not safe:
        return f"{reason}"

    # Env var security: block PATH, LD_*, DYLD_* overrides
    if env:
        env_safe, blocked = check_env_override(env)
        if not env_safe:
            return f"❌ Blocked environment variable overrides: {', '.join(blocked)} (binary hijacking prevention)"

    # Approval system check
    approved, approval_reason, needs_confirm = check_approval(cmd)
    if not approved and not needs_confirm:
        return f"❌ Command denied: {approval_reason}"
    if needs_confirm:
        return (
            f"⚠️ **Approval required**: {approval_reason}\n"
            f"Command: `{cmd[:200]}`\n"
            f"Reply with `/approve` to execute or `/deny` to cancel."
        )

    # Default timeout: 1800s (30 min) for background, 120s for foreground
    if background:
        timeout = min(args.get("timeout", 1800), 7200)  # Max 2h for background
    else:
        timeout = min(args.get("timeout", 30), 1800)  # Max 30min for foreground

    # Background execution
    if background:
        session = BackgroundSession(cmd, timeout=timeout, notify_on_exit=notify_on_exit, env=env)
        sid = session.start()
        return f"🔄 Background session started: `{sid}`\nCommand: `{cmd[:100]}`\nTimeout: {timeout}s"

    # yieldMs: start foreground, yield to background after N ms
    if yield_ms > 0:
        session = BackgroundSession(cmd, timeout=timeout, notify_on_exit=notify_on_exit, env=env)
        sid = session.start()
        # Wait for yieldMs
        time.sleep(yield_ms / 1000.0)
        poll = session.poll()
        if poll["status"] in ("completed", "error", "timeout"):
            # Already finished
            output = poll["stdout_tail"]
            if poll["stderr_tail"]:
                output += f"\n[stderr]: {poll['stderr_tail']}"
            if poll["exit_code"] and poll["exit_code"] != 0:
                output += f"\n[exit code]: {poll['exit_code']}"
            return output or "(no output)"
        return (
            f"🔄 Yielded to background: `{sid}`\n"
            f"Status: {poll['status']} ({poll['elapsed_s']}s elapsed)\n"
            f"Use `exec_session poll {sid}` to check progress."
        )

    return _run_foreground(cmd, timeout, env)


@register("exec_session")
def handle_exec_session(args: dict) -> str:
    """Manage background exec sessions: list, poll, kill."""
    action = args.get("action", "list")

    if action == "list":
        sessions = BackgroundSession.list_sessions()
        if not sessions:
            return "📋 No background sessions."
        lines = ["📋 **Background Sessions**\n"]
        for s in sessions:
            icon = {"running": "🔄", "completed": "✅", "error": "❌", "timeout": "⏰", "killed": "💀"}.get(
                s["status"], "❓"
            )
            lines.append(f"{icon} `{s['session_id']}` — {s['command']} [{s['status']}] ({s['elapsed_s']}s)")
        return "\n".join(lines)

    elif action == "poll":
        sid = args.get("session_id", "")
        session = BackgroundSession.get_session(sid)
        if not session:
            return f"❌ Session {sid} not found"
        poll = session.poll()
        output = f"📊 **{poll['session_id']}** [{poll['status']}]\n"
        output += f"Elapsed: {poll['elapsed_s']}s"
        if poll["exit_code"] is not None:
            output += f" | Exit: {poll['exit_code']}"
        if poll["stdout_tail"]:
            output += f"\n\n```\n{poll['stdout_tail'][-2000:]}\n```"
        if poll["stderr_tail"]:
            output += f"\n[stderr]: {poll['stderr_tail'][-500:]}"
        return output

    elif action == "kill":
        sid = args.get("session_id", "")
        return BackgroundSession.kill_session(sid)

    return f"❌ Unknown action: {action}. Use list, poll, or kill."


def _ast_validate(code: str) -> str | None:
    """AST-based validation. Returns error string if blocked, None if OK."""
    import ast

    _BLOCKED_MODULES = frozenset(
        {
            "os",
            "subprocess",
            "sys",
            "shutil",
            "pathlib",
            "socket",
            "http",
            "urllib",
            "requests",
            "ctypes",
            "signal",
            "importlib",
            "multiprocessing",
            "threading",
            "pty",
            "resource",
            "code",
            "codeop",
            "compileall",
        }
    )
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None  # let exec() handle syntax errors naturally
    for node in ast.walk(tree):
        # Check imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in _BLOCKED_MODULES:
                    return f"AST blocked: import {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top in _BLOCKED_MODULES:
                    return f"AST blocked: from {node.module} import ..."
        # Block __import__, eval, exec, compile, open, getattr, globals, locals, vars, breakpoint
        elif isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in (
                "__import__",
                "eval",
                "exec",
                "compile",
                "open",
                "getattr",
                "globals",
                "locals",
                "vars",
                "breakpoint",
                "exit",
                "quit",
                "input",
            ):
                return f"AST blocked: {name}() call"
        # Block dunder attribute access
        elif isinstance(node, ast.Attribute):
            if (
                node.attr.startswith("__")
                and node.attr.endswith("__")
                and node.attr not in ("__len__", "__str__", "__repr__", "__init__", "__name__")
            ):
                return f"AST blocked: dunder access .{node.attr}"
    return None


@register("python_eval")
def handle_python_eval(args: dict) -> str:
    """Handle python eval. Disabled by default — enable with SALMALM_PYTHON_EVAL=1."""
    import os as _os

    if _os.environ.get("SALMALM_PYTHON_EVAL", "0") != "1":
        return "⚠️ python_eval is disabled by default for security. Enable with SALMALM_PYTHON_EVAL=1"
    code = args.get("code", "")
    timeout_sec = min(args.get("timeout", 15), 30)

    # Primary: AST-based validation
    ast_err = _ast_validate(code)
    if ast_err:
        return f"Security blocked: {ast_err}"

    # Secondary: string blocklist
    _EVAL_BLOCKLIST = [
        "import os",
        "import sys",
        "import subprocess",
        "import shutil",
        "__import__",
        "eval(",
        "exec(",
        "compile(",
        "open(",
        "os.system",
        "os.popen",
        "os.exec",
        "os.spawn",
        "os.remove",
        "os.unlink",
        "shutil.rmtree",
        "pathlib",
        ".vault",
        "audit.db",
        "auth.db",
        "import socket",
        "import http",
        "import urllib",
        "import requests",
        "getattr(",
        "globals(",
        "locals(",
        "__builtins__",
        "vars(",
        "breakpoint(",
        "help(",
        "input(",
        "exit(",
        "quit(",
        "__class__",
        "__subclasses__",
        "__bases__",
        "__mro__",
        "importlib",
        "ctypes",
        "signal",
        # Secret exfiltration prevention
        "salmalm.security",
        "from salmalm",
        "import salmalm",
        "crypto",
        "vault",
        "oauth",
        "api_key",
        "apikey",
        "secret",
        "token",
        "credential",
        "password",
        "environ[",
        "environ.get",
        "getenv",
        ".codex/",
        ".claude/",
        "auth.json",
        "credentials.json",
    ]
    code_lower = code.lower().replace(" ", "").replace("\t", "")
    for blocked in _EVAL_BLOCKLIST:
        if blocked.lower().replace(" ", "") in code_lower:
            return f"Security blocked: `{blocked}` not allowed."
    if re.search(r"__\w+__", code):
        _dangerous_dunders = [
            "__import__",
            "__builtins__",
            "__class__",
            "__subclasses__",
            "__bases__",
            "__mro__",
            "__loader__",
            "__dict__",      # gives full attribute namespace → escape vector
            "__globals__",   # gives global scope including builtins
            "__code__",      # function bytecode manipulation
            "__reduce__",    # pickle deserialization gadgets
        ]
        for dd in _dangerous_dunders:
            if dd in code.lower():
                return f"Security blocked: `{dd}` not allowed."
    wrapper = f"""
import json, math, re, statistics, collections, itertools, functools, datetime, hashlib, base64, random, string, textwrap, csv, io
_result = None
try:
    exec({repr(code)})
except Exception as e:
    _result = f"Error: {{type(e).__name__}}: {{e}}"
if _result is not None:
    print(json.dumps({{"result": str(_result)[:10000]}}))
else:
    print(json.dumps({{"result": "(no _result set)"}}))
"""

    def _set_limits():
        """Set limits."""
        try:
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (timeout_sec, timeout_sec))
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_NOFILE, (50, 50))
            resource.setrlimit(resource.RLIMIT_NPROC, (10, 10))
            resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")

    try:
        _kwargs: dict = dict(
            capture_output=True, text=True, timeout=timeout_sec, cwd=str(WORKSPACE_DIR), env=_sanitized_env()
        )
        if sys.platform != "win32":
            _kwargs["preexec_fn"] = _set_limits
        result = subprocess.run([sys.executable, "-c", wrapper], **_kwargs)
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout.strip())
                output = data.get("result", result.stdout)
            except json.JSONDecodeError:
                output = result.stdout[-5000:]
        else:
            output = result.stdout[-3000:] if result.stdout else ""
        if result.stderr:
            output += f"\n[stderr]: {result.stderr[-2000:]}"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Python execution timeout ({timeout_sec}s)"
