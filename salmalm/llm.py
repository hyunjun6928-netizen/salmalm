import json
import time
from typing import Any, Optional
import urllib.error
import urllib.parse
import urllib.request

from .constants import DEFAULT_MAX_TOKENS
from .crypto import vault, log
from .core import response_cache, router, track_usage

_UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'


def _http_post(url: str, headers: dict, body: dict, timeout: int = 120) -> dict:
    data = json.dumps(body).encode('utf-8')
    headers.setdefault('User-Agent', _UA)
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')
        log.error(f"HTTP {e.code}: {err_body[:300]}")
        raise


def _http_get(url: str, headers: dict = None, timeout: int = 30) -> dict:
    h = headers or {}
    h.setdefault('User-Agent', _UA)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def call_llm(messages: list, model: str = None, tools: list = None,
             max_tokens: int = DEFAULT_MAX_TOKENS, thinking: bool = False) -> dict:
    """Call LLM API. Returns {'content': str, 'tool_calls': list, 'usage': dict}."""
    if not model:
        last_user = next((m['content'] for m in reversed(messages)
                          if m['role'] == 'user'), '')
        model = router.route(last_user, has_tools=bool(tools))

    # Check cache (only for tool-free queries)
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
        return {'content': f'❌ {provider} API 키가 설정되지 않았습니다.', 'tool_calls': [],
                'usage': {'input': 0, 'output': 0}, 'model': model}

    log.info(f"🤖 LLM call: {model} ({len(messages)} msgs, tools={len(tools or [])})")

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
            log.warning(f"🚨 Token overflow detected ({len(messages)} msgs). Force-truncating.")
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
            fb_models = {'anthropic': 'claude-sonnet-4-20250514', 'xai': 'grok-4',
                         'google': 'gemini-3-flash-preview'}
            fb_model_id = fb_models[fb_provider]
            log.info(f"🔄 Fallback: {provider} → {fb_provider}/{fb_model_id}")
            try:
                if not tools:
                    fb_tools = None
                elif fb_provider == 'anthropic':
                    fb_tools = [{'name': t['name'], 'description': t['description'],
                                 'input_schema': t['input_schema']} for t in tools]
                elif fb_provider in ('openai', 'xai', 'google'):
                    fb_tools = [{'name': t['name'], 'description': t['description'],
                                 'parameters': t.get('input_schema', t.get('parameters', {}))} for t in tools]
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
        return {'content': f'❌ 모든 LLM 호출 실패. 마지막 오류: {str(e)[:200]}', 'tool_calls': [],
                'usage': {'input': 0, 'output': 0}, 'model': model}


def _call_provider(provider, api_key, model_id, messages, tools, max_tokens,
                    thinking: bool = False):
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


def _call_anthropic(api_key, model_id, messages, tools, max_tokens,
                     thinking: bool = False):
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
        body['max_tokens'] = 16000
        body['thinking'] = {'type': 'enabled', 'budget_tokens': 10000}
    else:
        body['max_tokens'] = max_tokens

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
        log.info(f"🧠 Thinking: {len(thinking_text)} chars")
    return result


def _call_openai(api_key, model_id, messages, tools, max_tokens, base_url):
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


def _call_google(api_key, model_id, messages, max_tokens, tools=None):
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
    merged = []
    for p in parts:
        if merged and merged[-1]['role'] == p['role']:
            merged[-1]['parts'].extend(p['parts'])
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
