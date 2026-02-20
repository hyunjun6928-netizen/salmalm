"""Brave Search API tools — web, news, images, LLM context."""
import json
import os
import urllib.request
import urllib.parse
import urllib.error
from salmalm.tools.tool_registry import register

_BASE_URL = 'https://api.search.brave.com/res/v1'


def _get_api_key() -> str:
    """Get Brave API key from env or vault."""
    key = os.environ.get('BRAVE_API_KEY', '')
    if not key:
        try:
            from salmalm.crypto import vault
            key = vault.get('brave_api_key', '') or ''
        except Exception:
            pass
    return key


def _brave_request(endpoint: str, params: dict, timeout: int = 15) -> dict:
    """Make a request to Brave Search API. Returns parsed JSON."""
    api_key = _get_api_key()
    if not api_key:
        return {'_error': '🔑 BRAVE_API_KEY가 설정되지 않았습니다. 환경변수 BRAVE_API_KEY를 설정하거나 vault에 brave_api_key를 추가하세요.'}

    # Filter None values
    params = {k: v for k, v in params.items() if v is not None}
    qs = urllib.parse.urlencode(params)
    url = f'{_BASE_URL}/{endpoint}?{qs}'

    req = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'Accept-Encoding': 'identity',
        'X-Subscription-Token': api_key,
    })

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return data
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')[:500]
        return {'_error': f'Brave API HTTP {e.code}: {body}'}
    except Exception as e:
        return {'_error': f'Brave API error: {e}'}


@register('brave_search')
def brave_web_search(args: dict) -> str:
    """Brave 웹 검색."""
    query = args.get('query', args.get('q', ''))
    if not query:
        return '❌ query is required'

    params = {
        'q': query,
        'count': min(int(args.get('count', 5)), 20),
        'offset': args.get('offset'),
        'freshness': args.get('freshness'),
        'country': args.get('country'),
        'search_lang': args.get('search_lang'),
        'extra_snippets': 'true' if args.get('extra_snippets') else None,
    }

    data = _brave_request('web/search', params)
    if '_error' in data:
        return data['_error']

    results = []
    for r in data.get('web', {}).get('results', []):
        title = r.get('title', '')
        url = r.get('url', '')
        desc = r.get('description', '')
        extra = ''
        if r.get('extra_snippets'):
            extra = '\n'.join(f'  > {s}' for s in r['extra_snippets'][:2])
        entry = f"**{title}**\n{url}\n{desc}"
        if extra:
            entry += f'\n{extra}'
        results.append(entry)

    return '\n\n'.join(results) if results else 'No results found.'


@register('brave_context')
def brave_llm_context(args: dict) -> str:
    """Brave LLM Context API — RAG 강화용."""
    query = args.get('query', args.get('q', ''))
    if not query:
        return '❌ query is required'

    params = {
        'q': query,
        'count': min(int(args.get('count', 5)), 20),
        'country': args.get('country'),
        'search_lang': args.get('search_lang'),
    }

    data = _brave_request('llm/context', params)
    if '_error' in data:
        return data['_error']

    # LLM context endpoint returns various structures
    parts = []

    # Web results context
    for r in data.get('web', {}).get('results', [])[:5]:
        parts.append(f"[{r.get('title', '')}]({r.get('url', '')})\n{r.get('description', '')}")

    # Summaries / knowledge
    if data.get('summary'):
        parts.insert(0, f"**Summary:** {data['summary']}")

    # Infobox
    if data.get('infobox'):
        info = data['infobox']
        parts.append(f"**{info.get('title', '')}**: {info.get('description', '')}")

    return '\n\n'.join(parts) if parts else json.dumps(data, ensure_ascii=False)[:3000]


@register('brave_news')
def brave_news_search(args: dict) -> str:
    """Brave 뉴스 검색."""
    query = args.get('query', args.get('q', ''))
    if not query:
        return '❌ query is required'

    params = {
        'q': query,
        'count': min(int(args.get('count', 5)), 20),
        'offset': args.get('offset'),
        'freshness': args.get('freshness'),
        'country': args.get('country'),
        'search_lang': args.get('search_lang'),
    }

    data = _brave_request('news/search', params)
    if '_error' in data:
        return data['_error']

    results = []
    for r in data.get('results', []):
        age = r.get('age', '')
        source = r.get('meta_url', {}).get('hostname', '') if isinstance(r.get('meta_url'), dict) else ''
        entry = f"📰 **{r.get('title', '')}**"
        if source:
            entry += f' ({source})'
        if age:
            entry += f' — {age}'
        entry += f"\n{r.get('url', '')}\n{r.get('description', '')}"
        results.append(entry)

    return '\n\n'.join(results) if results else 'No news found.'


@register('brave_images')
def brave_image_search(args: dict) -> str:
    """Brave 이미지 검색."""
    query = args.get('query', args.get('q', ''))
    if not query:
        return '❌ query is required'

    params = {
        'q': query,
        'count': min(int(args.get('count', 5)), 20),
        'country': args.get('country'),
        'search_lang': args.get('search_lang'),
    }

    data = _brave_request('images/search', params)
    if '_error' in data:
        return data['_error']

    results = []
    for r in data.get('results', []):
        title = r.get('title', '')
        src = r.get('properties', {}).get('url', r.get('url', ''))
        thumb = r.get('thumbnail', {}).get('src', '')
        entry = f"🖼 **{title}**\n{src}"
        if thumb:
            entry += f'\nThumb: {thumb}'
        results.append(entry)

    return '\n\n'.join(results) if results else 'No images found.'
