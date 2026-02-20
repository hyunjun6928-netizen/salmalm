"""Utility tools: hash_text, regex_test, json_query, clipboard, qr_code, translate."""
import json
import re
import hashlib
import secrets
import string
from datetime import datetime
from pathlib import Path
from salmalm.tools.tool_registry import register
from salmalm.tools.tools_common import _resolve_path, _clipboard_lock
from salmalm.constants import WORKSPACE_DIR, KST

import urllib.request
import urllib.parse


@register('hash_text')
def handle_hash_text(args: dict) -> str:
    import uuid as _uuid_mod
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
        return f'🔐 {algo.upper()}: {h}'
    elif action == 'password':
        length = max(8, min(args.get('length', 16), 128))
        charset = string.ascii_letters + string.digits + '!@#$%^&*'
        pw = ''.join(secrets.choice(charset) for _ in range(length))
        return f'🔑 Password ({length}chars): {pw}'
    elif action == 'uuid':
        return f'🆔 UUID: {_uuid_mod.uuid4()}'
    elif action == 'token':
        length = min(args.get('length', 32), 256)
        token = secrets.token_hex((length + 1) // 2)[:length]
        return f'🎫 Token ({len(token)}chars): {token}'
    return f'❌ Unknown action: {action}'


@register('regex_test')
def handle_regex_test(args: dict) -> str:
    pattern = args.get('pattern', '')
    text = args.get('text', '')
    action = args.get('action', 'find')
    flags_str = args.get('flags', '')

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
                lines.append(f'  ... and {len(matches) - 50} more')
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

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        try:
            future = pool.submit(_run_regex)
            return future.result(timeout=5)
        except concurrent.futures.TimeoutError:
            return '❌ Regex execution timeout (5s)'


@register('json_query')
def handle_json_query(args: dict) -> str:
    import subprocess
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
        data = json.loads(data_str)
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


@register('clipboard')
def handle_clipboard(args: dict) -> str:
    action = args.get('action', 'list')
    slot = args.get('slot', 'default')

    if len(slot) > 100:
        return '❌ Slot name must be under 100 characters'

    clip_file = WORKSPACE_DIR / '.clipboard.json'

    with _clipboard_lock:
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
                'size': len(content[:50000])
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


@register('translate')
def handle_translate(args: dict) -> str:
    text = args.get('text', '')
    target = args.get('target', '')
    source = args.get('source', 'auto')
    if not text or not target:
        return '❌ text and target language are required'

    encoded = urllib.parse.quote(text[:5000])
    url = (f'https://translate.googleapis.com/translate_a/single'
           f'?client=gtx&sl={source}&tl={target}&dt=t&q={encoded}')

    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return f'❌ Translation failed: {e}'

    try:
        translated_parts = []
        for segment in data[0]:
            if segment[0]:
                translated_parts.append(segment[0])
        translated = ''.join(translated_parts)
        detected = data[2] if len(data) > 2 else source
        lang_names = {
            'ko': '한국어', 'en': 'English', 'ja': '日本語', 'zh-CN': '中文',
            'es': 'Español', 'fr': 'Français', 'de': 'Deutsch', 'ru': 'Русский',
            'pt': 'Português', 'it': 'Italiano', 'vi': 'Tiếng Việt', 'th': 'ไทย',
            'ar': 'العربية', 'hi': 'हिन्दी',
        }
        src_name = lang_names.get(str(detected), str(detected))
        tgt_name = lang_names.get(target, target)
        return f'🌐 **{src_name} → {tgt_name}:**\n{translated}'
    except (IndexError, TypeError):
        return f'❌ Translation parse error: {str(data)[:200]}'


@register('qr_code')
def handle_qr_code(args: dict) -> str:
    data = args.get('data', '')
    if not data:
        return '❌ data is required'
    fmt = args.get('format', 'svg')
    size = args.get('size', 10)
    output = args.get('output', '')

    if not output:
        fname = f"qr_{secrets.token_hex(4)}.{'svg' if fmt == 'svg' else 'txt'}"
        output_dir = WORKSPACE_DIR / 'qr_output'
        output_dir.mkdir(exist_ok=True)
        output = str(output_dir / fname)

    encoded = urllib.parse.quote(data)
    qr_url = f'https://chart.googleapis.com/chart?cht=qr&chs={size * 25}x{size * 25}&chl={encoded}&choe=UTF-8'

    if fmt == 'text':
        try:
            api_url = f'https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={encoded}&format=svg'
            req = urllib.request.Request(api_url, headers={'User-Agent': 'SalmAlm/1.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                svg_data = resp.read().decode('utf-8')
            Path(output).write_text(f'QR Code for: {data}\nGenerate at: {qr_url}\n\n(SVG saved)', encoding='utf-8')
            svg_path = output.replace('.txt', '.svg')
            Path(svg_path).write_text(svg_data, encoding='utf-8')
            return f'📱 QR code generated:\n  Text: {output}\n  SVG: {svg_path}\n  Data: {data[:50]}'
        except Exception as e:
            return f'❌ QR generation failed: {e}'
    else:
        try:
            api_url = f'https://api.qrserver.com/v1/create-qr-code/?size={size * 25}x{size * 25}&data={encoded}&format=svg'
            req = urllib.request.Request(api_url, headers={'User-Agent': 'SalmAlm/1.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                svg_data = resp.read().decode('utf-8')
            Path(output).write_text(svg_data, encoding='utf-8')
            return f'📱 QR code saved: {output} ({len(svg_data)} bytes)\n  Data: {data[:50]}'
        except Exception as e:
            return f'❌ QR generation failed: {e}'
