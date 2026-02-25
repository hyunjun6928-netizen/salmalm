"""RAG indexing methods mixin."""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Tuple

log = logging.getLogger(__name__)

from salmalm.constants import DATA_DIR, BASE_DIR, MEMORY_DIR, MEMORY_FILE, WORKSPACE_DIR  # noqa: E402

REINDEX_INTERVAL = 120
from salmalm.features.rag_utils import CHUNK_SIZE, CHUNK_OVERLAP, MAX_CHUNK_CHARS, compute_tf  # noqa: E402  # default seconds


class RAGIndexerMixin:
    """Mixin for RAG indexing operations."""

    def _index_text(self, label: str, text: str, mtime: float):
        """Index text content as chunks."""
        cfg = self.config
        chunk_size = cfg.get("chunkSize", CHUNK_SIZE)
        chunk_overlap = cfg.get("chunkOverlap", CHUNK_OVERLAP)

        lines = text.splitlines()
        new_docs = []
        vectors = []
        doc_freq: Dict[str, int] = {}

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

            # TF vector for this chunk
            tf_vec = compute_tf(tokens)
            vectors.append(tf_vec)

            for t in set(tokens):
                doc_freq[t] = doc_freq.get(t, 0) + 1

        if not new_docs:
            return

        # Remove old chunks for this label
        self._conn.execute(
            "DELETE FROM tfidf_vectors WHERE chunk_id IN (SELECT id FROM chunks WHERE source=?)", (label,)
        )
        self._conn.execute("DELETE FROM chunks WHERE source=?", (label,))

        # Insert new chunks
        for doc in new_docs:
            cur = self._conn.execute(
                "INSERT INTO chunks (source, line_start, line_end, text, tokens, token_count, mtime, hash) VALUES (?,?,?,?,?,?,?,?)",
                doc,
            )
            chunk_id = cur.lastrowid
            idx = len(vectors) - len(new_docs) + new_docs.index(doc)
            self._conn.execute(
                "INSERT INTO tfidf_vectors (chunk_id, vector) VALUES (?,?)", (chunk_id, json.dumps(vectors[idx]))
            )

        # Update doc_freq (rebuild entirely for simplicity during reindex)
        # This is handled in reindex(); for single file we just update
        for term, df_val in doc_freq.items():
            self._conn.execute(
                "INSERT OR REPLACE INTO doc_freq (term, df) VALUES (?, COALESCE((SELECT df FROM doc_freq WHERE term=?), 0) + ?)",
                (term, term, df_val),
            )

        self._conn.commit()
        self._load_stats()

        # Generate embeddings for new chunks (async-friendly, non-blocking on failure)
        try:
            from salmalm.features.rag_embeddings import get_available_provider, batch_embed
            if get_available_provider():
                chunk_texts = [doc[3] for doc in new_docs]  # text field
                batch_embed(chunk_texts, conn=self._conn)
        except Exception as e:
            log.debug(f"[RAG] Embedding during index_text skipped: {e}")

    def _get_indexable_files(self) -> List[Tuple[str, Path]]:
        """Enumerate files to index."""
        files = []
        if MEMORY_FILE.exists():
            files.append(("MEMORY.md", MEMORY_FILE))
        if MEMORY_DIR.exists():
            for f in sorted(MEMORY_DIR.glob("*.md")):
                files.append((f"memory/{f.name}", f))
        for name in ("SOUL.md", "USER.md", "TOOLS.md", "AGENTS.md", "HEARTBEAT.md"):
            p = BASE_DIR / name
            if p.exists():
                files.append((name, p))
        uploads = WORKSPACE_DIR / "uploads"
        if uploads.exists():
            for f in uploads.glob("*"):
                if f.suffix.lower() in (
                    ".txt",
                    ".md",
                    ".py",
                    ".js",
                    ".json",
                    ".csv",
                    ".html",
                    ".css",
                    ".log",
                    ".xml",
                    ".yaml",
                    ".yml",
                    ".sql",
                    ".sh",
                    ".bat",
                    ".toml",
                    ".cfg",
                    ".ini",
                ):
                    files.append((f"uploads/{f.name}", f))
        skills = WORKSPACE_DIR / "skills"
        if skills.exists():
            for f in skills.glob("**/*.md"):
                files.append((f"skills/{f.relative_to(skills)}", f))

        # Extra paths from config
        cfg = self.config
        for extra in cfg.get("extraPaths", []):
            ep = Path(extra).expanduser()
            if ep.is_file():
                files.append((str(ep.name), ep))
            elif ep.is_dir():
                for f in ep.glob("**/*"):
                    if f.is_file() and f.suffix.lower() in (".txt", ".md", ".py", ".json"):
                        files.append((str(f.relative_to(ep)), f))

        return files

    def _get_session_files(self) -> List[Tuple[str, Path]]:
        """Get session transcript files for indexing."""
        cfg = self.config
        si = cfg.get("sessionIndexing", {})
        if not si.get("enabled", False):
            return []

        sessions_dir = DATA_DIR / "sessions"
        if not sessions_dir.exists():
            return []

        retention_days = si.get("retentionDays", 30)
        cutoff = time.time() - (retention_days * 86400)
        files = []
        for f in sessions_dir.glob("*.json"):
            try:
                if f.stat().st_mtime >= cutoff:
                    files.append((f"session/{f.name}", f))
            except OSError:
                continue
        return files

    def _index_session_file(self, label: str, fpath: Path, mtime: float):
        """Index a session JSON file, extracting conversation text."""
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:  # noqa: broad-except
            return

        # Extract messages text
        parts = []
        messages = data if isinstance(data, list) else data.get("messages", [])
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    parts.append(content)

        if parts:
            text = "\n".join(parts)
            self._index_text(label, text, mtime)

    def _needs_reindex(self) -> bool:
        """Check if any source files changed since last index."""
        now = time.time()
        reindex_interval = self.config.get("reindexInterval", REINDEX_INTERVAL)
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
