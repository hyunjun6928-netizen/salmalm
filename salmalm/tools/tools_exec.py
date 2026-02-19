"""Exec tools: exec, python_eval, background session management."""
import subprocess, sys, json, re, os, time
from salmalm.tool_registry import register
from salmalm.tools_common import _is_safe_command
from salmalm.constants import WORKSPACE_DIR
from salmalm.exec_approvals import (check_approval, check_env_override, BackgroundSession,
                              BLOCKED_ENV_OVERRIDES)


@register('exec')
def handle_exec(args: dict) -> str:
    cmd = args.get('command', '')
    background = args.get('background', False)
    yield_ms = args.get('yieldMs', 0)
    notify_on_exit = args.get('notifyOnExit', False)
    env = args.get('env', None)

    # Basic safety check
    safe, reason = _is_safe_command(cmd)
    if not safe:
        return f'{reason}'

    # Env var security: block PATH, LD_*, DYLD_* overrides
    if env:
        env_safe, blocked = check_env_override(env)
        if not env_safe:
            return f'❌ Blocked environment variable overrides: {", ".join(blocked)} (binary hijacking prevention)'

    # Approval system check
    approved, approval_reason, needs_confirm = check_approval(cmd)
    if not approved and not needs_confirm:
        return f'❌ Command denied: {approval_reason}'
    if needs_confirm:
        return (f'⚠️ **Approval required**: {approval_reason}\n'
                f'Command: `{cmd[:200]}`\n'
                f'Reply with `/approve` to execute or `/deny` to cancel.')

    # Default timeout: 1800s (30 min) for background, 120s for foreground
    if background:
        timeout = min(args.get('timeout', 1800), 7200)  # Max 2h for background
    else:
        timeout = min(args.get('timeout', 30), 1800)  # Max 30min for foreground

    # Background execution
    if background:
        session = BackgroundSession(cmd, timeout=timeout, notify_on_exit=notify_on_exit, env=env)
        sid = session.start()
        return f'🔄 Background session started: `{sid}`\nCommand: `{cmd[:100]}`\nTimeout: {timeout}s'

    # yieldMs: start foreground, yield to background after N ms
    if yield_ms > 0:
        session = BackgroundSession(cmd, timeout=timeout, notify_on_exit=notify_on_exit, env=env)
        sid = session.start()
        # Wait for yieldMs
        time.sleep(yield_ms / 1000.0)
        poll = session.poll()
        if poll['status'] in ('completed', 'error', 'timeout'):
            # Already finished
            output = poll['stdout_tail']
            if poll['stderr_tail']:
                output += f'\n[stderr]: {poll["stderr_tail"]}'
            if poll['exit_code'] and poll['exit_code'] != 0:
                output += f'\n[exit code]: {poll["exit_code"]}'
            return output or '(no output)'
        return (f'🔄 Yielded to background: `{sid}`\n'
                f'Status: {poll["status"]} ({poll["elapsed_s"]}s elapsed)\n'
                f'Use `exec_session poll {sid}` to check progress.')

    # Foreground execution (original behavior)
    try:
        import shlex
        needs_shell = any(c in cmd for c in ['|', '>', '<', '&&', '||', ';', '`', '$('])

        # Build environment
        run_env = None
        if env:
            run_env = dict(os.environ)
            run_env.update(env)

        if needs_shell:
            run_args = {'args': cmd, 'shell': True}
        else:
            try:
                run_args = {'args': shlex.split(cmd), 'shell': False}
            except ValueError:
                run_args = {'args': cmd, 'shell': True}
        extra_kwargs = {}
        if run_env:
            extra_kwargs['env'] = run_env
        result = subprocess.run(
            **run_args, capture_output=True, text=True,
            timeout=timeout, cwd=str(WORKSPACE_DIR), **extra_kwargs
        )
        # Output truncation: 50KB max
        MAX_OUTPUT = 50 * 1024
        output = result.stdout[-MAX_OUTPUT:] if result.stdout else ''
        if len(result.stdout or '') > MAX_OUTPUT:
            output = f'[truncated: {len(result.stdout)} chars total, showing last {MAX_OUTPUT}]\n' + output
        if result.stderr:
            output += f'\n[stderr]: {result.stderr[-2000:]}'
        if result.returncode != 0:
            output += f'\n[exit code]: {result.returncode}'
        return output or '(no output)'
    except subprocess.TimeoutExpired:
        return f'Timeout ({timeout}s)'


@register('exec_session')
def handle_exec_session(args: dict) -> str:
    """Manage background exec sessions: list, poll, kill."""
    action = args.get('action', 'list')

    if action == 'list':
        sessions = BackgroundSession.list_sessions()
        if not sessions:
            return '📋 No background sessions.'
        lines = ['📋 **Background Sessions**\n']
        for s in sessions:
            icon = {'running': '🔄', 'completed': '✅', 'error': '❌',
                    'timeout': '⏰', 'killed': '💀'}.get(s['status'], '❓')
            lines.append(f"{icon} `{s['session_id']}` — {s['command']} [{s['status']}] ({s['elapsed_s']}s)")
        return '\n'.join(lines)

    elif action == 'poll':
        sid = args.get('session_id', '')
        session = BackgroundSession.get_session(sid)
        if not session:
            return f'❌ Session {sid} not found'
        poll = session.poll()
        output = f"📊 **{poll['session_id']}** [{poll['status']}]\n"
        output += f"Elapsed: {poll['elapsed_s']}s"
        if poll['exit_code'] is not None:
            output += f" | Exit: {poll['exit_code']}"
        if poll['stdout_tail']:
            output += f"\n\n```\n{poll['stdout_tail'][-2000:]}\n```"
        if poll['stderr_tail']:
            output += f"\n[stderr]: {poll['stderr_tail'][-500:]}"
        return output

    elif action == 'kill':
        sid = args.get('session_id', '')
        return BackgroundSession.kill_session(sid)

    return f'❌ Unknown action: {action}. Use list, poll, or kill.'


@register('python_eval')
def handle_python_eval(args: dict) -> str:
    code = args.get('code', '')
    timeout_sec = min(args.get('timeout', 15), 30)
    _EVAL_BLOCKLIST = [
        'import os', 'import sys', 'import subprocess', 'import shutil',
        '__import__', 'eval(', 'exec(', 'compile(', 'open(',
        'os.system', 'os.popen', 'os.exec', 'os.spawn', 'os.remove', 'os.unlink',
        'shutil.rmtree', 'pathlib', '.vault', 'audit.db', 'auth.db',
        'import socket', 'import http', 'import urllib', 'import requests',
        'getattr(', 'globals(', 'locals(', '__builtins__', 'vars(',
        'breakpoint(', 'help(', 'input(', 'exit(', 'quit(',
        '__class__', '__subclasses__', '__bases__', '__mro__',
        'importlib', 'ctypes', 'signal',
    ]
    code_lower = code.lower().replace(' ', '').replace('\t', '')
    for blocked in _EVAL_BLOCKLIST:
        if blocked.lower().replace(' ', '') in code_lower:
            return f'Security blocked: `{blocked}` not allowed.'
    if re.search(r'__\w+__', code):
        _dangerous_dunders = ['__import__', '__builtins__', '__class__',
                               '__subclasses__', '__bases__', '__mro__', '__loader__']
        for dd in _dangerous_dunders:
            if dd in code.lower():
                return f'Security blocked: `{dd}` not allowed.'
    wrapper = f'''
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
'''
    def _set_limits():
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (timeout_sec, timeout_sec))
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_NOFILE, (50, 50))
            resource.setrlimit(resource.RLIMIT_NPROC, (10, 10))
            resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
        except Exception:
            pass
    try:
        _kwargs: dict = dict(capture_output=True, text=True, timeout=timeout_sec, cwd=str(WORKSPACE_DIR))
        if sys.platform != 'win32':
            _kwargs['preexec_fn'] = _set_limits
        result = subprocess.run([sys.executable, '-c', wrapper], **_kwargs)
        if result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout.strip())
                output = data.get('result', result.stdout)
            except json.JSONDecodeError:
                output = result.stdout[-5000:]
        else:
            output = result.stdout[-3000:] if result.stdout else ''
        if result.stderr:
            output += f'\n[stderr]: {result.stderr[-2000:]}'
        return output or '(no output)'
    except subprocess.TimeoutExpired:
        return f'Python execution timeout ({timeout_sec}s)'
