"""SalmAlm tool handlers — thin shim delegating to tool_registry.

Keeps shared utilities (_resolve_path, _is_safe_command, _is_subpath) that other
modules import, plus _legacy_execute for tools_media.py bridge.
"""
import subprocess, sys, os, re, time, json, traceback, uuid, secrets
import urllib.request, base64, mimetypes, difflib, threading
from datetime import datetime
from pathlib import Path

from .constants import (EXEC_ALLOWLIST, EXEC_BLOCKLIST, EXEC_BLOCKLIST_PATTERNS, EXEC_ELEVATED,
                        PROTECTED_FILES, WORKSPACE_DIR, VERSION, KST, MEMORY_FILE, MEMORY_DIR, AUDIT_DB)
from .crypto import vault, log
from .core import audit_log
from .llm import _http_post, _http_get

# Re-export symbols that tests and other modules import from here
from .tools_misc import (  # noqa: F401 — re-export for tests and other modules
    _reminders, _reminder_lock, _send_notification_impl,
    _parse_relative_time, _parse_rss,
    _workflows_file, _feeds_file,
)

# clipboard lock (used by tools_util.py)
_clipboard_lock = threading.Lock()
telegram_bot = None


# ── Shared Utilities ─────────────────────────────────────────

def _is_safe_command(cmd: str):
    """Check if command is safe to execute (allowlist + blocklist double defense)."""
    if not cmd.strip():
        return False, 'Empty command'

    # Blocklist patterns first (catches dangerous combos)
    for pattern in EXEC_BLOCKLIST_PATTERNS:
        if re.search(pattern, cmd):
            return False, f'Blocked pattern: {pattern}'

    # Split on pipe/chain operators and check EVERY stage
    stages = re.split(r'\s*(?:\|\||&&|;|\|)\s*', cmd)
    for stage in stages:
        words = stage.strip().split()
        if not words:
            continue
        first_word = words[0].split('/')[-1]  # strip path prefix
        if first_word in EXEC_BLOCKLIST:
            return False, f'Blocked command in pipeline: {first_word}'
        if first_word in EXEC_ELEVATED:
            log.warning(f"[WARN] Elevated exec: {first_word} (can run arbitrary code)")
        elif first_word not in EXEC_ALLOWLIST:
            return False, f'Command not in allowlist: {first_word}'

    # Check for subshell/backtick/process substitution bypasses
    if re.search(r'`.*`|\$\(.*\)|<\(|>\(', cmd):
        inner = re.findall(r'`([^`]+)`|\$\(([^)]+)\)', cmd)
        for groups in inner:
            inner_cmd = groups[0] or groups[1]
            safe, reason = _is_safe_command(inner_cmd)
            if not safe:
                return False, f'Unsafe subcommand: {reason}'

    return True, 'OK'


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


def _is_private_url(url: str):
    """Check if URL resolves to a private/internal IP. Returns (blocked, reason)."""
    import ipaddress, socket
    from urllib.parse import urlparse
    hostname = urlparse(url).hostname or ''
    if not hostname:
        return True, 'No hostname'
    _BLOCKED_HOSTS = frozenset([
        'metadata.google.internal', '169.254.169.254', 'metadata.internal',
        'metadata', 'instance-data', '100.100.100.200',
    ])
    if hostname in _BLOCKED_HOSTS or hostname.endswith('.internal'):
        return True, f'Blocked metadata endpoint: {hostname}'
    try:
        addrs = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True, f'Internal IP blocked: {hostname} → {ip}'
    except socket.gaierror:
        return True, f'DNS resolution failed: {hostname}'
    return False, ''


def _is_subpath(path: Path, parent: Path) -> bool:
    """Check if path is under parent (safe, no startswith tricks)."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


# ── Main Entry Point (thin shim) ────────────────────────────

def execute_tool(name: str, args: dict) -> str:
    """Execute a tool — delegates to tool_registry."""
    audit_log('tool_exec', f'{name}: {json.dumps(args, ensure_ascii=False)[:200]}')

    # Try remote node dispatch first (if gateway has registered nodes)
    try:
        from .nodes import gateway
        if gateway._nodes:
            result = gateway.dispatch_auto(name, args)
            if result and 'error' not in result:
                return result.get('result', str(result))  # type: ignore[no-any-return]
    except Exception:
        pass  # Fall through to local execution

    from .tool_registry import execute_tool as _registry_execute
    return _registry_execute(name, args)


# ── Legacy Bridge (for tools_media.py) ──────────────────────

def _legacy_execute(name: str, args: dict) -> str:
    """Legacy tool execution — used by tools_media.py for not-yet-extracted tools."""
    return _execute_inner(name, args)


def _execute_inner(name: str, args: dict) -> str:
    """Inner dispatch — ONLY media tools that tools_media.py delegates back here."""
    try:
        if name == 'image_generate':
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
            log.info(f"[ART] Image generated: {fname} ({size_kb:.1f}KB)")
            return f'✅ Image generated: uploads/{fname} ({size_kb:.1f}KB)\nPrompt: {prompt}'

        elif name == 'image_analyze':
            image_path = args['image_path']
            question = args.get('question', 'Describe this image in detail.')
            import base64 as b64mod
            if image_path.startswith('http://') or image_path.startswith('https://'):
                image_url = image_path
                content_parts = [
                    {'type': 'image_url', 'image_url': {'url': image_url}},
                    {'type': 'text', 'text': question}
                ]
            else:
                img_path = Path(image_path)
                if not img_path.is_absolute():
                    img_path = WORKSPACE_DIR / img_path
                if not img_path.exists():
                    return f'❌ Image not found: {image_path}'
                ext = img_path.suffix.lower()
                mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp'}
                mime = mime_map.get(ext, 'image/png')
                img_b64 = b64mod.b64encode(img_path.read_bytes()).decode()
                content_parts = [
                    {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{img_b64}'}},
                    {'type': 'text', 'text': question}
                ]
            api_key = vault.get('openai_api_key')
            if api_key:
                resp = _http_post(
                    'https://api.openai.com/v1/chat/completions',
                    {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                    {'model': 'gpt-4o', 'messages': [{'role': 'user', 'content': content_parts}], 'max_tokens': 1000}
                )
                return resp['choices'][0]['message']['content']  # type: ignore[no-any-return]
            api_key = vault.get('anthropic_api_key')
            if api_key:
                img_source = content_parts[0]['image_url']['url']
                if img_source.startswith('data:'):
                    media_type = img_source.split(';')[0].split(':')[1]
                    data = img_source.split(',')[1]
                    img_block = {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': data}}
                else:
                    img_block = {'type': 'image', 'source': {'type': 'url', 'url': img_source}}
                resp = _http_post(
                    'https://api.anthropic.com/v1/messages',
                    {'x-api-key': api_key, 'Content-Type': 'application/json', 'anthropic-version': '2023-06-01'},
                    {'model': 'claude-sonnet-4-20250514', 'max_tokens': 1000,
                     'messages': [{'role': 'user', 'content': [img_block, {'type': 'text', 'text': question}]}]}
                )
                return resp['content'][0]['text']  # type: ignore[no-any-return]
            return '❌ No vision API key found (need OpenAI or Anthropic)'

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
            log.info(f"[AUDIO] TTS generated: {fname} ({size_kb:.1f}KB)")
            return f'✅ TTS generated: uploads/{fname} ({size_kb:.1f}KB)\nText: {text[:100]}'

        elif name == 'stt':
            api_key = vault.get('openai_api_key')
            if not api_key:
                return '❌ OpenAI API key not found'
            audio_path = args.get('audio_path', '')
            audio_b64 = args.get('audio_base64', '')
            lang = args.get('language', 'ko')
            if audio_path:
                fpath = Path(audio_path).expanduser()
                if not fpath.exists():
                    return f'❌ File not found: {audio_path}'
                audio_data = fpath.read_bytes()
                fname = fpath.name
            elif audio_b64:
                audio_data = base64.b64decode(audio_b64)
                fname = 'audio.webm'
            else:
                return '❌ Provide audio_path or audio_base64'
            boundary = secrets.token_hex(16)
            body = b''
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
            body += audio_data
            body += f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-1'.encode()
            body += f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\n{lang}'.encode()
            body += f'\r\n--{boundary}--\r\n'.encode()
            req = urllib.request.Request(
                'https://api.openai.com/v1/audio/transcriptions',
                data=body,
                headers={'Authorization': f'Bearer {api_key}',
                         'Content-Type': f'multipart/form-data; boundary={boundary}'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
            text = result.get('text', '')
            log.info(f"[MIC] STT transcribed: {len(text)} chars")
            return f'🎤 Transcription:\n{text}'

        elif name == 'screenshot':
            region = args.get('region', 'full')
            fname = f'screenshot_{int(time.time())}.png'
            fpath = WORKSPACE_DIR / 'uploads' / fname
            fpath.parent.mkdir(exist_ok=True)
            try:
                cmd = ['import', '-window', 'root', str(fpath)] if region == 'full' else ['import', '-crop', region, '-window', 'root', str(fpath)]
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

        elif name == 'tts_generate':
            return _handle_tts_generate(args)

        else:
            return f'❌ Unknown legacy tool: {name}'

    except PermissionError as e:
        return f'❌ Permission denied: {e}'
    except Exception as e:
        log.error(f"Tool error ({name}): {e}")
        return f'❌ Tool error: {str(e)[:200]}'


def _handle_tts_generate(args: dict) -> str:
    """TTS generation handler — Google TTS (free) or OpenAI TTS."""
    text = args.get('text', '')
    if not text:
        return '❌ text is required'
    provider = args.get('provider', 'google')
    language = args.get('language', 'ko-KR')
    output_path = args.get('output', '')

    if not output_path:
        fname = f"tts_{secrets.token_hex(4)}.mp3"
        output_dir = WORKSPACE_DIR / 'tts_output'
        output_dir.mkdir(exist_ok=True)
        output_path = str(output_dir / fname)

    import urllib.parse

    if provider == 'google':
        chunks = []
        while text:
            chunk = text[:200]
            text = text[200:]
            chunks.append(chunk)

        audio_data = b''
        for chunk in chunks:
            encoded = urllib.parse.quote(chunk)
            url = f'https://translate.google.com/translate_tts?ie=UTF-8&q={encoded}&tl={language}&client=tw-ob'
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://translate.google.com/',
            })
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    audio_data += resp.read()
            except Exception as e:
                return f'❌ Google TTS failed: {e}'

        Path(output_path).write_bytes(audio_data)
        return f'🔊 TTS generated: {output_path} ({len(audio_data)} bytes, {len(chunks)} chunks)'

    elif provider == 'openai':
        api_key = vault.get('openai_api_key') or ''
        if not api_key:
            return '❌ OpenAI API key not configured in vault'
        voice = args.get('voice', 'alloy')
        body = json.dumps({'model': 'tts-1', 'input': text[:4096], 'voice': voice}).encode()
        req = urllib.request.Request(
            'https://api.openai.com/v1/audio/speech',
            data=body,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            method='POST')
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio = resp.read()
            Path(output_path).write_bytes(audio)
            return f'🔊 TTS generated: {output_path} ({len(audio)} bytes, voice={voice})'
        except Exception as e:
            return f'❌ OpenAI TTS failed: {e}'

    return f'❌ Unknown TTS provider: {provider}'
