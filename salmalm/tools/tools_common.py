"""Shared helper functions for tool modules."""
import re
import threading
from pathlib import Path

from salmalm.constants import (EXEC_ALLOWLIST, EXEC_BLOCKLIST, EXEC_BLOCKLIST_PATTERNS,
                               EXEC_ELEVATED, PROTECTED_FILES, WORKSPACE_DIR)
from salmalm.crypto import log

_clipboard_lock = threading.Lock()


def _is_safe_command(cmd: str):
    """Check if command is safe to execute (allowlist + blocklist double defense)."""
    if not cmd.strip():
        return False, 'Empty command'
    for pattern in EXEC_BLOCKLIST_PATTERNS:
        if re.search(pattern, cmd):
            return False, f'Blocked pattern: {pattern}'
    stages = re.split(r'\s*(?:\|\||&&|;|\|)\s*', cmd)
    for stage in stages:
        words = stage.strip().split()
        if not words:
            continue
        first_word = words[0].split('/')[-1]
        if first_word in EXEC_BLOCKLIST:
            return False, f'Blocked command in pipeline: {first_word}'
        if first_word in EXEC_ELEVATED:
            log.warning(f"[WARN] Elevated exec: {first_word} (can run arbitrary code)")
        elif first_word not in EXEC_ALLOWLIST:
            return False, f'Command not in allowlist: {first_word}'
    if re.search(r'`.*`|\$\(.*\)|<\(|>\(', cmd):
        inner = re.findall(r'`([^`]+)`|\$\(([^)]+)\)', cmd)
        for groups in inner:
            inner_cmd = groups[0] or groups[1]
            inner_first = inner_cmd.strip().split()[0].split('/')[-1] if inner_cmd.strip() else ''
            if inner_first and inner_first not in EXEC_ALLOWLIST:
                return False, f'Blocked subshell command: {inner_first}'
    return True, ''


def _resolve_path(path: str, writing: bool = False) -> Path:
    """Resolve path, preventing traversal outside allowed directories."""
    p = Path(path)
    if not p.is_absolute():
        p = WORKSPACE_DIR / p
    p = p.resolve()
    if writing:
        try:
            p.relative_to(WORKSPACE_DIR.resolve())
        except ValueError:
            raise PermissionError(f'Write denied (outside workspace): {p}')
    else:
        allowed = [WORKSPACE_DIR.resolve(), Path.home().resolve()]
        if not any(_is_subpath(p, a) for a in allowed):
            raise PermissionError(f'Access denied: {p}')
    if writing and p.name in PROTECTED_FILES:
        raise PermissionError(f'Protected file: {p.name}')
    return p


def _is_subpath(path: Path, parent: Path) -> bool:
    """Check if path is under parent."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_private_url(url: str):
    """Check if URL resolves to a private/internal IP."""
    import ipaddress
    import socket
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
                return True, f'Internal IP blocked: {hostname} -> {ip}'
    except socket.gaierror:
        return True, f'DNS resolution failed: {hostname}'
    return False, ''
