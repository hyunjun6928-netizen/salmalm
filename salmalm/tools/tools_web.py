"""Web tools: web_search, web_fetch, http_request."""

import json
import os
import re
import urllib.request
import urllib.parse
import urllib.error
from salmalm.tools.tool_registry import register
from salmalm.tools.tools_common import _is_private_url_follow_redirects
from salmalm.constants import VERSION
from salmalm.security.crypto import vault
from salmalm.core.llm import _http_get


@register("web_search")
def handle_web_search(args: dict) -> str:
    """Handle web search."""
    api_key = vault.get("brave_api_key")
    if not api_key:
        return "Brave Search API key not found"
    query = urllib.parse.quote(args["query"])
    count = min(args.get("count", 5), 10)
    resp = _http_get(
        f"https://api.search.brave.com/res/v1/web/search?q={query}&count={count}",
        {"Accept": "application/json", "X-Subscription-Token": api_key},
    )
    results = []
    for r in resp.get("web", {}).get("results", [])[:count]:
        results.append(f"**{r['title']}**\n{r['url']}\n{r.get('description', '')}\n")
    return "\n".join(results) or "No results"


@register("web_fetch")
def handle_web_fetch(args: dict) -> str:
    """Handle web fetch."""
    url = args["url"]
    max_chars = args.get("max_chars", 10000)
    blocked, reason, final_url = _is_private_url_follow_redirects(url)
    if blocked:
        return f"{reason}"
    req = urllib.request.Request(final_url, headers={"User-Agent": "Mozilla/5.0 (SalmAlm/0.1)"})
    # DNS pinning: connect to the IP we already validated (anti-rebinding)
    try:
        from salmalm.tools.tools_common import _resolve_and_pin
        opener = _resolve_and_pin(final_url)
    except ValueError as e:
        return f"SSRF blocked: {e}"
    with opener.open(req, timeout=15) as resp:
        # Limit download to 2MB to prevent memory explosion
        raw = resp.read(2 * 1024 * 1024).decode("utf-8", errors="replace")
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        def __init__(self) -> None:
            """Init  ."""
            super().__init__()
            self._parts: list = []
            self._skip = False
            self._skip_tags = {"script", "style", "noscript", "svg"}

        def handle_starttag(self, tag, attrs) -> None:
            """Handle starttag."""
            if tag.lower() in self._skip_tags:
                self._skip = True
            elif tag.lower() in ("br", "p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"):
                self._parts.append("\n")

        def handle_endtag(self, tag) -> None:
            """Handle endtag."""
            if tag.lower() in self._skip_tags:
                self._skip = False

        def handle_data(self, data) -> None:
            """Handle data."""
            if not self._skip:
                self._parts.append(data)

        def get_text(self) -> str:
            """Get text."""
            return re.sub(r"\n{3,}", "\n\n", "".join(self._parts)).strip()

    extractor = _TextExtractor()
    extractor.feed(raw)
    return extractor.get_text()[:max_chars]


@register("http_request")
def handle_http_request(args: dict) -> str:
    """Handle http request."""
    method = args.get("method", "GET").upper()
    url = args.get("url", "")
    headers = args.get("headers", {})
    body_str = args.get("body", "")
    timeout_sec = min(args.get("timeout", 15), 60)
    if not url:
        return "URL is required"
    blocked, reason, final_url = _is_private_url_follow_redirects(url)
    if blocked:
        return f"{reason}"
    url = final_url  # Use redirect-validated URL
    # Header security: allowlist mode (default) or blocklist mode (SALMALM_HEADER_PERMISSIVE=1)
    _HEADER_ALLOWLIST = frozenset(
        {
            "accept",
            "accept-language",
            "accept-encoding",
            "authorization",
            "content-type",
            "content-length",
            "cookie",
            "user-agent",
            "cache-control",
            "if-none-match",
            "if-modified-since",
            "range",
            "referer",
            "origin",
            "x-requested-with",
            "x-api-key",
            "x-csrf-token",
        }
    )
    _HEADER_BLOCKLIST = frozenset(
        {
            "host",
            "transfer-encoding",
            "te",
            "proxy-authorization",
            "proxy-connection",
            "upgrade",
            "connection",
            "x-forwarded-for",
            "x-real-ip",
            "forwarded",
            "x-forwarded-host",
            "x-forwarded-proto",
        }
    )
    _permissive = os.environ.get("SALMALM_HEADER_PERMISSIVE", "") == "1"
    _extra_blocked = os.environ.get("SALMALM_BLOCKED_HEADERS", "")
    if _extra_blocked:
        _HEADER_BLOCKLIST = _HEADER_BLOCKLIST | frozenset(
            h.strip().lower() for h in _extra_blocked.split(",") if h.strip()
        )
    for h in list(headers.keys()):
        hl = h.lower()
        if _permissive:
            # Blocklist mode: only reject explicitly dangerous headers
            if hl in _HEADER_BLOCKLIST:
                return f"❌ Blocked request header: {h}"
        else:
            # Allowlist mode (default): reject unknown headers
            if hl not in _HEADER_ALLOWLIST:
                return f"❌ Header not in allowlist: {h} (set SALMALM_HEADER_PERMISSIVE=1 to use blocklist mode)"
    headers.setdefault("User-Agent", f"SalmAlm/{VERSION}")
    data = body_str.encode("utf-8") if body_str else None
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        _MAX_RESP_BYTES = 2 * 1024 * 1024  # 2 MB guard
        # DNS pinning (anti-rebinding)
        try:
            from salmalm.tools.tools_common import _resolve_and_pin
            _opener = _resolve_and_pin(url)
        except ValueError as _ve:
            return f"SSRF blocked: {_ve}"
        with _opener.open(req, timeout=timeout_sec) as resp:
            status = resp.status
            resp_headers = dict(resp.headers)
            raw = resp.read(_MAX_RESP_BYTES + 1)
            truncated = len(raw) > _MAX_RESP_BYTES
            if truncated:
                raw = raw[:_MAX_RESP_BYTES]
        try:
            body_json = json.loads(raw)
            body_out = json.dumps(body_json, ensure_ascii=False, indent=2)[:8000]
        except (json.JSONDecodeError, UnicodeDecodeError):
            body_out = raw.decode("utf-8", errors="replace")[:8000]
        header_str = "\n".join(f"  {k}: {v}" for k, v in list(resp_headers.items())[:10])
        trunc_note = " [truncated at 2MB]" if truncated else ""
        return f"HTTP {status}{trunc_note}\nHeaders:\n{header_str}\n\nBody:\n{body_out}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:3000]
        return f"HTTP {e.code} {e.reason}\n{body}"
    except Exception as e:
        return f"Request error: {e}"
