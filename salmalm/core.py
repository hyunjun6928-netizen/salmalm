"""SalmAlm core — audit, cache, usage, router, compaction, search,
subagent, skills, session, cron, daily."""
import asyncio, hashlib, json, math, os, re, sqlite3, textwrap, threading, time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .constants import *
from .crypto import vault, log

# ============================================================
_audit_lock = threading.Lock()   # Audit log writes
_usage_lock = threading.Lock()   # Usage tracking (separate to avoid contention)
_thread_local = threading.local()  # Thread-local DB connections


def _get_db() -> sqlite3.Connection:
    """Get thread-local SQLite connection (reused across calls, WAL mode)."""
    conn = getattr(_thread_local, 'audit_conn', None)
    if conn is None:
        conn = sqlite3.connect(str(AUDIT_DB), check_same_thread=True)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        # Auto-create tables on first connection per thread
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
        _thread_local.audit_conn = conn
    return conn


def _init_audit_db():
    conn = _get_db()
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


def audit_log(event: str, detail: str = ''):
    """Write an audit event to the security log file."""
    with _audit_lock:
        conn = _get_db()
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



class ResponseCache:
    """Simple TTL cache for LLM responses to avoid duplicate calls."""

    def __init__(self, max_size=100, ttl=CACHE_TTL):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    def _key(self, model: str, messages: list, session_id: str = '') -> str:
        # Include last 5 messages for better session isolation even without explicit session_id
        content = json.dumps({'s': session_id, 'm': model, 'msgs': messages[-5:]}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(self, model: str, messages: list, session_id: str = '') -> Optional[str]:
        """Get a cached response by key, or None if expired/missing."""
        k = self._key(model, messages, session_id)
        if k in self._cache:
            entry = self._cache[k]
            if time.time() - entry['ts'] < self._ttl:
                self._cache.move_to_end(k)
                log.info(f"[COST] Cache hit -- saved API call")
                return entry['response']  # type: ignore[no-any-return]
            del self._cache[k]
        return None

    def put(self, model: str, messages: list, response: str, session_id: str = ''):
        """Store a response in cache with TTL."""
        k = self._key(model, messages, session_id)
        self._cache[k] = {'response': response, 'ts': time.time()}
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)


response_cache = ResponseCache()

# _usage_lock already defined at top of file
_usage = {'total_input': 0, 'total_output': 0, 'total_cost': 0.0,
          'by_model': {}, 'session_start': time.time()}

# Production observability metrics
_metrics = {"llm_calls": 0, "llm_errors": 0, "tool_calls": 0, "tool_errors": 0,
            "total_cost": 0.0, "total_tokens_in": 0, "total_tokens_out": 0}

# Hard cost cap — stop all LLM calls after this threshold (per session lifetime)
# Override with SALMALM_COST_CAP env var (in USD)
COST_CAP = float(os.environ.get('SALMALM_COST_CAP', '50.0'))


class CostCapExceeded(Exception):
    """Raised when cumulative API spend exceeds the cost cap."""
    pass

def _restore_usage():
    """Restore cumulative usage from SQLite on startup."""
    try:
        conn = _get_db()
        rows = conn.execute('SELECT model, SUM(input_tokens), SUM(output_tokens), SUM(cost), COUNT(*) FROM usage_stats GROUP BY model').fetchall()
        for model, inp, out, cost, calls in rows:
            short = model.split('/')[-1] if '/' in model else model
            _usage['total_input'] += (inp or 0)  # type: ignore[operator]
            _usage['total_output'] += (out or 0)  # type: ignore[operator]
            _usage['total_cost'] += (cost or 0)  # type: ignore[operator]
            _usage['by_model'][short] = {'input': inp or 0, 'output': out or 0,  # type: ignore[index]
                                          'cost': cost or 0, 'calls': calls or 0}
        if _usage['total_cost'] > 0:  # type: ignore[operator]
            log.info(f"[STAT] Usage restored: ${_usage['total_cost']:.4f} total")
    except Exception as e:
        log.warning(f"Usage restore failed: {e}")


def check_cost_cap():
    """Raise CostCapExceeded if cumulative cost exceeds the cap. 0 = disabled."""
    if COST_CAP <= 0:
        return
    with _usage_lock:
        if _usage['total_cost'] >= COST_CAP:
            raise CostCapExceeded(
                f"Cost cap exceeded: ${_usage['total_cost']:.2f} >= ${COST_CAP:.2f}. "
                f"Increase SALMALM_COST_CAP env var or restart.")


def track_usage(model: str, input_tokens: int, output_tokens: int):
    """Record token usage and cost for a model call."""
    with _usage_lock:
        short = model.split('/')[-1] if '/' in model else model
        cost_info = MODEL_COSTS.get(short, {'input': 1.0, 'output': 5.0})
        cost = (input_tokens * cost_info['input'] + output_tokens * cost_info['output']) / 1_000_000
        _usage['total_input'] += input_tokens  # type: ignore[operator]
        _usage['total_output'] += output_tokens  # type: ignore[operator]
        _usage['total_cost'] += cost  # type: ignore[operator]
        if short not in _usage['by_model']:  # type: ignore[operator]
            _usage['by_model'][short] = {'input': 0, 'output': 0, 'cost': 0.0, 'calls': 0}  # type: ignore[index]
        _usage['by_model'][short]['input'] += input_tokens  # type: ignore[index]
        _usage['by_model'][short]['output'] += output_tokens  # type: ignore[index]
        _usage['by_model'][short]['cost'] += cost  # type: ignore[index]
        _usage['by_model'][short]['calls'] += 1  # type: ignore[index]
        # Persist to SQLite
        try:
            conn = _get_db()
            conn.execute('INSERT INTO usage_stats (ts, model, input_tokens, output_tokens, cost) VALUES (?,?,?,?,?)',
                         (datetime.now(KST).isoformat(), model, input_tokens, output_tokens, cost))
            conn.commit()
        except Exception as e:
            log.debug(f"Suppressed: {e}")


def get_usage_report() -> dict:
    """Generate a formatted usage report with token counts and costs."""
    with _usage_lock:
        elapsed = time.time() - _usage['session_start']  # type: ignore[operator]
        return {**_usage, 'elapsed_hours': round(elapsed / 3600, 2)}



class ModelRouter:
    """Routes queries to appropriate models based on complexity."""

    # Tier pools sourced from constants.py MODEL_TIERS (single source of truth)
    TIERS = MODEL_TIERS

    _MODEL_PREF_FILE = BASE_DIR / '.model_pref'

    def __init__(self):
        self.default_tier = 2
        self.force_model: Optional[str] = None
        # Restore persisted model preference
        try:
            if self._MODEL_PREF_FILE.exists():
                saved = self._MODEL_PREF_FILE.read_text().strip()
                if saved and saved != 'auto':
                    self.force_model = saved
                    log.info(f"[FIX] Restored model preference: {saved}")
        except Exception as e:
            log.debug(f"Suppressed: {e}")

    def set_force_model(self, model: Optional[str]):
        """Set and persist model preference."""
        self.force_model = model
        try:
            if model:
                self._MODEL_PREF_FILE.write_text(model)
            elif self._MODEL_PREF_FILE.exists():
                self._MODEL_PREF_FILE.unlink()
        except Exception as e:
            log.error(f"Failed to persist model pref: {e}")

    def route(self, user_message: str, has_tools: bool = False,
              iteration: int = 0) -> str:
        """Route a message to the best model based on intent classification."""
        if self.force_model:
            return self.force_model

        msg = user_message.lower()
        msg_len = len(user_message)

        # Tool-heavy iterations → always Tier 2+
        if iteration > 2:
            return self._pick_available(2)

        # Tier 3: complex tasks
        complex_score = sum(1 for kw in COMPLEX_INDICATORS if kw in msg)
        tool_hint_score = sum(1 for kw in TOOL_HINT_KEYWORDS if kw in msg)
        if complex_score >= 2 or msg_len > 1000 or (complex_score >= 1 and tool_hint_score >= 1):
            return self._pick_available(3)

        # Tier 2: tool usage likely or medium complexity
        if has_tools and (tool_hint_score >= 1 or msg_len > 300):
            return self._pick_available(2)

        # Tier 1: simple queries only
        if msg_len < SIMPLE_QUERY_MAX_CHARS and not has_tools and complex_score == 0:
            return self._pick_available(1)

        # Tier 2: default
        return self._pick_available(2)

    _OR_PROVIDERS = frozenset(['deepseek', 'meta-llama', 'mistralai', 'qwen'])

    def _has_key(self, provider: str) -> bool:
        if provider == 'ollama':
            return True  # Ollama always available (local)
        if provider in self._OR_PROVIDERS:
            return bool(vault.get('openrouter_api_key'))
        return bool(vault.get(f'{provider}_api_key'))

    def _pick_available(self, tier: int) -> str:
        models = self.TIERS.get(tier, self.TIERS[2])
        for m in models:
            provider = m.split('/')[0]
            if self._has_key(provider):
                return m
        # Fallback: try any available model
        for t in [2, 1, 3]:
            for m in self.TIERS.get(t, []):
                provider = m.split('/')[0]
                if self._has_key(provider):
                    return m
        return 'google/gemini-3-flash-preview'  # last resort


router = ModelRouter()


# ============================================================
def _msg_content_str(msg: dict) -> str:
    """Extract text content from a message (handles list content blocks)."""
    c = msg.get('content', '')
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return ' '.join(b.get('text', '') for b in c if isinstance(b, dict) and b.get('type') == 'text')
    return str(c)


def compact_messages(messages: list, model: Optional[str] = None,
                     session: Optional['Session'] = None) -> list:
    """Multi-stage compaction: trim tool results → drop old tools → summarize.
    Hard limit: max 100 messages, max 500K chars (≈125K tokens).
    OpenClaw-style: flush memory before compaction."""
    MAX_MESSAGES = 100
    MAX_CHARS = 500_000

    # OpenClaw-style: pre-compaction memory flush
    total_chars_check = sum(len(_msg_content_str(m)) for m in messages)
    if session and total_chars_check > COMPACTION_THRESHOLD * 0.8:
        try:
            memory_manager.flush_before_compaction(session)
        except Exception as e:
            log.warning(f"[MEM] Memory flush error: {e}")

    # Hard message count limit
    if len(messages) > MAX_MESSAGES:
        system_msgs = [m for m in messages if m['role'] == 'system'][:1]
        recent = [m for m in messages if m['role'] != 'system'][-40:]
        messages = system_msgs + recent
        log.warning(f"[CUT] Hard msg limit: truncated to {len(messages)} messages")

    total_chars = sum(len(_msg_content_str(m)) for m in messages)

    # Hard char limit — emergency truncation
    if total_chars > MAX_CHARS:
        system_msgs = [m for m in messages if m['role'] == 'system'][:1]
        recent = [m for m in messages if m['role'] != 'system'][-20:]
        messages = system_msgs + recent
        total_chars = sum(len(_msg_content_str(m)) for m in messages)
        log.warning(f"[CUT] Hard char limit: truncated to {len(messages)} msgs ({total_chars} chars)")

    if total_chars < COMPACTION_THRESHOLD:
        return messages

    log.info(f"[PKG] Compacting {len(messages)} messages ({total_chars} chars)")

    # Stage 1: Trim long tool results (keep first 500 chars)
    trimmed = []
    for m in messages:
        if m['role'] == 'tool' and len(_msg_content_str(m)) > 500:
            trimmed.append({**m, 'content': _msg_content_str(m)[:500] + '\n... [truncated]'})
        elif m['role'] == 'user' and isinstance(m.get('content'), list):
            # Strip base64 image data from old messages
            new_content = []
            for block in m['content']:
                if isinstance(block, dict) and block.get('type') == 'image':
                    new_content.append({'type': 'text', 'text': '[Image attached]'})
                else:
                    new_content.append(block)
            trimmed.append({**m, 'content': new_content})
        else:
            trimmed.append(m)

    total_after_trim = sum(len(_msg_content_str(m)) for m in trimmed)
    if total_after_trim < COMPACTION_THRESHOLD:
        log.info(f"[PKG] Stage 1 sufficient: {total_chars} -> {total_after_trim} chars")
        return trimmed

    # Stage 2: Drop old tool messages entirely, keep last 10 messages
    system_msgs = [m for m in trimmed if m['role'] == 'system']
    non_system = [m for m in trimmed if m['role'] != 'system']
    recent = non_system[-10:]
    old = non_system[:-10]

    # Drop tool/tool_result messages from old, keep user/assistant
    old_important = [m for m in old if m['role'] in ('user', 'assistant')]

    stage2 = system_msgs + old_important + recent
    total_after_drop = sum(len(_msg_content_str(m)) for m in stage2)
    if total_after_drop < COMPACTION_THRESHOLD:
        log.info(f"[PKG] Stage 2 sufficient: {total_chars} -> {total_after_drop} chars")
        return stage2

    # Stage 3: Summarize old messages
    to_summarize = old_important
    if not to_summarize:
        return system_msgs + recent

    summary_text = '\n'.join(
        f"[{m['role']}]: {_msg_content_str(m)[:300]}" for m in to_summarize[-20:]
    )

    from .llm import call_llm
    # Pick cheapest available model for summarization (avoid hardcoded google)
    summary_model = router._pick_available(1)
    _summ_msgs = [
        {'role': 'system', 'content': 'Summarize the following conversation concisely. Focus on decisions, tasks, and key context in 5-8 sentences.'},
        {'role': 'user', 'content': summary_text}
    ]
    # Note: call_llm is sync (urllib). Always call directly since compact_messages
    # is invoked from sync context. If ever called from async, wrap in run_in_executor.
    summary_result = call_llm(_summ_msgs, model=summary_model, max_tokens=800)

    compacted = system_msgs + [
        {'role': 'system', 'content': f'[Previous conversation summary]\n{summary_result["content"]}'}
    ] + recent

    log.info(f"[PKG] Stage 3 compacted: {len(messages)} -> {len(compacted)} messages, "
             f"{total_chars} → {sum(len(_msg_content_str(m)) for m in compacted)} chars")
    return compacted



# ============================================================
import math

class TFIDFSearch:
    """Lightweight TF-IDF + cosine similarity search. No external deps."""

    def __init__(self):
        self._docs: list = []        # [(label, line_no, text, tokens)]
        self._idf: dict = {}         # term -> IDF score
        self._built = False
        self._last_index_time = 0
        self._stop_words = frozenset([
            '의', '가', '이', '은', '는', '을', '를', '에', '에서', '로', '으로',
            '와', '과', '도', '만', '부터', '까지', '에게', '한테', '에서의',
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'that', 'this', 'it', 'not', 'no', 'if', 'then', 'so', 'as', 'by',
        ])

    def _tokenize(self, text: str) -> list:
        """Split text into normalized tokens."""
        text = text.lower()
        # Split on non-alphanumeric (keeping Korean chars)
        tokens = re.findall(r'[\w가-힣]+', text)
        return [t for t in tokens if len(t) > 1 and t not in self._stop_words]

    def _index_files(self):
        """Build index from MEMORY.md, memory/*.md, uploads/*.txt etc."""
        now = time.time()
        if self._built and now - self._last_index_time < 300:  # Re-index every 5 min
            return

        self._docs = []
        doc_freq: dict = {}  # term -> number of docs containing it  # type: ignore[var-annotated]
        search_files = []

        if MEMORY_FILE.exists():
            search_files.append(('MEMORY.md', MEMORY_FILE))
        for f in sorted(MEMORY_DIR.glob('*.md')):
            search_files.append((f'memory/{f.name}', f))
        uploads_dir = WORKSPACE_DIR / 'uploads'
        if uploads_dir.exists():
            for f in uploads_dir.glob('*'):
                if f.suffix.lower() in ('.txt', '.md', '.py', '.js', '.json', '.csv',
                                         '.html', '.css', '.log', '.xml', '.yaml', '.yml'):
                    search_files.append((f'uploads/{f.name}', f))
        # Also index skills
        skills_dir = WORKSPACE_DIR / 'skills'
        if skills_dir.exists():
            for f in skills_dir.glob('**/*.md'):
                search_files.append((f'skills/{f.relative_to(skills_dir)}', f))

        for label, fpath in search_files:
            try:
                text = fpath.read_text(encoding='utf-8', errors='replace')
                lines = text.splitlines()
                # Index in chunks of 3 lines for context
                for i in range(0, len(lines), 2):
                    chunk = '\n'.join(lines[i:i+3])
                    if not chunk.strip():
                        continue
                    tokens = self._tokenize(chunk)
                    if not tokens:
                        continue
                    # TF for this chunk
                    tf = {}  # type: ignore[var-annotated]
                    for t in tokens:
                        tf[t] = tf.get(t, 0) + 1
                    self._docs.append((label, i + 1, chunk, tf))
                    # Doc frequency
                    for t in set(tokens):
                        doc_freq[t] = doc_freq.get(t, 0) + 1
            except Exception:
                continue

        # Compute IDF
        n_docs = len(self._docs)
        if n_docs > 0:
            self._idf = {t: math.log(n_docs / (1 + df))
                         for t, df in doc_freq.items()}
        self._built = True
        self._last_index_time = now  # type: ignore[assignment]
        log.info(f"[SEARCH] TF-IDF index built: {len(self._docs)} chunks from {len(search_files)} files")

    def search(self, query: str, max_results: int = 5) -> list:
        """Search with TF-IDF + cosine similarity. Returns [(score, label, lineno, snippet)]."""
        self._index_files()
        if not self._docs:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Query TF-IDF vector
        query_tf = {}  # type: ignore[var-annotated]
        for t in query_tokens:
            query_tf[t] = query_tf.get(t, 0) + 1
        query_vec = {t: tf * self._idf.get(t, 0) for t, tf in query_tf.items()}
        query_norm = math.sqrt(sum(v ** 2 for v in query_vec.values()))
        if query_norm == 0:
            return []

        # Score each document
        scored = []
        for label, lineno, chunk, doc_tf in self._docs:
            doc_vec = {t: tf * self._idf.get(t, 0) for t, tf in doc_tf.items()}
            # Cosine similarity
            dot = sum(query_vec.get(t, 0) * doc_vec.get(t, 0)
                      for t in set(query_vec) | set(doc_vec))
            doc_norm = math.sqrt(sum(v ** 2 for v in doc_vec.values()))
            if doc_norm == 0:
                continue
            similarity = dot / (query_norm * doc_norm)
            if similarity > 0.05:  # Threshold
                scored.append((similarity, label, lineno, chunk))

        scored.sort(key=lambda x: -x[0])
        return scored[:max_results]


_tfidf = TFIDFSearch()


# ============================================================
# MEMORY MANAGER — delegated to salmalm.memory module
# ============================================================
from .memory import MemoryManager, memory_manager


# ============================================================
# LLM CRON MANAGER — Scheduled tasks with LLM execution
# ============================================================
class LLMCronManager:
    """OpenClaw-style LLM cron with isolated session execution.

    Each cron job runs in its own isolated session (no cross-contamination).
    Completed tasks announce results to configured channels.
    """

    _JOBS_FILE = BASE_DIR / '.cron_jobs.json'

    def __init__(self):
        self.jobs = []

    def load_jobs(self):
        """Load persisted cron jobs from file."""
        try:
            if self._JOBS_FILE.exists():
                self.jobs = json.loads(self._JOBS_FILE.read_text())
                log.info(f"[CRON] Loaded {len(self.jobs)} LLM cron jobs")
        except Exception as e:
            log.error(f"Failed to load cron jobs: {e}")
            self.jobs = []

    def save_jobs(self):
        """Persist cron jobs to file."""
        try:
            self._JOBS_FILE.write_text(json.dumps(self.jobs, ensure_ascii=False, indent=2))
        except Exception as e:
            log.error(f"Failed to save cron jobs: {e}")

    def add_job(self, name: str, schedule: dict, prompt: str,
                model: Optional[str] = None, notify: bool = True) -> dict:
        """Add a new LLM cron job.
        schedule: {'kind': 'cron', 'expr': '0 6 * * *', 'tz': 'Asia/Seoul'}
                  {'kind': 'every', 'seconds': 3600}
                  {'kind': 'at', 'time': '2026-02-18T06:00:00+09:00'}
        """
        import uuid as _uuid
        job = {
            'id': str(_uuid.uuid4())[:8],
            'name': name,
            'schedule': schedule,
            'prompt': prompt,
            'model': model,
            'notify': notify,
            'enabled': True,
            'created': datetime.now(KST).isoformat(),
            'last_run': None,
            'run_count': 0
        }
        self.jobs.append(job)
        self.save_jobs()
        log.info(f"[CRON] LLM cron job added: {name} ({job['id']})")
        return job

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled cron job by ID."""
        before = len(self.jobs)
        self.jobs = [j for j in self.jobs if j['id'] != job_id]
        if len(self.jobs) < before:
            self.save_jobs()
            return True
        return False

    def list_jobs(self) -> list:
        """List all registered cron jobs with their schedules."""
        return [{'id': j['id'], 'name': j['name'], 'schedule': j['schedule'],
                 'enabled': j['enabled'], 'last_run': j['last_run'],
                 'run_count': j['run_count']} for j in self.jobs]

    def _should_run(self, job: dict) -> bool:
        """Check if a job should run now."""
        if not job['enabled']:
            return False
        sched = job['schedule']
        now = datetime.now(KST)

        if sched['kind'] == 'every':
            if not job['last_run']:
                return True
            elapsed = (now - datetime.fromisoformat(job['last_run'])).total_seconds()
            return elapsed >= sched['seconds']  # type: ignore[no-any-return]

        elif sched['kind'] == 'cron':
            # Simple cron: minute hour day month weekday
            expr = sched['expr'].split()
            if len(expr) != 5:
                return False
            checks = [
                (expr[0], now.minute), (expr[1], now.hour),
                (expr[2], now.day), (expr[3], now.month),
                (expr[4], now.weekday())  # 0=Monday
            ]
            for field, val in checks:
                if field == '*':
                    continue
                try:
                    if ',' in field:
                        if val not in [int(x) for x in field.split(',')]:
                            return False
                    elif '-' in field:
                        lo, hi = field.split('-')
                        if not (int(lo) <= val <= int(hi)):
                            return False
                    elif int(field) != val:
                        return False
                except ValueError:
                    return False
            # Don't run twice in same minute
            if job['last_run']:
                last = datetime.fromisoformat(job['last_run'])
                if (now - last).total_seconds() < 60:
                    return False
            return True

        elif sched['kind'] == 'at':
            target = datetime.fromisoformat(sched['time'])
            if job['last_run']:
                return False  # One-shot, already ran
            return now >= target

        return False

    async def tick(self):
        """Check and execute due jobs. Also runs heartbeat if due."""
        # OpenClaw-style heartbeat check
        if heartbeat.should_beat():
            try:
                await heartbeat.beat()
            except Exception as e:
                log.error(f"[HEARTBEAT] Tick error: {e}")

        for job in self.jobs:
            if not self._should_run(job):
                continue
            log.info(f"[CRON] LLM cron firing: {job['name']} ({job['id']})")
            try:
                from .engine import process_message
                # Track cost before/after to enforce per-cron-job cap
                cost_before = _usage['total_cost']
                response = await process_message(
                    f"cron-{job['id']}", job['prompt'],
                    model_override=job.get('model'))
                cost_after = _usage['total_cost']
                cron_cost = cost_after - cost_before
                MAX_CRON_JOB_COST = 2.0  # $2 max per cron execution
                if cron_cost > MAX_CRON_JOB_COST:
                    log.warning(f"[CRON] Job {job['name']} cost ${cron_cost:.2f} — exceeds ${MAX_CRON_JOB_COST} cap")
                job['last_run'] = datetime.now(KST).isoformat()
                job['run_count'] = job.get('run_count', 0) + 1
                self.save_jobs()
                log.info(f"[CRON] Cron completed: {job['name']} ({len(response)} chars)")

                # Notify via Telegram
                if job.get('notify') and _tg_bot and _tg_bot.token and _tg_bot.owner_id:
                    summary = response[:800] + ('...' if len(response) > 800 else '')
                    _tg_bot.send_message(
                        _tg_bot.owner_id,
                        f"⏰ SalmAlm scheduled task completed: {job['name']}\n\n{summary}")

                # Notify via web (store for polling)
                if job.get('notify'):
                    web_session = _sessions.get('web')
                    if web_session:
                        if not hasattr(web_session, '_notifications'):
                            web_session._notifications = []
                        web_session._notifications.append({
                            'time': time.time(),
                            'text': f"⏰ Cron [{job['name']}]: {response[:200]}"
                        })

                # Log to daily memory
                write_daily_log(f"[CRON] {job['name']}: {response[:150]}")

                # One-shot jobs: auto-disable
                if job['schedule']['kind'] == 'at':
                    job['enabled'] = False
                    self.save_jobs()

            except Exception as e:
                log.error(f"LLM cron error ({job['name']}): {e}")
                job['last_run'] = datetime.now(KST).isoformat()
                self.save_jobs()


# ============================================================
# PLUGIN LOADER — Auto-load tools from plugins/ directory
class Session:
    """OpenClaw-style isolated session with its own context.

    Each session has:
    - Unique ID and isolated message history
    - No cross-contamination between sessions
    - Automatic memory flush before compaction
    - Session metadata tracking
    """

    def __init__(self, session_id: str):
        self.id = session_id
        self.messages: list = []
        self.created = time.time()
        self.last_active = time.time()
        self.metadata: dict = {}  # Arbitrary session metadata
        self._memory_flushed = False  # Track if pre-compaction memory flush happened

    def add_system(self, content: str):
        # Replace existing system message
        """Add a system message to the session."""
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
            conn = _get_db()
            conn.execute('INSERT OR REPLACE INTO session_store (session_id, messages, updated_at) VALUES (?,?,?)',
                         (self.id, json.dumps(saveable, ensure_ascii=False), datetime.now(KST).isoformat()))
            conn.commit()
        except Exception as e:
            log.warning(f"Session persist error: {e}")

    def add_user(self, content: str):
        """Add a user message to the session."""
        self.messages.append({'role': 'user', 'content': content})
        self.last_active = time.time()

    def add_assistant(self, content: str):
        """Add an assistant response to the session."""
        self.messages.append({'role': 'assistant', 'content': content})
        self.last_active = time.time()
        self._persist()
        # Auto-save to disk after final response (debounced — not on tool calls)
        try:
            save_session_to_disk(self.id)
        except Exception:
            pass

    def add_tool_results(self, results: list):
        """Add tool results as a single user message with all results.
        results: list of {'tool_use_id': str, 'content': str}
        """
        content = [{'type': 'tool_result', 'tool_use_id': r['tool_use_id'],
                     'content': r['content']} for r in results]
        self.messages.append({'role': 'user', 'content': content})


_tg_bot = None  # Set during startup by telegram module


def get_telegram_bot():
    """Accessor for the Telegram bot instance (avoids direct global access)."""
    return _tg_bot


def set_telegram_bot(bot):
    """Set the Telegram bot instance (called during startup)."""
    global _tg_bot
    _tg_bot = bot
_llm_cron = None  # Set during startup by __main__ (LLMCron instance)
_sessions = {}  # type: ignore[var-annotated]
_session_lock = threading.Lock()  # Protects _sessions dict
_session_cleanup_ts = 0.0
_SESSION_TTL = 3600 * 8  # 8 hours
_SESSION_MAX = 200


def _cleanup_sessions():
    """Remove inactive sessions older than TTL."""
    global _session_cleanup_ts
    now = time.time()
    if now - _session_cleanup_ts < 600:  # Check every 10 min
        return
    _session_cleanup_ts = now
    with _session_lock:
        stale = [sid for sid, s in _sessions.items()
                 if now - s.last_active > _SESSION_TTL]
        for sid in stale:
            try:
                _sessions[sid]._persist()
            except Exception:
                pass
            del _sessions[sid]
        if stale:
            log.info(f"[CLEAN] Session cleanup: removed {len(stale)} inactive sessions")
        # Hard cap
        if len(_sessions) > _SESSION_MAX:
            by_age = sorted(_sessions.items(), key=lambda x: x[1].last_active)
            for sid, _ in by_age[:len(_sessions) - _SESSION_MAX]:
                del _sessions[sid]


def get_session(session_id: str) -> Session:
    """Get or create a chat session by ID."""
    _cleanup_sessions()
    with _session_lock:
        if session_id not in _sessions:
            _sessions[session_id] = Session(session_id)
            # Try to restore from SQLite
            try:
                conn = _get_db()
                row = conn.execute('SELECT messages FROM session_store WHERE session_id=?', (session_id,)).fetchone()
                if row:
                    restored = json.loads(row[0])
                    _sessions[session_id].messages = restored
                    log.info(f"[NOTE] Session restored: {session_id} ({len(restored)} msgs)")
                    # Refresh system prompt
                    from .prompt import build_system_prompt
                    _sessions[session_id].add_system(build_system_prompt(full=False))
                    return _sessions[session_id]
            except Exception as e:
                log.warning(f"Session restore error: {e}")
            from .prompt import build_system_prompt
            _sessions[session_id].add_system(build_system_prompt(full=True))
            log.info(f"[NOTE] New session: {session_id} (system prompt: {len(_sessions[session_id].messages[0]['content'])} chars)")
        return _sessions[session_id]



_SESSIONS_DIR = Path.home() / '.salmalm' / 'sessions'


def save_session_to_disk(session_id: str):
    """Serialize session state to ~/.salmalm/sessions/{id}.json."""
    with _session_lock:
        session = _sessions.get(session_id)
        if not session:
            return
    try:
        _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        saveable_msgs = []
        for m in session.messages[-50:]:
            if isinstance(m.get('content'), list):
                texts = [b for b in m['content'] if isinstance(b, dict) and b.get('type') == 'text']
                if texts:
                    saveable_msgs.append({**m, 'content': texts})
            elif isinstance(m.get('content'), str):
                saveable_msgs.append(m)
        data = {
            'session_id': session.id,
            'messages': saveable_msgs,
            'created': session.created,
            'last_active': session.last_active,
            'metadata': session.metadata,
        }
        path = _SESSIONS_DIR / f'{session_id}.json'
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as e:
        log.warning(f"[DISK] Failed to save session {session_id}: {e}")


def restore_session(session_id: str) -> Optional[Session]:
    """Load session from ~/.salmalm/sessions/{id}.json."""
    path = _SESSIONS_DIR / f'{session_id}.json'
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        session = Session(session_id)
        session.messages = data.get('messages', [])
        session.created = data.get('created', time.time())
        session.last_active = data.get('last_active', time.time())
        session.metadata = data.get('metadata', {})
        with _session_lock:
            _sessions[session_id] = session
        log.info(f"[DISK] Restored session from disk: {session_id} ({len(session.messages)} msgs)")
        return session
    except Exception as e:
        log.warning(f"[DISK] Failed to restore session {session_id}: {e}")
        return None


def restore_all_sessions_from_disk():
    """On startup, restore all sessions from disk."""
    if not _SESSIONS_DIR.exists():
        return
    count = 0
    for path in _SESSIONS_DIR.glob('*.json'):
        sid = path.stem
        if restore_session(sid):
            count += 1
    if count:
        log.info(f"[DISK] Restored {count} sessions from disk")


class CronScheduler:
    """OpenClaw-style cron scheduler with isolated session execution."""

    def __init__(self):
        self.jobs = []
        self._running = False

    def add_job(self, name: str, interval_seconds: int, callback, **kwargs):
        """Add a new cron job with the given schedule and callback."""
        self.jobs.append({
            'name': name, 'interval': interval_seconds,
            'callback': callback, 'kwargs': kwargs,
            'last_run': 0, 'enabled': True
        })

    async def run(self):
        """Start the cron scheduler loop."""
        self._running = True
        log.info(f"[CRON] Cron scheduler started ({len(self.jobs)} jobs)")
        while self._running:
            now = time.time()
            for job in self.jobs:
                if not job['enabled']:
                    continue
                if now - job['last_run'] >= job['interval']:
                    try:
                        log.info(f"[CRON] Running cron: {job['name']}")
                        if asyncio.iscoroutinefunction(job['callback']):
                            await job['callback'](**job['kwargs'])
                        else:
                            job['callback'](**job['kwargs'])
                        job['last_run'] = now
                    except Exception as e:
                        log.error(f"Cron error ({job['name']}): {e}")
            await asyncio.sleep(10)

    def stop(self):
        """Stop the cron scheduler loop."""
        self._running = False


cron = CronScheduler()


# ============================================================
# HEARTBEAT SYSTEM — OpenClaw-style periodic self-check
# ============================================================

class HeartbeatManager:
    """OpenClaw-style heartbeat: periodic self-check with HEARTBEAT.md.

    Reads HEARTBEAT.md for a checklist of things to do on each heartbeat.
    Runs in an isolated session to avoid polluting main conversation.
    Announces results to configured channels.
    Tracks check state in heartbeat-state.json.
    """

    _HEARTBEAT_FILE = BASE_DIR / 'HEARTBEAT.md'
    _STATE_FILE = MEMORY_DIR / 'heartbeat-state.json'
    _DEFAULT_INTERVAL = 1800  # 30 minutes
    _last_beat = 0.0
    _enabled = True
    _beat_count = 0

    @classmethod
    def _load_state(cls) -> dict:
        """Load heartbeat state from JSON file."""
        try:
            if cls._STATE_FILE.exists():
                return json.loads(cls._STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
        return {'lastChecks': {}, 'history': [], 'totalBeats': 0}

    @classmethod
    def _save_state(cls, state: dict):
        """Persist heartbeat state to JSON file."""
        try:
            MEMORY_DIR.mkdir(exist_ok=True)
            cls._STATE_FILE.write_text(
                json.dumps(state, indent=2, ensure_ascii=False), encoding='utf-8')
        except Exception as e:
            log.error(f"[HEARTBEAT] Failed to save state: {e}")

    @classmethod
    def get_prompt(cls) -> str:
        """Read HEARTBEAT.md for the heartbeat checklist."""
        if cls._HEARTBEAT_FILE.exists():
            try:
                content = cls._HEARTBEAT_FILE.read_text(encoding='utf-8', errors='replace')
                if content.strip():
                    return content
            except Exception:
                pass
        return ''

    @classmethod
    def should_beat(cls) -> bool:
        """Check if it's time for a heartbeat."""
        if not cls._enabled:
            return False
        now = time.time()
        if now - cls._last_beat < cls._DEFAULT_INTERVAL:
            return False
        # Respect quiet hours (23:00-08:00 KST)
        hour = datetime.now(KST).hour
        if hour >= 23 or hour < 8:
            return False
        return True

    @classmethod
    def get_state(cls) -> dict:
        """Get current heartbeat state (for tools/API)."""
        state = cls._load_state()
        state['enabled'] = cls._enabled
        state['interval'] = cls._DEFAULT_INTERVAL
        state['lastBeat'] = cls._last_beat
        state['beatCount'] = cls._beat_count
        return state

    @classmethod
    def update_check(cls, check_name: str):
        """Record that a specific check was performed (email, calendar, etc)."""
        state = cls._load_state()
        state['lastChecks'][check_name] = time.time()
        cls._save_state(state)

    @classmethod
    def time_since_check(cls, check_name: str) -> Optional[float]:
        """Seconds since a named check was last performed. None if never."""
        state = cls._load_state()
        ts = state.get('lastChecks', {}).get(check_name)
        if ts:
            return time.time() - ts
        return None

    @classmethod
    async def beat(cls) -> Optional[str]:
        """Execute a heartbeat check in an isolated session.

        Returns the heartbeat result or None if nothing to do.
        """
        prompt = cls.get_prompt()
        if not prompt:
            cls._last_beat = time.time()
            return None

        cls._last_beat = time.time()
        cls._beat_count += 1
        log.info("[HEARTBEAT] Running periodic heartbeat check")

        # Load state for context injection
        state = cls._load_state()
        state_ctx = ''
        if state.get('lastChecks'):
            checks = []
            for name, ts in state['lastChecks'].items():
                ago = int((time.time() - ts) / 60)
                checks.append(f"  {name}: {ago}min ago")
            state_ctx = f"\n\nLast checks:\n" + '\n'.join(checks)

        try:
            from .engine import process_message
            # Run in isolated session (OpenClaw pattern: no cross-contamination)
            result = await process_message(
                f'heartbeat-{int(time.time())}',
                f"[Heartbeat check]\n{prompt}{state_ctx}\n\n"
                f"If nothing needs attention, reply HEARTBEAT_OK.",
                model_override=None  # Use auto-routing
            )

            # Update state
            state['totalBeats'] = state.get('totalBeats', 0) + 1
            state['lastBeatTime'] = time.time()
            state['lastBeatResult'] = 'ok' if (result and 'HEARTBEAT_OK' in result) else 'action'
            # Keep last 20 history entries
            history = state.get('history', [])
            history.append({
                'time': time.time(),
                'result': state['lastBeatResult'],
                'summary': (result or '')[:200]
            })
            state['history'] = history[-20:]
            cls._save_state(state)

            # Announce if result is meaningful
            if result and 'HEARTBEAT_OK' not in result:
                cls._announce(result)
                write_daily_log(f"[HEARTBEAT] {result[:200]}")

            return result
        except Exception as e:
            log.error(f"[HEARTBEAT] Error: {e}")
            return None

    @classmethod
    def _announce(cls, result: str):
        """Announce heartbeat results to configured channels."""
        # Telegram notification
        if _tg_bot and _tg_bot.token and _tg_bot.owner_id:
            try:
                summary = result[:800] + ('...' if len(result) > 800 else '')
                _tg_bot.send_message(
                    _tg_bot.owner_id,
                    f"💓 Heartbeat alert:\n{summary}")
            except Exception as e:
                log.error(f"[HEARTBEAT] Announce error: {e}")

        # Store for web polling
        web_session = _sessions.get('web')
        if web_session:
            if not hasattr(web_session, '_notifications'):
                web_session._notifications = []
            web_session._notifications.append({
                'time': time.time(),
                'text': f"💓 Heartbeat: {result[:200]}"
            })


heartbeat = HeartbeatManager()


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

# Re-export from agents.py
from .agents import SubAgent, SkillLoader, PluginLoader

# Module-level exports for convenience
__all__ = [
    'audit_log', 'response_cache', 'router', 'track_usage', 'get_usage_report', 'check_cost_cap', 'CostCapExceeded',
    '_metrics', 'compact_messages', 'get_session', 'write_daily_log', 'cron',
    'save_session_to_disk', 'restore_session', 'restore_all_sessions_from_disk',
    'memory_manager', 'heartbeat',
    'get_telegram_bot', 'set_telegram_bot',
    'Session', 'MemoryManager', 'HeartbeatManager', 'LLMCronManager',
    'SubAgent', 'SkillLoader', 'PluginLoader',
]
