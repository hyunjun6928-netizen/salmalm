from __future__ import annotations
"""SalmAlm RAG — Retrieval-Augmented Generation with hybrid search.

Pure stdlib. No external dependencies.
Features:
  - BM25 scoring
  - TF-IDF vector search with cosine similarity
  - Hybrid search (BM25 + Vector weighted fusion)
  - N-gram support (unigrams, bigrams, character 3-grams)
  - Korean jamo decomposition for fuzzy phonetic matching
  - Simple English stemming (Porter-like suffix stripping)
  - Query expansion via synonym dictionary
  - Persistent index (SQLite-backed)
  - Automatic re-indexing on file changes
  - Chunk overlap for better context capture
  - Session transcript indexing (opt-in)
  - rag.json configuration file

Usage:
  from salmalm.rag import rag_engine
  results = rag_engine.search("DB schema")
  context = rag_engine.build_context("DB schema", max_chars=3000)
"""

import hashlib
import json
import math
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .constants import MEMORY_DIR, WORKSPACE_DIR, MEMORY_FILE, BASE_DIR, KST
from .crypto import log

# ── BM25 Parameters ──
BM25_K1 = 1.5
BM25_B = 0.75
CHUNK_SIZE = 5
CHUNK_OVERLAP = 2
REINDEX_INTERVAL = 120
MAX_CHUNK_CHARS = 1500

# Stop words (Korean + English)
_STOP_WORDS = frozenset([
    '의', '가', '이', '은', '는', '을', '를', '에', '에서', '로', '으로',
    '와', '과', '도', '만', '부터', '까지', '에게', '한테', '하다', '있다',
    '되다', '하는', '있는', '되는', '했다', '했던', '하고', '그리고', '그런데',
    '또는', '혹은', '및', '대한', '위한', '통해', '따라', '대해', '이를',
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
    'that', 'this', 'it', 'not', 'no', 'if', 'then', 'so', 'as', 'by',
    'from', 'has', 'have', 'had', 'do', 'does', 'did', 'will', 'would',
    'can', 'could', 'may', 'might', 'shall', 'should', 'must', 'need',
])

# ── Korean Jamo Decomposition ──
_CHO = list('ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ')
_JUNG = list('ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ')
_JONG = [''] + list('ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ')


def decompose_jamo(text: str) -> str:
    """Decompose Korean syllables into jamo (초성/중성/종성)."""
    result = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            offset = code - 0xAC00
            cho = offset // (21 * 28)
            jung = (offset % (21 * 28)) // 28
            jong = offset % 28
            result.append(_CHO[cho])
            result.append(_JUNG[jung])
            if jong:
                result.append(_JONG[jong])
        else:
            result.append(ch)
    return ''.join(result)


# ── English Stemming (simple Porter-like) ──

def simple_stem(word: str) -> str:
    """Simple English suffix stripping."""
    if len(word) <= 3:
        return word
    # Order matters: try longest suffixes first
    for suffix, replacement in [
        ('ational', 'ate'), ('tional', 'tion'), ('enci', 'ence'),
        ('anci', 'ance'), ('izer', 'ize'), ('isation', 'ize'),
        ('ization', 'ize'), ('ation', 'ate'), ('fulness', 'ful'),
        ('ousness', 'ous'), ('iveness', 'ive'), ('ement', ''),
        ('ment', ''), ('ness', ''), ('ible', ''), ('able', ''),
        ('ling', ''), ('ying', 'y'), ('ting', 't'), ('ning', 'n'),
        ('ring', 'r'), ('ies', 'y'), ('ing', ''), ('ely', ''),
        ('ally', 'al'), ('ity', ''), ('ous', ''), ('ive', ''),
        ('ful', ''), ('less', ''), ('ion', ''), ('ers', ''),
        ('ed', ''), ('es', ''), ('ly', ''), ('er', ''), ('s', ''),
    ]:
        if word.endswith(suffix) and len(word) - len(suffix) + len(replacement) >= 3:
            return word[:-len(suffix)] + replacement
    return word


# ── Synonym / Query Expansion Dictionary ──

_SYNONYMS: Dict[str, List[str]] = {
    # Korean
    '검색': ['찾기', '탐색', '서치'],
    '파일': ['문서', '파일'],
    '설정': ['설정', '세팅', '구성', '환경설정'],
    '삭제': ['제거', '지우기'],
    '추가': ['생성', '만들기', '등록'],
    '수정': ['변경', '편집', '업데이트'],
    '저장': ['보관', '세이브'],
    '실행': ['구동', '런', '시작'],
    '오류': ['에러', '버그', '문제'],
    '메모리': ['기억', '메모'],
    '사용자': ['유저', '사용자'],
    '서버': ['서버', '호스트'],
    '데이터': ['정보', '자료'],
    '데이터베이스': ['디비', 'DB', '데이터베이스'],
    # English
    'search': ['find', 'lookup', 'query'],
    'file': ['document', 'doc'],
    'config': ['configuration', 'settings', 'setup'],
    'delete': ['remove', 'erase'],
    'create': ['add', 'make', 'new'],
    'update': ['modify', 'edit', 'change'],
    'save': ['store', 'persist'],
    'run': ['execute', 'start', 'launch'],
    'error': ['bug', 'issue', 'problem', 'fail'],
    'memory': ['recall', 'remember'],
    'user': ['person', 'account'],
    'server': ['host', 'backend'],
    'data': ['info', 'information'],
    'database': ['db', 'datastore'],
}

# Build reverse lookup
_SYNONYM_REVERSE: Dict[str, List[str]] = {}
for _key, _vals in _SYNONYMS.items():
    for _v in _vals:
        _vl = _v.lower()
        if _vl not in _SYNONYM_REVERSE:
            _SYNONYM_REVERSE[_vl] = []
        _SYNONYM_REVERSE[_vl].append(_key.lower())
    _kl = _key.lower()
    if _kl not in _SYNONYM_REVERSE:
        _SYNONYM_REVERSE[_kl] = []
    _SYNONYM_REVERSE[_kl].extend(v.lower() for v in _vals)


def expand_query(tokens: List[str]) -> List[str]:
    """Expand query tokens with synonyms."""
    expanded = list(tokens)
    seen = set(t.lower() for t in tokens)
    for t in tokens:
        tl = t.lower()
        # Direct lookup
        if tl in _SYNONYMS:
            for syn in _SYNONYMS[tl]:
                sl = syn.lower()
                if sl not in seen:
                    expanded.append(sl)
                    seen.add(sl)
        # Reverse lookup
        if tl in _SYNONYM_REVERSE:
            for syn in _SYNONYM_REVERSE[tl]:
                if syn not in seen:
                    expanded.append(syn)
                    seen.add(syn)
    return expanded


# ── RAG Configuration ──

_DEFAULT_CONFIG = {
    "hybrid": {"enabled": True, "vectorWeight": 0.7, "textWeight": 0.3},
    "sessionIndexing": {"enabled": False, "retentionDays": 30},
    "extraPaths": [],
    "chunkSize": 5,
    "chunkOverlap": 2,
    "reindexInterval": 120,
}


def load_rag_config(config_path: Optional[Path] = None) -> dict:
    """Load rag.json config, falling back to defaults."""
    path = config_path or Path.home() / ".salmalm" / "rag.json"
    config = dict(_DEFAULT_CONFIG)
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                user_cfg = json.load(f)
            # Merge top-level keys
            for k, v in user_cfg.items():
                if k in config and isinstance(config[k], dict) and isinstance(v, dict):
                    merged = dict(config[k])
                    merged.update(v)
                    config[k] = merged
                else:
                    config[k] = v
        except Exception as e:
            log.warning(f"RAG config load error: {e}")
    return config


# ── TF-IDF Vector Utilities ──

def compute_tf(tokens: List[str]) -> Dict[str, float]:
    """Compute term frequency vector (normalized)."""
    if not tokens:
        return {}
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    n = len(tokens)
    return {t: c / n for t, c in counts.items()}


def cosine_similarity(v1: Dict[str, float], v2: Dict[str, float]) -> float:
    """Cosine similarity between two sparse vectors (dict-based)."""
    if not v1 or not v2:
        return 0.0
    # Dot product - iterate over smaller dict
    if len(v1) > len(v2):
        v1, v2 = v2, v1
    dot = 0.0
    for k, val in v1.items():
        if k in v2:
            dot += val * v2[k]
    if dot == 0.0:
        return 0.0
    norm1 = math.sqrt(sum(v * v for v in v1.values()))
    norm2 = math.sqrt(sum(v * v for v in v2.values()))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


class RAGEngine:
    """Hybrid BM25 + TF-IDF vector retrieval engine with persistent SQLite index."""

    def __init__(self, db_path: Optional[Path] = None, config_path: Optional[Path] = None):
        self._db_path = db_path or (BASE_DIR / "rag.db")
        self._config_path = config_path
        self._conn: Optional[sqlite3.Connection] = None
        self._mtimes: Dict[str, float] = {}
        self._last_check = 0
        self._doc_count = 0
        self._avg_dl = 0.0
        self._idf_cache: Dict[str, float] = {}
        self._initialized = False
        self._config: Optional[dict] = None

    @property
    def config(self) -> dict:
        if self._config is None:
            self._config = load_rag_config(self._config_path)
        return self._config

    def _ensure_db(self):
        if self._conn:
            return
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute('''CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            text TEXT NOT NULL,
            tokens TEXT NOT NULL,
            token_count INTEGER NOT NULL,
            mtime REAL NOT NULL,
            hash TEXT NOT NULL
        )''')
        self._conn.execute('''CREATE TABLE IF NOT EXISTS doc_freq (
            term TEXT PRIMARY KEY,
            df INTEGER NOT NULL
        )''')
        self._conn.execute('''CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )''')
        self._conn.execute('''CREATE TABLE IF NOT EXISTS tfidf_vectors (
            chunk_id INTEGER PRIMARY KEY,
            vector TEXT NOT NULL,
            FOREIGN KEY (chunk_id) REFERENCES chunks(id)
        )''')
        self._conn.execute('''CREATE INDEX IF NOT EXISTS idx_chunks_source
            ON chunks(source)''')
        self._conn.commit()
        self._load_stats()
        self._initialized = True

    def _load_stats(self):
        """Load cached statistics."""
        row = self._conn.execute("SELECT COUNT(*), AVG(token_count) FROM chunks").fetchone()
        self._doc_count = row[0] or 0
        self._avg_dl = row[1] or 1.0
        self._idf_cache.clear()
        for term, df in self._conn.execute("SELECT term, df FROM doc_freq"):
            self._idf_cache[term] = math.log((self._doc_count - df + 0.5) / (df + 0.5) + 1)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenize with unigrams + bigrams + char 3-grams + jamo + stemming."""
        text_lower = text.lower()
        # Split on non-word chars (keeping Korean)
        raw = re.findall(r'[\w가-힣]+', text_lower)
        unigrams = []
        for t in raw:
            if len(t) <= 1 or t in _STOP_WORDS:
                continue
            # Apply stemming for English words
            if re.match(r'^[a-z]+$', t):
                stemmed = simple_stem(t)
                unigrams.append(stemmed)
                if stemmed != t:
                    unigrams.append(t)  # Keep original too
            else:
                unigrams.append(t)

        # Bigrams
        bigrams = [f"{unigrams[i]}_{unigrams[i+1]}"
                   for i in range(len(unigrams) - 1)]

        # Character 3-grams (especially useful for Korean)
        char_trigrams = []
        clean = re.sub(r'\s+', '', text_lower)
        for i in range(len(clean) - 2):
            tri = clean[i:i+3]
            if re.match(r'^[\w가-힣]{3}$', tri):
                char_trigrams.append(f"c3:{tri}")

        # Jamo decomposition for Korean text
        korean_chars = re.findall(r'[가-힣]+', text_lower)
        jamo_tokens = []
        for kw in korean_chars:
            if len(kw) >= 2:
                jamo = decompose_jamo(kw)
                jamo_tokens.append(f"j:{jamo}")

        return unigrams + bigrams + char_trigrams + jamo_tokens

    def index_file(self, label: str, fpath: Path):
        """Index a single file."""
        self._ensure_db()
        try:
            mtime = fpath.stat().st_mtime
            self._mtimes[label] = mtime
            text = fpath.read_text(encoding='utf-8', errors='replace')
            self._index_text(label, text, mtime)
            self._last_check = time.time()
        except Exception as e:
            log.warning(f"RAG index_file error ({label}): {e}")

    def _index_text(self, label: str, text: str, mtime: float):
        """Index text content as chunks."""
        cfg = self.config
        chunk_size = cfg.get('chunkSize', CHUNK_SIZE)
        chunk_overlap = cfg.get('chunkOverlap', CHUNK_OVERLAP)

        lines = text.splitlines()
        new_docs = []
        vectors = []
        doc_freq: Dict[str, int] = {}

        step = max(1, chunk_size - chunk_overlap)
        for i in range(0, len(lines), step):
            chunk_lines = lines[i:i + chunk_size]
            chunk_text = '\n'.join(chunk_lines).strip()
            if not chunk_text or len(chunk_text) < 10:
                continue
            if len(chunk_text) > MAX_CHUNK_CHARS:
                chunk_text = chunk_text[:MAX_CHUNK_CHARS]

            tokens = self._tokenize(chunk_text)
            if not tokens:
                continue

            h = hashlib.md5(chunk_text.encode()).hexdigest()[:12]
            new_docs.append((label, i + 1, i + len(chunk_lines),
                             chunk_text, json.dumps(tokens), len(tokens),
                             mtime, h))

            # TF vector for this chunk
            tf_vec = compute_tf(tokens)
            vectors.append(tf_vec)

            for t in set(tokens):
                doc_freq[t] = doc_freq.get(t, 0) + 1

        if not new_docs:
            return

        # Remove old chunks for this label
        self._conn.execute(
            "DELETE FROM tfidf_vectors WHERE chunk_id IN (SELECT id FROM chunks WHERE source=?)",
            (label,))
        self._conn.execute("DELETE FROM chunks WHERE source=?", (label,))

        # Insert new chunks
        for doc in new_docs:
            cur = self._conn.execute(
                "INSERT INTO chunks (source, line_start, line_end, text, tokens, token_count, mtime, hash) VALUES (?,?,?,?,?,?,?,?)",
                doc)
            chunk_id = cur.lastrowid
            idx = len(vectors) - len(new_docs) + new_docs.index(doc)
            self._conn.execute(
                "INSERT INTO tfidf_vectors (chunk_id, vector) VALUES (?,?)",
                (chunk_id, json.dumps(vectors[idx])))

        # Update doc_freq (rebuild entirely for simplicity during reindex)
        # This is handled in reindex(); for single file we just update
        for term, df_val in doc_freq.items():
            self._conn.execute(
                "INSERT OR REPLACE INTO doc_freq (term, df) VALUES (?, COALESCE((SELECT df FROM doc_freq WHERE term=?), 0) + ?)",
                (term, term, df_val))

        self._conn.commit()
        self._load_stats()

    def _get_indexable_files(self) -> List[Tuple[str, Path]]:
        """Enumerate files to index."""
        files = []
        if MEMORY_FILE.exists():
            files.append(('MEMORY.md', MEMORY_FILE))
        if MEMORY_DIR.exists():
            for f in sorted(MEMORY_DIR.glob('*.md')):
                files.append((f'memory/{f.name}', f))
        for name in ('SOUL.md', 'USER.md', 'TOOLS.md', 'AGENTS.md', 'HEARTBEAT.md'):
            p = BASE_DIR / name
            if p.exists():
                files.append((name, p))
        uploads = WORKSPACE_DIR / 'uploads'
        if uploads.exists():
            for f in uploads.glob('*'):
                if f.suffix.lower() in ('.txt', '.md', '.py', '.js', '.json', '.csv',
                                         '.html', '.css', '.log', '.xml', '.yaml', '.yml',
                                         '.sql', '.sh', '.bat', '.toml', '.cfg', '.ini'):
                    files.append((f'uploads/{f.name}', f))
        skills = WORKSPACE_DIR / 'skills'
        if skills.exists():
            for f in skills.glob('**/*.md'):
                files.append((f'skills/{f.relative_to(skills)}', f))

        # Extra paths from config
        cfg = self.config
        for extra in cfg.get('extraPaths', []):
            ep = Path(extra).expanduser()
            if ep.is_file():
                files.append((str(ep.name), ep))
            elif ep.is_dir():
                for f in ep.glob('**/*'):
                    if f.is_file() and f.suffix.lower() in ('.txt', '.md', '.py', '.json'):
                        files.append((str(f.relative_to(ep)), f))

        return files

    def _get_session_files(self) -> List[Tuple[str, Path]]:
        """Get session transcript files for indexing."""
        cfg = self.config
        si = cfg.get('sessionIndexing', {})
        if not si.get('enabled', False):
            return []

        sessions_dir = Path.home() / '.salmalm' / 'sessions'
        if not sessions_dir.exists():
            return []

        retention_days = si.get('retentionDays', 30)
        cutoff = time.time() - (retention_days * 86400)
        files = []
        for f in sessions_dir.glob('*.json'):
            try:
                if f.stat().st_mtime >= cutoff:
                    files.append((f'session/{f.name}', f))
            except OSError:
                continue
        return files

    def _index_session_file(self, label: str, fpath: Path, mtime: float):
        """Index a session JSON file, extracting conversation text."""
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return

        # Extract messages text
        parts = []
        messages = data if isinstance(data, list) else data.get('messages', [])
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get('content', '')
                if isinstance(content, str) and content.strip():
                    parts.append(content)

        if parts:
            text = '\n'.join(parts)
            self._index_text(label, text, mtime)

    def _needs_reindex(self) -> bool:
        """Check if any source files changed since last index."""
        now = time.time()
        reindex_interval = self.config.get('reindexInterval', REINDEX_INTERVAL)
        if now - self._last_check < reindex_interval:
            return False
        self._last_check = now

        all_files = self._get_indexable_files() + self._get_session_files()
        for label, fpath in all_files:
            try:
                mtime = fpath.stat().st_mtime
                if label not in self._mtimes or self._mtimes[label] != mtime:
                    return True
            except OSError:
                continue
        return False

    def reindex(self, force: bool = False):
        """Rebuild the index from source files."""
        self._ensure_db()
        if not force and not self._needs_reindex():
            return

        files = self._get_indexable_files()
        session_files = self._get_session_files()

        cfg = self.config
        chunk_size = cfg.get('chunkSize', CHUNK_SIZE)
        chunk_overlap = cfg.get('chunkOverlap', CHUNK_OVERLAP)

        new_docs = []
        vectors = []
        doc_freq: Dict[str, int] = {}

        def process_text(label: str, text: str, mtime: float):
            lines = text.splitlines()
            step = max(1, chunk_size - chunk_overlap)
            for i in range(0, len(lines), step):
                chunk_lines = lines[i:i + chunk_size]
                chunk_text = '\n'.join(chunk_lines).strip()
                if not chunk_text or len(chunk_text) < 10:
                    continue
                if len(chunk_text) > MAX_CHUNK_CHARS:
                    chunk_text = chunk_text[:MAX_CHUNK_CHARS]

                tokens = self._tokenize(chunk_text)
                if not tokens:
                    continue

                h = hashlib.md5(chunk_text.encode()).hexdigest()[:12]
                new_docs.append((label, i + 1, i + len(chunk_lines),
                                 chunk_text, json.dumps(tokens), len(tokens),
                                 mtime, h))

                tf_vec = compute_tf(tokens)
                vectors.append(tf_vec)

                for t in set(tokens):
                    doc_freq[t] = doc_freq.get(t, 0) + 1

        for label, fpath in files:
            try:
                mtime = fpath.stat().st_mtime
                self._mtimes[label] = mtime
                text = fpath.read_text(encoding='utf-8', errors='replace')
                process_text(label, text, mtime)
            except Exception as e:
                log.warning(f"RAG index error ({label}): {e}")
                continue

        # Session files
        for label, fpath in session_files:
            try:
                mtime = fpath.stat().st_mtime
                self._mtimes[label] = mtime
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                parts = []
                messages = data if isinstance(data, list) else data.get('messages', [])
                for msg in messages:
                    if isinstance(msg, dict):
                        content = msg.get('content', '')
                        if isinstance(content, str) and content.strip():
                            parts.append(content)
                if parts:
                    process_text(label, '\n'.join(parts), mtime)
            except Exception as e:
                log.warning(f"RAG session index error ({label}): {e}")
                continue

        if not new_docs:
            return

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute("DELETE FROM tfidf_vectors")
            self._conn.execute("DELETE FROM chunks")
            self._conn.execute("DELETE FROM doc_freq")
            self._conn.executemany(
                "INSERT INTO chunks (source, line_start, line_end, text, tokens, token_count, mtime, hash) VALUES (?,?,?,?,?,?,?,?)",
                new_docs
            )
            # Insert TF-IDF vectors
            # Get the inserted chunk IDs
            rows = self._conn.execute("SELECT id FROM chunks ORDER BY id").fetchall()
            for (chunk_id,), vec in zip(rows, vectors):
                self._conn.execute(
                    "INSERT INTO tfidf_vectors (chunk_id, vector) VALUES (?,?)",
                    (chunk_id, json.dumps(vec)))

            self._conn.executemany(
                "INSERT OR REPLACE INTO doc_freq (term, df) VALUES (?,?)",
                list(doc_freq.items())
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        self._load_stats()
        log.info(f"[AI] RAG index rebuilt: {len(new_docs)} chunks from {len(files) + len(session_files)} files, "
                 f"{len(doc_freq)} unique terms")

    def _bm25_search(self, query_tokens: List[str], max_results: int,
                     min_score: float) -> List[Dict]:
        """Pure BM25 search, returns scored results with bm25 rank."""
        term_set = set(query_tokens)
        scored = []

        for row in self._conn.execute("SELECT id, source, line_start, text, tokens, token_count FROM chunks"):
            chunk_id, source, line_start, text, tokens_json, token_count = row
            chunk_tokens = json.loads(tokens_json)
            chunk_token_set = set(chunk_tokens)
            if not term_set & chunk_token_set:
                continue

            score = 0.0
            tf_map: Dict[str, int] = {}
            for t in chunk_tokens:
                tf_map[t] = tf_map.get(t, 0) + 1

            dl = token_count
            for qt in query_tokens:
                if qt not in tf_map:
                    continue
                tf = tf_map[qt]
                idf = self._idf_cache.get(qt, 0)
                numerator = tf * (BM25_K1 + 1)
                denominator = tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / self._avg_dl)
                score += idf * (numerator / denominator)

            if score >= min_score:
                scored.append({
                    'score': score,
                    'source': source,
                    'line': line_start,
                    'text': text,
                    'chunk_id': chunk_id,
                })

        scored.sort(key=lambda x: -x['score'])
        return scored[:max_results]

    def _vector_search(self, query_tokens: List[str], max_results: int) -> List[Dict]:
        """TF-IDF vector cosine similarity search."""
        if self._doc_count == 0:
            return []

        # Build query TF-IDF vector
        query_tf = compute_tf(query_tokens)
        # Weight by IDF
        query_vec: Dict[str, float] = {}
        for term, tf_val in query_tf.items():
            idf = self._idf_cache.get(term, 0)
            if idf > 0:
                query_vec[term] = tf_val * idf

        if not query_vec:
            return []

        scored = []
        for row in self._conn.execute(
            "SELECT c.id, c.source, c.line_start, c.text, v.vector "
            "FROM chunks c JOIN tfidf_vectors v ON c.id = v.chunk_id"
        ):
            chunk_id, source, line_start, text, vec_json = row
            chunk_tf = json.loads(vec_json)
            # Apply IDF weighting to chunk vector
            chunk_vec: Dict[str, float] = {}
            for term, tf_val in chunk_tf.items():
                idf = self._idf_cache.get(term, 0)
                if idf > 0:
                    chunk_vec[term] = tf_val * idf

            sim = cosine_similarity(query_vec, chunk_vec)
            if sim > 0:
                scored.append({
                    'score': sim,
                    'source': source,
                    'line': line_start,
                    'text': text,
                    'chunk_id': chunk_id,
                })

        scored.sort(key=lambda x: -x['score'])
        return scored[:max_results]

    def search(self, query: str, max_results: int = 8,
               min_score: float = 0.1) -> List[Dict]:
        """Hybrid search (BM25 + Vector). Returns list of {score, source, line, text}."""
        self._ensure_db()
        self.reindex()

        if self._doc_count == 0:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Expand query with synonyms
        expanded_tokens = expand_query(query_tokens)

        cfg = self.config
        hybrid_cfg = cfg.get('hybrid', {})
        hybrid_enabled = hybrid_cfg.get('enabled', True)

        if not hybrid_enabled:
            # BM25 only (legacy mode)
            results = self._bm25_search(expanded_tokens, max_results, min_score)
            for r in results:
                r['score'] = round(r['score'], 4)
                r.pop('chunk_id', None)
            return results

        # Hybrid search
        vector_weight = hybrid_cfg.get('vectorWeight', 0.7)
        text_weight = hybrid_cfg.get('textWeight', 0.3)
        # Normalize weights
        total_w = vector_weight + text_weight
        if total_w > 0:
            vector_weight /= total_w
            text_weight /= total_w

        candidate_multiplier = 4
        pool_size = max_results * candidate_multiplier

        # Get candidates from both methods
        vector_results = self._vector_search(expanded_tokens, pool_size)
        bm25_results = self._bm25_search(expanded_tokens, pool_size, 0.0)

        # Build score maps
        # Vector scores are already cosine similarity [0,1]
        vector_scores: Dict[int, float] = {}
        vector_data: Dict[int, Dict] = {}
        for r in vector_results:
            cid = r['chunk_id']
            vector_scores[cid] = r['score']
            vector_data[cid] = r

        # BM25: textScore = 1 / (1 + max(0, rank))
        bm25_scores: Dict[int, float] = {}
        bm25_data: Dict[int, Dict] = {}
        for rank, r in enumerate(bm25_results):
            cid = r['chunk_id']
            bm25_scores[cid] = 1.0 / (1.0 + max(0, rank))
            bm25_data[cid] = r

        # Merge all candidate chunk IDs
        all_ids = set(vector_scores.keys()) | set(bm25_scores.keys())

        final = []
        for cid in all_ids:
            vs = vector_scores.get(cid, 0.0)
            ts = bm25_scores.get(cid, 0.0)
            final_score = vector_weight * vs + text_weight * ts

            data = vector_data.get(cid) or bm25_data.get(cid)
            if data and final_score > 0:
                final.append({
                    'score': round(final_score, 4),
                    'source': data['source'],
                    'line': data['line'],
                    'text': data['text'],
                })

        final.sort(key=lambda x: -x['score'])

        # Filter by min_score
        final = [r for r in final if r['score'] >= min_score]
        return final[:max_results]

    def build_context(self, query: str, max_chars: int = 4000,
                      max_results: int = 6) -> str:
        """Build a context string for RAG injection into LLM prompts."""
        results = self.search(query, max_results=max_results)
        if not results:
            return ""

        parts = ["[Retrieved relevant information]"]
        total = 0
        for r in results:
            snippet = f"\n--- {r['source']}#L{r['line']} (relevance: {r['score']}) ---\n{r['text']}"
            if total + len(snippet) > max_chars:
                break
            parts.append(snippet)
            total += len(snippet)

        return '\n'.join(parts)

    def get_stats(self) -> dict:
        """Return index statistics."""
        self._ensure_db()
        return {
            'total_chunks': self._doc_count,
            'unique_terms': len(self._idf_cache),
            'avg_chunk_length': round(self._avg_dl, 1),
            'db_size_kb': round(self._db_path.stat().st_size / 1024, 1) if self._db_path.exists() else 0,
            'indexed_files': len(self._mtimes),
        }

    def close(self):
        """Close the RAG database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


# ── RAG-augmented prompt injection ─────────────────────────────

def inject_rag_context(messages: list, system_prompt: str,
                       max_chars: int = 3000) -> str:
    """Analyze recent messages and inject relevant RAG context into system prompt."""
    user_msgs = [m['content'] for m in messages[-6:]
                 if m.get('role') == 'user' and isinstance(m.get('content'), str)]
    if not user_msgs:
        return system_prompt

    query = ' '.join(user_msgs[-3:])
    context = rag_engine.build_context(query, max_chars=max_chars)
    if not context:
        return system_prompt

    return system_prompt + "\n\n" + context


# ── Module-level instance ──────────────────────────────────────

rag_engine = RAGEngine()
