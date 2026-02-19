"""Web tools: web_search, web_fetch, http_request."""
import json, re, urllib.request, urllib.parse, urllib.error
from .tool_registry import register
from .tools_common import _is_private_url
from .constants import VERSION
from .crypto import vault
from .llm import _http_get


@register('web_search')
def handle_web_search(args: dict) -> str:
    api_key = vault.get('brave_api_key')
    if not api_key:
        return 'Brave Search API key not found'
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


@register('web_fetch')
def handle_web_fetch(args: dict) -> str:
    url = args['url']
    max_chars = args.get('max_chars', 10000)
    blocked, reason = _is_private_url(url)
    if blocked:
        return f'{reason}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (SalmAlm/0.1)'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode('utf-8', errors='replace')
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


@register('http_request')
def handle_http_request(args: dict) -> str:
    method = args.get('method', 'GET').upper()
    url = args.get('url', '')
    headers = args.get('headers', {})
    body_str = args.get('body', '')
    timeout_sec = min(args.get('timeout', 15), 60)
    if not url:
        return 'URL is required'
    blocked, reason = _is_private_url(url)
    if blocked:
        return f'{reason}'
    headers.setdefault('User-Agent', f'SalmAlm/{VERSION}')
    data = body_str.encode('utf-8') if body_str else None
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            status = resp.status
            resp_headers = dict(resp.headers)
            raw = resp.read()
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
        return f'Request error: {e}'
