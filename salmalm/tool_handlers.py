"""SalmAlm tool handlers — execution logic for all 30 tools."""
import subprocess, sys, os, re, time, json, traceback, uuid
import urllib.request, base64, mimetypes, difflib, threading
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser
try:
    import resource as _resource_mod
except ImportError:
    _resource_mod = None

from .constants import (EXEC_ALLOWLIST, EXEC_BLOCKLIST, EXEC_BLOCKLIST_PATTERNS, PROTECTED_FILES,
                        WORKSPACE_DIR, VERSION, KST, MEMORY_FILE, MEMORY_DIR, AUDIT_DB)
from .crypto import vault, log
from .core import (audit_log, get_usage_report, _tfidf, SubAgent, SkillLoader,
                   _sessions, get_session, _tg_bot)
from .llm import _http_post, _http_get

# clipboard lock
_clipboard_lock = threading.Lock()
telegram_bot = None

def _is_safe_command(cmd: str) -> tuple[bool, str]:
    """Check if command is safe to execute (allowlist + blocklist double defense)."""
    first_word = cmd.strip().split()[0].split('/')[-1] if cmd.strip() else ''
    if not first_word:
        return False, 'Empty command'
    # Blocklist takes priority (even if somehow in allowlist)
    if first_word in EXEC_BLOCKLIST:
        return False, f'Blocked command: {first_word}'
    for pattern in EXEC_BLOCKLIST_PATTERNS:
        if re.search(pattern, cmd):
            return False, f'Blocked pattern: {pattern}'
    # Allowlist check — unknown commands blocked
    if first_word not in EXEC_ALLOWLIST:
        return False, f'Command not in allowlist: {first_word} (not in EXEC_ALLOWLIST)'
    return True, ''


def _resolve_path(path: str, writing: bool = False) -> Path:
    """Resolve path, preventing traversal outside allowed directories.

    Read: workspace + home directory
    Write: workspace only (stricter)
    """
    p = Path(path)
    if not p.is_absolute():
        p = WORKSPACE_DIR / p
    p = p.resolve()

    if writing:
        # Write operations: workspace only
        try:
            p.relative_to(WORKSPACE_DIR.resolve())
        except ValueError:
            raise PermissionError(f'Write denied (outside workspace): {p}')
    else:
        # Read operations: workspace + home
        allowed = [WORKSPACE_DIR.resolve(), Path.home().resolve()]
        if not any(_is_subpath(p, a) for a in allowed):
            raise PermissionError(f'Access denied: {p}')

    if writing and p.name in PROTECTED_FILES:
        raise PermissionError(f'Protected file: {p.name}')
    return p


def _is_subpath(path: Path, parent: Path) -> bool:
    """Check if path is under parent (safe, no startswith tricks)."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return result string."""
    audit_log('tool_exec', f'{name}: {json.dumps(args, ensure_ascii=False)[:200]}')
    try:
        if name == 'exec':
            cmd = args.get('command', '')
            safe, reason = _is_safe_command(cmd)
            if not safe:
                return f'❌ {reason}'
            timeout = min(args.get('timeout', 30), 120)
            try:
                # Use shell=False by default (safer), shell=True only for pipes/redirects
                import shlex
                needs_shell = any(c in cmd for c in ['|', '>', '<', '&&', '||', ';', '`', '$(' ])
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
                output = result.stdout[-5000:] if result.stdout else ''
                if result.stderr:
                    output += f'\n[stderr]: {result.stderr[-2000:]}'
                if result.returncode != 0:
                    output += f'\n[exit code]: {result.returncode}'
                return output or '(no output)'
            except subprocess.TimeoutExpired:
                return f'❌ Timeout ({timeout}s)'

        elif name == 'read_file':
            p = _resolve_path(args['path'])
            if not p.exists():
                return f'❌ File not found: {p}'
            text = p.read_text(encoding='utf-8', errors='replace')
            lines = text.splitlines()
            offset = args.get('offset', 1) - 1
            limit = args.get('limit', len(lines))
            selected = lines[offset:offset + limit]
            return '\n'.join(selected)[:50000]

        elif name == 'write_file':
            p = _resolve_path(args['path'], writing=True)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args['content'], encoding='utf-8')
            return f'✅ {p} ({len(args["content"])} chars)'

        elif name == 'edit_file':
            p = _resolve_path(args['path'], writing=True)
            text = p.read_text(encoding='utf-8')
            if args['old_text'] not in text:
                return f'❌ Text not found'
            text = text.replace(args['old_text'], args['new_text'], 1)
            p.write_text(text, encoding='utf-8')
            return f'✅ File edited: {p}'

        elif name == 'web_search':
            api_key = vault.get('brave_api_key')
            if not api_key:
                return '❌ Brave Search API key not found'
            query = urllib.parse.quote(args['query'])
            count = min(args.get('count', 5), 10)
            resp = _http_get(
                f'https://api.search.brave.com/res/v1/web/search?q={query}&count={count}',
                {'Accept': 'application/json', 'X-Subscription-Token': api_key}
            )
            results = []
            for r in resp.get('web', {}).get('results', [])[:count]:
                results.append(f"**{r['title']}**\n{r['url']}\n{r.get('description', '')}\n")
            return '\n'.join(results) or 'No results'

        elif name == 'web_fetch':
            url = args['url']
            max_chars = args.get('max_chars', 10000)
            # SSRF protection: block internal/private IPs
            from urllib.parse import urlparse
            _host = urlparse(url).hostname or ''
            _blocked = ('localhost', '127.', '10.', '192.168.', '172.16.',
                        '172.17.', '172.18.', '172.19.', '172.2', '172.30.', '172.31.',
                        '169.254.', '0.0.0.0', '::1', 'metadata.google', '169.254.169.254')
            if any(_host.startswith(b) or _host == b for b in _blocked):
                return f'❌ Internal network access blocked: {_host}'
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (SalmAlm/0.1)'
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
            # HTML to text using html.parser (robust, no regex fragility)
            from html.parser import HTMLParser

            class _TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self._parts: list = []
                    self._skip = False
                    self._skip_tags = {'script', 'style', 'noscript', 'svg'}

                def handle_starttag(self, tag, attrs):
                    if tag.lower() in self._skip_tags:
                        self._skip = True
                    elif tag.lower() in ('br', 'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr'):
                        self._parts.append('\n')

                def handle_endtag(self, tag):
                    if tag.lower() in self._skip_tags:
                        self._skip = False

                def handle_data(self, data):
                    if not self._skip:
                        self._parts.append(data)

                def get_text(self) -> str:
                    return re.sub(r'\n{3,}', '\n\n', ''.join(self._parts)).strip()

            extractor = _TextExtractor()
            extractor.feed(raw)
            return extractor.get_text()[:max_chars]

        elif name == 'memory_read':
            fname = args['file']
            if fname == 'MEMORY.md':
                p = MEMORY_FILE
            else:
                p = MEMORY_DIR / fname
            if not p.exists():
                return f'❌ File not found: {fname}'
            return p.read_text(encoding='utf-8')[:30000]

        elif name == 'memory_write':
            fname = args['file']
            if fname == 'MEMORY.md':
                p = MEMORY_FILE
            else:
                p = MEMORY_DIR / fname
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args['content'], encoding='utf-8')
            return f'✅ {fname} saved'

        elif name == 'usage_report':
            report = get_usage_report()
            lines = [f"📊 SalmAlm Usage Report",
                     f"⏱️ Uptime: {report['elapsed_hours']}h",
                     f"📥 Input: {report['total_input']:,} tokens",
                     f"📤 Output: {report['total_output']:,} tokens",
                     f"💰 Total cost: ${report['total_cost']:.4f}", ""]
            for m, d in report.get('by_model', {}).items():
                lines.append(f"  {m}: {d['calls']}calls, ${d['cost']:.4f}")
            return '\n'.join(lines)

        elif name == 'memory_search':
            query = args['query']
            max_results = args.get('max_results', 5)
            # Use TF-IDF semantic search
            results = _tfidf.search(query, max_results)
            if not results:
                return f'No results for: "{query}"'
            out = []
            for score, label, lineno, snippet in results:
                out.append(f'📍 {label}#{lineno} (similarity:{score:.3f})\n{snippet}\n')
            return '\n'.join(out)

        elif name == 'sub_agent':
            action = args.get('action', 'list')
            if action == 'spawn':
                task = args.get('task', '')
                if not task:
                    return '❌ Task is required'
                model = args.get('model')
                agent_id = SubAgent.spawn(task, model=model)
                return f'🤖 Sub-agent spawned: [{agent_id}]\nTask: {task[:100]}\nWill notify on completion.'
            elif action == 'list':
                agents = SubAgent.list_agents()
                if not agents:
                    return '📋 No running sub-agents.'
                lines = []
                for a in agents:
                    icon = '🟢' if a['status'] == 'running' else '✅' if a['status'] == 'completed' else '❌'
                    lines.append(f'{icon} [{a["id"]}] {a["task"]} — {a["status"]}')
                return '\n'.join(lines)
            elif action == 'result':
                agent_id = args.get('agent_id', '')
                info = SubAgent.get_result(agent_id)
                if 'error' in info:
                    return f'❌ {info["error"]}'
                status = info['status']
                if status == 'running':
                    return f'⏳ [{agent_id}] Still running.\nStarted: {info["started"]}'
                result = info.get('result', '(no result)')
                return f'{"✅" if status == "completed" else "❌"} [{agent_id}] {status}\nStarted: {info["started"]}\nFinished: {info["completed"]}\n\n{result[:3000]}'
            elif action == 'send':
                agent_id = args.get('agent_id', '')
                message = args.get('message', '')
                if not agent_id or not message:
                    return '❌ agent_id and message are required'
                result = SubAgent.send_message(agent_id, message)
                return result
            return f'❌ Unknown action: {action}'

        elif name == 'skill_manage':
            action = args.get('action', 'list')
            if action == 'list':
                skills = SkillLoader.scan()
                if not skills:
                    return '📚 No skills registered.\nCreate a skill directory in skills/ and add SKILL.md.'
                lines = []
                for s in skills:
                    lines.append(f'📚 **{s["name"]}** ({s["dir_name"]})\n   {s["description"]}\n   Size: {s["size"]}chars')
                return '\n'.join(lines)
            elif action == 'load':
                skill_name = args.get('skill_name', '')
                content = SkillLoader.load(skill_name)
                if not content:
                    return f'❌ Skill "{skill_name}" not found'
                return f'📚 Skill loaded: {skill_name}\n\n{content[:5000]}'
            elif action == 'match':
                query = args.get('query', '')
                content = SkillLoader.match(query)
                if not content:
                    return 'No matching skill found.'
                return f'📚 Auto-matched skill:\n\n{content[:5000]}'
            elif action == 'install':
                url = args.get('url', '')
                if not url:
                    return '❌ url is required (Git URL or GitHub shorthand user/repo)'
                return SkillLoader.install(url)
            elif action == 'uninstall':
                skill_name = args.get('skill_name', '')
                if not skill_name:
                    return '❌ skill_name is required'
                return SkillLoader.uninstall(skill_name)
            return f'❌ Unknown action: {action}'

        elif name == 'image_generate':
            prompt = args['prompt']
            provider = args.get('provider', 'xai')
            size = args.get('size', '1024x1024')
            save_dir = WORKSPACE_DIR / 'uploads'
            save_dir.mkdir(exist_ok=True)
            fname = f"gen_{int(time.time())}.png"
            save_path = save_dir / fname

            if provider == 'xai':
                api_key = vault.get('xai_api_key')
                if not api_key:
                    return '❌ xAI API key not found'
                resp = _http_post(
                    'https://api.x.ai/v1/images/generations',
                    {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                    {'model': 'aurora', 'prompt': prompt, 'n': 1, 'size': size,
                     'response_format': 'b64_json'}
                )
                import base64 as b64mod
                img_data = b64mod.b64decode(resp['data'][0]['b64_json'])
                save_path.write_bytes(img_data)
            else:
                api_key = vault.get('openai_api_key')
                if not api_key:
                    return '❌ OpenAI API key not found'
                resp = _http_post(
                    'https://api.openai.com/v1/images/generations',
                    {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                    {'model': 'gpt-image-1', 'prompt': prompt, 'n': 1, 'size': size,
                     'output_format': 'b64_json'}
                )
                import base64 as b64mod
                img_data = b64mod.b64decode(resp['data'][0]['b64_json'])
                save_path.write_bytes(img_data)

            size_kb = len(img_data) / 1024
            log.info(f"🎨 Image generated: {fname} ({size_kb:.1f}KB)")
            return f'✅ Image generated: uploads/{fname} ({size_kb:.1f}KB)\nPrompt: {prompt}'

        elif name == 'tts':
            text = args['text']
            voice = args.get('voice', 'nova')
            api_key = vault.get('openai_api_key')
            if not api_key:
                return '❌ OpenAI API key not found'
            save_dir = WORKSPACE_DIR / 'uploads'
            save_dir.mkdir(exist_ok=True)
            fname = f"tts_{int(time.time())}.mp3"
            save_path = save_dir / fname
            data = json.dumps({'model': 'tts-1', 'input': text, 'voice': voice}).encode()
            req = urllib.request.Request(
                'https://api.openai.com/v1/audio/speech',
                data=data,
                headers={'Authorization': f'Bearer {api_key}',
                         'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio = resp.read()
            save_path.write_bytes(audio)
            size_kb = len(audio) / 1024
            log.info(f"🔊 TTS generated: {fname} ({size_kb:.1f}KB)")
            return f'✅ TTS generated: uploads/{fname} ({size_kb:.1f}KB)\nText: {text[:100]}'

        elif name == 'python_eval':
            code = args.get('code', '')
            timeout_sec = min(args.get('timeout', 15), 30)
            # Block dangerous patterns in code
            _EVAL_BLOCKLIST = [
                'import os', 'import sys', 'import subprocess', 'import shutil',
                '__import__', 'eval(', 'exec(', 'compile(', 'open(',
                'os.system', 'os.popen', 'os.exec', 'os.spawn', 'os.remove', 'os.unlink',
                'shutil.rmtree', 'pathlib', '.vault', 'audit.db', 'auth.db',
                'import socket', 'import http', 'import urllib', 'import requests',
            ]
            code_lower = code.lower().replace(' ', '')
            for blocked in _EVAL_BLOCKLIST:
                if blocked.lower().replace(' ', '') in code_lower:
                    return f'❌ Security blocked: `{blocked}` not allowed. python_eval is for computation only.'
            # Execute in isolated subprocess (no network, limited imports)
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
            # Resource limits (Linux only — graceful no-op on Windows/macOS)
            def _set_limits():
                try:
                    import resource
                    resource.setrlimit(resource.RLIMIT_CPU, (timeout_sec, timeout_sec))
                    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))  # 512MB
                    resource.setrlimit(resource.RLIMIT_NOFILE, (50, 50))  # fd limit
                    resource.setrlimit(resource.RLIMIT_NPROC, (10, 10))  # fork bomb prevention
                    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))  # 10MB file write limit
                except Exception:
                    pass  # Windows or unsupported

            try:
                result = subprocess.run(
                    [sys.executable, '-c', wrapper],
                    capture_output=True, text=True,
                    timeout=timeout_sec, cwd=str(WORKSPACE_DIR),
                    preexec_fn=_set_limits
                )
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
                return f'❌ Python execution timeout ({timeout_sec}s)'

        elif name == 'system_monitor':
            detail = args.get('detail', 'overview')
            lines = []
            try:
                if detail in ('overview', 'cpu'):
                    load = os.getloadavg()
                    cpu_count = os.cpu_count() or 1
                    lines.append(f'🖥️ CPU: {cpu_count}cores, load: {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f} (1/5/15min)')
                if detail in ('overview', 'memory'):
                    mem = subprocess.run(['free', '-h'], capture_output=True, text=True, timeout=5)
                    if mem.stdout:
                        for l in mem.stdout.strip().split('\n'):
                            lines.append(f'💾 {l}')
                if detail in ('overview', 'disk'):
                    disk = subprocess.run(['df', '-h', '/'], capture_output=True, text=True, timeout=5)
                    if disk.stdout:
                        for l in disk.stdout.strip().split('\n'):
                            lines.append(f'💿 {l}')
                if detail in ('overview', 'network'):
                    # Quick network check
                    net = subprocess.run(['ss', '-s'], capture_output=True, text=True, timeout=5)
                    if net.stdout:
                        lines.append(f'🌐 Network:')
                        for l in net.stdout.strip().split('\n')[:5]:
                            lines.append(f'   {l}')
                if detail == 'processes':
                    ps = subprocess.run(['ps', 'aux', '--sort=-rss'], capture_output=True, text=True, timeout=5)
                    if ps.stdout:
                        for l in ps.stdout.strip().split('\n')[:20]:
                            lines.append(l)
                if detail in ('overview',):
                    uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True, timeout=5)
                    if uptime.stdout:
                        lines.append(f'⏱️ Uptime: {uptime.stdout.strip()}')
                    # Python process info
                    mem_mb = 0
                    if _resource_mod:
                        mem_mb = _resource_mod.getrusage(_resource_mod.RUSAGE_SELF).ru_maxrss / 1024
                    lines.append(f'🐍 SalmAlm memory: {mem_mb:.1f}MB')
                    lines.append(f'📂 Sessions: {len(_sessions)}')
            except Exception as e:
                lines.append(f'❌ Monitor error: {e}')
            return '\n'.join(lines) or 'No info'

        elif name == 'http_request':
            method = args.get('method', 'GET').upper()
            url = args.get('url', '')
            headers = args.get('headers', {})
            body_str = args.get('body', '')
            timeout_sec = min(args.get('timeout', 15), 60)
            if not url:
                return '❌ URL is required'
            # SSRF protection: block internal/private IPs
            from urllib.parse import urlparse
            _host = urlparse(url).hostname or ''
            _blocked = ('localhost', '127.', '10.', '192.168.', '172.16.',
                        '172.17.', '172.18.', '172.19.', '172.2', '172.30.', '172.31.',
                        '169.254.', '0.0.0.0', '::1', 'metadata.google', '169.254.169.254')
            if any(_host.startswith(b) or _host == b for b in _blocked):
                return f'❌ Internal network access blocked: {_host}'
            headers.setdefault('User-Agent', f'SalmAlm/{VERSION}')
            data = body_str.encode('utf-8') if body_str else None
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                    status = resp.status
                    resp_headers = dict(resp.headers)
                    raw = resp.read()
                # Try JSON
                try:
                    body_json = json.loads(raw)
                    body_out = json.dumps(body_json, ensure_ascii=False, indent=2)[:8000]
                except (json.JSONDecodeError, UnicodeDecodeError):
                    body_out = raw.decode('utf-8', errors='replace')[:8000]
                header_str = '\n'.join(f'  {k}: {v}' for k, v in list(resp_headers.items())[:10])
                return f'HTTP {status}\nHeaders:\n{header_str}\n\nBody:\n{body_out}'
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8', errors='replace')[:3000]
                return f'HTTP {e.code} {e.reason}\n{body}'
            except Exception as e:
                return f'❌ Request error: {e}'

        elif name == 'screenshot':
            region = args.get('region', 'full')
            fname = f'screenshot_{int(time.time())}.png'
            fpath = WORKSPACE_DIR / 'uploads' / fname
            fpath.parent.mkdir(exist_ok=True)
            try:
                cmd = ['import', '-window', 'root', str(fpath)] if region == 'full' else ['import', '-crop', region, '-window', 'root', str(fpath)]
                # Try scrot first (more common)
                try:
                    if region == 'full':
                        subprocess.run(['scrot', str(fpath)], timeout=10, check=True)
                    else:
                        subprocess.run(['scrot', '-a', region, str(fpath)], timeout=10, check=True)
                except FileNotFoundError:
                    subprocess.run(cmd, timeout=10, check=True)
                size_kb = fpath.stat().st_size / 1024
                return f'✅ Screenshot saved: uploads/{fname} ({size_kb:.1f}KB)'
            except Exception as e:
                return f'❌ Screenshot failed: {e}'

        elif name == 'json_query':
            data_str = args.get('data', '')
            query = args.get('query', '.')
            from_file = args.get('from_file', False)
            if from_file:
                fpath = _resolve_path(data_str)
                data_str = fpath.read_text(encoding='utf-8', errors='replace')
            try:
                result = subprocess.run(
                    ['jq', query],
                    input=data_str, capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    return result.stdout[:8000] or '(empty)'
                return f'❌ jq error: {result.stderr[:500]}'
            except FileNotFoundError:
                # jq not installed, try Python fallback
                data = json.loads(data_str)
                # Simple dot notation query
                parts = query.strip('.').split('.')
                current = data
                for p in parts:
                    if not p:
                        continue
                    if p.endswith('[]'):
                        p = p[:-2]
                        if p:
                            current = current[p]
                        if isinstance(current, list):
                            current = current
                    elif p.isdigit():
                        current = current[int(p)]
                    else:
                        current = current[p]
                return json.dumps(current, ensure_ascii=False, indent=2)[:8000]

        elif name == 'diff_files':
            f1 = args.get('file1', '')
            f2 = args.get('file2', '')
            ctx = args.get('context_lines', 3)
            import difflib
            # If paths exist, read them
            try:
                p1 = _resolve_path(f1)
                text1 = p1.read_text(encoding='utf-8', errors='replace').splitlines()
                label1 = f1
            except Exception:
                text1 = f1.splitlines()
                label1 = 'text1'
            try:
                p2 = _resolve_path(f2)
                text2 = p2.read_text(encoding='utf-8', errors='replace').splitlines()
                label2 = f2
            except Exception:
                text2 = f2.splitlines()
                label2 = 'text2'
            diff = list(difflib.unified_diff(text1, text2, fromfile=label1, tofile=label2, n=ctx))
            if not diff:
                return '✅ Files/texts are identical.'
            return '\n'.join(diff[:300])

        elif name == 'clipboard':
            action = args.get('action', 'list')
            slot = args.get('slot', 'default')
            
            # Slot name length limit (100 chars)
            if len(slot) > 100:
                return '❌ Slot name must be under 100 characters'
            
            clip_file = WORKSPACE_DIR / '.clipboard.json'
            
            with _clipboard_lock:  # race condition prevention
                try:
                    clips = json.loads(clip_file.read_text()) if clip_file.exists() else {}
                except Exception:
                    clips = {}

                if action == 'copy':
                    content = args.get('content', '')
                    if not content:
                        return '❌ content is required'
                    if len(clips) >= 50 and slot not in clips:
                        return '❌ Clipboard slot limit exceeded (max 50)'
                    clips[slot] = {
                        'content': content[:50000],
                        'created': datetime.now(KST).isoformat(),
                        'size': len(content[:50000])  # actual saved size
                    }
                    clip_file.write_text(json.dumps(clips, ensure_ascii=False, indent=2))
                    return f'📋 [{slot}] saved ({len(content[:50000])} chars)'

                elif action == 'paste':
                    if slot not in clips:
                        return f'❌ Slot [{slot}] not found. Available: {", ".join(clips.keys()) or "none"}'
                    return clips[slot]['content']

                elif action == 'list':
                    if not clips:
                        return '📋 Clipboard is empty.'
                    lines = ['📋 Clipboard:']
                    for slot_name, data in clips.items():
                        preview = data['content'][:60].replace('\n', ' ')
                        if len(data['content']) > 60:
                            preview += "..."
                        lines.append(f'  [{slot_name}] {data["size"]} chars — "{preview}"')
                    return '\n'.join(lines)

                elif action == 'clear':
                    clip_file.write_text('{}')
                    return '🗑️ Clipboard cleared'

                return f'❌ Unknown action: {action}'

        elif name == 'hash_text':
            import hashlib, secrets, string
            action = args.get('action', 'hash')

            if action == 'hash':
                text = args.get('text', '')
                if not text:
                    return '❌ text is required'
                algo = args.get('algorithm', 'sha256')
                algos = {'sha256': hashlib.sha256, 'md5': hashlib.md5, 'sha1': hashlib.sha1,
                         'sha512': hashlib.sha512, 'sha384': hashlib.sha384}
                if algo not in algos:
                    return f'❌ Supported algorithms: {", ".join(algos.keys())}'
                h = algos[algo](text.encode('utf-8')).hexdigest()
                return f'🔐 {algo.upper()}: {h}'  # prevent sensitive data leak

            elif action == 'password':
                length = max(8, min(args.get('length', 16), 128))  # min 8 chars enforced
                charset = string.ascii_letters + string.digits + '!@#$%^&*'
                pw = ''.join(secrets.choice(charset) for _ in range(length))
                return f'🔑 Password ({length}chars): {pw}'

            elif action == 'uuid':
                import uuid as _uuid_mod
                return f'🆔 UUID: {_uuid_mod.uuid4()}'

            elif action == 'token':
                length = min(args.get('length', 32), 256)
                token = secrets.token_hex((length + 1) // 2)[:length]  # handle odd length
                return f'🎫 Token ({len(token)}chars): {token}'

            return f'❌ Unknown action: {action}'

        elif name == 'regex_test':
            pattern = args.get('pattern', '')
            text = args.get('text', '')
            action = args.get('action', 'find')
            flags_str = args.get('flags', '')

            # Parse flags
            flags = 0
            if 'i' in flags_str:
                flags |= re.IGNORECASE
            if 'm' in flags_str:
                flags |= re.MULTILINE
            if 's' in flags_str:
                flags |= re.DOTALL

            try:
                compiled = re.compile(pattern, flags)
            except re.error as e:
                return f'❌ Regex error: {e}'

            # ReDoS defense - isolate via subprocess (cross-platform)
            def _run_regex():
                if action == 'match':
                    m = compiled.fullmatch(text)
                    if m:
                        groups = m.groups()
                        gdict = m.groupdict()
                        result = f'✅ Full match: "{m.group()}"'
                        if groups:
                            result += f'\nGroups: {groups}'
                        if gdict:
                            result += f'\nNamed groups: {gdict}'
                        return result
                    return '❌ No match'

                elif action == 'find':
                    matches = compiled.findall(text)
                    if not matches:
                        return '❌ No matches found'
                    lines = [f'🔍 {len(matches)} found:']
                    for i, m in enumerate(matches[:50], 1):
                        lines.append(f'  {i}. {m}')
                    if len(matches) > 50:
                        lines.append(f'  ... and {len(matches)-50} more')
                    return '\n'.join(lines)

                elif action == 'replace':
                    replacement = args.get('replacement', '')
                    result = compiled.sub(replacement, text)
                    return f'🔄 Replace result:\n{result[:5000]}'

                elif action == 'split':
                    parts = compiled.split(text)
                    lines = [f'✂️ {len(parts)} parts:']
                    for i, p in enumerate(parts[:50], 1):
                        preview = p[:100]
                        if len(p) > 100:
                            preview += "..."
                        lines.append(f'  {i}. "{preview}"')
                    return '\n'.join(lines)

                return f'❌ Unknown action: {action}'

            # Run with timeout using threading
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                try:
                    future = pool.submit(_run_regex)
                    return future.result(timeout=5)
                except concurrent.futures.TimeoutError:
                    return '❌ Regex execution timeout (5s)'

        elif name == 'cron_manage':
            from .core import _llm_cron
            if not _llm_cron:
                return '❌ LLM cron manager not initialized'
            action = args.get('action', 'list')
            if action == 'list':
                jobs = _llm_cron.list_jobs()
                if not jobs:
                    return '⏰ No scheduled jobs.'
                lines = ['⏰ **Scheduled Jobs:**']
                for j in jobs:
                    status = '✅' if j['enabled'] else '⏸️'
                    lines.append(f"{status} [{j['id']}] {j['name']} — {j['schedule']} (runs: {j['run_count']})")
                return '\n'.join(lines)
            elif action == 'add':
                name_ = args.get('name', 'Untitled')
                prompt = args.get('prompt', '')
                schedule = args.get('schedule', {})
                if not prompt:
                    return '❌ prompt is required'
                if not schedule:
                    return '❌ schedule is required (kind: cron/every/at)'
                model = args.get('model')
                job = _llm_cron.add_job(name_, schedule, prompt, model=model)
                return f"⏰ Job registered: [{job['id']}] {name_}"
            elif action == 'remove':
                job_id = args.get('job_id', '')
                if _llm_cron.remove_job(job_id):
                    return f'⏰ Job removed: {job_id}'
                return f'❌ Job not found: {job_id}'
            elif action == 'toggle':
                job_id = args.get('job_id', '')
                for j in _llm_cron.jobs:
                    if j['id'] == job_id:
                        j['enabled'] = not j['enabled']
                        _llm_cron.save_jobs()
                        return f"⏰ {j['name']}: {'enabled' if j['enabled'] else 'disabled'}"
                return f'❌ Job not found: {job_id}'
            return f'❌ Unknown action: {action}'

        elif name == 'plugin_manage':
            from .core import PluginLoader
            action = args.get('action', 'list')
            if action == 'list':
                tools = PluginLoader.get_all_tools()
                plugins = PluginLoader._plugins
                if not plugins:
                    return '🔌 No plugins loaded. Add .py files to plugins/ directory.'
                lines = ['🔌 **Plugins:**']
                for name_, info in plugins.items():
                    lines.append(f"  📦 {name_} — {len(info['tools'])} tools ({info['path']})")
                    for t in info['tools']:
                        lines.append(f"    🔧 {t['name']}: {t['description'][:60]}")
                return '\n'.join(lines)
            elif action == 'reload':
                count = PluginLoader.reload()
                return f'🔌 Plugins reloaded: {count} tools loaded'
            return f'❌ Unknown action: {action}'

        elif name == 'browser':
            import asyncio
            from .browser import browser

            def _run_async(coro):
                """Safely run async coroutine from sync context (ThreadPool)."""
                try:
                    loop = asyncio.get_running_loop()
                    # Already in async context — use new thread with new loop
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(1) as pool:
                        return pool.submit(lambda: asyncio.run(coro)).result(timeout=30)
                except RuntimeError:
                    # No running loop — safe to use asyncio.run
                    return asyncio.run(coro)

            action = args.get('action', 'status')
            if action == 'status':
                return json.dumps(browser.get_status(), ensure_ascii=False)
            elif action == 'connect':
                ok = _run_async(browser.connect())
                return '🌐 Browser connected' if ok else '❌ Connection failed. Check Chrome --remote-debugging-port=9222'
            elif action == 'navigate':
                url = args.get('url', '')
                if not url:
                    return '❌ url is required'
                result = _run_async(browser.navigate(url))
                return f'🌐 Navigated: {url}\n{json.dumps(result, ensure_ascii=False)}'
            elif action == 'text':
                text = _run_async(browser.get_text())
                return text[:5000] if text else '(empty page or not connected)'
            elif action == 'html':
                html = _run_async(browser.get_html())
                return html[:8000] if html else '(empty page or not connected)'
            elif action == 'screenshot':
                b64 = _run_async(browser.screenshot())
                if b64:
                    import base64 as b64mod
                    save_dir = WORKSPACE_DIR / 'uploads'
                    save_dir.mkdir(exist_ok=True)
                    fname = f'screenshot_{int(time.time())}.png'
                    (save_dir / fname).write_bytes(b64mod.b64decode(b64))
                    return f'📸 Screenshot saved: uploads/{fname} ({len(b64)//1024}KB base64)'
                return '❌ Screenshot failed (not connected?)'
            elif action == 'evaluate':
                expr = args.get('expression', '')
                if not expr:
                    return '❌ expression is required'
                result = _run_async(browser.evaluate(expr))
                return json.dumps(result, ensure_ascii=False, default=str)[:5000]
            elif action == 'click':
                sel = args.get('selector', '')
                ok = _run_async(browser.click(sel))
                return f'✅ Clicked: {sel}' if ok else f'❌ Element not found: {sel}'
            elif action == 'type':
                sel = args.get('selector', '')
                text = args.get('text', '')
                ok = _run_async(browser.type_text(sel, text))
                return f'✅ Input: {sel}' if ok else f'❌ Element not found: {sel}'
            elif action == 'tabs':
                tabs = _run_async(browser.get_tabs())
                return json.dumps(tabs, ensure_ascii=False)
            elif action == 'console':
                logs = browser.get_console_logs(limit=30)
                return '\n'.join(logs) if logs else '(no console logs)'
            elif action == 'pdf':
                b64 = _run_async(browser.pdf())
                if b64:
                    import base64 as b64mod
                    save_dir = WORKSPACE_DIR / 'uploads'
                    save_dir.mkdir(exist_ok=True)
                    fname = f'page_{int(time.time())}.pdf'
                    (save_dir / fname).write_bytes(b64mod.b64decode(b64))
                    return f'📄 PDF saved: uploads/{fname}'
                return '❌ PDF generation failed'
            return f'❌ Unknown action: {action}'

        elif name == 'node_manage':
            from .nodes import node_manager
            action = args.get('action', 'list')
            if action == 'list':
                nodes = node_manager.list_nodes()
                if not nodes:
                    return '📡 No nodes registered. node_manage(action="add", name="...", host="...") to add'
                lines = ['📡 **Nodes:**']
                for n in nodes:
                    lines.append(f"  {'🔗' if n['type']=='ssh' else '🌐'} {n['name']} ({n.get('host', n.get('url', '?'))})")
                return '\n'.join(lines)
            elif action == 'add':
                nname = args.get('name', '')
                ntype = args.get('type', 'ssh')
                if not nname:
                    return '❌ name is required'
                if ntype == 'ssh':
                    host = args.get('host', '')
                    if not host:
                        return '❌ host is required'
                    node_manager.add_ssh_node(nname, host, user=args.get('user', 'root'),
                                              port=args.get('port', 22), key=args.get('key'))
                    return f'📡 SSH node added: {nname}'
                elif ntype == 'http':
                    url = args.get('url', '')
                    if not url:
                        return '❌ url is required'
                    node_manager.add_http_node(nname, url)
                    return f'📡 HTTP node added: {nname}'
                return f'❌ Unknown type: {ntype}'
            elif action == 'remove':
                nname = args.get('name', '')
                if node_manager.remove_node(nname):
                    return f'📡 Node removed: {nname}'
                return f'❌ Node not found: {nname}'
            elif action == 'run':
                nname = args.get('name', '')
                cmd = args.get('command', '')
                if not nname or not cmd:
                    return '❌ name and command are required'
                result = node_manager.run_on(nname, cmd)
                return json.dumps(result, ensure_ascii=False)[:5000]
            elif action == 'status':
                nname = args.get('name')
                if nname:
                    node = node_manager.get_node(nname)
                    if not node:
                        return f'❌ Node not found: {nname}'
                    return json.dumps(node.status(), ensure_ascii=False)[:3000]
                return json.dumps(node_manager.status_all(), ensure_ascii=False)[:5000]
            elif action == 'wake':
                mac = args.get('mac', '')
                if not mac:
                    return '❌ mac is required'
                result = node_manager.wake_on_lan(mac)
                return json.dumps(result, ensure_ascii=False)
            return f'❌ Unknown action: {action}'

        elif name == 'health_check':
            from .stability import health_monitor
            action = args.get('action', 'check')
            if action == 'check':
                report = health_monitor.check_health()
                lines = [f"🏥 **System status: {report['status'].upper()}**",
                         f"⏱️ Uptime: {report['uptime_human']}"]
                sys_info = report.get('system', {})
                if sys_info.get('memory_mb'):
                    lines.append(f"💾 Memory: {sys_info['memory_mb']}MB")
                if sys_info.get('disk_free_mb'):
                    lines.append(f"💿 Disk: {sys_info['disk_free_mb']}MB free ({sys_info.get('disk_pct',0)}% used)")
                lines.append(f"🧵 Threads: {sys_info.get('threads', '?')}")
                lines.append("")
                for comp, status in report['components'].items():
                    icon = '✅' if status.get('status') == 'ok' else '⚠️' if status.get('status') != 'error' else '❌'
                    lines.append(f"  {icon} {comp}: {status.get('status', '?')}")
                return '\n'.join(lines)
            elif action == 'selftest':
                result = health_monitor.startup_selftest()
                lines = [f"🧪 **Self-test: {result['passed']}/{result['total']}**"]
                for mod, status in result['modules'].items():
                    icon = '✅' if status == 'ok' else '❌'
                    lines.append(f"  {icon} {mod}: {status}")
                return '\n'.join(lines)
            elif action == 'recover':
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(1) as pool:
                        recovered = pool.submit(lambda: asyncio.run(health_monitor.auto_recover())).result(timeout=30)
                except RuntimeError:
                    recovered = asyncio.run(health_monitor.auto_recover())
                if recovered:
                    return f'🔧 Recovery completed: {", ".join(recovered)}'
                return '🔧 No components need recovery (all OK)'
            return f'❌ Unknown action: {action}'

        elif name == 'mcp_manage':
            from .mcp import mcp_manager
            action = args.get('action', 'list')
            if action == 'list':
                servers = mcp_manager.list_servers()
                if not servers:
                    return '🔌 No MCP servers connected. mcp_manage(action="add", name="...", command="...") to add.'
                lines = ['🔌 **MCP Servers:**']
                for s in servers:
                    status = '🟢' if s['connected'] else '🔴'
                    lines.append(f"  {status} {s['name']} — {s['tools']} tools ({' '.join(s['command'])})")
                return '\n'.join(lines)
            elif action == 'add':
                sname = args.get('name', '')
                cmd_str = args.get('command', '')
                if not sname or not cmd_str:
                    return '❌ name and command are required'
                cmd_list = cmd_str.split()
                env = args.get('env', {})
                ok = mcp_manager.add_server(sname, cmd_list, env=env)
                if ok:
                    mcp_manager.save_config()
                    tools_count = len([t for t in mcp_manager.get_all_tools() if t.get('_mcp_server') == sname])
                    return f'🔌 MCP server added: {sname} ({tools_count} tools)'
                return f'❌ MCP server connection failed: {sname}'
            elif action == 'remove':
                sname = args.get('name', '')
                mcp_manager.remove_server(sname)
                mcp_manager.save_config()
                return f'🔌 MCP server removed: {sname}'
            elif action == 'tools':
                all_mcp = mcp_manager.get_all_tools()
                if not all_mcp:
                    return '🔌 No MCP tools (no servers connected)'
                lines = [f'🔌 **MCP Tools ({len(all_mcp)}):**']
                for t in all_mcp:
                    lines.append(f"  🔧 {t['name']}: {t['description'][:80]}")
                return '\n'.join(lines)
            return f'❌ Unknown action: {action}'

        elif name == 'rag_search':
            from .rag import rag_engine
            query = args.get('query', '')
            if not query:
                return '❌ query is required'
            max_results = args.get('max_results', 5)
            results = rag_engine.search(query, max_results=max_results)
            if not results:
                return f'🔍 "{query}" No results for'
            lines = [f'🔍 **"{query}" Results ({len(results)}):**']
            for r in results:
                lines.append(f"\n📄 **{r['source']}** (L{r['line']}, score: {r['score']})")
                lines.append(r['text'][:300])
            stats = rag_engine.get_stats()
            lines.append(f"\n📊 Index: {stats['total_chunks']}chunks, {stats['unique_terms']}terms, {stats['db_size_kb']}KB")
            return '\n'.join(lines)

        else:
            # Try plugin tools as fallback
            from .core import PluginLoader
            result = PluginLoader.execute(name, args)
            if result is not None:
                return result
            # Try MCP tools as last fallback
            if name.startswith('mcp_'):
                from .mcp import mcp_manager
                mcp_result = mcp_manager.call_tool(name, args)
                if mcp_result is not None:
                    return mcp_result
            return f'❌ Unknown tool: {name}'

    except PermissionError as e:
        return f'❌ Permission denied: {e}'
    except Exception as e:
        log.error(f"Tool error ({name}): {e}")
        return f'❌ Tool error: {str(e)[:200]}'
