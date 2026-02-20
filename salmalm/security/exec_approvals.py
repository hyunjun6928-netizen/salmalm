"""Exec approval system — allowlist/denylist + dangerous command detection."""
import re
import threading
import time
import os
from pathlib import Path
from salmalm.crypto import log

_APPROVALS_FILE = Path.home() / '.salmalm' / 'exec_approvals.json'
_lock = threading.Lock()

# Dangerous command patterns that require user approval
DANGEROUS_PATTERNS = [
    r'\brm\s+(-[a-zA-Z]*[rR][a-zA-Z]*\s+|.*--recursive)',  # rm -r, rm -rf
    r'\brm\s+-[a-zA-Z]*f',  # rm -f
    r'\bsudo\b',
    r'\bchmod\s+777\b',
    r'\bchown\b',
    r'\bmkfs\b',
    r'\bdd\s+',
    r'\b:(){ :|:& };:',  # fork bomb
    r'\bshutdown\b',
    r'\breboot\b',
    r'\bsystemctl\s+(stop|disable|mask)',
    r'\bkill\s+-9\s',
    r'\bpkill\b',
    r'\bkillall\b',
    r'\bnc\s.*-[lL]',  # netcat listen
    r'\bcurl\s.*\|\s*(ba)?sh',  # curl | sh
    r'\bwget\s.*\|\s*(ba)?sh',
]

# Env vars that cannot be overridden (binary hijacking prevention)
BLOCKED_ENV_OVERRIDES = {
    'PATH', 'LD_PRELOAD', 'LD_LIBRARY_PATH', 'LD_AUDIT',
    'DYLD_INSERT_LIBRARIES', 'DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH',
}


from salmalm.config_manager import ConfigManager

_EXEC_APPROVALS_DEFAULTS = {'allowlist': [], 'denylist': [], 'auto_approve': False}


def _load_config() -> dict:
    """Load exec approval config."""
    return ConfigManager.load('exec_approvals', defaults=_EXEC_APPROVALS_DEFAULTS)


def _save_config(config: dict):
    """Save exec approval config."""
    try:
        ConfigManager.save('exec_approvals', config)
    except Exception as e:
        log.error(f"Failed to save exec approvals: {e}")


def check_approval(command: str) -> tuple:
    """Check if a command needs approval.

    Returns (approved: bool, reason: str, needs_user_confirm: bool).
    """
    config = _load_config()
    cmd_stripped = command.strip()

    # Denylist check (exact or pattern match)
    for pattern in config.get('denylist', []):
        if re.search(pattern, cmd_stripped):
            return False, f'Denied by denylist pattern: {pattern}', False

    # Allowlist check (exact prefix match)
    for allowed in config.get('allowlist', []):
        if cmd_stripped.startswith(allowed):
            return True, 'Allowed by allowlist', False

    # Dangerous pattern detection
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_stripped, re.IGNORECASE):
            if config.get('auto_approve'):
                return True, f'Auto-approved (dangerous: {pattern})', False
            return False, f'Dangerous command detected: {pattern}', True

    return True, 'OK', False


def check_env_override(env: dict) -> tuple:
    """Check if env dict tries to override blocked variables.

    Returns (safe: bool, blocked_vars: list).
    """
    if not env:
        return True, []
    blocked = []
    for key in env:
        if key in BLOCKED_ENV_OVERRIDES:
            blocked.append(key)
        # Also catch LD_* and DYLD_* patterns
        if key.startswith('LD_') or key.startswith('DYLD_'):
            if key not in BLOCKED_ENV_OVERRIDES:
                blocked.append(key)
    return len(blocked) == 0, blocked


# ============================================================
# Background session management
# ============================================================

class BackgroundSession:
    """Manages a background exec process."""

    _sessions: dict = {}  # session_id -> BackgroundSession
    _counter = 0
    _lock = threading.Lock()

    def __init__(self, command: str, timeout: int = 1800, notify_on_exit: bool = False,
                 env: dict = None):
        with BackgroundSession._lock:
            BackgroundSession._counter += 1
            self.session_id = f'bg-{BackgroundSession._counter}'

        self.command = command
        self.timeout = timeout
        self.notify_on_exit = notify_on_exit
        self.started = time.time()
        self.process = None
        self.stdout_data = ''
        self.stderr_data = ''
        self.exit_code = None
        self.status = 'starting'  # starting, running, completed, timeout, error
        self._thread = None
        self._env = env

    def start(self):
        """Start the background process."""
        import subprocess
        import shlex

        # Env var security check
        if self._env:
            safe, blocked = check_env_override(self._env)
            if not safe:
                self.status = 'error'
                self.stderr_data = f'Blocked env overrides: {", ".join(blocked)}'
                return self.session_id

        needs_shell = any(c in self.command for c in ['|', '>', '<', '&&', '||', ';'])
        if needs_shell and not os.environ.get('SALMALM_ALLOW_SHELL'):
            self.status = 'error'
            self.stderr_data = 'Shell operators require SALMALM_ALLOW_SHELL=1'
            return self.session_id
        run_env = dict(os.environ)
        if self._env:
            run_env.update(self._env)

        from salmalm.constants import WORKSPACE_DIR as _ws

        def _run():
            try:
                if needs_shell:
                    run_args = {'args': self.command, 'shell': True}
                else:
                    try:
                        run_args = {'args': shlex.split(self.command), 'shell': False}
                    except ValueError:
                        self.status = 'error'
                        self.stderr_data = 'Failed to parse command'
                        return

                self.status = 'running'
                result = subprocess.run(
                    **run_args, capture_output=True, text=True,
                    timeout=self.timeout, env=run_env,
                    cwd=str(_ws)
                )
                self.stdout_data = result.stdout[-100_000:]  # Keep last 100KB
                self.stderr_data = result.stderr[-10_000:]
                self.exit_code = result.returncode
                self.status = 'completed'
            except subprocess.TimeoutExpired:
                self.status = 'timeout'
                self.stderr_data = f'Process timed out after {self.timeout}s'
            except Exception as e:
                self.status = 'error'
                self.stderr_data = str(e)[:1000]

            # Notify on exit if requested
            if self.notify_on_exit:
                try:
                    from salmalm import core as _c
                    if _c._tg_bot and _c._tg_bot.token:
                        msg = (f'🖥 Background session `{self.session_id}` finished\n'
                               f'Command: `{self.command[:80]}`\n'
                               f'Status: {self.status} (exit: {self.exit_code})')
                        _c._tg_bot._api('sendMessage', {
                            'chat_id': _c._tg_bot.owner_id,
                            'text': msg, 'parse_mode': 'Markdown'
                        })
                except Exception:
                    pass

        self._thread = threading.Thread(target=_run, daemon=True,
                                        name=f'bg-exec-{self.session_id}')
        self._thread.start()
        BackgroundSession._sessions[self.session_id] = self
        return self.session_id

    def poll(self) -> dict:
        """Poll current status."""
        elapsed = time.time() - self.started
        return {
            'session_id': self.session_id,
            'command': self.command[:100],
            'status': self.status,
            'exit_code': self.exit_code,
            'elapsed_s': round(elapsed, 1),
            'stdout_tail': self.stdout_data[-2000:] if self.stdout_data else '',
            'stderr_tail': self.stderr_data[-1000:] if self.stderr_data else '',
        }

    def kill(self) -> str:
        """Kill the background process."""
        if self.process:
            try:
                self.process.kill()
            except Exception:
                pass
        self.status = 'killed'
        return f'Killed background session {self.session_id}'

    @classmethod
    def list_sessions(cls) -> list:
        """List all background sessions."""
        return [s.poll() for s in cls._sessions.values()]

    @classmethod
    def get_session(cls, session_id: str):
        """Get a background session by ID."""
        return cls._sessions.get(session_id)

    @classmethod
    def kill_session(cls, session_id: str) -> str:
        """Kill a specific background session."""
        s = cls._sessions.get(session_id)
        if not s:
            return f'❌ Session {session_id} not found'
        return s.kill()
