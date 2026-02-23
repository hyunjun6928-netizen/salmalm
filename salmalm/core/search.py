"""TF-IDF search engine — pure Python, no external deps."""

import math
import re
from collections import OrderedDict

class TFIDFSearch:
    """Lightweight TF-IDF + cosine similarity search. No external deps."""

    def __init__(self):
        self._docs: list = []  # [(label, line_no, text, tokens)]
        self._idf: dict = {}  # term -> IDF score
        self._built = False
        self._last_index_time = 0
        self._stop_words = frozenset(
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
                "에서의",
                "the",
                "a",
                "an",
                "is",
                "are",
                "was",
                "were",
                "be",
                "been",
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
            ]
        )

    def _tokenize(self, text: str) -> list:
        """Split text into normalized tokens."""
        text = text.lower()
        # Split on non-alphanumeric (keeping Korean chars)
        tokens = re.findall(r"[\w가-힣]+", text)
        return [t for t in tokens if len(t) > 1 and t not in self._stop_words]

    def _index_files(self):
        """Build index from MEMORY.md, memory/*.md, uploads/*.txt etc."""
        now = time.time()
        if self._built and now - self._last_index_time < 300:  # Re-index every 5 min
            return

        self._docs = []
        doc_freq: dict = {}  # term -> number of docs containing it  # type: ignore[var-annotated]
        search_files = []

        if MEMORY_FILE.exists():  # noqa: F405
            search_files.append(("MEMORY.md", MEMORY_FILE))  # noqa: F405
        for f in sorted(MEMORY_DIR.glob("*.md")):  # noqa: F405
            search_files.append((f"memory/{f.name}", f))
        uploads_dir = WORKSPACE_DIR / "uploads"  # noqa: F405
        if uploads_dir.exists():
            for f in uploads_dir.glob("*"):
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
                ):
                    search_files.append((f"uploads/{f.name}", f))
        # Also index skills
        skills_dir = WORKSPACE_DIR / "skills"  # noqa: F405
        if skills_dir.exists():
            for f in skills_dir.glob("**/*.md"):
                search_files.append((f"skills/{f.relative_to(skills_dir)}", f))

        for label, fpath in search_files:
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines()
                # Index in chunks of 3 lines for context
                for i in range(0, len(lines), 2):
                    chunk = "\n".join(lines[i : i + 3])
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
            self._idf = {t: math.log(n_docs / (1 + df)) for t, df in doc_freq.items()}
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
        query_norm = math.sqrt(sum(v**2 for v in query_vec.values()))
        if query_norm == 0:
            return []

        # Score each document
        scored = []
        for label, lineno, chunk, doc_tf in self._docs:
            doc_vec = {t: tf * self._idf.get(t, 0) for t, tf in doc_tf.items()}
            # Cosine similarity
            dot = sum(query_vec.get(t, 0) * doc_vec.get(t, 0) for t in set(query_vec) | set(doc_vec))
            doc_norm = math.sqrt(sum(v**2 for v in doc_vec.values()))
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
from salmalm.core.memory import MemoryManager, memory_manager


# ============================================================
