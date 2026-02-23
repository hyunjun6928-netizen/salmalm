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
  from salmalm.features.rag import rag_engine
  results = rag_engine.search("DB schema")
  context = rag_engine.build_context("DB schema", max_chars=3000)
"""

import hashlib
import json
import math
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from salmalm.constants import MEMORY_DIR, WORKSPACE_DIR, MEMORY_FILE, BASE_DIR, DATA_DIR
from salmalm.security.crypto import log
from salmalm.features.rag_utils import (  # noqa: F401
    decompose_jamo,
    simple_stem,
    compute_tf,
    expand_query,
    load_rag_config,
    cosine_similarity,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    MAX_CHUNK_CHARS,
)

# ── BM25 Parameters ──
BM25_K1 = 1.5
BM25_B = 0.75
REINDEX_INTERVAL = 120

# Stop words (Korean + English)
_STOP_WORDS = frozenset(
    [
        "의",
        "가",
        "이",
        "은",
        "는",
        "을",
        "를",
        "에",
        "에서",
        "로",
        "으로",
        "와",
        "과",
        "도",
        "만",
        "부터",
        "까지",
        "에게",
        "한테",
        "하다",
        "있다",
        "되다",
        "하는",
        "있는",
        "되는",
        "했다",
        "했던",
        "하고",
        "그리고",
        "그런데",
        "또는",
        "혹은",
        "및",
        "대한",
        "위한",
        "통해",
        "따라",
        "대해",
        "이를",
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "that",
        "this",
        "it",
        "not",
        "no",
        "if",
        "then",
        "so",
        "as",
        "by",
        "from",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "can",
        "could",
        "may",
        "might",
        "shall",
        "should",
        "must",
        "need",
    ]
)

# Korean jamo constants moved to rag_utils.py


# ── English Stemming (simple Porter-like) ──


# ── Synonym / Query Expansion Dictionary ──

from salmalm.features.rag_utils import _SYNONYMS, _SYNONYM_REVERSE  # noqa: F401,E402


# ── RAG Configuration ──

from salmalm.features.rag_utils import _DEFAULT_CONFIG  # noqa: F401


# ── TF-IDF Vector Utilities ──


from salmalm.features.rag_indexer import RAGIndexerMixin


class RAGEngine(RAGIndexerMixin):
    """Hybrid BM25 + TF-IDF vector retrieval engine with persistent SQLite index."""

    def __init__(self, db_path: Optional[Path] = None, config_path: Optional[Path] = None) -> None:
        """Init  ."""
        self._db_path = db_path or (DATA_DIR / "rag.db")
        self._config_path = config_path
        self._conn: Optional[sqlite3.Connection] = None
        self._db_lock = threading.Lock()
        self._mtimes: Dict[str, float] = {}
        self._last_check = 0
        self._doc_count = 0
        self._avg_dl = 0.0
        self._idf_cache: Dict[str, float] = {}
        self._initialized = False
        self._config: Optional[dict] = None

    @property
    def config(self) -> dict:
        """Config."""
        if self._config is None:
            self._config = load_rag_config(self._config_path)
        return self._config

    def _ensure_db(self):
        """Ensure db."""
        if self._conn:
            return
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            text TEXT NOT NULL,
            tokens TEXT NOT NULL,
            token_count INTEGER NOT NULL,
            mtime REAL NOT NULL,
            hash TEXT NOT NULL
        )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS doc_freq (
            term TEXT PRIMARY KEY,
            df INTEGER NOT NULL
        )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS tfidf_vectors (
            chunk_id INTEGER PRIMARY KEY,
            vector TEXT NOT NULL,
            FOREIGN KEY (chunk_id) REFERENCES chunks(id)
        )""")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS rag_embeddings (
            chunk_hash TEXT PRIMARY KEY,
            embedding TEXT NOT NULL,
            provider TEXT,
            dimensions INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        self._conn.execute("""CREATE INDEX IF NOT EXISTS idx_chunks_source
            ON chunks(source)""")
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
        raw = re.findall(r"[\w가-힣]+", text_lower)
        unigrams = []
        for t in raw:
            if len(t) <= 1 or t in _STOP_WORDS:
                continue
            # Apply stemming for English words
            if re.match(r"^[a-z]+$", t):
                stemmed = simple_stem(t)
                unigrams.append(stemmed)
                if stemmed != t:
                    unigrams.append(t)  # Keep original too
            else:
                unigrams.append(t)

        # Bigrams
        bigrams = [f"{unigrams[i]}_{unigrams[i + 1]}" for i in range(len(unigrams) - 1)]

        # Character 3-grams (especially useful for Korean)
        char_trigrams = []
        clean = re.sub(r"\s+", "", text_lower)
        for i in range(len(clean) - 2):
            tri = clean[i : i + 3]
            if re.match(r"^[\w가-힣]{3}$", tri):
                char_trigrams.append(f"c3:{tri}")

        # Jamo decomposition for Korean text
        korean_chars = re.findall(r"[가-힣]+", text_lower)
        jamo_tokens = []
        for kw in korean_chars:
            if len(kw) >= 2:
                jamo = decompose_jamo(kw)
                jamo_tokens.append(f"j:{jamo}")

        return unigrams + bigrams + char_trigrams + jamo_tokens

    def index_file(self, label: str, fpath: Path) -> None:
        """Index a single file."""
        self._ensure_db()
        try:
            mtime = fpath.stat().st_mtime
            self._mtimes[label] = mtime
            text = fpath.read_text(encoding="utf-8", errors="replace")
            self._index_text(label, text, mtime)
            self._last_check = time.time()
        except Exception as e:
            log.warning(f"RAG index_file error ({label}): {e}")

    def _chunk_and_index(self, label, text, mtime, chunk_size, chunk_overlap, new_docs, vectors, doc_freq):
        """Chunk text and add to index arrays."""
        lines = text.splitlines()
        step = max(1, chunk_size - chunk_overlap)
        for i in range(0, len(lines), step):
            chunk_lines = lines[i : i + chunk_size]
            chunk_text = "\n".join(chunk_lines).strip()
            if not chunk_text or len(chunk_text) < 10:
                continue
            if len(chunk_text) > MAX_CHUNK_CHARS:
                chunk_text = chunk_text[:MAX_CHUNK_CHARS]
            tokens = self._tokenize(chunk_text)
            if not tokens:
                continue
            h = hashlib.md5(chunk_text.encode()).hexdigest()[:12]
            new_docs.append((label, i + 1, i + len(chunk_lines), chunk_text, json.dumps(tokens), len(tokens), mtime, h))
            vectors.append(compute_tf(tokens))
            for t in set(tokens):
                doc_freq[t] = doc_freq.get(t, 0) + 1

    def reindex(self, force: bool = False) -> None:
        """Rebuild the index from source files."""
        self._ensure_db()
        if not force and not self._needs_reindex():
            return

        files = self._get_indexable_files()
        session_files = self._get_session_files()

        cfg = self.config
        chunk_size = cfg.get("chunkSize", CHUNK_SIZE)
        chunk_overlap = cfg.get("chunkOverlap", CHUNK_OVERLAP)

        new_docs = []
        vectors = []
        doc_freq: Dict[str, int] = {}

        def process_text(label: str, text: str, mtime: float) -> None:
            """Process text."""
            self._chunk_and_index(label, text, mtime, chunk_size, chunk_overlap, new_docs, vectors, doc_freq)

        for label, fpath in files:
            try:
                mtime = fpath.stat().st_mtime
                self._mtimes[label] = mtime
                text = fpath.read_text(encoding="utf-8", errors="replace")
                process_text(label, text, mtime)
            except Exception as e:
                log.warning(f"RAG index error ({label}): {e}")
                continue

        # Session files
        for label, fpath in session_files:
            try:
                mtime = fpath.stat().st_mtime
                self._mtimes[label] = mtime
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                parts = []
                messages = data if isinstance(data, list) else data.get("messages", [])
                for msg in messages:
                    if isinstance(msg, dict):
                        content = msg.get("content", "")
                        if isinstance(content, str) and content.strip():
                            parts.append(content)
                if parts:
                    process_text(label, "\n".join(parts), mtime)
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
                new_docs,
            )
            # Insert TF-IDF vectors
            # Get the inserted chunk IDs
            rows = self._conn.execute("SELECT id FROM chunks ORDER BY id").fetchall()
            for (chunk_id,), vec in zip(rows, vectors):
                self._conn.execute(
                    "INSERT INTO tfidf_vectors (chunk_id, vector) VALUES (?,?)", (chunk_id, json.dumps(vec))
                )

            self._conn.executemany("INSERT OR REPLACE INTO doc_freq (term, df) VALUES (?,?)", list(doc_freq.items()))
            self._conn.execute("COMMIT")
        except Exception as e:  # noqa: broad-except
            self._conn.execute("ROLLBACK")
            raise
        self._load_stats()
        log.info(
            f"[AI] RAG index rebuilt: {len(new_docs)} chunks from {len(files) + len(session_files)} files, "
            f"{len(doc_freq)} unique terms"
        )

        # Generate embeddings for all chunks if API available
        try:
            from salmalm.features.rag_embeddings import get_available_provider, batch_embed
            if get_available_provider():
                chunk_texts = [doc[3] for doc in new_docs]  # text field
                batch_embed(chunk_texts, conn=self._conn)
        except Exception as e:
            log.debug(f"[RAG] Embedding during reindex skipped: {e}")

    def _bm25_search(self, query_tokens: List[str], max_results: int, min_score: float) -> List[Dict]:
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
                scored.append(
                    {
                        "score": score,
                        "source": source,
                        "line": line_start,
                        "text": text,
                        "chunk_id": chunk_id,
                    }
                )

        scored.sort(key=lambda x: -x["score"])
        return scored[:max_results]

    @staticmethod
    def _has_embedding_api() -> bool:
        """Check if any embedding API provider is available."""
        try:
            from salmalm.features.rag_embeddings import get_available_provider
            return get_available_provider() is not None
        except Exception:
            return False

    def _embedding_search(self, query: str, max_results: int) -> List[Dict]:
        """Semantic search using embedding vectors."""
        try:
            from salmalm.features.rag_embeddings import get_embedding, cosine_similarity_vec
        except Exception:
            return []

        result = get_embedding(query, conn=self._conn)
        if result is None:
            return []
        query_emb, _ = result

        # Get all chunks that have embeddings
        scored = []
        for row in self._conn.execute(
            "SELECT c.id, c.source, c.line_start, c.text, c.hash "
            "FROM chunks c"
        ):
            chunk_id, source, line_start, text, chunk_hash = row
            # Look up embedding by chunk hash
            emb_row = self._conn.execute(
                "SELECT embedding FROM rag_embeddings WHERE chunk_hash=?",
                (hashlib.sha256(text.encode()).hexdigest()[:32],),
            ).fetchone()
            if not emb_row:
                continue
            chunk_emb = json.loads(emb_row[0])
            if len(chunk_emb) != len(query_emb):
                continue
            sim = cosine_similarity_vec(query_emb, chunk_emb)
            if sim > 0:
                scored.append({
                    "score": sim,
                    "source": source,
                    "line": line_start,
                    "text": text,
                    "chunk_id": chunk_id,
                })

        scored.sort(key=lambda x: -x["score"])
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
                scored.append(
                    {
                        "score": sim,
                        "source": source,
                        "line": line_start,
                        "text": text,
                        "chunk_id": chunk_id,
                    }
                )

        scored.sort(key=lambda x: -x["score"])
        return scored[:max_results]

    def search(self, query: str, max_results: int = 8, min_score: float = 0.1) -> List[Dict]:
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
        hybrid_cfg = cfg.get("hybrid", {})
        hybrid_enabled = hybrid_cfg.get("enabled", True)

        if not hybrid_enabled:
            # BM25 only (legacy mode)
            results = self._bm25_search(expanded_tokens, max_results, min_score)
            for r in results:
                r["score"] = round(r["score"], 4)
                r.pop("chunk_id", None)
            return results

        # Hybrid search
        vector_weight = hybrid_cfg.get("vectorWeight", 0.7)
        text_weight = hybrid_cfg.get("textWeight", 0.3)
        # Normalize weights
        total_w = vector_weight + text_weight
        if total_w > 0:
            vector_weight /= total_w
            text_weight /= total_w

        candidate_multiplier = 4
        pool_size = max_results * candidate_multiplier

        # Try embedding search first (semantic), fall back to TF-IDF vector search
        use_embeddings = self._has_embedding_api()
        if use_embeddings:
            try:
                vector_results = self._embedding_search(query, pool_size)
            except Exception:
                vector_results = self._vector_search(expanded_tokens, pool_size)
        else:
            vector_results = self._vector_search(expanded_tokens, pool_size)
        bm25_results = self._bm25_search(expanded_tokens, pool_size, 0.0)

        # Build score maps
        # Vector scores are already cosine similarity [0,1]
        vector_scores: Dict[int, float] = {}
        vector_data: Dict[int, Dict] = {}
        for r in vector_results:
            cid = r["chunk_id"]
            vector_scores[cid] = r["score"]
            vector_data[cid] = r

        # BM25: textScore = 1 / (1 + max(0, rank))
        bm25_scores: Dict[int, float] = {}
        bm25_data: Dict[int, Dict] = {}
        for rank, r in enumerate(bm25_results):
            cid = r["chunk_id"]
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
                final.append(
                    {
                        "score": round(final_score, 4),
                        "source": data["source"],
                        "line": data["line"],
                        "text": data["text"],
                    }
                )

        final.sort(key=lambda x: -x["score"])

        # Filter by min_score
        final = [r for r in final if r["score"] >= min_score]
        return final[:max_results]

    def build_context(self, query: str, max_chars: int = 4000, max_results: int = 6) -> str:
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

        context = "\n".join(parts)

        # If local results are thin, try Brave web augmentation
        if len(results) < 2:
            context += brave_augment_context(query, max_chars=max_chars - total)

        return context

    def get_stats(self) -> dict:
        """Return index statistics."""
        self._ensure_db()
        return {
            "total_chunks": self._doc_count,
            "unique_terms": len(self._idf_cache),
            "avg_chunk_length": round(self._avg_dl, 1),
            "db_size_kb": round(self._db_path.stat().st_size / 1024, 1) if self._db_path.exists() else 0,
            "indexed_files": len(self._mtimes),
        }

    def close(self) -> None:
        """Close the RAG database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


# ── RAG-augmented prompt injection ─────────────────────────────


def inject_rag_context(messages: list, system_prompt: str, max_chars: int = 3000) -> str:
    """Analyze recent messages and inject relevant RAG context into system prompt."""
    user_msgs = [m["content"] for m in messages[-6:] if m.get("role") == "user" and isinstance(m.get("content"), str)]
    if not user_msgs:
        return system_prompt

    query = " ".join(user_msgs[-3:])
    context = rag_engine.build_context(query, max_chars=max_chars)
    if not context:
        return system_prompt

    return system_prompt + "\n\n" + context


# ── Brave Web Augmentation ─────────────────────────────────────


def brave_augment_context(query: str, max_chars: int = 2000) -> str:
    """Augment RAG context with Brave LLM Context API when local results are thin.

    Enable via config: ConfigManager.save('brave', {'rag_augment': True})
    """
    try:
        from salmalm.config_manager import ConfigManager

        cfg = ConfigManager.load("brave", {"rag_augment": False})
        if not cfg.get("rag_augment", False):
            return ""
        from salmalm.tools.tools_brave import brave_llm_context

        result = brave_llm_context({"query": query, "count": 3})
        if result and not result.startswith("❌") and not result.startswith("🔑"):
            return f"\n[Web context (Brave)]\n{result[:max_chars]}"
    except Exception as e:
        log.debug(f"Brave RAG augment failed: {e}")
    return ""


# ── Module-level instance ──────────────────────────────────────

rag_engine = RAGEngine()
