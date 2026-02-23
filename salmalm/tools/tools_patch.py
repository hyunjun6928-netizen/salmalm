"""apply_patch tool — multi-file patch application.

멀티 파일 패치 적용 도구.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple


# Safety: disallowed path components
_BLOCKED_COMPONENTS = {"..", "~"}
_BINARY_EXTENSIONS = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".o",
    ".a",
    ".pyc",
    ".pyo",
    ".class",
    ".jar",
    ".zip",
    ".gz",
    ".tar",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".pdf",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
}


def _is_safe_path(path: str, base_dir: str = None) -> Tuple[bool, str]:
    """Validate path is safe (no traversal, no binary)."""
    parts = Path(path).parts
    for part in parts:
        if part in _BLOCKED_COMPONENTS:
            return False, f"Path traversal blocked: {part}"
    if Path(path).suffix.lower() in _BINARY_EXTENSIONS:
        return False, f"Binary file rejected: {path}"
    if base_dir:
        resolved = (Path(base_dir) / path).resolve()
        if not str(resolved).startswith(str(Path(base_dir).resolve())):
            return False, f"Path escape blocked: {path}"
    return True, ""


def _find_context_match(lines: List[str], old_lines: List[str], start: int = 0) -> int:
    """Find where old_lines match in lines, starting from start. Returns index or -1."""
    if not old_lines:
        return start
    for i in range(start, len(lines) - len(old_lines) + 1):
        if all(lines[i + j].rstrip() == old_lines[j].rstrip() for j in range(len(old_lines))):
            return i
    return -1


def _skip_to_next_op(lines: list, i: int) -> int:
    """Skip lines until the next *** operation marker."""
    while i < len(lines) and not lines[i].strip().startswith("***"):
        i += 1
    return i


def _apply_add_file(filepath: str, lines: list, i: int, base_dir: str, results: list) -> int:
    """Apply *** Add File operation. Returns updated line index."""
    safe, reason = _is_safe_path(filepath, base_dir)
    if not safe:
        results.append(f"❌ {filepath}: {reason}")
        return _skip_to_next_op(lines, i)
    content_lines = []
    while i < len(lines) and not lines[i].strip().startswith("***"):
        if lines[i].startswith("+"):
            content_lines.append(lines[i][1:])
        i += 1
    full_path = Path(base_dir) / filepath
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text("\n".join(content_lines) + ("\n" if content_lines else ""), encoding="utf-8")
    results.append(f"✅ Added {filepath} ({len(content_lines)} lines)")
    return i


def _apply_update_file(filepath: str, lines: list, i: int, base_dir: str, results: list) -> int:
    """Apply *** Update File operation. Returns updated line index."""
    safe, reason = _is_safe_path(filepath, base_dir)
    if not safe:
        results.append(f"❌ {filepath}: {reason}")
        return _skip_to_next_op(lines, i)
    full_path = Path(base_dir) / filepath
    if not full_path.exists():
        results.append(f"❌ {filepath}: file not found")
        return _skip_to_next_op(lines, i)
    file_lines = full_path.read_text(encoding="utf-8").split("\n")
    hunks_applied = 0
    pos = 0
    while i < len(lines) and not lines[i].strip().startswith("***"):
        if lines[i].strip() == "@@":
            i += 1
            old_h: List[str] = []
            new_h: List[str] = []
            while i < len(lines) and not lines[i].strip().startswith("***") and lines[i].strip() != "@@":
                hl = lines[i]
                if hl.startswith("-"):
                    old_h.append(hl[1:])
                elif hl.startswith("+"):
                    new_h.append(hl[1:])
                elif hl.startswith(" "):
                    old_h.append(hl[1:])
                    new_h.append(hl[1:])
                else:
                    old_h.append(hl)
                    new_h.append(hl)
                i += 1
            match_idx = _find_context_match(file_lines, old_h, pos)
            if match_idx >= 0:
                file_lines[match_idx : match_idx + len(old_h)] = new_h
                pos = match_idx + len(new_h)
                hunks_applied += 1
            else:
                results.append(f"⚠️ {filepath}: hunk failed to match")
        else:
            i += 1
    full_path.write_text("\n".join(file_lines), encoding="utf-8")
    results.append(f"✅ Updated {filepath} ({hunks_applied} hunks)")
    return i


def _apply_delete_file(filepath: str, base_dir: str, results: list) -> None:
    """Apply *** Delete File operation."""
    safe, reason = _is_safe_path(filepath, base_dir)
    if not safe:
        results.append(f"❌ {filepath}: {reason}")
        return
    full_path = Path(base_dir) / filepath
    if full_path.exists():
        full_path.unlink()
        results.append(f"✅ Deleted {filepath}")
    else:
        results.append(f"⚠️ {filepath}: already absent")


def apply_patch(patch_text: str, base_dir: str = ".") -> str:
    """Apply a multi-file patch.

    Format:
    *** Begin Patch
    *** Add File: path/to/file.txt
    +line 1
    +line 2
    *** Update File: src/app.py
    @@
    -old line
    +new line
     context line
    *** Delete File: obsolete.txt
    *** End Patch

    Returns summary of changes.
    """
    lines = patch_text.split("\n")
    results: List[str] = []
    i = 0

    # Find start
    while i < len(lines) and not lines[i].strip().startswith("*** Begin Patch"):
        i += 1
    if i >= len(lines):
        return '❌ No "*** Begin Patch" found'
    i += 1

    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("*** End Patch"):
            break

        if line.startswith("*** Add File:"):
            filepath = line[len("*** Add File:") :].strip()
            i = _apply_add_file(filepath, lines, i + 1, base_dir, results)

        elif line.startswith("*** Update File:"):
            filepath = line[len("*** Update File:") :].strip()
            i = _apply_update_file(filepath, lines, i + 1, base_dir, results)

        elif line.startswith("*** Delete File:"):
            filepath = line[len("*** Delete File:") :].strip()
            _apply_delete_file(filepath, base_dir, results)
            i += 1
        else:
            i += 1

    if not results:
        return "⚠️ No operations found in patch"
    return "\n".join(results)
