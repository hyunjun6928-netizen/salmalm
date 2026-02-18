#!/usr/bin/env python3
"""
삶앎 (SalmAlm) v0.1.0 — Personal AI Gateway
Copyright 2026. All rights reserved. Private use only.

Single-file AI gateway with:
- Telegram bot integration
- Multi-LLM (Anthropic/OpenAI/xAI/Google)
- Tools: exec, file read/write/edit, web_search, web_fetch
- AES-256-GCM vault (API keys encrypted)
- Memory system (SOUL.md, MEMORY.md, daily logs)
- Token optimization (context compression, model routing, caching)
- Web UI
- Cron scheduler
- Audit log hash chain
"""

import asyncio, base64, hashlib, hmac, http.server, json, logging, os, re
import secrets, shutil, signal, socket, ssl, sqlite3, subprocess, sys
import textwrap, threading, time, traceback, urllib.error, urllib.parse
import urllib.request, uuid
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

# ============================================================
# CONSTANTS
# ============================================================
VERSION = "0.2.0"
APP_NAME = "삶앎 (SalmAlm)"
KST = timezone(timedelta(hours=9))

# Paths
BASE_DIR = Path(__file__).parent.resolve()
MEMORY_DIR = BASE_DIR / "memory"
WORKSPACE_DIR = BASE_DIR  # workspace = project dir itself
SOUL_FILE = BASE_DIR / "SOUL.md"
AGENTS_FILE = BASE_DIR / "AGENTS.md"
MEMORY_FILE = BASE_DIR / "MEMORY.md"
USER_FILE = BASE_DIR / "USER.md"
TOOLS_FILE = BASE_DIR / "TOOLS.md"
VAULT_FILE = BASE_DIR / ".vault.enc"
AUDIT_DB = BASE_DIR / "audit.db"
MEMORY_DB = BASE_DIR / "memory.db"
CACHE_DB = BASE_DIR / "cache.db"
LOG_FILE = BASE_DIR / "salmalm.log"

# Security
VAULT_VERSION = b'\x03'  # v3 = AES-256-GCM (with HMAC-CTR fallback)
PBKDF2_ITER = 200_000
SESSION_TIMEOUT = 3600 * 8  # 8 hours
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = 60  # seconds
EXEC_BLOCKLIST = {
    'rm', 'rmdir', 'mkfs', 'dd', 'format', 'fdisk', 'shutdown',
    'reboot', 'halt', 'poweroff', 'init', 'systemctl', 'passwd',
    'useradd', 'userdel', 'groupadd', 'groupdel', 'chown', 'chmod',
    'mount', 'umount', 'iptables', 'ufw', 'kill', 'killall', 'pkill',
}
EXEC_BLOCKLIST_PATTERNS = [
    r'>\s*/dev/sd', r'>\s*/dev/nv', r'curl\s+.*\|\s*(ba)?sh',
    r'wget\s+.*\|\s*(ba)?sh', r'python.*-c.*import\s+os',
]
PROTECTED_FILES = {'.vault.enc', 'audit.db', 'server.py'}

# LLM
DEFAULT_MAX_TOKENS = 4096
COMPACTION_THRESHOLD = 60000  # chars before compaction triggers
CACHE_TTL = 3600  # 1 hour cache for identical queries

# Token cost estimates (per 1M tokens, USD)
MODEL_COSTS = {
    'claude-opus-4-6': {'input': 15.0, 'output': 75.0},
    'claude-sonnet-4': {'input': 3.0, 'output': 15.0},
    'gpt-5.3-codex': {'input': 2.0, 'output': 8.0},
    'gpt-5.1-codex': {'input': 1.5, 'output': 6.0},
    'grok-4': {'input': 3.0, 'output': 15.0},
    'gemini-3-pro-preview': {'input': 1.25, 'output': 10.0},
    'gemini-3-flash-preview': {'input': 0.15, 'output': 0.60},
}

# Model routing thresholds
SIMPLE_QUERY_MAX_CHARS = 200  # short queries → cheap model
COMPLEX_INDICATORS = ['코드', '분석', '보안', '최적화', '설계', '구현',
                       'code', 'analyze', 'security', 'build', 'implement',
                       'refactor', '디버그', 'debug', '아키텍처']

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('salmalm')

# ============================================================
# CRYPTO — AES-256-GCM with HMAC-CTR fallback
# ============================================================
HAS_CRYPTO = False
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes as crypto_hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
    log.info("✅ cryptography available — AES-256-GCM enabled")
except ImportError:
    log.warning("⚠️ cryptography not installed — falling back to HMAC-CTR")


def _derive_key(password: str, salt: bytes, length: int = 32) -> bytes:
    if HAS_CRYPTO:
        kdf = PBKDF2HMAC(
            algorithm=crypto_hashes.SHA256(), length=length,
            salt=salt, iterations=PBKDF2_ITER
        )
        return kdf.derive(password.encode('utf-8'))
    else:
        return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'),
                                    salt, PBKDF2_ITER, dklen=length)


class Vault:
    """Encrypted key-value store for API keys and secrets."""

    def __init__(self):
        self._data: dict = {}
        self._password: Optional[str] = None
        self._salt: Optional[bytes] = None

    def create(self, password: str):
        self._password = password
        self._salt = secrets.token_bytes(16)
        self._data = {}
        self._save()

    def unlock(self, password: str) -> bool:
        if not VAULT_FILE.exists():
            return False
        raw = VAULT_FILE.read_bytes()
        if len(raw) < 17:
            return False
        version = raw[0:1]
        self._salt = raw[1:17]
        ciphertext = raw[17:]
        self._password = password
        try:
            key = _derive_key(password, self._salt)
            if version == b'\x03' and HAS_CRYPTO:
                # AES-256-GCM
                nonce = ciphertext[:12]
                ct = ciphertext[12:]
                aesgcm = AESGCM(key)
                plaintext = aesgcm.decrypt(nonce, ct, None)
            elif version == b'\x02' or (version == b'\x03' and not HAS_CRYPTO):
                # HMAC-CTR fallback
                tag = ciphertext[:32]
                ct = ciphertext[32:]
                hmac_key = _derive_key(password, self._salt + b'hmac', 32)
                expected = hmac.new(hmac_key, ct, hashlib.sha256).digest()
                if not hmac.compare_digest(tag, expected):
                    return False
                enc_key = _derive_key(password, self._salt + b'enc', 32)
                plaintext = self._ctr_decrypt(enc_key, ct)
            else:
                return False
            self._data = json.loads(plaintext.decode('utf-8'))
            return True
        except Exception:
            self._password = None
            return False

    def _save(self):
        if not self._password or self._salt is None:
            return
        plaintext = json.dumps(self._data).encode('utf-8')
        key = _derive_key(self._password, self._salt)
        if HAS_CRYPTO:
            nonce = secrets.token_bytes(12)
            aesgcm = AESGCM(key)
            ct = aesgcm.encrypt(nonce, plaintext, None)
            VAULT_FILE.write_bytes(VAULT_VERSION + self._salt + nonce + ct)
        else:
            # HMAC-CTR
            enc_key = _derive_key(self._password, self._salt + b'enc', 32)
            ct = self._ctr_encrypt(enc_key, plaintext)
            hmac_key = _derive_key(self._password, self._salt + b'hmac', 32)
            tag = hmac.new(hmac_key, ct, hashlib.sha256).digest()
            VAULT_FILE.write_bytes(b'\x02' + self._salt + tag + ct)

    @staticmethod
    def _ctr_encrypt(key: bytes, data: bytes) -> bytes:
        out, ctr = bytearray(), 0
        for i in range(0, len(data), 32):
            block = hmac.new(key, ctr.to_bytes(8, 'big'), hashlib.sha256).digest()
            chunk = data[i:i+32]
            out.extend(b ^ k for b, k in zip(chunk, block[:len(chunk)]))
            ctr += 1
        return bytes(out)

    _ctr_decrypt = _ctr_encrypt  # symmetric

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self._save()

    def delete(self, key: str):
        self._data.pop(key, None)
        self._save()

    def keys(self):
        return list(self._data.keys())

    @property
    def is_unlocked(self):
        return self._password is not None


vault = Vault()

# ============================================================
# AUDIT LOG — SHA256 hash chain
# ============================================================
_audit_lock = threading.Lock()


def _init_audit_db():
    conn = sqlite3.connect(str(AUDIT_DB))
    conn.execute('''CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL, event TEXT NOT NULL,
        detail TEXT, prev_hash TEXT, hash TEXT NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS usage_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL, model TEXT NOT NULL,
        input_tokens INTEGER, output_tokens INTEGER, cost REAL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS session_store (
        session_id TEXT PRIMARY KEY,
        messages TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )''')
    conn.commit()
    conn.close()


def audit_log(event: str, detail: str = ''):
    with _audit_lock:
        conn = sqlite3.connect(str(AUDIT_DB))
        row = conn.execute(
            'SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1'
        ).fetchone()
        prev = row[0] if row else '0' * 64
        ts = datetime.now(KST).isoformat()
        payload = f"{ts}|{event}|{detail}|{prev}"
        h = hashlib.sha256(payload.encode()).hexdigest()
        conn.execute(
            'INSERT INTO audit_log (ts, event, detail, prev_hash, hash) VALUES (?,?,?,?,?)',
            (ts, event, detail[:500], prev, h)
        )
        conn.commit()
        conn.close()


# ============================================================
# RESPONSE CACHE
# ============================================================
class ResponseCache:
    """Simple TTL cache for LLM responses to avoid duplicate calls."""

    def __init__(self, max_size=100, ttl=CACHE_TTL):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    def _key(self, model: str, messages: list) -> str:
        content = json.dumps({'m': model, 'msgs': messages[-3:]}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(self, model: str, messages: list) -> Optional[str]:
        k = self._key(model, messages)
        if k in self._cache:
            entry = self._cache[k]
            if time.time() - entry['ts'] < self._ttl:
                self._cache.move_to_end(k)
                log.info(f"💰 Cache hit — saved API call")
                return entry['response']
            del self._cache[k]
        return None

    def put(self, model: str, messages: list, response: str):
        k = self._key(model, messages)
        self._cache[k] = {'response': response, 'ts': time.time()}
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)


response_cache = ResponseCache()

# ============================================================
# TOKEN COUNTER & COST TRACKER
# ============================================================
_usage_lock = threading.Lock()
_usage = {'total_input': 0, 'total_output': 0, 'total_cost': 0.0,
          'by_model': {}, 'session_start': time.time()}

def _restore_usage():
    """Restore cumulative usage from SQLite on startup."""
    try:
        conn = sqlite3.connect(str(AUDIT_DB))
        rows = conn.execute('SELECT model, SUM(input_tokens), SUM(output_tokens), SUM(cost), COUNT(*) FROM usage_stats GROUP BY model').fetchall()
        for model, inp, out, cost, calls in rows:
            short = model.split('/')[-1] if '/' in model else model
            _usage['total_input'] += (inp or 0)
            _usage['total_output'] += (out or 0)
            _usage['total_cost'] += (cost or 0)
            _usage['by_model'][short] = {'input': inp or 0, 'output': out or 0,
                                          'cost': cost or 0, 'calls': calls or 0}
        conn.close()
        if _usage['total_cost'] > 0:
            log.info(f"📊 Usage restored: ${_usage['total_cost']:.4f} total")
    except Exception as e:
        log.warning(f"Usage restore failed: {e}")


def track_usage(model: str, input_tokens: int, output_tokens: int):
    with _usage_lock:
        short = model.split('/')[-1] if '/' in model else model
        cost_info = MODEL_COSTS.get(short, {'input': 1.0, 'output': 5.0})
        cost = (input_tokens * cost_info['input'] + output_tokens * cost_info['output']) / 1_000_000
        _usage['total_input'] += input_tokens
        _usage['total_output'] += output_tokens
        _usage['total_cost'] += cost
        if short not in _usage['by_model']:
            _usage['by_model'][short] = {'input': 0, 'output': 0, 'cost': 0.0, 'calls': 0}
        _usage['by_model'][short]['input'] += input_tokens
        _usage['by_model'][short]['output'] += output_tokens
        _usage['by_model'][short]['cost'] += cost
        _usage['by_model'][short]['calls'] += 1
        # Persist to SQLite
        try:
            conn = sqlite3.connect(str(AUDIT_DB))
            conn.execute('INSERT INTO usage_stats (ts, model, input_tokens, output_tokens, cost) VALUES (?,?,?,?,?)',
                         (datetime.now(KST).isoformat(), model, input_tokens, output_tokens, cost))
            conn.commit()
            conn.close()
        except Exception:
            pass


def get_usage_report() -> dict:
    with _usage_lock:
        elapsed = time.time() - _usage['session_start']
        return {**_usage, 'elapsed_hours': round(elapsed / 3600, 2)}


# ============================================================
# MODEL ROUTER — auto-select cheapest model that fits
# ============================================================
class ModelRouter:
    """Routes queries to appropriate models based on complexity."""

    # Tier 1: cheap & fast, Tier 2: balanced, Tier 3: powerful
    TIERS = {
        1: ['google/gemini-3-flash-preview', 'xai/grok-4'],
        2: ['anthropic/claude-sonnet-4-20250514', 'xai/grok-4', 'google/gemini-3-pro-preview'],
        3: ['anthropic/claude-opus-4-6', 'anthropic/claude-sonnet-4-20250514'],
    }

    def __init__(self):
        self.default_tier = 2
        self.force_model: Optional[str] = None

    def route(self, user_message: str, has_tools: bool = False) -> str:
        if self.force_model:
            return self.force_model

        msg = user_message.lower()
        msg_len = len(user_message)

        # Tier 3: complex tasks
        if any(kw in msg for kw in COMPLEX_INDICATORS) or msg_len > 1000:
            return self._pick_available(3)

        # Tier 1: simple queries
        if msg_len < SIMPLE_QUERY_MAX_CHARS and not has_tools:
            return self._pick_available(1)

        # Tier 2: default
        return self._pick_available(2)

    def _pick_available(self, tier: int) -> str:
        models = self.TIERS.get(tier, self.TIERS[2])
        for m in models:
            provider = m.split('/')[0]
            key_name = f'{provider}_api_key'
            if vault.get(key_name):
                return m
        # Fallback: try any available model
        for t in [2, 1, 3]:
            for m in self.TIERS.get(t, []):
                provider = m.split('/')[0]
                if vault.get(f'{provider}_api_key'):
                    return m
        return 'google/gemini-3-flash-preview'  # last resort


router = ModelRouter()

# ============================================================
# LLM API CALLS
# ============================================================
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
             max_tokens: int = DEFAULT_MAX_TOKENS) -> dict:
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
    api_key = vault.get(f'{provider}_api_key')
    if not api_key:
        return {'content': f'❌ {provider} API 키가 설정되지 않았습니다.', 'tool_calls': [],
                'usage': {'input': 0, 'output': 0}, 'model': model}

    log.info(f"🤖 LLM call: {model} ({len(messages)} msgs, tools={len(tools or [])})")

    try:
        result = _call_provider(provider, api_key, model_id, messages, tools, max_tokens)
        result['model'] = model
        usage = result.get('usage', {})
        track_usage(model, usage.get('input', 0), usage.get('output', 0))
        if not result.get('tool_calls') and result.get('content'):
            response_cache.put(model, messages, result['content'])
        return result
    except Exception as e:
        log.error(f"LLM error ({model}): {e}")
        # Auto-fallback to next available provider
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
                if fb_provider == 'google':
                    fb_tools = None
                elif fb_provider == 'anthropic':
                    fb_tools = [{'name': t['name'], 'description': t['description'],
                                 'input_schema': t['input_schema']} for t in TOOL_DEFINITIONS]
                elif fb_provider in ('openai', 'xai'):
                    fb_tools = [{'name': t['name'], 'description': t['description'],
                                 'parameters': t['input_schema']} for t in TOOL_DEFINITIONS]
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


def _call_provider(provider, api_key, model_id, messages, tools, max_tokens):
    if provider == 'anthropic':
        return _call_anthropic(api_key, model_id, messages, tools, max_tokens)
    elif provider in ('openai', 'xai'):
        base_url = 'https://api.x.ai/v1' if provider == 'xai' else 'https://api.openai.com/v1'
        return _call_openai(api_key, model_id, messages, tools, max_tokens, base_url)
    elif provider == 'google':
        return _call_google(api_key, model_id, messages, max_tokens)
    else:
        raise ValueError(f'Unknown provider: {provider}')


def _call_anthropic(api_key, model_id, messages, tools, max_tokens):
    system_msgs = [m['content'] for m in messages if m['role'] == 'system']
    chat_msgs = [m for m in messages if m['role'] != 'system']
    body = {
        'model': model_id, 'max_tokens': max_tokens,
        'messages': chat_msgs,
    }
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
    tool_calls = []
    for block in resp.get('content', []):
        if block['type'] == 'text':
            content += block['text']
        elif block['type'] == 'tool_use':
            tool_calls.append({
                'id': block['id'], 'name': block['name'],
                'arguments': block['input']
            })
    usage = resp.get('usage', {})
    return {
        'content': content, 'tool_calls': tool_calls,
        'usage': {'input': usage.get('input_tokens', 0),
                  'output': usage.get('output_tokens', 0)}
    }


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
    resp = _http_post(
        f'{base_url}/chat/completions',
        {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
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


def _call_google(api_key, model_id, messages, max_tokens):
    # Gemini API — text only (no tool support for simplicity)
    parts = []
    for m in messages:
        role = 'user' if m['role'] in ('user', 'system') else 'model'
        parts.append({'role': role, 'parts': [{'text': m['content']}]})
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
    resp = _http_post(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}',
        {'Content-Type': 'application/json'}, body
    )
    text = ''
    for cand in resp.get('candidates', []):
        for part in cand.get('content', {}).get('parts', []):
            text += part.get('text', '')
    usage_meta = resp.get('usageMetadata', {})
    return {
        'content': text, 'tool_calls': [],
        'usage': {'input': usage_meta.get('promptTokenCount', 0),
                  'output': usage_meta.get('candidatesTokenCount', 0)}
    }


# ============================================================
# CONTEXT COMPRESSION (Compaction)
# ============================================================
def compact_messages(messages: list, model: str = None) -> list:
    """If conversation is too long, summarize older messages."""
    total_chars = sum(len(m.get('content', '')) for m in messages)
    if total_chars < COMPACTION_THRESHOLD:
        return messages

    log.info(f"📦 Compacting {len(messages)} messages ({total_chars} chars)")

    # Keep system messages and last 6 messages
    system_msgs = [m for m in messages if m['role'] == 'system']
    recent = messages[-6:]
    to_summarize = [m for m in messages if m['role'] != 'system' and m not in recent]

    if not to_summarize:
        return messages

    summary_text = '\n'.join(
        f"[{m['role']}]: {m['content'][:300]}" for m in to_summarize[-20:]
    )

    # Use cheapest model for compaction
    summary_result = call_llm(
        [{'role': 'system', 'content': '다음 대화를 핵심만 간결하게 한국어로 요약해. 3~5문장으로.'},
         {'role': 'user', 'content': summary_text}],
        model='google/gemini-3-flash-preview',
        max_tokens=500
    )

    compacted = system_msgs + [
        {'role': 'system', 'content': f'[이전 대화 요약]\n{summary_result["content"]}'}
    ] + recent

    log.info(f"📦 Compacted: {len(messages)} → {len(compacted)} messages")
    return compacted


# ============================================================
# TOOLS
# ============================================================
TOOL_DEFINITIONS = [
    {
        'name': 'exec',
        'description': '셸 명령어를 실행합니다. 위험한 명령은 차단됩니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'command': {'type': 'string', 'description': '실행할 셸 명령어'},
                'timeout': {'type': 'integer', 'description': '타임아웃(초)', 'default': 30}
            },
            'required': ['command']
        }
    },
    {
        'name': 'read_file',
        'description': '파일 내용을 읽습니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': '파일 경로'},
                'offset': {'type': 'integer', 'description': '시작 줄 번호 (1-based)'},
                'limit': {'type': 'integer', 'description': '읽을 줄 수'}
            },
            'required': ['path']
        }
    },
    {
        'name': 'write_file',
        'description': '파일에 내용을 씁니다. 없으면 생성합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': '파일 경로'},
                'content': {'type': 'string', 'description': '파일 내용'}
            },
            'required': ['path', 'content']
        }
    },
    {
        'name': 'edit_file',
        'description': '파일에서 특정 텍스트를 찾아 교체합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': '파일 경로'},
                'old_text': {'type': 'string', 'description': '찾을 텍스트'},
                'new_text': {'type': 'string', 'description': '바꿀 텍스트'}
            },
            'required': ['path', 'old_text', 'new_text']
        }
    },
    {
        'name': 'web_search',
        'description': '웹 검색을 수행합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': '검색 쿼리'},
                'count': {'type': 'integer', 'description': '결과 수', 'default': 5}
            },
            'required': ['query']
        }
    },
    {
        'name': 'web_fetch',
        'description': 'URL에서 내용을 가져옵니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'url': {'type': 'string', 'description': 'URL'},
                'max_chars': {'type': 'integer', 'description': '최대 글자 수', 'default': 10000}
            },
            'required': ['url']
        }
    },
    {
        'name': 'memory_read',
        'description': 'MEMORY.md 또는 memory/ 파일을 읽습니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'file': {'type': 'string', 'description': '파일명 (예: MEMORY.md, 2026-02-18.md)'}
            },
            'required': ['file']
        }
    },
    {
        'name': 'memory_write',
        'description': 'MEMORY.md 또는 memory/ 파일에 씁니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'file': {'type': 'string', 'description': '파일명'},
                'content': {'type': 'string', 'description': '내용'}
            },
            'required': ['file', 'content']
        }
    },
    {
        'name': 'usage_report',
        'description': '현재 세션의 토큰 사용량과 비용을 보여줍니다.',
        'input_schema': {'type': 'object', 'properties': {}}
    },
    {
        'name': 'memory_search',
        'description': 'MEMORY.md와 memory/*.md 파일에서 키워드로 관련 내용을 검색합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': '검색할 키워드 또는 문장'},
                'max_results': {'type': 'integer', 'description': '최대 결과 수', 'default': 5}
            },
            'required': ['query']
        }
    },
    {
        'name': 'image_generate',
        'description': '이미지를 생성합니다. xAI Aurora 또는 OpenAI DALL-E를 사용합니다.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'prompt': {'type': 'string', 'description': '이미지 생성 프롬프트 (영어 권장)'},
                'provider': {'type': 'string', 'description': 'xai 또는 openai', 'default': 'xai'},
                'size': {'type': 'string', 'description': '이미지 크기', 'default': '1024x1024'}
            },
            'required': ['prompt']
        }
    },
    {
        'name': 'tts',
        'description': '텍스트를 음성으로 변환합니다 (OpenAI TTS).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'text': {'type': 'string', 'description': '변환할 텍스트'},
                'voice': {'type': 'string', 'description': 'alloy, echo, fable, onyx, nova, shimmer', 'default': 'nova'}
            },
            'required': ['text']
        }
    },
]


def _is_safe_command(cmd: str) -> tuple[bool, str]:
    """Check if command is safe to execute."""
    first_word = cmd.strip().split()[0].split('/')[-1] if cmd.strip() else ''
    if first_word in EXEC_BLOCKLIST:
        return False, f'차단된 명령어: {first_word}'
    for pattern in EXEC_BLOCKLIST_PATTERNS:
        if re.search(pattern, cmd):
            return False, f'차단된 패턴: {pattern}'
    return True, ''


def _resolve_path(path: str) -> Path:
    """Resolve path, preventing traversal outside workspace."""
    p = Path(path)
    if not p.is_absolute():
        p = WORKSPACE_DIR / p
    p = p.resolve()
    # Allow workspace and home directory access
    allowed = [WORKSPACE_DIR, Path.home()]
    if not any(str(p).startswith(str(a)) for a in allowed):
        raise PermissionError(f'접근 불가: {p}')
    if p.name in PROTECTED_FILES and 'write' in str(traceback.extract_stack()):
        raise PermissionError(f'보호된 파일: {p.name}')
    return p


def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return result string."""
    audit_log('tool_exec', f'{name}: {json.dumps(args, ensure_ascii=False)[:200]}')
    try:
        if name == 'exec':
            cmd = args.get('command', '')
            safe, reason = _is_safe_command(cmd)
            if not safe:
                return f'❌ {reason}'
            timeout = min(args.get('timeout', 30), 120)
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True,
                    timeout=timeout, cwd=str(WORKSPACE_DIR)
                )
                output = result.stdout[-5000:] if result.stdout else ''
                if result.stderr:
                    output += f'\n[stderr]: {result.stderr[-2000:]}'
                if result.returncode != 0:
                    output += f'\n[exit code]: {result.returncode}'
                return output or '(no output)'
            except subprocess.TimeoutExpired:
                return f'❌ 타임아웃 ({timeout}초)'

        elif name == 'read_file':
            p = _resolve_path(args['path'])
            if not p.exists():
                return f'❌ 파일 없음: {p}'
            text = p.read_text(encoding='utf-8', errors='replace')
            lines = text.splitlines()
            offset = args.get('offset', 1) - 1
            limit = args.get('limit', len(lines))
            selected = lines[offset:offset + limit]
            return '\n'.join(selected)[:50000]

        elif name == 'write_file':
            p = _resolve_path(args['path'])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args['content'], encoding='utf-8')
            return f'✅ {p} ({len(args["content"])} chars)'

        elif name == 'edit_file':
            p = _resolve_path(args['path'])
            text = p.read_text(encoding='utf-8')
            if args['old_text'] not in text:
                return f'❌ 텍스트를 찾을 수 없음'
            text = text.replace(args['old_text'], args['new_text'], 1)
            p.write_text(text, encoding='utf-8')
            return f'✅ 수정 완료: {p}'

        elif name == 'web_search':
            api_key = vault.get('brave_api_key')
            if not api_key:
                return '❌ Brave Search API 키가 없습니다'
            query = urllib.parse.quote(args['query'])
            count = min(args.get('count', 5), 10)
            resp = _http_get(
                f'https://api.search.brave.com/res/v1/web/search?q={query}&count={count}',
                {'Accept': 'application/json', 'X-Subscription-Token': api_key}
            )
            results = []
            for r in resp.get('web', {}).get('results', [])[:count]:
                results.append(f"**{r['title']}**\n{r['url']}\n{r.get('description', '')}\n")
            return '\n'.join(results) or '결과 없음'

        elif name == 'web_fetch':
            url = args['url']
            max_chars = args.get('max_chars', 10000)
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (SalmAlm/0.1)'
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
            # Simple HTML to text
            text = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.S)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.S)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:max_chars]

        elif name == 'memory_read':
            fname = args['file']
            if fname == 'MEMORY.md':
                p = MEMORY_FILE
            else:
                p = MEMORY_DIR / fname
            if not p.exists():
                return f'❌ 파일 없음: {fname}'
            return p.read_text(encoding='utf-8')[:30000]

        elif name == 'memory_write':
            fname = args['file']
            if fname == 'MEMORY.md':
                p = MEMORY_FILE
            else:
                p = MEMORY_DIR / fname
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args['content'], encoding='utf-8')
            return f'✅ {fname} 저장 완료'

        elif name == 'usage_report':
            report = get_usage_report()
            lines = [f"📊 삶앎 사용량 리포트",
                     f"⏱️ 가동: {report['elapsed_hours']}시간",
                     f"📥 입력: {report['total_input']:,} 토큰",
                     f"📤 출력: {report['total_output']:,} 토큰",
                     f"💰 총 비용: ${report['total_cost']:.4f}", ""]
            for m, d in report.get('by_model', {}).items():
                lines.append(f"  {m}: {d['calls']}회, ${d['cost']:.4f}")
            return '\n'.join(lines)

        elif name == 'memory_search':
            query = args['query'].lower()
            keywords = query.split()
            max_results = args.get('max_results', 5)
            results = []
            # Search MEMORY.md and all memory/*.md
            search_files = []
            if MEMORY_FILE.exists():
                search_files.append(('MEMORY.md', MEMORY_FILE))
            for f in sorted(MEMORY_DIR.glob('*.md')):
                search_files.append((f'memory/{f.name}', f))
            for label, fpath in search_files:
                try:
                    text = fpath.read_text(encoding='utf-8', errors='replace')
                    lines = text.splitlines()
                    for i, line in enumerate(lines):
                        ll = line.lower()
                        score = sum(1 for kw in keywords if kw in ll)
                        if score > 0:
                            # Get context (3 lines around match)
                            start = max(0, i - 1)
                            end = min(len(lines), i + 2)
                            snippet = '\n'.join(lines[start:end])
                            results.append((score, label, i + 1, snippet))
                except Exception:
                    continue
            results.sort(key=lambda x: -x[0])
            if not results:
                return f'검색 결과 없음: "{args["query"]}"'
            out = []
            for score, label, lineno, snippet in results[:max_results]:
                out.append(f'📍 {label}#{lineno} (score:{score})\n{snippet}\n')
            return '\n'.join(out)

        elif name == 'image_generate':
            prompt = args['prompt']
            provider = args.get('provider', 'xai')
            size = args.get('size', '1024x1024')
            save_dir = WORKSPACE_DIR / 'uploads'
            save_dir.mkdir(exist_ok=True)
            fname = f"gen_{int(time.time())}.png"
            save_path = save_dir / fname

            if provider == 'xai':
                api_key = vault.get('xai_api_key')
                if not api_key:
                    return '❌ xAI API 키가 없습니다'
                resp = _http_post(
                    'https://api.x.ai/v1/images/generations',
                    {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                    {'model': 'aurora', 'prompt': prompt, 'n': 1, 'size': size,
                     'response_format': 'b64_json'}
                )
                import base64 as b64mod
                img_data = b64mod.b64decode(resp['data'][0]['b64_json'])
                save_path.write_bytes(img_data)
            else:
                api_key = vault.get('openai_api_key')
                if not api_key:
                    return '❌ OpenAI API 키가 없습니다'
                resp = _http_post(
                    'https://api.openai.com/v1/images/generations',
                    {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                    {'model': 'gpt-image-1', 'prompt': prompt, 'n': 1, 'size': size,
                     'output_format': 'b64_json'}
                )
                import base64 as b64mod
                img_data = b64mod.b64decode(resp['data'][0]['b64_json'])
                save_path.write_bytes(img_data)

            size_kb = len(img_data) / 1024
            log.info(f"🎨 Image generated: {fname} ({size_kb:.1f}KB)")
            return f'✅ 이미지 생성 완료: uploads/{fname} ({size_kb:.1f}KB)\n프롬프트: {prompt}'

        elif name == 'tts':
            text = args['text']
            voice = args.get('voice', 'nova')
            api_key = vault.get('openai_api_key')
            if not api_key:
                return '❌ OpenAI API 키가 없습니다'
            save_dir = WORKSPACE_DIR / 'uploads'
            save_dir.mkdir(exist_ok=True)
            fname = f"tts_{int(time.time())}.mp3"
            save_path = save_dir / fname
            data = json.dumps({'model': 'tts-1', 'input': text, 'voice': voice}).encode()
            req = urllib.request.Request(
                'https://api.openai.com/v1/audio/speech',
                data=data,
                headers={'Authorization': f'Bearer {api_key}',
                         'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                audio = resp.read()
            save_path.write_bytes(audio)
            size_kb = len(audio) / 1024
            log.info(f"🔊 TTS generated: {fname} ({size_kb:.1f}KB)")
            return f'✅ 음성 생성 완료: uploads/{fname} ({size_kb:.1f}KB)\n텍스트: {text[:100]}'

        else:
            return f'❌ 알 수 없는 도구: {name}'

    except PermissionError as e:
        return f'❌ 권한 거부: {e}'
    except Exception as e:
        log.error(f"Tool error ({name}): {e}")
        return f'❌ 도구 오류: {str(e)[:200]}'


# ============================================================
# SYSTEM PROMPT — minimal for token savings
# ============================================================
def build_system_prompt(full: bool = True) -> str:
    """Build system prompt from SOUL.md + context files.
    full=True: load everything (first message / refresh)
    full=False: minimal reload (mid-conversation refresh)
    """
    parts = []

    # SOUL.md (persona — FULL load, this IS who we are)
    if SOUL_FILE.exists():
        soul = SOUL_FILE.read_text(encoding='utf-8')
        if full:
            parts.append(soul)
        else:
            parts.append(soul[:3000])

    # IDENTITY.md
    id_file = BASE_DIR / 'IDENTITY.md'
    if id_file.exists():
        parts.append(id_file.read_text(encoding='utf-8'))

    # USER.md
    if USER_FILE.exists():
        parts.append(USER_FILE.read_text(encoding='utf-8'))

    # MEMORY.md (full on first load, recent on refresh)
    if MEMORY_FILE.exists():
        mem = MEMORY_FILE.read_text(encoding='utf-8')
        if full:
            parts.append(f"# 장기 기억\n{mem}")
        else:
            parts.append(f"# 장기 기억 (최근)\n{mem[-2000:]}")

    # Today's memory log
    today = datetime.now(KST).strftime('%Y-%m-%d')
    today_log = MEMORY_DIR / f'{today}.md'
    if today_log.exists():
        tlog = today_log.read_text(encoding='utf-8')
        parts.append(f"# 오늘의 기록\n{tlog[-2000:]}")

    # AGENTS.md (behavior rules)
    if AGENTS_FILE.exists():
        agents = AGENTS_FILE.read_text(encoding='utf-8')
        if full:
            parts.append(agents)
        else:
            parts.append(agents[:2000])

    # TOOLS.md
    tools_file = BASE_DIR / 'TOOLS.md'
    if tools_file.exists():
        parts.append(tools_file.read_text(encoding='utf-8'))

    # HEARTBEAT.md
    hb_file = BASE_DIR / 'HEARTBEAT.md'
    if hb_file.exists():
        parts.append(hb_file.read_text(encoding='utf-8'))

    # Context
    now = datetime.now(KST)
    parts.append(f"현재: {now.strftime('%Y-%m-%d %H:%M')} KST")

    # Tool instructions
    parts.append(textwrap.dedent("""
    [삶앎 시스템]
    - 도구 사용 가능: exec(셸), read_file, write_file, edit_file, web_search, web_fetch, memory_read, memory_write, memory_search, image_generate, tts, usage_report
    - 파일 업로드: 텔레그램에서 보낸 파일은 uploads/ 폴더에 저장됨
    - 워크스페이스: 이 디렉토리가 작업 공간
    - 메모리: MEMORY.md(장기), memory/YYYY-MM-DD.md(일일)에 기록
    - 중요한 건 반드시 메모리에 기록할 것
    """).strip())

    return '\n\n'.join(parts)


# ============================================================
# CONVERSATION MANAGER
# ============================================================
class Session:
    def __init__(self, session_id: str):
        self.id = session_id
        self.messages: list = []
        self.created = time.time()
        self.last_active = time.time()

    def add_system(self, content: str):
        # Replace existing system message
        self.messages = [m for m in self.messages if m['role'] != 'system']
        self.messages.insert(0, {'role': 'system', 'content': content})

    def _persist(self):
        """Save session to SQLite (only text messages, skip image data)."""
        try:
            # Filter out large binary data from messages
            saveable = []
            for m in self.messages[-50:]:  # Keep last 50 messages
                if isinstance(m.get('content'), list):
                    # Multimodal — save text parts only
                    texts = [b for b in m['content'] if b.get('type') == 'text']
                    if texts:
                        saveable.append({**m, 'content': texts})
                elif isinstance(m.get('content'), str):
                    saveable.append(m)
            conn = sqlite3.connect(str(AUDIT_DB))
            conn.execute('INSERT OR REPLACE INTO session_store (session_id, messages, updated_at) VALUES (?,?,?)',
                         (self.id, json.dumps(saveable, ensure_ascii=False), datetime.now(KST).isoformat()))
            conn.commit()
            conn.close()
        except Exception as e:
            log.warning(f"Session persist error: {e}")

    def add_user(self, content: str):
        self.messages.append({'role': 'user', 'content': content})
        self.last_active = time.time()

    def add_assistant(self, content: str):
        self.messages.append({'role': 'assistant', 'content': content})
        self._persist()

    def add_tool_results(self, results: list):
        """Add tool results as a single user message with all results.
        results: list of {'tool_use_id': str, 'content': str}
        """
        content = [{'type': 'tool_result', 'tool_use_id': r['tool_use_id'],
                     'content': r['content']} for r in results]
        self.messages.append({'role': 'user', 'content': content})


_sessions: dict[str, Session] = {}


def get_session(session_id: str) -> Session:
    if session_id not in _sessions:
        _sessions[session_id] = Session(session_id)
        # Try to restore from SQLite
        try:
            conn = sqlite3.connect(str(AUDIT_DB))
            row = conn.execute('SELECT messages FROM session_store WHERE session_id=?', (session_id,)).fetchone()
            conn.close()
            if row:
                restored = json.loads(row[0])
                _sessions[session_id].messages = restored
                log.info(f"📋 Session restored: {session_id} ({len(restored)} msgs)")
                # Refresh system prompt
                _sessions[session_id].add_system(build_system_prompt(full=False))
                return _sessions[session_id]
        except Exception as e:
            log.warning(f"Session restore error: {e}")
        _sessions[session_id].add_system(build_system_prompt(full=True))
        log.info(f"📋 New session: {session_id} (system prompt: {len(_sessions[session_id].messages[0]['content'])} chars)")
    return _sessions[session_id]


async def process_message(session_id: str, user_message: str,
                          model_override: str = None,
                          image_data: tuple = None,
                          on_tool: callable = None) -> str:
    """Process a user message through the full pipeline.
    image_data: (base64_str, mime_type) or None
    """
    session = get_session(session_id)
    # Handle slash commands
    cmd = user_message.strip()
    if cmd == '/clear':
        session.messages = [m for m in session.messages if m['role'] == 'system'][:1]
        return '대화가 초기화되었습니다.'
    if cmd == '/help':
        return """😈 **삶앎 v{ver} 명령어**

**/clear** — 대화 초기화
**/help** — 이 도움말
**/model <이름>** — 모델 변경 (auto, claude, gpt, grok, gemini)
**/status** — 사용량 + 비용

**사용 가능한 도구 (AI가 자동 사용):**
🔧 exec — 셸 명령어
📄 read_file / write_file / edit_file — 파일 조작
🔍 web_search / web_fetch — 웹 검색/크롤링
🧠 memory_read / memory_write / memory_search — 기억
🎨 image_generate — 이미지 생성 (xAI Aurora / OpenAI)
🔊 tts — 텍스트→음성 (OpenAI)
📊 usage_report — 사용량 보고

**단축키:** Shift+Enter 줄바꿈 | Ctrl+V 이미지 붙여넣기""".format(ver=VERSION)
    if cmd == '/status':
        return execute_tool('usage_report', {})
    if cmd.startswith('/model '):
        model_name = cmd[7:].strip()
        model_map = {'auto': None, 'claude': 'anthropic/claude-sonnet-4-20250514',
                     'opus': 'anthropic/claude-opus-4-6', 'gpt': 'openai/gpt-5.3-codex',
                     'grok': 'xai/grok-4', 'gemini': 'google/gemini-3-pro-preview',
                     'flash': 'google/gemini-3-flash-preview'}
        if model_name in model_map:
            router.force_model = model_map[model_name]
            return f'모델 변경: {model_name}' + (' (자동 라우팅)' if not router.force_model else '')
        return f'알 수 없는 모델: {model_name}\\n가능: {", ".join(model_map.keys())}'
    if image_data:
        # Multimodal message with image
        b64, mime = image_data
        log.info(f"🖼️ Image attached: {mime}, {len(b64)//1024}KB base64")
        content = [
            {'type': 'image', 'source': {'type': 'base64', 'media_type': mime, 'data': b64}},
            {'type': 'text', 'text': user_message or '이 이미지를 분석해줘.'}
        ]
        session.messages.append({'role': 'user', 'content': content})
    else:
        session.add_user(user_message)

    # Compact if needed
    session.messages = compact_messages(session.messages)

    # Refresh system prompt periodically (minimal version to save tokens)
    if len(session.messages) % 20 == 0:
        session.add_system(build_system_prompt(full=False))

    # Tool loop (max 30 iterations)
    for iteration in range(30):
        model = model_override or router.route(user_message, has_tools=True)

        # Convert tools for the provider
        provider = model.split('/')[0] if '/' in model else 'anthropic'
        if provider == 'google':
            tools = None  # Gemini: no tools
        elif provider in ('openai', 'xai'):
            tools = [{'name': t['name'], 'description': t['description'],
                       'parameters': t['input_schema']} for t in TOOL_DEFINITIONS]
        elif provider == 'anthropic':
            tools = [{'name': t['name'], 'description': t['description'],
                       'input_schema': t['input_schema']} for t in TOOL_DEFINITIONS]
        else:
            tools = TOOL_DEFINITIONS

        result = call_llm(session.messages, model=model, tools=tools)

        if result.get('tool_calls'):
            # Build assistant message with tool_use blocks for Anthropic
            if provider == 'anthropic':
                content_blocks = []
                if result.get('content'):
                    content_blocks.append({'type': 'text', 'text': result['content']})
                for tc in result['tool_calls']:
                    content_blocks.append({
                        'type': 'tool_use', 'id': tc['id'],
                        'name': tc['name'], 'input': tc['arguments']
                    })
                session.messages.append({'role': 'assistant', 'content': content_blocks})
                # Execute tools and collect results
                tool_results = []
                for tc in result['tool_calls']:
                    if on_tool:
                        on_tool(tc['name'], tc['arguments'])
                    tr = execute_tool(tc['name'], tc['arguments'])
                    tool_results.append({'tool_use_id': tc['id'], 'content': tr})
                session.add_tool_results(tool_results)
            else:
                session.add_assistant(result.get('content', ''))
                for tc in result['tool_calls']:
                    if on_tool:
                        on_tool(tc['name'], tc['arguments'])
                    tr = execute_tool(tc['name'], tc['arguments'])
                    session.messages.append({
                        'role': 'tool', 'tool_call_id': tc['id'],
                        'name': tc['name'], 'content': tr
                    })
            continue  # Let LLM process tool results

        # No tool calls — final response
        response = result.get('content', '응답을 생성할 수 없습니다.')
        session.add_assistant(response)

        log.info(f"💬 Response ({result.get('model', '?')}): {len(response)} chars, "
                 f"iteration {iteration + 1}")
        return response

    # Loop exhausted — return last assistant content if any
    for m in reversed(session.messages):
        if m['role'] == 'assistant':
            content = m.get('content', '')
            if isinstance(content, str) and content:
                return content + "\n\n⚠️ (도구 실행 30회 도달, 여기까지 응답)"
            elif isinstance(content, list):
                texts = [b['text'] for b in content if b.get('type') == 'text']
                if texts:
                    return '\n'.join(texts) + "\n\n⚠️ (도구 실행 30회 도달, 여기까지 응답)"
    return "⚠️ 도구 실행 한도 초과 (30회). 질문을 더 구체적으로 해주세요."


# ============================================================
# TELEGRAM BOT
# ============================================================
class TelegramBot:
    def __init__(self):
        self.token: Optional[str] = None
        self.owner_id: Optional[str] = None
        self.offset = 0
        self._running = False

    def configure(self, token: str, owner_id: str):
        self.token = token
        self.owner_id = owner_id

    def _api(self, method: str, data: dict = None) -> dict:
        url = f'https://api.telegram.org/bot{self.token}/{method}'
        if data:
            return _http_post(url, {'Content-Type': 'application/json'}, data)
        return _http_get(url)

    def send_message(self, chat_id, text: str, parse_mode: str = None):
        # Split long messages
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            data = {'chat_id': chat_id, 'text': chunk}
            if parse_mode:
                data['parse_mode'] = parse_mode
            try:
                self._api('sendMessage', data)
            except Exception as e:
                # Retry without parse_mode
                if parse_mode:
                    self._api('sendMessage', {'chat_id': chat_id, 'text': chunk})

    def _send_photo(self, chat_id, path: Path, caption: str = ''):
        """Send a photo file to Telegram."""
        try:
            import mimetypes
            boundary = f'----SalmAlm{int(time.time())}'
            body = b''
            # chat_id field
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode()
            if caption:
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption[:1000]}\r\n'.encode()
            # photo field
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{path.name}"\r\nContent-Type: image/png\r\n\r\n'.encode()
            body += path.read_bytes()
            body += f'\r\n--{boundary}--\r\n'.encode()
            req = urllib.request.Request(
                f'https://api.telegram.org/bot{self.token}/sendPhoto',
                data=body,
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
                method='POST'
            )
            urllib.request.urlopen(req, timeout=30)
        except Exception as e:
            log.error(f"Send photo error: {e}")
            self.send_message(chat_id, f'📷 이미지 전송 실패: {e}')

    def _send_audio(self, chat_id, path: Path, caption: str = ''):
        """Send an audio file to Telegram."""
        try:
            boundary = f'----SalmAlm{int(time.time())}'
            body = b''
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode()
            if caption:
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption[:1000]}\r\n'.encode()
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="voice"; filename="{path.name}"\r\nContent-Type: audio/mpeg\r\n\r\n'.encode()
            body += path.read_bytes()
            body += f'\r\n--{boundary}--\r\n'.encode()
            req = urllib.request.Request(
                f'https://api.telegram.org/bot{self.token}/sendVoice',
                data=body,
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
                method='POST'
            )
            urllib.request.urlopen(req, timeout=30)
        except Exception as e:
            log.error(f"Send audio error: {e}")
            self.send_message(chat_id, f'🔊 음성 전송 실패: {e}')

    def send_typing(self, chat_id):
        try:
            self._api('sendChatAction', {'chat_id': chat_id, 'action': 'typing'})
        except Exception:
            pass

    async def poll(self):
        """Long-polling loop for Telegram updates."""
        self._running = True
        log.info(f"📡 Telegram bot started (owner: {self.owner_id})")

        while self._running:
            try:
                resp = self._api('getUpdates', {
                    'offset': self.offset, 'timeout': 30,
                    'allowed_updates': ['message']
                })
                for update in resp.get('result', []):
                    self.offset = update['update_id'] + 1
                    await self._handle_update(update)
            except Exception as e:
                log.error(f"Telegram poll error: {e}")
                await asyncio.sleep(5)

    def _download_file(self, file_id: str) -> tuple[bytes, str]:
        """Download a file from Telegram. Returns (data, filename)."""
        info = self._api('getFile', {'file_id': file_id})
        file_path = info['result']['file_path']
        filename = file_path.split('/')[-1]
        url = f'https://api.telegram.org/file/bot{self.token}/{file_path}'
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        return data, filename

    async def _handle_update(self, update: dict):
        msg = update.get('message')
        if not msg:
            return

        chat_id = msg['chat']['id']
        user_id = str(msg['from']['id'])

        # Owner check
        if user_id != self.owner_id:
            log.warning(f"🚫 Unauthorized: {user_id} tried to message")
            audit_log('unauthorized', f'user_id={user_id}')
            return

        text = msg.get('text', '') or msg.get('caption', '') or ''
        file_info = None

        # Handle photos (with vision support)
        _image_data = None
        if msg.get('photo'):
            photo = msg['photo'][-1]  # Largest size
            try:
                data, fname = self._download_file(photo['file_id'])
                save_path = WORKSPACE_DIR / 'uploads' / fname
                save_path.parent.mkdir(exist_ok=True)
                save_path.write_bytes(data)
                file_info = f'[📷 이미지 저장: uploads/{fname} ({len(data)//1024}KB)]'
                log.info(f"📷 Photo saved: {save_path}")
                # Prepare vision data
                import base64 as _b64
                _image_data = (_b64.b64encode(data).decode(), 'image/jpeg')
            except Exception as e:
                file_info = f'[📷 이미지 다운로드 실패: {e}]'

        # Handle documents
        if msg.get('document'):
            doc = msg['document']
            try:
                data, fname = self._download_file(doc['file_id'])
                save_path = WORKSPACE_DIR / 'uploads' / (doc.get('file_name', fname))
                save_path.parent.mkdir(exist_ok=True)
                save_path.write_bytes(data)
                file_info = f'[📎 파일 저장: uploads/{save_path.name} ({len(data)//1024}KB)]'
                log.info(f"📎 File saved: {save_path}")
                # If text file, include content preview
                if save_path.suffix in ('.txt', '.md', '.py', '.js', '.json', '.csv', '.log', '.html', '.css', '.sh', '.bat'):
                    try:
                        content = data.decode('utf-8', errors='replace')[:3000]
                        file_info += f'\n[파일 내용 미리보기]\n{content}'
                    except Exception:
                        pass
            except Exception as e:
                file_info = f'[📎 파일 다운로드 실패: {e}]'

        # Handle voice/audio
        if msg.get('voice') or msg.get('audio'):
            audio = msg.get('voice') or msg.get('audio')
            try:
                data, fname = self._download_file(audio['file_id'])
                save_path = WORKSPACE_DIR / 'uploads' / fname
                save_path.parent.mkdir(exist_ok=True)
                save_path.write_bytes(data)
                file_info = f'[🎤 음성 저장: uploads/{fname} ({len(data)//1024}KB)]'
                log.info(f"🎤 Voice saved: {save_path}")
                # Whisper transcription
                api_key = vault.get('openai_api_key')
                if api_key:
                    try:
                        boundary = f'----Whisper{int(time.time())}'
                        body = b''
                        body += f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n'.encode()
                        body += f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{fname}"\r\nContent-Type: audio/ogg\r\n\r\n'.encode()
                        body += data
                        body += f'\r\n--{boundary}--\r\n'.encode()
                        req = urllib.request.Request(
                            'https://api.openai.com/v1/audio/transcriptions',
                            data=body,
                            headers={'Authorization': f'Bearer {api_key}',
                                     'Content-Type': f'multipart/form-data; boundary={boundary}'},
                            method='POST'
                        )
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            result = json.loads(resp.read())
                        transcript = result.get('text', '')
                        if transcript:
                            file_info = f'[🎤 음성 전사]\n{transcript}'
                            log.info(f"🎤 Transcribed: {transcript[:100]}")
                    except Exception as we:
                        log.error(f"Whisper error: {we}")
                        file_info += f'\n[전사 실패: {we}]'
            except Exception as e:
                file_info = f'[🎤 음성 다운로드 실패: {e}]'

        # Build final message
        if file_info:
            text = f'{file_info}\n{text}' if text else file_info
        
        if not text:
            return

        audit_log('telegram_msg', text[:100])

        # Commands
        if text.startswith('/'):
            await self._handle_command(chat_id, text)
            return

        # Process message
        self.send_typing(chat_id)
        session_id = f'telegram_{chat_id}'
        _start = time.time()
        response = await process_message(session_id, text, image_data=_image_data)
        _elapsed = time.time() - _start

        # Send response (check for generated files to send)
        import re as _re
        img_match = _re.search(r'uploads/[\w.-]+\.(png|jpg|jpeg|gif|webp)', response)
        audio_match = _re.search(r'uploads/[\w.-]+\.(mp3|wav|ogg)', response)
        if img_match:
            img_path = WORKSPACE_DIR / img_match.group(0)
            if img_path.exists():
                self._send_photo(chat_id, img_path, response[:1000])
            else:
                self.send_message(chat_id, f'{response}\n\n⏱️ {_elapsed:.1f}초')
        elif audio_match:
            audio_path = WORKSPACE_DIR / audio_match.group(0)
            if audio_path.exists():
                self._send_audio(chat_id, audio_path, response[:1000])
            else:
                self.send_message(chat_id, f'{response}\n\n⏱️ {_elapsed:.1f}초')
        else:
            self.send_message(chat_id, f'{response}\n\n⏱️ {_elapsed:.1f}초')

    async def _handle_command(self, chat_id, text: str):
        cmd = text.split()[0].lower()
        if cmd == '/start':
            self.send_message(chat_id, f'😈 {APP_NAME} v{VERSION} 가동 중\n낄낄')
        elif cmd == '/usage':
            report = execute_tool('usage_report', {})
            self.send_message(chat_id, report)
        elif cmd == '/model':
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                router.force_model = parts[1] if parts[1] != 'auto' else None
                self.send_message(chat_id, f'모델 변경: {parts[1]}')
            else:
                current = router.force_model or 'auto (라우팅)'
                models = '\n'.join(f'  {m}' for tier in router.TIERS.values() for m in tier)
                self.send_message(chat_id, f'현재: {current}\n\n사용 가능:\n{models}\n\n/model auto — 자동')
        elif cmd == '/compact':
            session = get_session(f'telegram_{chat_id}')
            before = len(session.messages)
            session.messages = compact_messages(session.messages)
            self.send_message(chat_id, f'압축: {before} → {len(session.messages)} 메시지')
        elif cmd == '/clear':
            session = get_session(f'telegram_{chat_id}')
            session.messages = []
            session.add_system(build_system_prompt())
            self.send_message(chat_id, '🗑️ 대화 초기화')
        elif cmd == '/help':
            self.send_message(chat_id, textwrap.dedent(f"""
                😈 {APP_NAME} v{VERSION}
                /usage — 토큰 사용량/비용
                /model [name|auto] — 모델 변경
                /compact — 대화 압축
                /clear — 대화 초기화
                /help — 이 메시지
            """).strip())
        else:
            self.send_message(chat_id, f'❓ 알 수 없는 명령: {cmd}\n/help 참조')

    def stop(self):
        self._running = False


telegram_bot = TelegramBot()

# ============================================================
# WEB UI — simple chat interface
# ============================================================
WEB_HTML = '''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>삶앎 — Personal AI Gateway</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--bg:#0b0d14;--bg2:#12141f;--bg3:#1a1d2b;--border:#252838;--text:#d4d4dc;--text2:#8889a0;
--accent:#7c5cfc;--accent2:#9b7dff;--accent-dim:rgba(124,92,252,0.12);--green:#34d399;--red:#f87171;
--user-bg:linear-gradient(135deg,#6d5cfc,#8b5cf6);--bot-bg:#161928}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;font-family:'Inter',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text)}
body{display:grid;grid-template-rows:auto 1fr auto;grid-template-columns:260px 1fr;grid-template-areas:"side head" "side chat" "side input"}

/* SIDEBAR */
#sidebar{grid-area:side;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;padding:0}
.side-header{padding:20px;border-bottom:1px solid var(--border)}
.side-header h1{font-size:20px;font-weight:600;display:flex;align-items:center;gap:8px}
.side-header h1 .icon{font-size:24px}
.side-header .tagline{font-size:11px;color:var(--text2);margin-top:4px;letter-spacing:0.5px;text-transform:uppercase}
.side-nav{flex:1;padding:12px;overflow-y:auto}
.nav-section{font-size:10px;color:var(--text2);text-transform:uppercase;letter-spacing:1px;padding:12px 8px 6px;font-weight:600}
.nav-item{padding:10px 12px;border-radius:8px;cursor:pointer;font-size:13px;color:var(--text2);display:flex;align-items:center;gap:10px;transition:all 0.15s}
.nav-item:hover{background:var(--accent-dim);color:var(--text)}
.nav-item.active{background:var(--accent-dim);color:var(--accent2);font-weight:500}
.nav-item .badge{margin-left:auto;background:var(--accent);color:#fff;font-size:10px;padding:2px 7px;border-radius:10px;font-weight:600}
.side-footer{padding:16px;border-top:1px solid var(--border);font-size:11px;color:var(--text2)}
.side-footer .status{display:flex;align-items:center;gap:6px;margin-bottom:6px}
.side-footer .dot{width:8px;height:8px;border-radius:50%;background:var(--green);display:inline-block}

/* HEADER */
#header{grid-area:head;padding:14px 24px;background:var(--bg2);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:16px}
#header .title{font-size:15px;font-weight:500}
#header .model-badge{font-size:11px;padding:4px 10px;border-radius:6px;background:var(--accent-dim);color:var(--accent2);font-weight:500}
#header .spacer{flex:1}
#header .cost{font-size:12px;color:var(--text2)}
#header .cost b{color:var(--green);font-weight:600}
#new-chat-btn{background:var(--accent-dim);color:var(--accent2);border:none;padding:6px 14px;border-radius:8px;font-size:12px;cursor:pointer;font-weight:500;transition:all 0.15s}
#new-chat-btn:hover{background:var(--accent);color:#fff}

/* CHAT */
#chat{grid-area:chat;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:16px;scroll-behavior:smooth}
#chat::-webkit-scrollbar{width:6px}
#chat::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
.msg-row{display:flex;gap:12px;max-width:90%;animation:fadeIn 0.2s ease}
.msg-row.user{align-self:flex-end;flex-direction:row-reverse}
.msg-row.assistant{align-self:flex-start}
.avatar{width:32px;height:32px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}
.msg-row.user .avatar{background:var(--user-bg)}
.msg-row.assistant .avatar{background:var(--bg3);border:1px solid var(--border)}
.bubble{padding:12px 16px;border-radius:16px;font-size:14px;line-height:1.7;white-space:pre-wrap;word-break:break-word}
.msg-row.user .bubble{background:var(--user-bg);color:#fff;border-bottom-right-radius:4px}
.msg-row.assistant .bubble{background:var(--bot-bg);border:1px solid var(--border);border-bottom-left-radius:4px}
.bubble code{background:rgba(255,255,255,0.08);padding:2px 6px;border-radius:4px;font-size:13px;font-family:'SF Mono',monospace}
.bubble pre{background:rgba(0,0,0,0.3);padding:12px;border-radius:8px;overflow-x:auto;margin:8px 0;font-size:13px}
.bubble pre code{background:none;padding:0}
.meta{font-size:11px;color:var(--text2);margin-top:4px;display:flex;gap:8px;align-items:center}
.msg-row.user .meta{justify-content:flex-end}
.typing-indicator{display:flex;gap:4px;padding:8px 0}
.typing-indicator span{width:7px;height:7px;border-radius:50%;background:var(--text2);animation:bounce 1.4s infinite ease-in-out}
.typing-indicator span:nth-child(2){animation-delay:0.2s}
.typing-indicator span:nth-child(3){animation-delay:0.4s}
@keyframes bounce{0%,80%,100%{transform:scale(0.6)}40%{transform:scale(1)}}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

/* INPUT */
#input-area{grid-area:input;padding:16px 24px;background:var(--bg2);border-top:1px solid var(--border)}
.input-box{display:flex;gap:8px;align-items:flex-end;background:var(--bg);border:1px solid var(--border);border-radius:12px;padding:8px 12px;transition:border-color 0.2s}
.input-box:focus-within{border-color:var(--accent)}
#input{flex:1;padding:6px 0;border:none;background:transparent;color:var(--text);font-size:14px;font-family:inherit;outline:none;resize:none;max-height:150px;line-height:1.5}
#send-btn{width:36px;height:36px;border-radius:10px;border:none;background:var(--accent);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all 0.15s;flex-shrink:0}
#send-btn:hover{background:var(--accent2);transform:scale(1.05)}
#send-btn:disabled{opacity:0.3;cursor:not-allowed;transform:none}
#send-btn svg{width:18px;height:18px}
.input-hint{font-size:11px;color:var(--text2);margin-top:6px;text-align:center}

/* SETTINGS PANEL */
#settings{display:none;grid-area:chat;overflow-y:auto;padding:24px}
.settings-card{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px}
.settings-card h3{font-size:14px;font-weight:600;margin-bottom:12px;color:var(--accent2)}
.settings-card label{font-size:12px;color:var(--text2);display:block;margin-bottom:4px}
.settings-card input,.settings-card select{width:100%;padding:8px 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:13px;margin-bottom:12px}
.settings-card .btn{padding:8px 16px;border-radius:8px;border:none;background:var(--accent);color:#fff;cursor:pointer;font-size:13px}

/* MOBILE */
@media(max-width:768px){
  body{grid-template-columns:1fr;grid-template-areas:"head" "chat" "input"}
  #sidebar{display:none}
}
</style></head><body>

<div id="sidebar">
  <div class="side-header">
    <h1><span class="icon">😈</span> 삶앎</h1>
    <div class="tagline">Personal AI Gateway</div>
  </div>
  <div class="side-nav">
    <div class="nav-section">채널</div>
    <div class="nav-item active" onclick="showChat()">💬 웹 챗</div>
    <div class="nav-item" id="tg-status">📡 텔레그램 <span class="badge">ON</span></div>
    <div class="nav-section">도구</div>
    <div class="nav-item">🔧 exec</div>
    <div class="nav-item">📁 파일</div>
    <div class="nav-item">🔍 웹 검색</div>
    <div class="nav-item">🧠 메모리</div>
    <div class="nav-section">관리</div>
    <div class="nav-item" onclick="showSettings()">⚙️ 설정</div>
    <div class="nav-item" onclick="showUsage()">📊 사용량</div>
  </div>
  <div class="side-footer">
    <div class="status"><span class="dot"></span> 가동 중</div>
    <div>v''' + VERSION + ''' · AES-256-GCM</div>
  </div>
</div>

<div id="header">
  <div class="title">💬 웹 챗</div>
  <div class="model-badge" id="model-badge">auto routing</div>
  <div class="spacer"></div>
  <div class="cost">비용: <b id="cost-display">$0.0000</b></div>
  <button id="new-chat-btn" onclick="window.newChat()" title="새 대화">🗑️ 새 대화</button>
</div>

<div id="chat"></div>

<div id="settings">
  <div class="settings-card">
    <h3>🤖 모델 설정</h3>
    <label>기본 모델</label>
    <select id="s-model" onchange="setModel(this.value)">
      <option value="auto">🔄 자동 라우팅 (추천)</option>
      <option value="anthropic/claude-opus-4-6">Claude Opus 4.6 (강력)</option>
      <option value="openai/gpt-5.3-codex">GPT-5.3 Codex (기본)</option>
      <option value="xai/grok-4">Grok 4</option>
      <option value="google/gemini-3-pro-preview">Gemini 3 Pro</option>
      <option value="google/gemini-3-flash-preview">Gemini 3 Flash (저렴)</option>
    </select>
  </div>
  <div class="settings-card">
    <h3>🔐 Vault 키 관리</h3>
    <div id="vault-keys"></div>
  </div>
  <div class="settings-card" id="usage-card">
    <h3>📊 토큰 사용량</h3>
    <div id="usage-detail"></div>
  </div>
</div>

<div id="input-area">
  <div class="input-box">
    <textarea id="input" rows="1" placeholder="메시지를 입력하세요..."></textarea>
    <button id="send-btn">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>
    </button>
  </div>
  <div id="file-preview" style="display:none;padding:8px 0">
    <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--bg3);border-radius:8px;font-size:12px;color:var(--text2)">
      <span id="file-icon">📎</span>
      <span id="file-name" style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>
      <span id="file-size"></span>
      <button onclick="clearFile()" style="background:none;border:none;color:var(--red);cursor:pointer;font-size:14px">✕</button>
    </div>
    <img id="img-preview" style="display:none;max-height:120px;border-radius:8px;margin-top:8px">
  </div>
  <div class="input-hint">Enter 전송 · Shift+Enter 줄바꿈 · Ctrl+V 이미지/파일 · 드래그앤드롭 가능</div>
</div>

<script>
(function(){
  const chat=document.getElementById('chat'),input=document.getElementById('input'),
    btn=document.getElementById('send-btn'),costEl=document.getElementById('cost-display'),
    modelBadge=document.getElementById('model-badge'),settingsEl=document.getElementById('settings'),
    filePrev=document.getElementById('file-preview'),fileIconEl=document.getElementById('file-icon'),
    fileNameEl=document.getElementById('file-name'),fileSizeEl=document.getElementById('file-size'),
    imgPrev=document.getElementById('img-preview'),inputArea=document.getElementById('input-area');
  let _tok=sessionStorage.getItem('tok')||'',pendingFile=null;

  /* --- Restore chat history --- */
  (function(){
    var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
    if(hist.length){window._restoring=true;hist.forEach(function(m){addMsg(m.role,m.text,m.model)});window._restoring=false}
  })();

  /* --- New chat --- */
  window.newChat=function(){
    if(!confirm('대화 기록을 삭제하고 새 대화를 시작할까요?'))return;
    localStorage.removeItem('salm_chat');
    chat.innerHTML='';
    fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
      body:JSON.stringify({message:'/clear',session:'web'})}).catch(function(){});
    addMsg('system','😈 새 대화가 시작되었습니다.');
  };

  /* --- Helpers --- */
  function renderMd(t){
    if(t.startsWith('<img ')||t.startsWith('<audio '))return t; /* already HTML */
    return t.replace(/```([\\s\\S]*?)```/g,'<pre><code>$1</code></pre>')
            .replace(/`([^`]+)`/g,'<code>$1</code>')
            .replace(/\\*\\*([^*]+)\\*\\*/g,'<strong>$1</strong>')
            .replace(/\\*([^*]+)\\*/g,'<em>$1</em>')
            .replace(/^### (.+)$/gm,'<h4 style="margin:4px 0;font-size:13px">$1</h4>')
            .replace(/^## (.+)$/gm,'<h3 style="margin:6px 0;font-size:14px">$1</h3>')
            .replace(/^# (.+)$/gm,'<h2 style="margin:8px 0;font-size:15px">$1</h2>')
            .replace(/^[•\\-] (.+)$/gm,'<div style="padding-left:12px">• $1</div>')
            .replace(/^(\\d+)\\. (.+)$/gm,'<div style="padding-left:12px">$1. $2</div>')
            .replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g,'<a href="$2" target="_blank" style="color:var(--accent2)">$1</a>')
            .replace(/uploads\\/([\\w.-]+\\.(png|jpg|jpeg|gif|webp))/gi,'<img src="/uploads/$1" style="max-width:400px;max-height:400px;border-radius:8px;display:block;margin:8px 0" alt="$1">')
            .replace(/uploads\\/([\\w.-]+\\.(mp3|wav|ogg))/gi,'<audio controls src="/uploads/$1" style="display:block;margin:8px 0"></audio> 🔊 $1')
            .replace(/\\n/g,'<br>');
  }
  function addMsg(role,text,model){
    const row=document.createElement('div');row.className='msg-row '+role;
    const av=document.createElement('div');av.className='avatar';
    av.textContent=role==='user'?'👤':'😈';
    const wrap=document.createElement('div');
    const bubble=document.createElement('div');bubble.className='bubble';
    bubble.innerHTML=renderMd(text);
    wrap.appendChild(bubble);
    var meta_parts=[];
    if(model)meta_parts.push(model);
    meta_parts.push(new Date().toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'}));
    var mt=document.createElement('div');mt.className='meta';mt.textContent=meta_parts.join(' · ');wrap.appendChild(mt);
    row.appendChild(av);row.appendChild(wrap);
    chat.appendChild(row);chat.scrollTop=999999;
    if(!window._restoring){
      var hist=JSON.parse(localStorage.getItem('salm_chat')||'[]');
      hist.push({role:role,text:text,model:model||null});
      if(hist.length>200)hist=hist.slice(-200);
      localStorage.setItem('salm_chat',JSON.stringify(hist));
    }
  }
  function addTyping(){
    const row=document.createElement('div');row.className='msg-row assistant';row.id='typing-row';
    const av=document.createElement('div');av.className='avatar';av.textContent='😈';
    const wrap=document.createElement('div');
    const b=document.createElement('div');b.className='bubble';
    b.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div>';
    wrap.appendChild(b);row.appendChild(av);row.appendChild(wrap);
    chat.appendChild(row);chat.scrollTop=999999;
  }

  /* --- File handling --- */
  window.setFile=function(file){
    pendingFile=file;
    const isImg=file.type.startsWith('image/');
    fileIconEl.textContent=isImg?'🖼️':'📎';
    fileNameEl.textContent=file.name;
    fileSizeEl.textContent=(file.size/1024).toFixed(1)+'KB';
    filePrev.style.display='block';
    if(isImg){const r=new FileReader();r.onload=function(e){imgPrev.src=e.target.result;imgPrev.style.display='block'};r.readAsDataURL(file)}
    else{imgPrev.style.display='none'}
    input.focus();
  };
  window.clearFile=function(){pendingFile=null;filePrev.style.display='none';imgPrev.style.display='none'};

  /* --- Ctrl+V --- */
  document.addEventListener('paste',function(e){
    var items=e.clipboardData&&e.clipboardData.items;if(!items)return;
    for(var i=0;i<items.length;i++){
      if(items[i].kind==='file'){e.preventDefault();var f=items[i].getAsFile();if(f)window.setFile(f);return}
    }
  });

  /* --- Drag & drop --- */
  inputArea.addEventListener('dragenter',function(e){e.preventDefault();e.stopPropagation();inputArea.style.outline='2px solid var(--accent)'});
  inputArea.addEventListener('dragover',function(e){e.preventDefault();e.stopPropagation()});
  inputArea.addEventListener('dragleave',function(e){e.preventDefault();inputArea.style.outline=''});
  inputArea.addEventListener('drop',function(e){e.preventDefault();e.stopPropagation();inputArea.style.outline='';
    var f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];if(f)window.setFile(f)});

  /* --- Send --- */
  async function doSend(){
    var t=input.value.trim();
    if(!t&&!pendingFile)return;
    input.value='';input.style.height='auto';btn.disabled=true;

    var fileMsg='';var imgData=null;var imgMime=null;
    if(pendingFile){
      var isImg=pendingFile.type.startsWith('image/');
      if(isImg){
        var reader=new FileReader();
        var previewUrl=await new Promise(function(res){reader.onload=function(){res(reader.result)};reader.readAsDataURL(pendingFile)});
        addMsg('user','<img src="'+previewUrl+'" style="max-width:300px;max-height:300px;border-radius:8px;display:block;margin:4px 0" alt="'+pendingFile.name+'">');
      }else{addMsg('user','[📎 '+pendingFile.name+' 업로드 중...]')}
      var fd=new FormData();fd.append('file',pendingFile);
      try{
        var ur=await fetch('/api/upload',{method:'POST',body:fd});
        var ud=await ur.json();
        if(ud.ok){fileMsg=ud.info;if(ud.image_base64){imgData=ud.image_base64;imgMime=ud.image_mime}}
        else addMsg('assistant','❌ 업로드 실패: '+(ud.error||''));
      }catch(ue){addMsg('assistant','❌ 업로드 오류: '+ue.message)}
      window.clearFile();
    }

    var msg=(fileMsg?fileMsg+'\\n':'')+t;
    if(t)addMsg('user',t);
    if(!msg){btn.disabled=false;return}

    addTyping();
    var _sendStart=Date.now();
    var chatBody={message:msg,session:'web'};
    if(imgData){chatBody.image_base64=imgData;chatBody.image_mime=imgMime}
    try{
      var useStream=true;
      try{
        var r=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
          body:JSON.stringify(chatBody)});
        if(!r.ok||!r.body){throw new Error('stream unavailable')}
        var reader=r.body.getReader();var decoder=new TextDecoder();var buf='';var gotDone=false;
        var typingEl=document.getElementById('typing-row');
        while(true){
          var chunk=await reader.read();
          if(chunk.done)break;
          buf+=decoder.decode(chunk.value,{stream:true});
          var evts=buf.split('\\n\\n');buf=evts.pop();
          for(var i=0;i<evts.length;i++){
            var evt=evts[i];
            var em=evt.match(/^event: (\\w+)\\ndata: (.+)$/m);
            if(!em)continue;
            var etype=em[1],edata=JSON.parse(em[2]);
            if(etype==='status'){
              if(typingEl){var tb=typingEl.querySelector('.bubble');if(tb)tb.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div> '+edata.text}
            }else if(etype==='tool'){
              if(typingEl){var tb2=typingEl.querySelector('.bubble');if(tb2)tb2.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div> 🔧 '+edata.name+'...'}
            }else if(etype==='done'){
              gotDone=true;
              if(typingEl)typingEl.remove();
              var _secs=((Date.now()-_sendStart)/1000).toFixed(1);
              addMsg('assistant',edata.response||'',(edata.model||'')+' · ⏱️'+_secs+'초');
              fetch('/api/status').then(function(r2){return r2.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
            }
          }
        }
        if(!gotDone)throw new Error('stream incomplete');
        if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
      }catch(streamErr){
        /* Fallback to regular /api/chat */
        console.warn('Stream failed, falling back:',streamErr);
        var typRow=document.getElementById('typing-row');
        if(typRow){var tb3=typRow.querySelector('.bubble');if(tb3)tb3.innerHTML='<div class="typing-indicator"><span></span><span></span><span></span></div> 처리 중...'}
        var r2=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':_tok},
          body:JSON.stringify(chatBody)});
        var d=await r2.json();
        if(document.getElementById('typing-row'))document.getElementById('typing-row').remove();
        var _secs2=((Date.now()-_sendStart)/1000).toFixed(1);
        if(d.response)addMsg('assistant',d.response,(d.model||'')+' · ⏱️'+_secs2+'초');
        else if(d.error)addMsg('assistant','❌ '+d.error);
        fetch('/api/status').then(function(r3){return r3.json()}).then(function(s){costEl.textContent='$'+s.usage.total_cost.toFixed(4)});
      }
    }catch(se){var tr2=document.getElementById('typing-row');if(tr2)tr2.remove();addMsg('assistant','❌ 오류: '+se.message)}
    btn.disabled=false;input.focus();
  }
  window.doSend=doSend;

  /* --- Key handler --- */
  input.addEventListener('keydown',function(e){
    if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();doSend()}
  });
  input.addEventListener('input',function(){input.style.height='auto';input.style.height=Math.min(input.scrollHeight,150)+'px'});
  btn.addEventListener('click',function(){doSend()});

  /* --- Settings --- */
  window.showChat=function(){settingsEl.style.display='none';chat.style.display='flex';inputArea.style.display='block'};
  window.showSettings=function(){chat.style.display='none';inputArea.style.display='none';settingsEl.style.display='block';
    fetch('/api/vault',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'keys'})})
      .then(function(r){return r.json()}).then(function(d){
        document.getElementById('vault-keys').innerHTML=d.keys.map(function(k){return '<div style="padding:4px 0;font-size:13px;color:var(--text2)">🔑 '+k+'</div>'}).join('')});
    fetch('/api/status').then(function(r){return r.json()}).then(function(d){
      var u=d.usage,h='<div style="font-size:13px;line-height:2">📥 입력: '+u.total_input.toLocaleString()+' 토큰<br>📤 출력: '+u.total_output.toLocaleString()+' 토큰<br>💰 비용: $'+u.total_cost.toFixed(4)+'<br>⏱️ 가동: '+u.elapsed_hours+'시간</div>';
      if(u.by_model){h+='<div style="margin-top:12px;font-size:12px">';for(var m in u.by_model){var v=u.by_model[m];h+='<div style="padding:4px 0;color:var(--text2)">'+m+': '+v.calls+'회 · $'+v.cost.toFixed(4)+'</div>'}h+='</div>'}
      document.getElementById('usage-detail').innerHTML=h});
  };
  window.showUsage=window.showSettings;
  window.setModel=function(m){modelBadge.textContent=m==='auto'?'auto routing':m.split('/').pop();
    fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:'/model '+(m==='auto'?'auto':m),session:'web'})})};

  /* --- Welcome (only if no history) --- */
  if(!JSON.parse(localStorage.getItem('salm_chat')||'[]').length){
    addMsg('assistant','😈 삶앎에 오신 걸 환영합니다!\\n\\n텔레그램과 웹에서 동시에 사용 가능합니다.\\nCtrl+V 이미지 붙여넣기 · 드래그앤드롭 · Enter 전송\\n/help로 명령어 확인','system');
  }
  input.focus();
})();
</script></body></html>'''


class WebHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for web UI and API."""

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')

    def _json(self, data: dict, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _html(self, content: str):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.end_headers()

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            if not vault.is_unlocked:
                self._html(UNLOCK_HTML)
            else:
                self._html(WEB_HTML)
        elif self.path == '/api/status':
            self._json({'app': APP_NAME, 'version': VERSION,
                        'unlocked': vault.is_unlocked,
                        'usage': get_usage_report()})
        elif self.path.startswith('/uploads/'):
            # Serve uploaded files (images, audio)
            fname = self.path.split('/uploads/')[-1]
            fpath = WORKSPACE_DIR / 'uploads' / fname
            if not fpath.exists():
                self.send_error(404)
                return
            mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                        '.gif': 'image/gif', '.webp': 'image/webp', '.mp3': 'audio/mpeg',
                        '.wav': 'audio/wav', '.ogg': 'audio/ogg'}
            ext = fpath.suffix.lower()
            mime = mime_map.get(ext, 'application/octet-stream')
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(fpath.stat().st_size))
            self.end_headers()
            self.wfile.write(fpath.read_bytes())
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        # Don't parse multipart as JSON
        if self.path == '/api/upload':
            body = {}
        else:
            body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == '/api/unlock':
            password = body.get('password', '')
            if VAULT_FILE.exists():
                ok = vault.unlock(password)
            else:
                vault.create(password)
                ok = True
            if ok:
                audit_log('unlock', 'vault unlocked')
                token = secrets.token_hex(32)
                self._json({'ok': True, 'token': token})
            else:
                audit_log('unlock_fail', 'wrong password')
                self._json({'ok': False, 'error': '비밀번호 틀림'}, 401)

        elif self.path in ('/api/chat', '/api/chat/stream'):
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            message = body.get('message', '')
            session_id = body.get('session', 'web')
            image_b64 = body.get('image_base64')
            image_mime = body.get('image_mime', 'image/png')
            use_stream = self.path.endswith('/stream')

            if use_stream:
                # SSE streaming response
                self.send_response(200)
                self._cors()
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Connection', 'keep-alive')
                self.end_headers()

                def send_sse(event, data):
                    try:
                        payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                        self.wfile.write(payload.encode())
                        self.wfile.flush()
                    except Exception:
                        pass

                send_sse('status', {'text': '🤔 생각 중...'})
                loop = asyncio.new_event_loop()
                response = loop.run_until_complete(
                    process_message(session_id, message,
                                    image_data=(image_b64, image_mime) if image_b64 else None,
                                    on_tool=lambda name, args: send_sse('tool', {'name': name, 'args': str(args)[:200]}))
                )
                loop.close()
                send_sse('done', {'response': response, 'model': router.force_model or 'auto'})
                try:
                    self.wfile.write(b"event: close\ndata: {}\n\n")
                    self.wfile.flush()
                except Exception:
                    pass
            else:
                loop = asyncio.new_event_loop()
                response = loop.run_until_complete(
                    process_message(session_id, message,
                                    image_data=(image_b64, image_mime) if image_b64 else None)
                )
                loop.close()
                self._json({'response': response, 'model': router.force_model or 'auto'})

        elif self.path == '/api/vault':
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            action = body.get('action')
            if action == 'set':
                vault.set(body['key'], body['value'])
                self._json({'ok': True})
            elif action == 'get':
                val = vault.get(body['key'])
                self._json({'value': val})
            elif action == 'keys':
                self._json({'keys': vault.keys()})
            elif action == 'delete':
                vault.delete(body['key'])
                self._json({'ok': True})
            else:
                self._json({'error': 'Unknown action'}, 400)

        elif self.path == '/api/upload':
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            # Parse multipart form data
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self._json({'error': 'multipart required'}, 400)
                return
            try:
                boundary = content_type.split('boundary=')[1].strip()
                raw = self.rfile.read(length)
                # Simple multipart parser
                parts = raw.split(f'--{boundary}'.encode())
                for part in parts:
                    if b'filename="' not in part:
                        continue
                    # Extract filename
                    header_end = part.find(b'\r\n\r\n')
                    if header_end < 0:
                        continue
                    header = part[:header_end].decode('utf-8', errors='replace')
                    fname_match = re.search(r'filename="([^"]+)"', header)
                    if not fname_match:
                        continue
                    fname = fname_match.group(1)
                    file_data = part[header_end+4:]
                    # Remove trailing \r\n--
                    if file_data.endswith(b'\r\n'):
                        file_data = file_data[:-2]
                    if file_data.endswith(b'--'):
                        file_data = file_data[:-2]
                    if file_data.endswith(b'\r\n'):
                        file_data = file_data[:-2]
                    # Save
                    save_dir = WORKSPACE_DIR / 'uploads'
                    save_dir.mkdir(exist_ok=True)
                    save_path = save_dir / fname
                    save_path.write_bytes(file_data)
                    size_kb = len(file_data) / 1024
                    is_image = any(fname.lower().endswith(ext) for ext in ('.png','.jpg','.jpeg','.gif','.webp','.bmp'))
                    is_text = any(fname.lower().endswith(ext) for ext in ('.txt','.md','.py','.js','.json','.csv','.log','.html','.css','.sh','.bat','.yaml','.yml','.xml','.sql'))
                    info = f'[{"🖼️ 이미지" if is_image else "📎 파일"} 업로드: uploads/{fname} ({size_kb:.1f}KB)]'
                    if is_text:
                        try:
                            preview = file_data.decode('utf-8', errors='replace')[:3000]
                            info += f'\n[파일 내용]\n{preview}'
                        except Exception:
                            pass
                    log.info(f"📤 Web upload: {fname} ({size_kb:.1f}KB)")
                    audit_log('web_upload', fname)
                    resp = {'ok': True, 'filename': fname, 'size': len(file_data),
                                'info': info, 'is_image': is_image}
                    if is_image:
                        import base64
                        ext = fname.rsplit('.', 1)[-1].lower()
                        mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                                'gif': 'image/gif', 'webp': 'image/webp', 'bmp': 'image/bmp'}.get(ext, 'image/png')
                        resp['image_base64'] = base64.b64encode(file_data).decode()
                        resp['image_mime'] = mime
                    self._json(resp)
                    return
                self._json({'error': 'No file found'}, 400)
            except Exception as e:
                log.error(f"Upload error: {e}")
                self._json({'error': str(e)[:200]}, 500)
                return

        elif self.path == '/api/config/telegram':
            if not vault.is_unlocked:
                self._json({'error': 'Vault locked'}, 403)
                return
            vault.set('telegram_token', body.get('token', ''))
            vault.set('telegram_owner_id', body.get('owner_id', ''))
            self._json({'ok': True, 'message': 'Telegram 설정 저장. 재시작 필요.'})

        else:
            self._json({'error': 'Not found'}, 404)


UNLOCK_HTML = '''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>삶앎 — Unlock</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#0f1117;color:#e0e0e0;height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:#1a1d27;padding:40px;border-radius:16px;border:1px solid #2a2d37;text-align:center;min-width:320px}
h1{color:#a78bfa;margin-bottom:8px}
p{color:#888;margin-bottom:24px;font-size:14px}
input{width:100%;padding:12px;border-radius:8px;border:1px solid #333;background:#0f1117;color:#e0e0e0;font-size:16px;margin-bottom:16px;text-align:center}
button{width:100%;padding:12px;border-radius:8px;border:none;background:#4f46e5;color:#fff;font-size:16px;cursor:pointer}
button:hover{background:#4338ca}
.error{color:#ef4444;margin-top:12px;font-size:14px;display:none}
</style></head><body>
<div class="card">
<h1>😈 삶앎</h1>
<p>Personal AI Gateway v''' + VERSION + '''</p>
<input type="password" id="pw" placeholder="마스터 비밀번호" onkeydown="if(event.key==='Enter')unlock()">
<button onclick="unlock()">잠금 해제</button>
<div class="error" id="err"></div>
</div>
<script>
async function unlock(){
  const pw=document.getElementById('pw').value;
  const r=await fetch('/api/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
  const d=await r.json();
  if(d.ok){sessionStorage.setItem('tok',d.token||'');location.reload()}
  else{const e=document.getElementById('err');e.textContent=d.error;e.style.display='block'}
}
</script></body></html>'''


# ============================================================
# CRON SCHEDULER
# ============================================================
class CronScheduler:
    """Simple cron-like scheduler."""

    def __init__(self):
        self.jobs: list[dict] = []
        self._running = False

    def add_job(self, name: str, interval_seconds: int, callback, **kwargs):
        self.jobs.append({
            'name': name, 'interval': interval_seconds,
            'callback': callback, 'kwargs': kwargs,
            'last_run': 0, 'enabled': True
        })

    async def run(self):
        self._running = True
        log.info(f"⏰ Cron scheduler started ({len(self.jobs)} jobs)")
        while self._running:
            now = time.time()
            for job in self.jobs:
                if not job['enabled']:
                    continue
                if now - job['last_run'] >= job['interval']:
                    try:
                        log.info(f"⏰ Running cron: {job['name']}")
                        if asyncio.iscoroutinefunction(job['callback']):
                            await job['callback'](**job['kwargs'])
                        else:
                            job['callback'](**job['kwargs'])
                        job['last_run'] = now
                    except Exception as e:
                        log.error(f"Cron error ({job['name']}): {e}")
            await asyncio.sleep(10)

    def stop(self):
        self._running = False


cron = CronScheduler()


# ============================================================
# DAILY MEMORY LOG
# ============================================================
def write_daily_log(entry: str):
    """Append to today's memory log."""
    today = datetime.now(KST).strftime('%Y-%m-%d')
    log_file = MEMORY_DIR / f'{today}.md'
    MEMORY_DIR.mkdir(exist_ok=True)
    header = f'# {today} Daily Log\n\n' if not log_file.exists() else ''
    with open(log_file, 'a', encoding='utf-8') as f:
        ts = datetime.now(KST).strftime('%H:%M')
        f.write(f'{header}- [{ts}] {entry}\n')


# ============================================================
# MAIN
# ============================================================
async def main():
    _init_audit_db()
    _restore_usage()
    audit_log('startup', f'{APP_NAME} v{VERSION}')

    # Ensure memory dir
    MEMORY_DIR.mkdir(exist_ok=True)

    # Start web server
    port = int(os.environ.get('SALMALM_PORT', 18800))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), WebHandler)
    web_thread = threading.Thread(target=server.serve_forever, daemon=True)
    web_thread.start()
    log.info(f"🌐 Web UI: http://127.0.0.1:{port}")

    # Try to auto-unlock vault and start Telegram
    vault_pw = os.environ.get('SALMALM_VAULT_PW')
    if vault_pw and VAULT_FILE.exists():
        if vault.unlock(vault_pw):
            log.info("🔓 Vault auto-unlocked from env")
            tg_token = vault.get('telegram_token')
            tg_owner = vault.get('telegram_owner_id')
            if tg_token and tg_owner:
                telegram_bot.configure(tg_token, tg_owner)
                asyncio.create_task(telegram_bot.poll())
        else:
            log.warning("🔒 Vault auto-unlock failed")

    # Register default cron jobs
    def heartbeat_job():
        """Periodic heartbeat — check memory, clean old sessions."""
        active = len([s for s in _sessions.values() if s.messages])
        log.info(f"💓 Heartbeat: {active} active sessions, vault={'🔓' if vault.is_unlocked else '🔒'}")
        # Auto-create daily memory file
        today = time.strftime('%Y-%m-%d')
        daily = MEMORY_DIR / f'{today}.md'
        if not daily.exists():
            daily.write_text(f'# {today} 일일 기록\n\n', encoding='utf-8')
            log.info(f"📝 Daily memory created: {today}.md")
        # Clean old sessions (>2h idle)
        now = time.time()
        stale = [k for k, s in _sessions.items() if now - s.last_active > 7200 and k != 'web']
        for k in stale:
            del _sessions[k]
            log.info(f"🧹 Cleaned stale session: {k}")

    cron.add_job('heartbeat', 1800, heartbeat_job)  # 30분마다

    # Start cron
    asyncio.create_task(cron.run())

    print(f"""
╔══════════════════════════════════════╗
║  😈 {APP_NAME} v{VERSION}           ║
║  Web UI: http://127.0.0.1:{port:<5}     ║
║  Vault: {'🔓 Unlocked' if vault.is_unlocked else '🔒 Locked — open Web UI'}  ║
║  Crypto: {'AES-256-GCM' if HAS_CRYPTO else 'HMAC-CTR (fallback)'}     ║
╚══════════════════════════════════════╝
""")

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down...")
        telegram_bot.stop()
        cron.stop()
        server.shutdown()
        audit_log('shutdown', 'clean')


if __name__ == '__main__':
    asyncio.run(main())
