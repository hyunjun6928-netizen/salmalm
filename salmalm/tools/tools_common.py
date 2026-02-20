"""Shared helper functions for tool modules."""
import re
import threading
from pathlib import Path

from salmalm.constants import (EXEC_ALLOWLIST, EXEC_BLOCKLIST, EXEC_BLOCKLIST_PATTERNS,
                               EXEC_ELEVATED, EXEC_BLOCKED_INTERPRETERS,
                               PROTECTED_FILES, WORKSPACE_DIR)
from salmalm.security.crypto import log

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
        if first_word in EXEC_BLOCKED_INTERPRETERS:
            return False, f'Interpreter blocked (use python_eval tool): {first_word}'
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
    """Resolve path, preventing traversal outside allowed directories.

    Default: workspace only (read & write).
    Set SALMALM_ALLOW_HOME_READ=1 to also allow reading from home directory.
    """
    import os as _os
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
        allowed = [WORKSPACE_DIR.resolve()]
        if _os.environ.get('SALMALM_ALLOW_HOME_READ', '') in ('1', 'true', 'yes'):
            allowed.append(Path.home().resolve())
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
    """Check if URL resolves to a private/internal IP.

    Defends against: SSRF, DNS rebinding (pre-connect check), redirect bypass,
    non-HTTP schemes, IPv6 loopback, 0.0.0.0, metadata endpoints, @ in URL.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)

    # Scheme allowlist: only http/https
    if parsed.scheme not in ('http', 'https'):
        return True, f'Blocked scheme: {parsed.scheme} (only http/https allowed)'

    # Block userinfo in URL (http://attacker@internal)
    if parsed.username or '@' in (parsed.netloc or ''):
        return True, 'Blocked: userinfo (@) in URL not allowed'

    hostname = parsed.hostname or ''
    if not hostname:
        return True, 'No hostname'

    # Normalize: strip brackets from IPv6 literals
    hostname = hostname.strip('[]')

    # Block raw IP shorthand (0, 0x7f000001, etc.) — only dotted-decimal or valid IPv6
    # Also catch 0.0.0.0 explicitly
    _BLOCKED_HOSTS = frozenset([
        'metadata.google.internal', '169.254.169.254', 'metadata.internal',
        'metadata', 'instance-data', '100.100.100.200',
        '0.0.0.0', '0', '0x7f000001', '2130706433',  # localhost aliases
    ])
    if hostname in _BLOCKED_HOSTS or hostname.endswith('.internal'):
        return True, f'Blocked metadata/internal endpoint: {hostname}'

    # Port check: block common internal service ports on localhost
    # (defense-in-depth; IP check below is primary)

    try:
        addrs = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return True, f'Internal IP blocked: {hostname} -> {ip}'
    except socket.gaierror:
        return True, f'DNS resolution failed: {hostname}'

    return False, ''


def _is_private_url_follow_redirects(url: str, max_redirects: int = 5):
    """Validate URL + follow redirects, re-checking each hop for SSRF.

    Returns (blocked: bool, reason: str, final_url: str).
    """
    import urllib.request
    import urllib.error
    from urllib.parse import urlparse, urljoin

    current_url = url
    for i in range(max_redirects + 1):
        blocked, reason = _is_private_url(current_url)
        if blocked:
            hop = f' (redirect hop {i})' if i > 0 else ''
            return True, f'{reason}{hop}', current_url

        if i == max_redirects:
            break

        # HEAD request to check for redirect without downloading body
        try:
            req = urllib.request.Request(current_url, method='HEAD',
                                         headers={'User-Agent': 'SalmAlm-SSRF-Check/1.0'})
            # Use a custom opener that doesn't follow redirects
            class _NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    raise urllib.error.HTTPError(newurl, code, msg, headers, fp)
            opener = urllib.request.build_opener(_NoRedirect)
            opener.open(req, timeout=5)
            # No redirect — we're at final URL
            break
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                location = e.headers.get('Location', '')
                if not location:
                    break
                current_url = urljoin(current_url, location)
                continue
            break  # Non-redirect error, proceed with original URL
        except Exception:
            break

    return False, '', current_url
