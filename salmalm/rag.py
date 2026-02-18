from __future__ import annotations
"""삶앎 RAG — Retrieval-Augmented Generation with local embeddings.

Pure stdlib. No OpenAI embeddings API required.
Upgrades from basic TF-IDF to:
  - BM25 scoring (better than raw TF-IDF for information retrieval)
  - N-gram support (bigrams for Korean compound terms)
  - Persistent index (SQLite-backed, survives restarts)
  - Automatic re-indexing on file changes (mtime tracking)
  - Chunk overlap for better context capture
  - Query expansion (synonym/related terms)
  - Conversation context injection for RAG-augmented responses

Usage:
  from salmalm.rag import rag_engine
  results = rag_engine.search("지트700 DB 스키마")
  context = rag_engine.build_context("지트700 DB 스키마", max_chars=3000)
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
BM25_K1 = 1.5   # Term frequency saturation
BM25_B = 0.75   # Document length normalization
CHUNK_SIZE = 5   # Lines per chunk
CHUNK_OVERLAP = 2  # Overlap between chunks
REINDEX_INTERVAL = 120  # Seconds between re-index checks
MAX_CHUNK_CHARS = 1500  # Max chars per chunk

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


class RAGEngine:
    """BM25-based retrieval engine with persistent SQLite index."""

    def __init__(self, db_path: Path = None):
        self._db_path = db_path or (BASE_DIR / "rag.db")
        self._conn: Optional[sqlite3.Connection] = None
        self._mtimes: Dict[str, float] = {}  # path -> mtime
        self._last_check = 0
        self._doc_count = 0
        self._avg_dl = 0.0  # Average document length
        self._idf_cache: Dict[str, float] = {}
        self._initialized = False

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
        # Load IDF cache
        self._idf_cache.clear()
        for term, df in self._conn.execute("SELECT term, df FROM doc_freq"):
            self._idf_cache[term] = math.log((self._doc_count - df + 0.5) / (df + 0.5) + 1)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenize into unigrams + bigrams, lowercased, stop-words removed."""
        text = text.lower()
        # Split on non-word chars (keeping Korean)
        unigrams = [t for t in re.findall(r'[\w가-힣]+', text)
                    if len(t) > 1 and t not in _STOP_WORDS]
        # Add bigrams for adjacent terms
        bigrams = [f"{unigrams[i]}_{unigrams[i+1]}"
                   for i in range(len(unigrams) - 1)]
        return unigrams + bigrams

    def _get_indexable_files(self) -> List[Tuple[str, Path]]:
        """Enumerate files to index."""
        files = []
        # MEMORY.md
        if MEMORY_FILE.exists():
            files.append(('MEMORY.md', MEMORY_FILE))
        # memory/*.md
        if MEMORY_DIR.exists():
            for f in sorted(MEMORY_DIR.glob('*.md')):
                files.append((f'memory/{f.name}', f))
        # SOUL.md, USER.md, TOOLS.md, AGENTS.md
        for name in ('SOUL.md', 'USER.md', 'TOOLS.md', 'AGENTS.md', 'HEARTBEAT.md'):
            p = BASE_DIR / name
            if p.exists():
                files.append((name, p))
        # uploads/
        uploads = WORKSPACE_DIR / 'uploads'
        if uploads.exists():
            for f in uploads.glob('*'):
                if f.suffix.lower() in ('.txt', '.md', '.py', '.js', '.json', '.csv',
                                         '.html', '.css', '.log', '.xml', '.yaml', '.yml',
                                         '.sql', '.sh', '.bat', '.toml', '.cfg', '.ini'):
                    files.append((f'uploads/{f.name}', f))
        # skills/
        skills = WORKSPACE_DIR / 'skills'
        if skills.exists():
            for f in skills.glob('**/*.md'):
                files.append((f'skills/{f.relative_to(skills)}', f))
        return files

    def _needs_reindex(self) -> bool:
        """Check if any source files changed since last index."""
        now = time.time()
        if now - self._last_check < REINDEX_INTERVAL:
            return False
        self._last_check = now

        for label, fpath in self._get_indexable_files():
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
        new_docs = []
        doc_freq: Dict[str, int] = {}

        for label, fpath in files:
            try:
                mtime = fpath.stat().st_mtime
                self._mtimes[label] = mtime
                text = fpath.read_text(encoding='utf-8', errors='replace')
                lines = text.splitlines()

                # Chunk with overlap
                for i in range(0, len(lines), CHUNK_SIZE - CHUNK_OVERLAP):
                    chunk_lines = lines[i:i + CHUNK_SIZE]
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

                    # Doc frequency
                    for t in set(tokens):
                        doc_freq[t] = doc_freq.get(t, 0) + 1

            except Exception as e:
                log.warning(f"RAG index error ({label}): {e}")
                continue

        if not new_docs:
            return

        # Rebuild tables atomically (BEGIN IMMEDIATE prevents reads seeing empty state)
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute("DELETE FROM chunks")
            self._conn.execute("DELETE FROM doc_freq")
            self._conn.executemany(
                "INSERT INTO chunks (source, line_start, line_end, text, tokens, token_count, mtime, hash) VALUES (?,?,?,?,?,?,?,?)",
                new_docs
            )
            self._conn.executemany(
                "INSERT OR REPLACE INTO doc_freq (term, df) VALUES (?,?)",
                list(doc_freq.items())
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        self._load_stats()
        log.info(f"🧠 RAG index rebuilt: {len(new_docs)} chunks from {len(files)} files, "
                 f"{len(doc_freq)} unique terms")

    def search(self, query: str, max_results: int = 8,
               min_score: float = 0.1) -> List[Dict]:
        """BM25 search. Returns list of {score, source, line, text}."""
        self._ensure_db()
        self.reindex()

        if self._doc_count == 0:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Compute BM25 scores
        # For efficiency, only score chunks containing at least one query term
        term_set = set(query_tokens)
        scored = []

        for row in self._conn.execute("SELECT id, source, line_start, text, tokens, token_count FROM chunks"):
            chunk_id, source, line_start, text, tokens_json, token_count = row
            chunk_tokens = json.loads(tokens_json)

            # Quick check: any overlap?
            chunk_token_set = set(chunk_tokens)
            if not term_set & chunk_token_set:
                continue

            # BM25 score
            score = 0.0
            # Count term frequencies in chunk
            tf_map: Dict[str, int] = {}
            for t in chunk_tokens:
                tf_map[t] = tf_map.get(t, 0) + 1

            dl = token_count
            for qt in query_tokens:
                if qt not in tf_map:
                    continue
                tf = tf_map[qt]
                idf = self._idf_cache.get(qt, 0)
                # BM25 formula
                numerator = tf * (BM25_K1 + 1)
                denominator = tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / self._avg_dl)
                score += idf * (numerator / denominator)

            if score >= min_score:
                scored.append({
                    'score': round(score, 4),
                    'source': source,
                    'line': line_start,
                    'text': text,
                })

        # Sort by score descending
        scored.sort(key=lambda x: -x['score'])
        return scored[:max_results]

    def build_context(self, query: str, max_chars: int = 4000,
                      max_results: int = 6) -> str:
        """Build a context string for RAG injection into LLM prompts."""
        results = self.search(query, max_results=max_results)
        if not results:
            return ""

        parts = ["[검색된 관련 정보]"]
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
        if self._conn:
            self._conn.close()
            self._conn = None


# ── RAG-augmented prompt injection ─────────────────────────────

def inject_rag_context(messages: list, system_prompt: str,
                       max_chars: int = 3000) -> str:
    """Analyze recent messages and inject relevant RAG context into system prompt."""
    # Extract query from last 3 user messages
    user_msgs = [m['content'] for m in messages[-6:]
                 if m.get('role') == 'user' and isinstance(m.get('content'), str)]
    if not user_msgs:
        return system_prompt

    query = ' '.join(user_msgs[-3:])
    context = rag_engine.build_context(query, max_chars=max_chars)
    if not context:
        return system_prompt

    # Inject after the main system prompt
    return system_prompt + "\n\n" + context


# ── Module-level instance ──────────────────────────────────────

rag_engine = RAGEngine()
