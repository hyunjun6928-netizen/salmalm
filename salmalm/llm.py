"""SalmAlm LLM — Multi-provider API calls with caching and fallback.

Includes streaming support for Anthropic API (SSE token-by-token).
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request

from .constants import DEFAULT_MAX_TOKENS, FALLBACK_MODELS
from .crypto import vault, log
from .core import response_cache, router, track_usage

_UA: str = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'


def _http_post(url: str, headers: Dict[str, str], body: dict, timeout: int = 120) -> dict:
    data = json.dumps(body).encode('utf-8')
    headers.setdefault('User-Agent', _UA)
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))  # type: ignore[no-any-return]
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')
        log.error(f"HTTP {e.code}: {err_body[:300]}")
        # Friendly error messages
        if e.code == 401:
            raise ValueError(f'Invalid API key (401). Please check your key.') from e
        elif e.code == 429:
            raise ValueError(f'Rate limit exceeded (429). Please try again later.') from e
        elif e.code == 402:
            raise ValueError(f'Insufficient API credits (402). Check billing info.') from e
        elif e.code == 529:
            raise ValueError(f'Server overloaded (529). Please try again later.') from e
        raise


def _http_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30) -> dict:
    h: Dict[str, str] = headers or {}
    h.setdefault('User-Agent', _UA)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))  # type: ignore[no-any-return]


def call_llm(messages: List[Dict[str, Any]], model: Optional[str] = None,
             tools: Optional[List[dict]] = None,
             max_tokens: int = DEFAULT_MAX_TOKENS,
             thinking: bool = False) -> Dict[str, Any]:
    """Call LLM API. Returns {'content': str, 'tool_calls': list, 'usage': dict}."""
    if not model:
        last_user = next((m['content'] for m in reversed(messages)
                          if m['role'] == 'user'), '')
        model = router.route(last_user, has_tools=bool(tools))

    # Check cache (only for tool-free queries, scoped by last few messages)
    if not tools:
        cached = response_cache.get(model, messages)
        if cached:
            return {'content': cached, 'tool_calls': [], 'usage': {'input': 0, 'output': 0},
                    'model': model, 'cached': True}

    provider, model_id = model.split('/', 1) if '/' in model else ('anthropic', model)
    # OpenRouter-routed providers use openrouter key
    _openrouter_providers = ('deepseek', 'meta-llama', 'mistralai', 'qwen')
    if provider in _openrouter_providers:
        api_key = vault.get('openrouter_api_key')
    elif provider == 'ollama':
        api_key = 'ollama'  # Ollama doesn't need real API key
    else:
        api_key = vault.get(f'{provider}_api_key')
    if not api_key:
        return {'content': f'❌ {provider} API key not configured.\n\n'
                f'💡 In Settings, add `{provider}_api_key` or\n'
                f'try switching models: `/model auto`', 'tool_calls': [],
                'usage': {'input': 0, 'output': 0}, 'model': model}

    log.info(f"[BOT] LLM call: {model} ({len(messages)} msgs, tools={len(tools or [])})")

    try:
        result = _call_provider(provider, api_key, model_id, messages, tools, max_tokens,
                                thinking=thinking)
        result['model'] = model
        usage = result.get('usage', {})
        track_usage(model, usage.get('input', 0), usage.get('output', 0))
        if not result.get('tool_calls') and result.get('content'):
            response_cache.put(model, messages, result['content'])
        return result
    except Exception as e:
        err_str = str(e)
        log.error(f"LLM error ({model}): {err_str}")

        # ── Token overflow detection — don't fallback, truncate instead ──
        if 'prompt is too long' in err_str or 'maximum context' in err_str.lower():
            log.warning(f"[ERR] Token overflow detected ({len(messages)} msgs). Force-truncating.")
            return {'content': '', 'tool_calls': [], 'error': 'token_overflow',
                    'usage': {'input': 0, 'output': 0}, 'model': model}

        # Auto-fallback to next available provider (non-overflow errors only)
        fallback_order = ['anthropic', 'xai', 'google']
        for fb_provider in fallback_order:
            if fb_provider == provider:
                continue
            fb_key = vault.get(f'{fb_provider}_api_key')
            if not fb_key:
                continue
            fb_model_id = FALLBACK_MODELS.get(fb_provider)
            if not fb_model_id:
                continue
            log.info(f"[SYNC] Fallback: {provider} -> {fb_provider}/{fb_model_id}")
            try:
                if not tools:
                    fb_tools = None
                elif fb_provider == 'anthropic':
                    fb_tools = [{'name': t['name'], 'description': t['description'],
                                 'input_schema': t.get('input_schema', t.get('parameters', {}))} for t in tools]
                elif fb_provider in ('openai', 'xai', 'google'):
                    fb_tools = [{'name': t['name'], 'description': t['description'],
                                 'parameters': t.get('parameters', t.get('input_schema', {}))} for t in tools]
                else:
                    fb_tools = None
                result = _call_provider(fb_provider, fb_key, fb_model_id, messages,
                                        fb_tools, max_tokens)
                result['model'] = f'{fb_provider}/{fb_model_id}'
                usage = result.get('usage', {})
                track_usage(result['model'], usage.get('input', 0), usage.get('output', 0))
                return result
            except Exception as e2:
                log.error(f"Fallback {fb_provider} also failed: {e2}")
                continue
        return {'content': f'❌ All LLM calls failed. Last error: {str(e)[:200]}', 'tool_calls': [],
                'usage': {'input': 0, 'output': 0}, 'model': model}


def _call_provider(provider: str, api_key: str, model_id: str,
                    messages: List[Dict[str, Any]],
                    tools: Optional[List[dict]], max_tokens: int,
                    thinking: bool = False) -> Dict[str, Any]:
    if provider == 'anthropic':
        return _call_anthropic(api_key, model_id, messages, tools, max_tokens,
                                thinking=thinking)
    elif provider in ('openai', 'xai'):
        base_url = 'https://api.x.ai/v1' if provider == 'xai' else 'https://api.openai.com/v1'
        return _call_openai(api_key, model_id, messages, tools, max_tokens, base_url)
    elif provider == 'google':
        return _call_google(api_key, model_id, messages, max_tokens, tools=tools)
    elif provider == 'ollama':
        ollama_url = vault.get('ollama_url') or 'http://localhost:11434/v1'
        return _call_openai('ollama', model_id, messages, tools, max_tokens, ollama_url)
    elif provider == 'openrouter':
        return _call_openai(api_key, model_id, messages, tools, max_tokens, 'https://openrouter.ai/api/v1')
    elif provider in ('deepseek', 'meta-llama', 'mistralai', 'qwen'):
        # Route through OpenRouter
        or_key = vault.get('openrouter_api_key')
        if not or_key:
            raise ValueError(f'{provider} requires openrouter_api_key in vault')
        full_model = f'{provider}/{model_id}'
        return _call_openai(or_key, full_model, messages, tools, max_tokens, 'https://openrouter.ai/api/v1')
    else:
        raise ValueError(f'Unknown provider: {provider}')


def _call_anthropic(api_key: str, model_id: str, messages: List[Dict[str, Any]],
                     tools: Optional[List[dict]], max_tokens: int,
                     thinking: bool = False) -> Dict[str, Any]:
    system_msgs = [m['content'] for m in messages if m['role'] == 'system']
    chat_msgs = [m for m in messages if m['role'] != 'system']

    # Extended thinking for Opus/Sonnet
    use_thinking = thinking and ('opus' in model_id or 'sonnet' in model_id)

    body = {
        'model': model_id,
        'messages': chat_msgs,
    }
    if use_thinking:
        # Extended thinking mode — budget_tokens controls thinking depth
        body['max_tokens'] = 16000  # type: ignore[assignment]
        body['thinking'] = {'type': 'enabled', 'budget_tokens': 10000}  # type: ignore[assignment]
    else:
        body['max_tokens'] = max_tokens  # type: ignore[assignment]

    if system_msgs:
        body['system'] = '\n'.join(system_msgs)
    if tools:
        body['tools'] = tools
    resp = _http_post(
        'https://api.anthropic.com/v1/messages',
        {'x-api-key': api_key, 'content-type': 'application/json',
         'anthropic-version': '2023-06-01'},
        body
    )
    content = ''
    thinking_text = ''
    tool_calls = []
    for block in resp.get('content', []):
        if block['type'] == 'text':
            content += block['text']
        elif block['type'] == 'thinking':
            thinking_text += block.get('thinking', '')
        elif block['type'] == 'tool_use':
            tool_calls.append({
                'id': block['id'], 'name': block['name'],
                'arguments': block['input']
            })
    usage = resp.get('usage', {})
    result = {
        'content': content, 'tool_calls': tool_calls,
        'usage': {'input': usage.get('input_tokens', 0),
                  'output': usage.get('output_tokens', 0)}
    }
    if thinking_text:
        result['thinking'] = thinking_text
        log.info(f"[AI] Thinking: {len(thinking_text)} chars")
    return result


def _call_openai(api_key: str, model_id: str, messages: List[Dict[str, Any]],
                  tools: Optional[List[dict]], max_tokens: int,
                  base_url: str) -> Dict[str, Any]:
    # Convert Anthropic-style image blocks to OpenAI format
    converted_msgs = []
    for m in messages:
        if isinstance(m.get('content'), list):
            new_content = []
            for block in m['content']:
                if block.get('type') == 'image' and block.get('source', {}).get('type') == 'base64':
                    src = block['source']
                    new_content.append({'type': 'image_url', 'image_url': {
                        'url': f"data:{src['media_type']};base64,{src['data']}"}})
                elif block.get('type') == 'text':
                    new_content.append({'type': 'text', 'text': block['text']})
                else:
                    new_content.append(block)
            converted_msgs.append({**m, 'content': new_content})
        else:
            converted_msgs.append(m)
    body = {'model': model_id, 'max_tokens': max_tokens, 'messages': converted_msgs}
    if tools:
        body['tools'] = [{'type': 'function', 'function': t} for t in tools]
    headers = {'Content-Type': 'application/json'}
    if api_key and api_key != 'ollama':
        headers['Authorization'] = f'Bearer {api_key}'
    resp = _http_post(
        f'{base_url}/chat/completions',
        headers,
        body
    )
    choice = resp['choices'][0]['message']
    tool_calls = []
    for tc in (choice.get('tool_calls') or []):
        tool_calls.append({
            'id': tc['id'], 'name': tc['function']['name'],
            'arguments': json.loads(tc['function']['arguments'])
        })
    usage = resp.get('usage', {})
    return {
        'content': choice.get('content', ''), 'tool_calls': tool_calls,
        'usage': {'input': usage.get('prompt_tokens', 0),
                  'output': usage.get('completion_tokens', 0)}
    }


def _call_google(api_key: str, model_id: str, messages: List[Dict[str, Any]],
                  max_tokens: int, tools: Optional[List[dict]] = None) -> Dict[str, Any]:
    # Gemini API — with optional tool support
    parts = []
    for m in messages:
        content = m.get('content', '')
        if isinstance(content, list):
            # Multimodal — extract text only for Google
            text_parts = [b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text']
            content = ' '.join(text_parts)
        role = 'user' if m['role'] in ('user', 'system') else 'model'
        parts.append({'role': role, 'parts': [{'text': str(content)}]})
    # Merge consecutive same-role messages
    merged = []  # type: ignore[var-annotated]
    for p in parts:
        if merged and merged[-1]['role'] == p['role']:
            merged[-1]['parts'].extend(p['parts'])  # type: ignore[attr-defined]
        else:
            merged.append(p)
    body = {
        'contents': merged,
        'generationConfig': {'maxOutputTokens': max_tokens}
    }
    # Add tools if provided
    if tools:
        gemini_tools = []
        for t in tools:
            fn_decl = {'name': t['name'], 'description': t.get('description', '')}
            params = t.get('parameters', t.get('input_schema', {}))
            if params and params.get('properties'):
                fn_decl['parameters'] = params
            gemini_tools.append(fn_decl)
        body['tools'] = [{'functionDeclarations': gemini_tools}]
    resp = _http_post(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}',
        {'Content-Type': 'application/json'}, body
    )
    text = ''
    tool_calls = []
    for cand in resp.get('candidates', []):
        for part in cand.get('content', {}).get('parts', []):
            if 'text' in part:
                text += part['text']
            elif 'functionCall' in part:
                fc = part['functionCall']
                tool_calls.append({
                    'id': f"google_{fc['name']}_{int(time.time()*1000)}",
                    'name': fc['name'],
                    'arguments': fc.get('args', {})
                })
    usage_meta = resp.get('usageMetadata', {})
    return {
        'content': text, 'tool_calls': tool_calls,
        'usage': {'input': usage_meta.get('promptTokenCount', 0),
                  'output': usage_meta.get('candidatesTokenCount', 0)}
    }


# ============================================================
# STREAMING API — Token-by-token streaming for Anthropic
# ============================================================

def stream_anthropic(messages: List[Dict[str, Any]], model: Optional[str] = None,
                     tools: Optional[List[dict]] = None,
                     max_tokens: int = DEFAULT_MAX_TOKENS,
                     thinking: bool = False) -> Generator[Dict[str, Any], None, None]:
    """Stream Anthropic API responses token-by-token using raw urllib SSE.

    Yields events:
        {'type': 'text_delta', 'text': '...'}
        {'type': 'thinking_delta', 'text': '...'}
        {'type': 'tool_use_start', 'id': '...', 'name': '...'}
        {'type': 'tool_use_delta', 'partial_json': '...'}
        {'type': 'tool_use_end', 'id': '...', 'name': '...', 'arguments': {...}}
        {'type': 'message_end', 'content': '...', 'tool_calls': [...], 'usage': {...}, 'model': '...'}
        {'type': 'error', 'error': '...'}
    """
    if not model:
        last_user = next((m['content'] for m in reversed(messages)
                          if m['role'] == 'user'), '')
        model = router.route(last_user, has_tools=bool(tools))

    provider, model_id = model.split('/', 1) if '/' in model else ('anthropic', model)

    # Only Anthropic supports our streaming implementation
    if provider != 'anthropic':
        # Fallback: non-streaming call, yield as single chunk
        result = call_llm(messages, model=model, tools=tools, max_tokens=max_tokens, thinking=thinking)
        if result.get('content'):
            yield {'type': 'text_delta', 'text': result['content']}
        yield {'type': 'message_end', **result}
        return

    api_key = vault.get('anthropic_api_key')
    if not api_key:
        yield {'type': 'error', 'error': '❌ Anthropic API key not configured.'}
        return

    system_msgs = [m['content'] for m in messages if m['role'] == 'system']
    chat_msgs = [m for m in messages if m['role'] != 'system']

    use_thinking = thinking and ('opus' in model_id or 'sonnet' in model_id)

    body: dict = {
        'model': model_id,
        'messages': chat_msgs,
        'stream': True,
    }
    if use_thinking:
        body['max_tokens'] = 16000
        body['thinking'] = {'type': 'enabled', 'budget_tokens': 10000}
    else:
        body['max_tokens'] = max_tokens
    if system_msgs:
        body['system'] = '\n'.join(system_msgs)
    if tools:
        body['tools'] = tools

    data = json.dumps(body).encode('utf-8')
    headers = {
        'x-api-key': api_key,
        'content-type': 'application/json',
        'anthropic-version': '2023-06-01',
        'User-Agent': _UA,
    }
    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=data, headers=headers, method='POST'
    )

    # Accumulators
    content_text = ''
    thinking_text = ''
    tool_calls: List[dict] = []
    current_tool: Optional[dict] = None
    current_tool_json = ''
    usage = {'input': 0, 'output': 0}

    try:
        resp = urllib.request.urlopen(req, timeout=180)
        buffer = ''
        for raw_chunk in _iter_chunks(resp):
            buffer += raw_chunk
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()
                if not line:
                    continue
                if line.startswith('data: '):
                    json_str = line[6:]
                    if json_str.strip() == '[DONE]':
                        continue
                    try:
                        event = json.loads(json_str)
                    except json.JSONDecodeError:
                        continue
                    yield from _process_stream_event(
                        event, content_text, thinking_text,
                        tool_calls, current_tool, current_tool_json, usage
                    )
                    # Update accumulators from event
                    etype = event.get('type', '')
                    if etype == 'content_block_delta':
                        delta = event.get('delta', {})
                        dt = delta.get('type', '')
                        if dt == 'text_delta':
                            content_text += delta.get('text', '')
                        elif dt == 'thinking_delta':
                            thinking_text += delta.get('thinking', '')
                        elif dt == 'input_json_delta':
                            current_tool_json += delta.get('partial_json', '')
                    elif etype == 'content_block_start':
                        cb = event.get('content_block', {})
                        if cb.get('type') == 'tool_use':
                            current_tool = {'id': cb['id'], 'name': cb['name']}
                            current_tool_json = ''
                    elif etype == 'content_block_stop':
                        if current_tool:
                            try:
                                args = json.loads(current_tool_json) if current_tool_json else {}
                            except json.JSONDecodeError:
                                args = {}
                            tc = {**current_tool, 'arguments': args}
                            tool_calls.append(tc)
                            current_tool = None
                            current_tool_json = ''
                    elif etype == 'message_delta':
                        u = event.get('usage', {})
                        usage['output'] = u.get('output_tokens', usage['output'])
                    elif etype == 'message_start':
                        msg = event.get('message', {})
                        u = msg.get('usage', {})
                        usage['input'] = u.get('input_tokens', 0)

        # Track usage
        track_usage(model, usage['input'], usage['output'])

        result = {
            'type': 'message_end',
            'content': content_text,
            'tool_calls': tool_calls,
            'usage': usage,
            'model': model,
        }
        if thinking_text:
            result['thinking'] = thinking_text
        yield result

    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')
        log.error(f"[STREAM] HTTP {e.code}: {err_body[:300]}")
        yield {'type': 'error', 'error': f'HTTP {e.code}: {err_body[:200]}'}
    except Exception as e:
        log.error(f"[STREAM] Error: {e}")
        yield {'type': 'error', 'error': str(e)[:200]}


def _iter_chunks(resp, chunk_size: int = 1024) -> Generator[str, None, None]:
    """Read HTTP response in chunks, decode to str."""
    while True:
        chunk = resp.read(chunk_size)
        if not chunk:
            break
        yield chunk.decode('utf-8', errors='replace')


def _process_stream_event(event: dict, content_text: str, thinking_text: str,
                          tool_calls: list, current_tool: Optional[dict],
                          current_tool_json: str, usage: dict) -> Generator[Dict[str, Any], None, None]:
    """Process a single SSE event from Anthropic stream and yield UI events."""
    etype = event.get('type', '')

    if etype == 'content_block_delta':
        delta = event.get('delta', {})
        dt = delta.get('type', '')
        if dt == 'text_delta':
            text = delta.get('text', '')
            if text:
                yield {'type': 'text_delta', 'text': text}
        elif dt == 'thinking_delta':
            text = delta.get('thinking', '')
            if text:
                yield {'type': 'thinking_delta', 'text': text}
        elif dt == 'input_json_delta':
            yield {'type': 'tool_use_delta', 'partial_json': delta.get('partial_json', '')}

    elif etype == 'content_block_start':
        cb = event.get('content_block', {})
        if cb.get('type') == 'tool_use':
            yield {'type': 'tool_use_start', 'id': cb['id'], 'name': cb['name']}

    elif etype == 'content_block_stop':
        if current_tool:
            try:
                args = json.loads(current_tool_json) if current_tool_json else {}
            except json.JSONDecodeError:
                args = {}
            yield {'type': 'tool_use_end', 'id': current_tool['id'],
                   'name': current_tool['name'], 'arguments': args}
