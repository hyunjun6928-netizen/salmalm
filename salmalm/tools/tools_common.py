"""Shared helper functions for tool modules."""

import os
import re
import shlex
import threading
from pathlib import Path

from salmalm.constants import (
    EXEC_ALLOWLIST,
    EXEC_BLOCKLIST,
    EXEC_BLOCKLIST_PATTERNS,
    EXEC_ELEVATED,
    EXEC_BLOCKED_INTERPRETERS,
    EXEC_ARG_BLOCKLIST,
    EXEC_INLINE_CODE_PATTERNS,
    PROTECTED_FILES,
    WORKSPACE_DIR,
)
from salmalm.security.crypto import log

_clipboard_lock = threading.Lock()


def _is_safe_command(cmd: str) -> tuple:
    """Check if command is safe to execute (allowlist + blocklist double defense)."""
    if not cmd.strip():
        return False, "Empty command"
    # Shell operator blocking (pipe, redirect, chain) — requires SALMALM_ALLOW_SHELL=1
    if not os.environ.get("SALMALM_ALLOW_SHELL"):
        if re.search(r"[|;&]|>>?|<<", cmd):
            return False, "Shell operators (|, >, >>, ;, &&, ||) blocked. Set SALMALM_ALLOW_SHELL=1 to enable."
    for pattern in EXEC_BLOCKLIST_PATTERNS:
        if re.search(pattern, cmd):
            return False, f"Blocked pattern: {pattern}"
    # Inline code execution patterns (awk system(), getline, etc.)
    for pattern in EXEC_INLINE_CODE_PATTERNS:
        if re.search(pattern, cmd):
            return False, "Blocked inline code execution pattern"
    stages = re.split(r"\s*(?:\|\||&&|;|\|)\s*", cmd)
    for stage in stages:
        try:
            words = shlex.split(stage.strip())
        except ValueError:
            # Malformed quoting — reject
            return False, "Malformed quoting in command"
        if not words:
            continue
        first_word = os.path.basename(words[0])
        if first_word in EXEC_BLOCKLIST:
            return False, f"Blocked command in pipeline: {first_word}"
        if first_word in EXEC_BLOCKED_INTERPRETERS:
            return False, f"Interpreter blocked (use python_eval tool): {first_word}"
        if first_word in EXEC_ELEVATED:
            # On external bind, elevated commands are blocked by default
            _bind = os.environ.get("SALMALM_BIND", "127.0.0.1")
            if _bind not in ("127.0.0.1", "::1", "localhost"):
                if not os.environ.get("SALMALM_ALLOW_ELEVATED"):
                    return False, f"Elevated command '{first_word}' blocked on external bind (set SALMALM_ALLOW_ELEVATED=1 to override)"
            log.warning(f"[WARN] Elevated exec: {first_word} (can run arbitrary code)")
        elif first_word not in EXEC_ALLOWLIST:
            return False, f"Command not in allowlist: {first_word}"
        # Per-command arg/flag blocklist
        blocked_args = EXEC_ARG_BLOCKLIST.get(first_word)
        if blocked_args:
            for w in words[1:]:
                w_base = w.split("=")[0]
                if w in blocked_args or w_base in blocked_args:
                    return False, f"Blocked argument for {first_word}: {w}"
                # Match flags with attached values (e.g., -I{} matches -I)
                for ba in blocked_args:
                    if ba.startswith("-") and w.startswith(ba) and len(w) > len(ba):
                        return False, f"Blocked argument for {first_word}: {w}"
    # ── Path safety: block access to sensitive paths outside workspace ──
    _SENSITIVE_PATHS = (
        "/etc/shadow", "/etc/passwd", "/etc/sudoers", "/proc/", "/sys/",
        ".ssh/", ".gnupg/", ".aws/", ".kube/", ".docker/",
        ".pypirc", ".netrc", ".env",
    )
    _ARCHIVE_CMDS = {"tar", "unzip", "zip", "gzip", "gunzip"}
    for stage in stages:
        try:
            words = shlex.split(stage.strip())
        except ValueError:
            pass
        else:
            cmd_name = os.path.basename(words[0]) if words else ""
            for arg in words[1:]:
                if arg.startswith("-"):
                    continue
                # Block sensitive system/user files
                try:
                    expanded = os.path.expanduser(arg)
                    resolved = str(Path(expanded).resolve())
                    home = str(Path.home())
                    for sp in _SENSITIVE_PATHS:
                        if sp.startswith("/"):
                            # Absolute system paths
                            if resolved.startswith(sp) or resolved == sp.rstrip("/"):
                                return False, f"Access to sensitive path blocked: {arg}"
                        else:
                            # Relative to home (e.g. .ssh/, .pypirc)
                            sensitive_full = os.path.join(home, sp)
                            if resolved.startswith(sensitive_full) or resolved == sensitive_full.rstrip("/"):
                                return False, f"Access to sensitive path blocked: {arg}"
                except (OSError, ValueError):
                    pass
                # Archive commands: block path traversal (../)
                if cmd_name in _ARCHIVE_CMDS and ".." in arg:
                    return False, f"Path traversal in archive argument blocked: {arg}"

    if re.search(r"`.*`|\$\(.*\)|<\(|>\(", cmd):
        inner = re.findall(r"`([^`]+)`|\$\(([^)]+)\)", cmd)
        for groups in inner:
            inner_cmd = groups[0] or groups[1]
            inner_first = inner_cmd.strip().split()[0].split("/")[-1] if inner_cmd.strip() else ""
            if inner_first and inner_first not in EXEC_ALLOWLIST:
                return False, f"Blocked subshell command: {inner_first}"
    return True, ""


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
            raise PermissionError(f"Write denied (outside workspace): {p}")
    else:
        allowed = [WORKSPACE_DIR.resolve()]
        if _os.environ.get("SALMALM_ALLOW_HOME_READ", "") in ("1", "true", "yes"):
            allowed.append(Path.home().resolve())
        if not any(_is_subpath(p, a) for a in allowed):
            raise PermissionError(f"Access denied: {p}")
    if writing and p.name in PROTECTED_FILES:
        raise PermissionError(f"Protected file: {p.name}")
    return p


def _is_subpath(path: Path, parent: Path) -> bool:
    """Check if path is under parent."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_private_url(url: str) -> tuple:
    """Check if URL resolves to a private/internal IP.

    Defends against: SSRF, DNS rebinding (pre-connect check), redirect bypass,
    non-HTTP schemes, IPv6 loopback, 0.0.0.0, metadata endpoints, @ in URL.
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)

    # Scheme allowlist: only http/https
    if parsed.scheme not in ("http", "https"):
        return True, f"Blocked scheme: {parsed.scheme} (only http/https allowed)"

    # Block userinfo in URL (http://attacker@internal)
    if parsed.username or "@" in (parsed.netloc or ""):
        return True, "Blocked: userinfo (@) in URL not allowed"

    hostname = parsed.hostname or ""
    if not hostname:
        return True, "No hostname"

    # Normalize: strip brackets from IPv6 literals
    hostname = hostname.strip("[]")

    # Block raw IP shorthand (0, 0x7f000001, etc.) — only dotted-decimal or valid IPv6
    # Also catch 0.0.0.0 explicitly
    _BLOCKED_HOSTS = frozenset(
        [
            "metadata.google.internal",
            "169.254.169.254",
            "metadata.internal",
            "metadata",
            "instance-data",
            "100.100.100.200",
            "0.0.0.0",
            "0",
            "0x7f000001",
            "2130706433",  # localhost aliases
        ]
    )
    if hostname in _BLOCKED_HOSTS or hostname.endswith(".internal"):
        return True, f"Blocked metadata/internal endpoint: {hostname}"

    # Port check: block common internal service ports on localhost
    # (defense-in-depth; IP check below is primary)

    try:
        addrs = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return True, f"Internal IP blocked: {hostname} -> {ip}"
    except socket.gaierror:
        return True, f"DNS resolution failed: {hostname}"

    return False, ""


def _is_private_url_follow_redirects(url: str, max_redirects: int = 5) -> tuple:
    """Validate URL + follow redirects, re-checking each hop for SSRF.

    Returns (blocked: bool, reason: str, final_url: str).
    """
    import urllib.request
    import urllib.error
    from urllib.parse import urljoin

    current_url = url
    for i in range(max_redirects + 1):
        blocked, reason = _is_private_url(current_url)
        if blocked:
            hop = f" (redirect hop {i})" if i > 0 else ""
            return True, f"{reason}{hop}", current_url

        if i == max_redirects:
            break

        # HEAD request to check for redirect without downloading body
        try:
            req = urllib.request.Request(current_url, method="HEAD", headers={"User-Agent": "SalmAlm-SSRF-Check/1.0"})
            # Use a custom opener that doesn't follow redirects

            class _NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers: dict, newurl) -> None:
                    """Redirect request."""
                    raise urllib.error.HTTPError(newurl, code, msg, headers, fp)

            opener = urllib.request.build_opener(_NoRedirect)
            opener.open(req, timeout=5)
            # No redirect — we're at final URL
            break
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                location = e.headers.get("Location", "")
                if not location:
                    break
                current_url = urljoin(current_url, location)
                continue
            break  # Non-redirect error, proceed with original URL
        except Exception as e:  # noqa: broad-except
            break

    return False, "", current_url


def _make_pinned_opener(resolved_ip: str, hostname: str):
    """Create a urllib opener that pins DNS to a pre-resolved IP.

    Prevents DNS rebinding: the actual TCP connection uses the IP we already
    validated, not a fresh DNS lookup that could return a different (internal) IP.
    """
    import http.client
    import urllib.request
    import ssl  # noqa: F401

    class _PinnedHTTPConnection(http.client.HTTPConnection):
        def connect(self) -> None:
            """Connect."""
            self.host = resolved_ip
            super().connect()
            self.host = hostname  # Restore for Host header

    class _PinnedHTTPSConnection(http.client.HTTPSConnection):
        def connect(self) -> None:
            # Connect TCP to pinned IP, but use original hostname for SNI + cert check
            """Connect."""
            import socket as _sock
            self.sock = _sock.create_connection((resolved_ip, self.port or 443), self.timeout)
            ctx = ssl.create_default_context()
            self.sock = ctx.wrap_socket(self.sock, server_hostname=hostname)
            self.host = hostname

    class _PinnedHTTPHandler(urllib.request.HTTPHandler):
        def http_open(self, req):
            """Http open."""
            return self.do_open(_PinnedHTTPConnection, req)

    class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            """Https open."""
            return self.do_open(_PinnedHTTPSConnection, req)

    return urllib.request.build_opener(_PinnedHTTPHandler, _PinnedHTTPSHandler)


def _resolve_and_pin(url: str):
    """Resolve URL hostname, validate IP, return (opener, final_url) or raise.

    Combines SSRF check + DNS pinning in one step.
    """
    import socket
    import ipaddress
    from urllib.parse import urlparse

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").strip("[]")
    if not hostname:
        raise ValueError("No hostname in URL")

    # Resolve
    addrs = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    if not addrs:
        raise ValueError(f"DNS resolution failed: {hostname}")

    # Pick first valid non-private IP
    chosen_ip = None
    for family, _, _, _, sockaddr in addrs:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            continue
        chosen_ip = sockaddr[0]
        break

    if not chosen_ip:
        raise ValueError(f"All resolved IPs are internal: {hostname}")

    opener = _make_pinned_opener(chosen_ip, hostname)
    return opener
