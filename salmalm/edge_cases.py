"""SalmAlm Edge Cases — features inspired by LibreChat, Open WebUI, LobeChat, BIG-AGI.

엣지케이스 처리 모듈:
1. Abort Generation (생성 중지) — LibreChat
2. Token Usage Tracking (사용량 추적) — LibreChat
3. Conversation Fork / Regenerate (대화 포크) — LibreChat
4. Provider Health Check (프로바이더 상태 확인) — Open WebUI
5. Model Auto-Detection (모델 자동 감지) — Open WebUI
6. Enhanced File Upload (파일 업로드 강화) — Open WebUI
7. Session Groups (대화 주제 그룹) — LobeChat
8. Message Bookmarks (메시지 북마크) — LobeChat
9. System Prompt Variables (시스템 프롬프트 변수) — LobeChat
10. Response Compare / Beam (응답 비교) — BIG-AGI
11. Smart Paste (스마트 붙여넣기) — BIG-AGI
12. Conversation Summary Card (대화 요약 카드) — BIG-AGI
13-15. Common: offline detection, auth renewal, draft autosave (프론트엔드)

All pure stdlib. No external dependencies.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import KST, VERSION
from .crypto import log

# ============================================================
# 1. Abort Generation (생성 중지) — LibreChat style
# ============================================================

class AbortController:
    """Per-session abort flag for stopping LLM generation.

    Usage:
        abort_ctrl.set_abort(session_id)  # User clicks Stop
        if abort_ctrl.is_aborted(session_id): break  # In tool loop
        abort_ctrl.clear(session_id)  # After completion
    """

    def __init__(self):
        self._flags: Dict[str, bool] = {}
        self._lock = threading.Lock()
        self._partial_responses: Dict[str, str] = {}

    def set_abort(self, session_id: str):
        """Signal abort for a session (사용자가 Stop 클릭)."""
        with self._lock:
            self._flags[session_id] = True
            log.info(f"[ABORT] Generation abort requested: session={session_id}")

    def is_aborted(self, session_id: str) -> bool:
        """Check if abort was requested (매 반복마다 체크)."""
        with self._lock:
            return self._flags.get(session_id, False)

    def clear(self, session_id: str):
        """Clear abort flag after handling (처리 후 초기화)."""
        with self._lock:
            self._flags.pop(session_id, None)

    def save_partial(self, session_id: str, text: str):
        """Save partial response before aborting (중단된 부분 응답 저장)."""
        with self._lock:
            self._partial_responses[session_id] = text

    def get_partial(self, session_id: str) -> Optional[str]:
        """Get and clear the saved partial response."""
        with self._lock:
            return self._partial_responses.pop(session_id, None)


# Singleton
abort_controller = AbortController()


# ============================================================
# 2. Token Usage Tracking (사용량 추적) — LibreChat style
# ============================================================

class UsageTracker:
    """Per-user, per-model token usage tracking with daily/monthly reports.

    Extends existing cost tracking in core.py with detailed breakdowns.
    사용자별/모델별 토큰 사용량 추적 + 일별/월별 리포트.
    """

    def __init__(self):
        self._db_path = Path.home() / '.salmalm' / 'salmalm.db'

    def _get_db(self):
        from .core import _get_db
        conn = _get_db()
        # Ensure usage_detail table exists
        conn.execute('''CREATE TABLE IF NOT EXISTS usage_detail (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            session_id TEXT,
            model TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cost REAL DEFAULT 0.0,
            intent TEXT DEFAULT ''
        )''')
        conn.commit()
        return conn

    def record(self, session_id: str, model: str, input_tokens: int,
               output_tokens: int, cost: float, intent: str = ''):
        """Record a usage entry (사용량 기록)."""
        try:
            conn = self._get_db()
            now = datetime.now(KST).isoformat()
            conn.execute(
                'INSERT INTO usage_detail (ts, session_id, model, input_tokens, output_tokens, cost, intent) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (now, session_id, model, input_tokens, output_tokens, cost, intent))
            conn.commit()
        except Exception as e:
            log.warning(f"Usage tracking error: {e}")

    def daily_report(self, days: int = 7) -> List[Dict]:
        """Daily usage report (일별 사용량 리포트)."""
        try:
            conn = self._get_db()
            cutoff = (datetime.now(KST) - timedelta(days=days)).isoformat()
            rows = conn.execute(
                'SELECT substr(ts,1,10) as day, model, '
                'SUM(input_tokens) as inp, SUM(output_tokens) as out, '
                'SUM(cost) as total_cost, COUNT(*) as calls '
                'FROM usage_detail WHERE ts >= ? '
                'GROUP BY day, model ORDER BY day DESC',
                (cutoff,)).fetchall()
            return [{'date': r[0], 'model': r[1], 'input_tokens': r[2],
                     'output_tokens': r[3], 'cost': round(r[4], 6), 'calls': r[5]}
                    for r in rows]
        except Exception:
            return []

    def monthly_report(self, months: int = 3) -> List[Dict]:
        """Monthly usage report (월별 사용량 리포트)."""
        try:
            conn = self._get_db()
            cutoff = (datetime.now(KST) - timedelta(days=months * 30)).isoformat()
            rows = conn.execute(
                'SELECT substr(ts,1,7) as month, model, '
                'SUM(input_tokens) as inp, SUM(output_tokens) as out, '
                'SUM(cost) as total_cost, COUNT(*) as calls '
                'FROM usage_detail WHERE ts >= ? '
                'GROUP BY month, model ORDER BY month DESC',
                (cutoff,)).fetchall()
            return [{'month': r[0], 'model': r[1], 'input_tokens': r[2],
                     'output_tokens': r[3], 'cost': round(r[4], 6), 'calls': r[5]}
                    for r in rows]
        except Exception:
            return []

    def model_breakdown(self) -> Dict[str, float]:
        """Cost breakdown by model (모델별 비용 분류)."""
        try:
            conn = self._get_db()
            rows = conn.execute(
                'SELECT model, SUM(cost) FROM usage_detail GROUP BY model'
            ).fetchall()
            return {r[0]: round(r[1], 6) for r in rows}
        except Exception:
            return {}


usage_tracker = UsageTracker()


# ============================================================
# 3. Conversation Fork / Regenerate (대화 포크) — LibreChat style
# ============================================================

class ConversationFork:
    """Manage alternative responses at the same message index.

    Stores multiple assistant responses for the same user message,
    allowing navigation between alternatives (◀ 1/3 ▶).
    대화 포크: 같은 메시지에 대한 여러 응답 관리.
    """

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        try:
            from .core import _get_db
            conn = _get_db()
            conn.execute('''CREATE TABLE IF NOT EXISTS message_alternatives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                model TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 0
            )''')
            conn.execute('''CREATE INDEX IF NOT EXISTS idx_alt_session_msg
                ON message_alternatives(session_id, message_index)''')
            conn.commit()
        except Exception as e:
            log.warning(f"Alternatives table init: {e}")

    def save_alternative(self, session_id: str, message_index: int,
                         content: str, model: str = '', active: bool = True):
        """Save an alternative response (대안 응답 저장)."""
        try:
            from .core import _get_db
            conn = _get_db()
            now = datetime.now(KST).isoformat()
            if active:
                # Deactivate previous alternatives
                conn.execute(
                    'UPDATE message_alternatives SET is_active=0 '
                    'WHERE session_id=? AND message_index=?',
                    (session_id, message_index))
            conn.execute(
                'INSERT INTO message_alternatives '
                '(session_id, message_index, content, model, created_at, is_active) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (session_id, message_index, content, model, now, 1 if active else 0))
            conn.commit()
        except Exception as e:
            log.warning(f"Save alternative error: {e}")

    def get_alternatives(self, session_id: str, message_index: int) -> List[Dict]:
        """Get all alternatives for a message (해당 메시지의 모든 대안)."""
        try:
            from .core import _get_db
            conn = _get_db()
            rows = conn.execute(
                'SELECT id, content, model, created_at, is_active '
                'FROM message_alternatives '
                'WHERE session_id=? AND message_index=? ORDER BY id',
                (session_id, message_index)).fetchall()
            return [{'id': r[0], 'content': r[1], 'model': r[2],
                     'created_at': r[3], 'is_active': bool(r[4])} for r in rows]
        except Exception:
            return []

    def switch_alternative(self, session_id: str, message_index: int,
                           alt_id: int) -> Optional[str]:
        """Switch to a specific alternative (대안 전환). Returns new content."""
        try:
            from .core import _get_db
            conn = _get_db()
            conn.execute(
                'UPDATE message_alternatives SET is_active=0 '
                'WHERE session_id=? AND message_index=?',
                (session_id, message_index))
            conn.execute('UPDATE message_alternatives SET is_active=1 WHERE id=?', (alt_id,))
            conn.commit()
            row = conn.execute('SELECT content FROM message_alternatives WHERE id=?',
                               (alt_id,)).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    async def regenerate(self, session_id: str, message_index: int) -> Optional[str]:
        """Regenerate assistant response at given index (응답 재생성).

        1. Find the user message before this assistant message
        2. Save current assistant response as alternative
        3. Delete assistant message
        4. Re-run LLM with same user message
        5. Save new response as active alternative
        """
        from .core import get_session
        session = get_session(session_id)
        msgs = session.messages

        # Validate: message_index should point to an assistant message
        # Filter to only user/assistant messages (skip system, tool results)
        ua_indices = [(i, m) for i, m in enumerate(msgs)
                      if m.get('role') in ('user', 'assistant')]

        if message_index < 0 or message_index >= len(ua_indices):
            return None

        real_idx, target_msg = ua_indices[message_index]
        if target_msg.get('role') != 'assistant':
            return None

        # Save current response as alternative
        current_content = target_msg.get('content', '')
        if isinstance(current_content, list):
            current_content = ' '.join(
                b.get('text', '') for b in current_content
                if isinstance(b, dict) and b.get('type') == 'text')
        self.save_alternative(session_id, message_index, current_content, active=False)

        # Find preceding user message
        user_msg = None
        for i in range(real_idx - 1, -1, -1):
            if msgs[i].get('role') == 'user':
                content = msgs[i].get('content', '')
                if isinstance(content, str):
                    user_msg = content
                elif isinstance(content, list):
                    user_msg = ' '.join(
                        b.get('text', '') for b in content
                        if isinstance(b, dict) and b.get('type') == 'text')
                break

        if not user_msg:
            return None

        # Remove assistant message and everything after it
        session.messages = msgs[:real_idx]

        # Re-process
        from .engine import process_message
        response = await process_message(session_id, user_msg)

        # Save new response as active alternative
        self.save_alternative(session_id, message_index, response, active=True)

        return response


conversation_fork = ConversationFork()


# ============================================================
# 4. Provider Health Check (프로바이더 상태 확인) — Open WebUI style
# ============================================================

class ProviderHealthCheck:
    """Check health of all configured LLM providers.

    프로바이더별 상태 확인: API 키 유효성 + 실제 연결 테스트.
    """

    # Cache results for 5 minutes
    _cache: Dict[str, Any] = {}
    _cache_ts: float = 0
    _CACHE_TTL = 300

    def check_all(self, force: bool = False) -> Dict[str, Any]:
        """Check all providers. Returns {provider: status_string}.

        모든 프로바이더 상태 확인. 캐시 5분.
        """
        now = time.time()
        if not force and self._cache and (now - self._cache_ts) < self._CACHE_TTL:
            return self._cache

        from .crypto import vault
        results = {}

        # Anthropic
        if vault.is_unlocked and vault.get('anthropic_api_key'):
            results['anthropic'] = self._test_anthropic(vault.get('anthropic_api_key'))
        else:
            results['anthropic'] = 'not configured'

        # OpenAI
        if vault.is_unlocked and vault.get('openai_api_key'):
            results['openai'] = self._test_openai(vault.get('openai_api_key'))
        else:
            results['openai'] = 'not configured'

        # xAI
        if vault.is_unlocked and vault.get('xai_api_key'):
            results['xai'] = self._test_xai(vault.get('xai_api_key'))
        else:
            results['xai'] = 'not configured'

        # Google
        if vault.is_unlocked and vault.get('google_api_key'):
            results['google'] = self._test_google(vault.get('google_api_key'))
        else:
            results['google'] = 'not configured'

        # Ollama
        ollama_url = vault.get('ollama_url') if vault.is_unlocked else None
        if ollama_url:
            results['ollama'] = self._test_ollama(ollama_url)
        else:
            results['ollama'] = 'not configured'

        # DeepSeek
        if vault.is_unlocked and vault.get('deepseek_api_key'):
            results['deepseek'] = self._test_deepseek(vault.get('deepseek_api_key'))
        else:
            results['deepseek'] = 'not configured'

        overall = 'ok' if any(v == 'ok' for v in results.values()) else 'error'
        result = {'status': overall, 'providers': results, 'checked_at': datetime.now(KST).isoformat()}
        self._cache = result
        self._cache_ts = now
        return result

    def _test_anthropic(self, key: str) -> str:
        try:
            from .llm import _http_post
            _http_post('https://api.anthropic.com/v1/messages',
                       {'x-api-key': key, 'content-type': 'application/json',
                        'anthropic-version': '2023-06-01'},
                       {'model': 'claude-3-5-haiku-20241022', 'max_tokens': 5,
                        'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=10)
            return 'ok'
        except Exception as e:
            return f'error: {str(e)[:100]}'

    def _test_openai(self, key: str) -> str:
        try:
            from .llm import _http_post
            _http_post('https://api.openai.com/v1/chat/completions',
                       {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                       {'model': 'gpt-4o-mini', 'max_tokens': 5,
                        'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=10)
            return 'ok'
        except Exception as e:
            return f'error: {str(e)[:100]}'

    def _test_xai(self, key: str) -> str:
        try:
            from .llm import _http_post
            _http_post('https://api.x.ai/v1/chat/completions',
                       {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                       {'model': 'grok-3-mini-fast', 'max_tokens': 5,
                        'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=10)
            return 'ok'
        except Exception as e:
            return f'error: {str(e)[:100]}'

    def _test_google(self, key: str) -> str:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
                data=json.dumps({'contents': [{'parts': [{'text': 'ping'}]}]}).encode(),
                headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=10)
            return 'ok'
        except Exception as e:
            return f'error: {str(e)[:100]}'

    def _test_deepseek(self, key: str) -> str:
        try:
            from .llm import _http_post
            _http_post('https://api.deepseek.com/v1/chat/completions',
                       {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                       {'model': 'deepseek-chat', 'max_tokens': 5,
                        'messages': [{'role': 'user', 'content': 'ping'}]}, timeout=10)
            return 'ok'
        except Exception as e:
            return f'error: {str(e)[:100]}'

    def _test_ollama(self, url: str) -> str:
        try:
            import urllib.request
            # Test Ollama connectivity by listing models
            req = urllib.request.Request(f"{url.rstrip('/')}/api/tags")
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            model_count = len(data.get('models', []))
            return f'ok ({model_count} models)'
        except Exception as e:
            return f'offline: {str(e)[:100]}'


provider_health = ProviderHealthCheck()


# ============================================================
# 5. Model Auto-Detection (모델 자동 감지) — Open WebUI style
# ============================================================

class ModelDetector:
    """Auto-detect available models from all configured providers.

    사용 가능한 모델 자동 감지: Ollama 로컬 모델 + API 프로바이더.
    """

    _cache: List[Dict] = []
    _cache_ts: float = 0
    _CACHE_TTL = 600  # 10 minutes

    def detect_all(self, force: bool = False) -> List[Dict]:
        """Detect all available models. Returns list of {id, name, provider, available}.

        모든 사용 가능한 모델 감지.
        """
        now = time.time()
        if not force and self._cache and (now - self._cache_ts) < self._CACHE_TTL:
            return self._cache

        from .crypto import vault
        from .constants import MODELS

        models = []

        # Static models from constants (always listed, availability based on key)
        for label, model_id in MODELS.items():
            provider = model_id.split('/')[0] if '/' in model_id else 'anthropic'
            key_name = f'{provider}_api_key'
            available = bool(vault.is_unlocked and vault.get(key_name))
            models.append({
                'id': model_id, 'name': label, 'provider': provider,
                'available': available, 'source': 'config'
            })

        # Ollama dynamic models
        ollama_url = vault.get('ollama_url') if vault.is_unlocked else None
        if ollama_url:
            try:
                import urllib.request
                req = urllib.request.Request(f"{ollama_url.rstrip('/')}/api/tags")
                resp = urllib.request.urlopen(req, timeout=5)
                data = json.loads(resp.read())
                for m in data.get('models', []):
                    name = m.get('name', '')
                    models.append({
                        'id': f'ollama/{name}', 'name': name,
                        'provider': 'ollama', 'available': True,
                        'source': 'auto-detected',
                        'size': m.get('size', 0),
                        'modified': m.get('modified_at', ''),
                    })
            except Exception as e:
                log.warning(f"Ollama model detection failed: {e}")

        self._cache = models
        self._cache_ts = now
        return models


model_detector = ModelDetector()


# ============================================================
# 6. Enhanced File Upload (파일 업로드 강화) — Open WebUI style
# ============================================================

# Allowed file types for upload (허용 파일 타입)
ALLOWED_UPLOAD_EXTENSIONS = {
    'png', 'jpg', 'jpeg', 'gif', 'webp',  # Images
    'pdf', 'txt', 'csv', 'json', 'md',    # Documents
    'py', 'js', 'ts', 'html', 'css',      # Code
    'sh', 'yaml', 'yml', 'xml', 'sql',    # Config/scripts
    'log', 'bat',                           # Misc
}


def validate_upload(filename: str, size_bytes: int) -> Tuple[bool, str]:
    """Validate file upload. Returns (ok, error_message).

    파일 업로드 검증: 확장자 + 크기.
    """
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return False, f'File type .{ext} not allowed. Allowed: {", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}'
    if size_bytes > 50 * 1024 * 1024:
        return False, 'File too large (max 50MB)'
    if size_bytes == 0:
        return False, 'Empty file'
    return True, ''


def extract_pdf_text(data: bytes) -> str:
    """Extract text from PDF using pure Python (간단한 PDF 텍스트 추출).

    This is a basic extractor that handles common PDF text streams.
    For complex PDFs with images/tables, results may be partial.
    순수 Python PDF 파서: 텍스트 스트림만 추출.
    """
    import zlib
    text_parts = []

    # Find all stream objects
    i = 0
    while i < len(data):
        # Find stream markers
        stream_start = data.find(b'stream\r\n', i)
        if stream_start == -1:
            stream_start = data.find(b'stream\n', i)
        if stream_start == -1:
            break

        stream_start += len(b'stream\r\n') if data[stream_start:stream_start + 8] == b'stream\r\n' else len(b'stream\n')
        stream_end = data.find(b'endstream', stream_start)
        if stream_end == -1:
            break

        stream_data = data[stream_start:stream_end]

        # Try to decompress (most PDF streams are FlateDecode)
        try:
            decompressed = zlib.decompress(stream_data)
        except Exception:
            decompressed = stream_data

        # Extract text between BT...ET markers (text objects)
        text_blocks = re.findall(rb'BT\s*(.*?)\s*ET', decompressed, re.DOTALL)
        for block in text_blocks:
            # Extract text from Tj, TJ, ' operators
            # Tj: (text) Tj
            for match in re.finditer(rb'\(([^)]*)\)\s*Tj', block):
                text_parts.append(match.group(1).decode('latin-1', errors='replace'))
            # TJ: [(text) -kern (text)] TJ
            for match in re.finditer(rb'\[(.*?)\]\s*TJ', block):
                inner = match.group(1)
                for text_match in re.finditer(rb'\(([^)]*)\)', inner):
                    text_parts.append(text_match.group(1).decode('latin-1', errors='replace'))

        i = stream_end + 9

    result = ' '.join(text_parts)
    # Clean up common PDF escape sequences
    result = result.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t')
    result = re.sub(r'\\(\d{3})', lambda m: chr(int(m.group(1), 8)), result)
    return result.strip() if result.strip() else '[PDF text extraction returned no text / PDF 텍스트 추출 실패]'


def process_uploaded_file(filename: str, data: bytes) -> str:
    """Process uploaded file and return content for LLM context.

    업로드된 파일 처리: 내용을 LLM 컨텍스트에 삽입.
    """
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    if ext == 'pdf':
        text = extract_pdf_text(data)
        return f'📄 **{filename}** ({len(data)/1024:.1f}KB)\n```\n{text[:10000]}\n```'

    if ext in ('txt', 'md', 'log', 'sh', 'bat', 'sql'):
        text = data.decode('utf-8', errors='replace')[:10000]
        return f'📄 **{filename}** ({len(data)/1024:.1f}KB)\n```\n{text}\n```'

    if ext in ('py', 'js', 'ts', 'html', 'css', 'yaml', 'yml', 'xml'):
        text = data.decode('utf-8', errors='replace')[:10000]
        return f'📄 **{filename}** ({len(data)/1024:.1f}KB)\n```{ext}\n{text}\n```'

    if ext == 'csv':
        text = data.decode('utf-8', errors='replace')
        lines = text.split('\n')[:100]  # First 100 lines
        preview = '\n'.join(lines)
        return f'📊 **{filename}** ({len(data)/1024:.1f}KB, {len(text.split(chr(10)))} rows)\n```csv\n{preview}\n```'

    if ext == 'json':
        text = data.decode('utf-8', errors='replace')
        try:
            parsed = json.loads(text)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)[:10000]
            return f'📋 **{filename}** ({len(data)/1024:.1f}KB)\n```json\n{pretty}\n```'
        except json.JSONDecodeError:
            return f'📋 **{filename}** ({len(data)/1024:.1f}KB)\n```json\n{text[:10000]}\n```'

    return f'📎 **{filename}** ({len(data)/1024:.1f}KB) — binary file, content not displayed.'


# ============================================================
# 7. Session Groups (대화 주제 그룹) — LobeChat style
# ============================================================

class SessionGroupManager:
    """Manage session groups/folders for organizing conversations.

    세션 그룹 관리: 대화를 폴더/그룹으로 분류.
    """

    def __init__(self):
        self._ensure_tables()

    def _ensure_tables(self):
        try:
            from .core import _get_db
            conn = _get_db()
            conn.execute('''CREATE TABLE IF NOT EXISTS session_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '#6366f1',
                sort_order INTEGER DEFAULT 0,
                collapsed INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )''')
            # Add group_id to session_store
            try:
                conn.execute('ALTER TABLE session_store ADD COLUMN group_id INTEGER DEFAULT NULL')
            except Exception:
                pass
            conn.commit()
            # Create default group if none exists
            row = conn.execute('SELECT COUNT(*) FROM session_groups').fetchone()
            if row[0] == 0:
                now = datetime.now(KST).isoformat()
                conn.execute(
                    'INSERT INTO session_groups (name, sort_order, created_at) VALUES (?, 0, ?)',
                    ('기본', now))
                conn.commit()
        except Exception as e:
            log.warning(f"Session groups init: {e}")

    def list_groups(self) -> List[Dict]:
        """List all groups (그룹 목록)."""
        try:
            from .core import _get_db
            conn = _get_db()
            rows = conn.execute(
                'SELECT id, name, color, sort_order, collapsed, created_at '
                'FROM session_groups ORDER BY sort_order, id'
            ).fetchall()
            groups = []
            for r in rows:
                # Count sessions in group
                count = conn.execute(
                    'SELECT COUNT(*) FROM session_store WHERE group_id=?', (r[0],)
                ).fetchone()[0]
                groups.append({
                    'id': r[0], 'name': r[1], 'color': r[2],
                    'sort_order': r[3], 'collapsed': bool(r[4]),
                    'created_at': r[5], 'session_count': count
                })
            return groups
        except Exception:
            return []

    def create_group(self, name: str, color: str = '#6366f1') -> Dict:
        """Create a new group (그룹 생성)."""
        from .core import _get_db
        conn = _get_db()
        now = datetime.now(KST).isoformat()
        max_order = conn.execute('SELECT COALESCE(MAX(sort_order),0) FROM session_groups').fetchone()[0]
        conn.execute(
            'INSERT INTO session_groups (name, color, sort_order, created_at) VALUES (?, ?, ?, ?)',
            (name, color, max_order + 1, now))
        conn.commit()
        gid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        return {'id': gid, 'name': name, 'color': color, 'ok': True}

    def update_group(self, group_id: int, **kwargs) -> bool:
        """Update group properties (그룹 수정)."""
        from .core import _get_db
        conn = _get_db()
        sets = []
        vals = []
        for key in ('name', 'color', 'sort_order', 'collapsed'):
            if key in kwargs:
                sets.append(f'{key}=?')
                vals.append(kwargs[key])
        if not sets:
            return False
        vals.append(group_id)
        conn.execute(f'UPDATE session_groups SET {",".join(sets)} WHERE id=?', vals)
        conn.commit()
        return True

    def delete_group(self, group_id: int) -> bool:
        """Delete a group. Sessions move to ungrouped (그룹 삭제)."""
        from .core import _get_db
        conn = _get_db()
        conn.execute('UPDATE session_store SET group_id=NULL WHERE group_id=?', (group_id,))
        conn.execute('DELETE FROM session_groups WHERE id=?', (group_id,))
        conn.commit()
        return True

    def move_session(self, session_id: str, group_id: Optional[int]) -> bool:
        """Move a session to a group (세션을 그룹으로 이동)."""
        from .core import _get_db
        conn = _get_db()
        conn.execute('UPDATE session_store SET group_id=? WHERE session_id=?',
                     (group_id, session_id))
        conn.commit()
        return True


session_groups = SessionGroupManager()


# ============================================================
# 8. Message Bookmarks (메시지 북마크) — LobeChat style
# ============================================================

class BookmarkManager:
    """Manage message bookmarks across sessions.

    메시지 북마크: 중요한 메시지에 ⭐ 표시.
    """

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        try:
            from .core import _get_db
            conn = _get_db()
            conn.execute('''CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                role TEXT DEFAULT 'assistant',
                content_preview TEXT,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(session_id, message_index)
            )''')
            conn.commit()
        except Exception as e:
            log.warning(f"Bookmarks table init: {e}")

    def add(self, session_id: str, message_index: int,
            content_preview: str = '', note: str = '', role: str = 'assistant') -> bool:
        """Add a bookmark (북마크 추가)."""
        try:
            from .core import _get_db
            conn = _get_db()
            now = datetime.now(KST).isoformat()
            conn.execute(
                'INSERT OR REPLACE INTO bookmarks '
                '(session_id, message_index, role, content_preview, note, created_at) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (session_id, message_index, role, content_preview[:200], note, now))
            conn.commit()
            return True
        except Exception:
            return False

    def remove(self, session_id: str, message_index: int) -> bool:
        """Remove a bookmark (북마크 제거)."""
        try:
            from .core import _get_db
            conn = _get_db()
            conn.execute('DELETE FROM bookmarks WHERE session_id=? AND message_index=?',
                         (session_id, message_index))
            conn.commit()
            return True
        except Exception:
            return False

    def list_all(self, limit: int = 50) -> List[Dict]:
        """List all bookmarks (전체 북마크 목록)."""
        try:
            from .core import _get_db
            conn = _get_db()
            rows = conn.execute(
                'SELECT id, session_id, message_index, role, content_preview, note, created_at '
                'FROM bookmarks ORDER BY created_at DESC LIMIT ?',
                (limit,)).fetchall()
            return [{'id': r[0], 'session_id': r[1], 'message_index': r[2],
                     'role': r[3], 'preview': r[4], 'note': r[5], 'created_at': r[6]}
                    for r in rows]
        except Exception:
            return []

    def list_session(self, session_id: str) -> List[Dict]:
        """List bookmarks for a session (세션별 북마크)."""
        try:
            from .core import _get_db
            conn = _get_db()
            rows = conn.execute(
                'SELECT id, message_index, role, content_preview, note, created_at '
                'FROM bookmarks WHERE session_id=? ORDER BY message_index',
                (session_id,)).fetchall()
            return [{'id': r[0], 'message_index': r[1], 'role': r[2],
                     'preview': r[3], 'note': r[4], 'created_at': r[5]}
                    for r in rows]
        except Exception:
            return []

    def is_bookmarked(self, session_id: str, message_index: int) -> bool:
        """Check if a message is bookmarked (북마크 여부)."""
        try:
            from .core import _get_db
            conn = _get_db()
            row = conn.execute(
                'SELECT 1 FROM bookmarks WHERE session_id=? AND message_index=?',
                (session_id, message_index)).fetchone()
            return row is not None
        except Exception:
            return False


bookmark_manager = BookmarkManager()


# ============================================================
# 9. System Prompt Variables (시스템 프롬프트 변수) — LobeChat style
# ============================================================

def substitute_prompt_variables(text: str, session_id: str = '',
                                model: str = '', user: str = '') -> str:
    """Replace template variables in system prompt.

    시스템 프롬프트 동적 변수 치환:
    {{date}} → 현재 날짜
    {{time}} → 현재 시간
    {{user}} → 사용자 이름
    {{model}} → 현재 모델
    {{session}} → 세션 ID
    {{version}} → SalmAlm 버전
    """
    now = datetime.now(KST)
    replacements = {
        '{{date}}': now.strftime('%Y-%m-%d'),
        '{{time}}': now.strftime('%H:%M:%S'),
        '{{datetime}}': now.strftime('%Y-%m-%d %H:%M'),
        '{{user}}': user or 'user',
        '{{model}}': model or 'auto',
        '{{session}}': session_id or 'default',
        '{{version}}': VERSION,
        '{{weekday}}': now.strftime('%A'),
        '{{weekday_kr}}': ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일'][now.weekday()],
    }
    for var, val in replacements.items():
        text = text.replace(var, val)
    return text


# ============================================================
# 10. Response Compare / Beam (응답 비교) — BIG-AGI style
# ============================================================

async def compare_models(session_id: str, message: str,
                         models: List[str] = None) -> List[Dict]:
    """Send same prompt to multiple models and compare responses.

    같은 프롬프트를 여러 모델에 전송하여 응답 비교.
    Returns list of {model, response, tokens, cost, time_ms}.
    """
    from .engine import _call_llm_async
    from .prompt import build_system_prompt
    from .core import get_session

    if not models:
        from .constants import MODELS
        models = [MODELS.get('haiku', ''), MODELS.get('sonnet', '')]
        models = [m for m in models if m]

    session = get_session(session_id)
    system_prompt = build_system_prompt(full=False)
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': message}
    ]

    async def _call_one(model_id: str) -> Dict:
        t0 = time.time()
        try:
            result = await _call_llm_async(messages, model=model_id, max_tokens=4096)
            elapsed = int((time.time() - t0) * 1000)
            usage = result.get('usage', {})
            return {
                'model': model_id,
                'response': result.get('content', ''),
                'input_tokens': usage.get('input', 0),
                'output_tokens': usage.get('output', 0),
                'time_ms': elapsed,
                'error': None,
            }
        except Exception as e:
            return {
                'model': model_id,
                'response': '',
                'input_tokens': 0, 'output_tokens': 0,
                'time_ms': int((time.time() - t0) * 1000),
                'error': str(e)[:200],
            }

    # Run all models in parallel
    tasks = [_call_one(m) for m in models]
    results = await asyncio.gather(*tasks)
    return list(results)


# ============================================================
# 11. Smart Paste (스마트 붙여넣기) — BIG-AGI style
# ============================================================

def detect_paste_type(text: str) -> Dict[str, Any]:
    """Detect the type of pasted content and suggest formatting.

    붙여넣기 내용 유형 감지 + 포맷팅 제안.
    Returns {type, formatted_text, suggestion}.
    """
    text = text.strip()

    # URL detection (URL 감지)
    url_pattern = re.compile(r'^https?://\S+$')
    if url_pattern.match(text):
        return {
            'type': 'url',
            'original': text,
            'suggestion': 'fetch_content',
            'message': '🔗 URL detected. Fetch page content? / URL이 감지되었습니다. 페이지 내용을 가져올까요?'
        }

    # Multiple URLs
    lines = text.split('\n')
    urls = [l.strip() for l in lines if url_pattern.match(l.strip())]
    if len(urls) > 1:
        return {
            'type': 'urls',
            'original': text,
            'urls': urls,
            'suggestion': 'fetch_all',
            'message': f'🔗 {len(urls)} URLs detected. / {len(urls)}개의 URL이 감지되었습니다.'
        }

    # Code detection (코드 감지)
    code_indicators = {
        'python': [r'^\s*(import |from .+ import |def |class |if __name__)', r'print\('],
        'javascript': [r'^\s*(const |let |var |function |import |export |=>)', r'console\.log'],
        'typescript': [r'^\s*(interface |type |const .+:.+= |import .+ from)', r': string|: number|: boolean'],
        'html': [r'<(!DOCTYPE|html|head|body|div|span|script)', r'</\w+>'],
        'css': [r'\{[^}]*:[^}]*;\s*\}', r'\.([\w-]+)\s*\{'],
        'sql': [r'^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\s', r'\bFROM\b.*\bWHERE\b'],
        'shell': [r'^#!/bin/(ba)?sh', r'^\s*(echo |export |alias |sudo )'],
        'json': [r'^\s*[\[{]', r'"[^"]+"\s*:\s*'],
        'yaml': [r'^\w+:\s*$', r'^\s*-\s+\w+'],
    }

    for lang, patterns in code_indicators.items():
        matches = sum(1 for p in patterns if re.search(p, text, re.MULTILINE | re.IGNORECASE))
        if matches >= 1 and len(text) > 20:
            # Check if it's likely code (not just a sentence with code-like words)
            if lang == 'json':
                try:
                    json.loads(text)
                    return {
                        'type': 'code', 'language': 'json',
                        'original': text,
                        'formatted': f'```json\n{text}\n```',
                        'suggestion': 'wrap_code',
                        'message': '📋 JSON detected. / JSON이 감지되었습니다.'
                    }
                except json.JSONDecodeError:
                    continue
            elif matches >= 1 and any(re.search(p, text, re.MULTILINE) for p in patterns):
                return {
                    'type': 'code', 'language': lang,
                    'original': text,
                    'formatted': f'```{lang}\n{text}\n```',
                    'suggestion': 'wrap_code',
                    'message': f'💻 {lang.title()} code detected. / {lang.title()} 코드가 감지되었습니다.'
                }

    # Plain text
    return {
        'type': 'text',
        'original': text,
        'suggestion': None,
        'message': None
    }


# ============================================================
# 12. Conversation Summary Card (대화 요약 카드) — BIG-AGI style
# ============================================================

def get_summary_card(session_id: str) -> Optional[Dict]:
    """Get conversation summary card for a session.

    대화 요약 카드: compaction 결과를 활용한 요약.
    Returns {summary, message_count, token_estimate, first_topic}.
    """
    from .core import get_session

    session = get_session(session_id)
    msgs = session.messages

    # Need enough messages to warrant a summary
    user_msgs = [m for m in msgs if m.get('role') == 'user' and isinstance(m.get('content'), str)]
    asst_msgs = [m for m in msgs if m.get('role') == 'assistant']

    if len(user_msgs) < 3:
        return None

    # Check for existing compaction summary in system message
    system_msg = next((m for m in msgs if m.get('role') == 'system'), None)
    summary = None
    if system_msg:
        content = system_msg.get('content', '')
        # Look for compaction marker
        marker = '## Conversation Summary'
        if marker in content:
            summary = content.split(marker, 1)[1].split('\n\n')[0].strip()
            summary = summary[:500]

    # If no compaction summary, generate a simple one from first messages
    if not summary:
        topics = []
        for m in user_msgs[:5]:
            text = m.get('content', '')[:100]
            if text:
                topics.append(text)
        if topics:
            summary = ' → '.join(t[:50] for t in topics[:3])

    if not summary:
        return None

    # Estimate tokens
    total_chars = sum(len(str(m.get('content', ''))) for m in msgs)
    token_estimate = total_chars // 4  # Rough estimate

    return {
        'summary': summary,
        'message_count': len(user_msgs) + len(asst_msgs),
        'token_estimate': token_estimate,
        'first_topic': user_msgs[0].get('content', '')[:100] if user_msgs else '',
    }
