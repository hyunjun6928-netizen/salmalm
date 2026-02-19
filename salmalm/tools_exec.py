"""Exec tools: exec, python_eval."""
import subprocess, sys, json, re
from .tool_registry import register
from .tools_common import _is_safe_command
from .constants import WORKSPACE_DIR


@register('exec')
def handle_exec(args: dict) -> str:
    cmd = args.get('command', '')
    safe, reason = _is_safe_command(cmd)
    if not safe:
        return f'{reason}'
    timeout = min(args.get('timeout', 30), 120)  # Max 120s, default 30s
    try:
        import shlex
        needs_shell = any(c in cmd for c in ['|', '>', '<', '&&', '||', ';', '`', '$('])
        if needs_shell:
            run_args = {'args': cmd, 'shell': True}
        else:
            try:
                run_args = {'args': shlex.split(cmd), 'shell': False}
            except ValueError:
                run_args = {'args': cmd, 'shell': True}
        result = subprocess.run(
            **run_args, capture_output=True, text=True,
            timeout=timeout, cwd=str(WORKSPACE_DIR)
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
