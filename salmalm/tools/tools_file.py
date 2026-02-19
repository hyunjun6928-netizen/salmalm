"""File tools: read_file, write_file, edit_file, diff_files."""
import difflib
from salmalm.tool_registry import register
from salmalm.tools_common import _resolve_path


@register('read_file')
def handle_read_file(args: dict) -> str:
    p = _resolve_path(args['path'])
    if not p.exists():
        return f'File not found: {p}'
    # Symlink loop detection
    try:
        p.resolve(strict=True)
    except (OSError, RuntimeError):
        return f'❌ Cannot resolve path (symlink loop?): {p}'
    # Size limit: 5MB max for reading
    try:
        size = p.stat().st_size
        if size > 5 * 1024 * 1024:
            return f'❌ File too large ({size // 1024}KB). Max 5MB for read_file.'
    except OSError as e:
        return f'❌ Cannot stat file: {e}'
    # Read with encoding fallback
    try:
        text = p.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        text = p.read_text(encoding='latin-1')
    except OSError as e:
        return f'❌ Read error: {e}'
    lines = text.splitlines()
    offset = args.get('offset', 1) - 1
    limit = args.get('limit', len(lines))
    selected = lines[offset:offset + limit]
    return '\n'.join(selected)[:50000]


@register('write_file')
def handle_write_file(args: dict) -> str:
    p = _resolve_path(args['path'], writing=True)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args['content'], encoding='utf-8')
    except OSError as e:
        if 'No space left' in str(e) or e.errno == 28:
            return f'❌ Disk full — cannot write: {e}'
        return f'❌ Write error: {e}'
    return f'{p} ({len(args["content"])} chars)'


@register('edit_file')
def handle_edit_file(args: dict) -> str:
    p = _resolve_path(args['path'], writing=True)
    text = p.read_text(encoding='utf-8')
    if args['old_text'] not in text:
        return 'Text not found'
    text = text.replace(args['old_text'], args['new_text'], 1)
    p.write_text(text, encoding='utf-8')
    return f'File edited: {p}'


@register('diff_files')
def handle_diff_files(args: dict) -> str:
    f1 = args.get('file1', '')
    f2 = args.get('file2', '')
    ctx = args.get('context_lines', 3)
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
        return 'Files/texts are identical.'
    return '\n'.join(diff[:300])
