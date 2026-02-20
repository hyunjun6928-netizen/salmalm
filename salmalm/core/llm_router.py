"""Multi-Provider LLM Router — unified API across Anthropic, OpenAI, Google, Groq, Ollama.

stdlib-only. Provides:
  - Provider auto-detection from model string
  - Unified OpenAI-compatible request/response format
  - Automatic fallback on failure
  - /model list, /model switch <name> commands
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider definitions
# ---------------------------------------------------------------------------

PROVIDERS: Dict[str, Dict[str, Any]] = {
    'anthropic': {
        'env_key': 'ANTHROPIC_API_KEY',
        'base_url': 'https://api.anthropic.com/v1',
        'chat_endpoint': '/messages',
        'models': [
            'claude-opus-4-6', 'claude-sonnet-4-20250514',
            'claude-haiku-3.5-20241022',
        ],
    },
    'openai': {
        'env_key': 'OPENAI_API_KEY',
        'base_url': 'https://api.openai.com/v1',
        'chat_endpoint': '/chat/completions',
        'models': [
            'gpt-5.3-codex', 'gpt-5.1-codex', 'gpt-4.1',
            'gpt-4.1-mini', 'gpt-4.1-nano', 'o3', 'o4-mini',
        ],
    },
    'google': {
        'env_key': 'GOOGLE_API_KEY',
        'alt_env_key': 'GEMINI_API_KEY',
        'base_url': 'https://generativelanguage.googleapis.com/v1beta',
        'chat_endpoint': '/chat/completions',  # OpenAI-compat
        'models': [
            'gemini-3-pro-preview', 'gemini-3-flash-preview',
            'gemini-2.5-pro', 'gemini-2.5-flash',
            'gemini-2.0-flash',
        ],
    },
    'groq': {
        'env_key': 'GROQ_API_KEY',
        'base_url': 'https://api.groq.com/openai/v1',
        'chat_endpoint': '/chat/completions',
        'models': [
            'llama-3.3-70b-versatile', 'llama-3.1-8b-instant',
            'mixtral-8x7b-32768', 'gemma2-9b-it',
        ],
    },
    'ollama': {
        'env_key': '',  # no key needed
        'base_url': os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434'),
        'chat_endpoint': '/api/chat',
        'models': [
            'llama3.2', 'llama3.3', 'qwen3', 'mistral',
        ],
    },
}

# Provider prefix → provider name
_PREFIX_MAP = {
    'anthropic/': 'anthropic',
    'openai/': 'openai',
    'google/': 'google',
    'groq/': 'groq',
    'ollama/': 'ollama',
    'xai/': 'openai',  # xAI uses OpenAI-compatible API
    'openrouter/': 'openai',  # OpenRouter uses OpenAI-compatible API
}


def detect_provider(model: str) -> Tuple[str, str]:
    """Detect provider from model string. Returns (provider_name, bare_model)."""
    for prefix, prov in _PREFIX_MAP.items():
        if model.startswith(prefix):
            return prov, model[len(prefix):]
    # Heuristic detection
    ml = model.lower()
    if 'claude' in ml:
        return 'anthropic', model
    if 'gpt' in ml or ml.startswith('o3') or ml.startswith('o4'):
        return 'openai', model
    if 'gemini' in ml:
        return 'google', model
    if 'llama' in ml or 'mixtral' in ml or 'gemma' in ml:
        # Could be groq or ollama — check if groq key exists
        if os.environ.get('GROQ_API_KEY'):
            return 'groq', model
        return 'ollama', model
    return 'openai', model  # default


def get_api_key(provider: str) -> Optional[str]:
    """Get API key for provider from environment."""
    prov_cfg = PROVIDERS.get(provider, {})
    env_key = prov_cfg.get('env_key', '')
    if not env_key:
        return None  # ollama doesn't need key
    key = os.environ.get(env_key)
    if not key:
        alt_key = prov_cfg.get('alt_env_key', '')
        if alt_key:
            key = os.environ.get(alt_key)
    return key


def is_provider_available(provider: str) -> bool:
    """Check if a provider is available (has API key or is local)."""
    if provider == 'ollama':
        return True  # always "available", may fail at call time
    return bool(get_api_key(provider))


def list_available_models() -> List[Dict[str, str]]:
    """List all available models across configured providers."""
    result = []
    for prov_name, prov in PROVIDERS.items():
        if not is_provider_available(prov_name):
            continue
        for m in prov['models']:
            result.append({
                'provider': prov_name,
                'model': f'{prov_name}/{m}',
                'name': m,
            })
    return result


class LLMRouter:
    """Multi-provider LLM router with fallback."""

    def __init__(self):
        self._current_model: Optional[str] = None
        self._fallback_order: List[str] = ['anthropic', 'openai', 'google', 'groq', 'ollama']
        self._call_history: List[Dict[str, Any]] = []

    @property
    def current_model(self) -> Optional[str]:
        return self._current_model

    @current_model.setter
    def current_model(self, model: str) -> None:
        self._current_model = model

    def switch_model(self, model: str) -> str:
        """Switch to a new model. Returns confirmation message."""
        provider, bare = detect_provider(model)
        if not is_provider_available(provider):
            return f'❌ Provider `{provider}` not configured (missing API key)'
        self._current_model = model
        return f'✅ Switched to `{model}` ({provider})'

    def list_models(self) -> str:
        """Format available models for display."""
        models = list_available_models()
        if not models:
            return '❌ No providers configured. Set API keys in environment.'
        lines = ['**Available Models:**\n']
        by_provider: Dict[str, List[str]] = {}
        for m in models:
            by_provider.setdefault(m['provider'], []).append(m['name'])
        for prov, names in by_provider.items():
            lines.append(f'**{prov}:**')
            for n in names:
                marker = ' ← current' if self._current_model and n in self._current_model else ''
                lines.append(f'  • `{prov}/{n}`{marker}')
        return '\n'.join(lines)

    def _build_request(self, provider: str, model: str,
                       messages: List[Dict], max_tokens: int = 4096,
                       tools: Optional[List] = None) -> Tuple[str, Dict[str, str], dict]:
        """Build HTTP request for provider. Returns (url, headers, body)."""
        prov_cfg = PROVIDERS.get(provider, PROVIDERS['openai'])
        base = prov_cfg['base_url']
        endpoint = prov_cfg['chat_endpoint']
        api_key = get_api_key(provider)

        if provider == 'anthropic':
            url = f'{base}{endpoint}'
            headers = {
                'x-api-key': api_key or '',
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            }
            # Convert OpenAI format → Anthropic format
            system = ''
            conv_msgs = []
            for m in messages:
                if m['role'] == 'system':
                    system += m.get('content', '') + '\n'
                else:
                    conv_msgs.append({'role': m['role'], 'content': m.get('content', '')})
            body: dict = {
                'model': model,
                'max_tokens': max_tokens,
                'messages': conv_msgs,
            }
            if system.strip():
                body['system'] = system.strip()
            if tools:
                body['tools'] = tools
        elif provider == 'ollama':
            url = f'{base}{endpoint}'
            headers = {'content-type': 'application/json'}
            body = {
                'model': model,
                'messages': messages,
                'stream': False,
            }
        else:
            # OpenAI-compatible (OpenAI, Groq, Google, xAI, OpenRouter)
            url = f'{base}{endpoint}'
            headers = {
                'Authorization': f'Bearer {api_key or ""}',
                'content-type': 'application/json',
            }
            body = {
                'model': model,
                'messages': messages,
                'max_tokens': max_tokens,
            }
            if tools:
                body['tools'] = tools

        return url, headers, body

    def _parse_response(self, provider: str, data: dict) -> Dict[str, Any]:
        """Parse provider response into unified format."""
        if provider == 'anthropic':
            content = ''
            tool_calls = []
            for block in data.get('content', []):
                if block.get('type') == 'text':
                    content += block.get('text', '')
                elif block.get('type') == 'tool_use':
                    tool_calls.append({
                        'id': block.get('id', ''),
                        'function': {
                            'name': block.get('name', ''),
                            'arguments': json.dumps(block.get('input', {})),
                        },
                    })
            usage = data.get('usage', {})
            return {
                'content': content,
                'tool_calls': tool_calls,
                'usage': {
                    'input': usage.get('input_tokens', 0),
                    'output': usage.get('output_tokens', 0),
                },
                'model': data.get('model', ''),
            }
        elif provider == 'ollama':
            msg = data.get('message', {})
            return {
                'content': msg.get('content', ''),
                'tool_calls': [],
                'usage': {
                    'input': data.get('prompt_eval_count', 0),
                    'output': data.get('eval_count', 0),
                },
                'model': data.get('model', ''),
            }
        else:
            # OpenAI-compatible
            choices = data.get('choices', [{}])
            msg = choices[0].get('message', {}) if choices else {}
            usage = data.get('usage', {})
            return {
                'content': msg.get('content', '') or '',
                'tool_calls': msg.get('tool_calls', []),
                'usage': {
                    'input': usage.get('prompt_tokens', 0),
                    'output': usage.get('completion_tokens', 0),
                },
                'model': data.get('model', ''),
            }

    def call(self, messages: List[Dict], model: Optional[str] = None,
             max_tokens: int = 4096, tools: Optional[List] = None,
             timeout: int = 120) -> Dict[str, Any]:
        """Call LLM with automatic fallback.

        Returns unified response dict: {content, tool_calls, usage, model}.
        """
        target_model = model or self._current_model
        if not target_model:
            # Pick first available
            for prov in self._fallback_order:
                if is_provider_available(prov):
                    models = PROVIDERS[prov]['models']
                    if models:
                        target_model = models[0]
                        break
        if not target_model:
            return {'content': '❌ No LLM providers configured', 'tool_calls': [],
                    'usage': {'input': 0, 'output': 0}, 'model': ''}

        provider, bare_model = detect_provider(target_model)
        errors = []

        # Try primary
        try:
            result = self._do_call(provider, bare_model, messages, max_tokens, tools, timeout)
            self._call_history.append({'model': target_model, 'provider': provider, 'ok': True, 'ts': time.time()})
            return result
        except Exception as e:
            errors.append(f'{provider}/{bare_model}: {e}')
            log.warning(f'LLM call failed for {provider}/{bare_model}: {e}')

        # Fallback
        for fb_prov in self._fallback_order:
            if fb_prov == provider or not is_provider_available(fb_prov):
                continue
            fb_models = PROVIDERS[fb_prov]['models']
            if not fb_models:
                continue
            fb_model = fb_models[0]
            try:
                log.info(f'Falling back to {fb_prov}/{fb_model}')
                result = self._do_call(fb_prov, fb_model, messages, max_tokens, tools, timeout)
                result['fallback'] = True
                result['original_model'] = target_model
                self._call_history.append({'model': f'{fb_prov}/{fb_model}', 'provider': fb_prov, 'ok': True, 'ts': time.time(), 'fallback': True})
                return result
            except Exception as e2:
                errors.append(f'{fb_prov}/{fb_model}: {e2}')

        return {
            'content': '❌ All providers failed:\n' + '\n'.join(errors),
            'tool_calls': [],
            'usage': {'input': 0, 'output': 0},
            'model': target_model,
        }

    def _do_call(self, provider: str, model: str, messages: List[Dict],
                 max_tokens: int, tools: Optional[List], timeout: int) -> Dict[str, Any]:
        """Execute a single LLM API call."""
        url, headers, body = self._build_request(provider, model, messages, max_tokens, tools)
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
        return self._parse_response(provider, result)


# Singleton
llm_router = LLMRouter()


# ---------------------------------------------------------------------------
# Command handlers (for CommandRouter registration)
# ---------------------------------------------------------------------------

def handle_model_command(cmd: str, session=None, **kw) -> str:
    """Handle /model list | /model switch <name>."""
    parts = cmd.strip().split()
    # /model list
    if len(parts) >= 2 and parts[1] == 'list':
        return llm_router.list_models()
    # /model switch <name>
    if len(parts) >= 3 and parts[1] == 'switch':
        return llm_router.switch_model(parts[2])
    # /model (just show current)
    current = llm_router.current_model or '(auto)'
    return f'Current model: `{current}`\nUse `/model list` or `/model switch <name>`'


def register_commands(router: object) -> None:
    """Register /model commands with CommandRouter."""
    router.register_prefix('/model', handle_model_command)


def register_tools(registry_module: Optional[object] = None) -> None:
    """Register LLM router tools."""
    try:
        from salmalm.tools.tool_registry import register_dynamic
        register_dynamic('llm_router_list', lambda args: llm_router.list_models(), {
            'name': 'llm_router_list',
            'description': 'List available LLM models across all configured providers',
            'input_schema': {'type': 'object', 'properties': {}},
        })
        register_dynamic('llm_router_switch', lambda args: llm_router.switch_model(args.get('model', '')), {
            'name': 'llm_router_switch',
            'description': 'Switch to a different LLM model',
            'input_schema': {'type': 'object', 'properties': {'model': {'type': 'string'}}, 'required': ['model']},
        })
    except Exception as e:
        log.warning(f'Failed to register LLM router tools: {e}')
