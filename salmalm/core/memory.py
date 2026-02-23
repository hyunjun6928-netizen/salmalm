"""Enhanced Memory System — OpenClaw-style two-layer memory.

Architecture:
  - MEMORY.md: curated long-term memory (key decisions, preferences, lessons)
  - memory/YYYY-MM-DD.md: daily append-only logs (raw events)
  - memory_search: TF-IDF hybrid search across all memory files
  - auto_curate(): promote important daily content → MEMORY.md
  - Session start: auto-load today + yesterday memory context
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from salmalm.constants import MEMORY_FILE, MEMORY_DIR, KST
from salmalm import log


class MemoryManager:
    """OpenClaw-style memory management with auto-curation.

    Two-layer memory:
      - MEMORY.md: curated long-term memory (loaded in main session only)
      - memory/YYYY-MM-DD.md: daily append-only logs

    Features:
      - Keyword search across all memory files (delegates to TF-IDF engine)
      - Pre-compaction memory flush
      - Daily log auto-creation
      - Auto-curation: promote important entries from daily logs to MEMORY.md
      - Session-start context loader (today + yesterday)
    """

    # Patterns that indicate important content worth curating
    _IMPORTANT_PATTERNS = [
        re.compile(r"\b(결정|decision|decided|결론)\b", re.I),
        re.compile(r"\b(중요|important|critical|핵심)\b", re.I),
        re.compile(r"\b(배운|learned|lesson|교훈)\b", re.I),
        re.compile(r"\b(preference|선호|좋아|싫어)\b", re.I),
        re.compile(r"\b(project|프로젝트|goal|목표|plan|계획)\b", re.I),
        re.compile(r"\b(remember|기억|잊지|forget)\b", re.I),
        re.compile(r"^\s*\*\*", re.M),  # Bold text often = important
        re.compile(r"^\s*#{1,3}\s", re.M),  # Headers = section markers
    ]

    # Secret detection/redaction delegated to shared utility
    @staticmethod
    def _contains_secret(text: str) -> bool:
        """Contains secret."""
        from salmalm.security.redact import contains_secret

        return contains_secret(text)

    @staticmethod
    def _scrub_secrets(text: str) -> str:
        """Scrub secrets."""
        from salmalm.security.redact import scrub_secrets

        return scrub_secrets(text)

    def __init__(self) -> None:
        """Init  ."""
        self._search = None  # Lazy — set after TFIDFSearch is ready

    def _get_search(self):
        """Lazy-load search engine to avoid circular imports."""
        if self._search is None:
            from salmalm.core import _tfidf

            self._search = _tfidf
        return self._search

    # ── Read / Write ──────────────────────────────────────────

    def read(self, filename: str) -> str:
        """Read a memory file. Supports MEMORY.md and memory/YYYY-MM-DD.md."""
        if filename == "MEMORY.md":
            if MEMORY_FILE.exists():
                return MEMORY_FILE.read_text(encoding="utf-8", errors="replace")
            return "(MEMORY.md does not exist yet)"
        fpath = MEMORY_DIR / filename
        if fpath.exists() and fpath.resolve().is_relative_to(MEMORY_DIR.resolve()):
            return fpath.read_text(encoding="utf-8", errors="replace")
        return f"(File not found: {filename})"

    def write(self, filename: str, content: str, append: bool = False) -> str:
        """Write to a memory file. Secrets are automatically scrubbed."""
        MEMORY_DIR.mkdir(exist_ok=True)
        # Scrub secrets before writing to any memory file
        if self._contains_secret(content):
            log.warning(f"[MEMORY] Secret detected in write to {filename} — redacting")
            content = self._scrub_secrets(content)
        if filename == "MEMORY.md":
            fpath = MEMORY_FILE
        else:
            fpath = MEMORY_DIR / filename
            if not fpath.resolve().is_relative_to(MEMORY_DIR.resolve()):
                return "❌ Invalid memory path"
        if append and fpath.exists():
            existing = fpath.read_text(encoding="utf-8", errors="replace")
            content = existing + "\n" + content
        fpath.write_text(content, encoding="utf-8")
        # Invalidate search index
        search = self._get_search()
        search._built = False
        return f"✅ Written to {filename} ({len(content)} chars)"

    # ── Search ────────────────────────────────────────────────

    def search(self, query: str, max_results: int = 5) -> list:
        """Search across all memory files using TF-IDF."""
        return self._get_search().search(query, max_results=max_results)

    # ── List ──────────────────────────────────────────────────

    def list_files(self) -> list:
        """List all memory files."""
        files = []
        if MEMORY_FILE.exists():
            stat = MEMORY_FILE.stat()
            files.append(
                {
                    "name": "MEMORY.md",
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, KST).isoformat(),
                }
            )
        MEMORY_DIR.mkdir(exist_ok=True)
        for f in sorted(MEMORY_DIR.glob("*.md"), reverse=True):
            stat = f.stat()
            files.append(
                {
                    "name": f.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, KST).isoformat(),
                }
            )
        return files

    # ── Session Start Context ─────────────────────────────────

    def load_session_context(self) -> str:
        """Load today + yesterday memory for session startup injection.

        Returns a formatted string suitable for system prompt injection.
        """
        parts = []
        now = datetime.now(KST)

        # Today's log
        today_str = now.strftime("%Y-%m-%d")
        today_file = MEMORY_DIR / f"{today_str}.md"
        if today_file.exists():
            content = today_file.read_text(encoding="utf-8", errors="replace")
            # Truncate to last 3000 chars for recent context
            if len(content) > 3000:
                content = "...\n" + content[-3000:]
            parts.append(f"## Today's Log ({today_str})\n{content}")

        # Yesterday's log
        yesterday = now - timedelta(days=1)
        yest_str = yesterday.strftime("%Y-%m-%d")
        yest_file = MEMORY_DIR / f"{yest_str}.md"
        if yest_file.exists():
            content = yest_file.read_text(encoding="utf-8", errors="replace")
            if len(content) > 2000:
                content = "...\n" + content[-2000:]
            parts.append(f"## Yesterday's Log ({yest_str})\n{content}")

        if not parts:
            return ""
        return "# Recent Memory\n\n" + "\n\n".join(parts)

    # ── Auto-Recall (OpenClaw-style mandatory memory search) ──

    def auto_recall(self, user_message: str, max_results: int = 3) -> str:
        """Search memory for context relevant to user message.

        Like OpenClaw's memory_search, but automatic — runs before each
        response to inject relevant prior context.

        Returns formatted context string or empty string.
        """
        if not user_message or len(user_message) < 5:
            return ""
        try:
            from salmalm.features.rag import rag_engine

            results = rag_engine.search(user_message, max_results=max_results)
            if not results:
                return ""
            parts = ["[Memory Recall]"]
            for r in results:
                source = r.get("source", "")
                snippet = r.get("content", "")[:200]
                score = r.get("score", 0)
                if score < 0.1:  # Too low relevance
                    continue
                parts.append(f"- {source}: {snippet}")
            if len(parts) <= 1:
                return ""
            return "\n".join(parts)
        except Exception:
            return ""

    # ── Pre-compaction Flush ──────────────────────────────────

    def flush_before_compaction(self, session) -> str:
        """Save important context from session to daily log before compaction."""
        if session._memory_flushed:
            return ""
        session._memory_flushed = True

        recent_user = [
            m["content"]
            for m in session.messages[-10:]
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ]
        recent_assistant = [
            m["content"]
            for m in session.messages[-10:]
            if m.get("role") == "assistant" and isinstance(m.get("content"), str)
        ]

        if not recent_user:
            return ""

        from salmalm.core import write_daily_log

        _today = datetime.now(KST).strftime("%Y-%m-%d")  # noqa: F841
        _ts = datetime.now(KST).strftime("%H:%M")  # noqa: F841
        summary_parts = []
        for msg in recent_user[-3:]:
            summary_parts.append(f"  Q: {msg[:100]}")
        for msg in recent_assistant[-2:]:
            summary_parts.append(f"  A: {msg[:150]}")

        entry = f"[session:{session.id}] Pre-compaction flush\n" + "\n".join(summary_parts)
        write_daily_log(entry)
        log.info(f"[MEM] Pre-compaction memory flush for session {session.id}")
        return entry

    # ── Auto-Curation ─────────────────────────────────────────

    def auto_curate(self, days_back: int = 3) -> str:
        """Scan recent daily logs and promote important entries to MEMORY.md.

        This is a lightweight heuristic-based curation:
        - Scans daily logs from the last N days
        - Identifies entries matching importance patterns
        - Appends new entries to MEMORY.md under a dated section
        - Skips entries already present in MEMORY.md (dedup by content hash)

        Returns a summary of what was curated.
        """
        now = datetime.now(KST)
        existing_memory = ""
        if MEMORY_FILE.exists():
            existing_memory = MEMORY_FILE.read_text(encoding="utf-8", errors="replace")

        curated = []

        for days_ago in range(days_back):
            date = now - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            log_file = MEMORY_DIR / f"{date_str}.md"
            if not log_file.exists():
                continue

            content = log_file.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            for line in lines:
                stripped = line.strip()
                if not stripped or len(stripped) < 10:
                    continue
                # Skip if already in MEMORY.md (substring match)
                # Use first 50 chars as fingerprint
                fingerprint = stripped[:50]
                if fingerprint in existing_memory:
                    continue
                # Block secret-containing lines from curation
                if self._contains_secret(stripped):
                    log.warning(f"[MEMORY] Secret detected in daily log — skipping curation: {stripped[:30]}...")
                    continue
                # Check importance patterns
                importance = sum(1 for pat in self._IMPORTANT_PATTERNS if pat.search(stripped))
                if importance >= 2:  # At least 2 pattern matches
                    curated.append((date_str, self._scrub_secrets(stripped)))

        if not curated:
            return "No new entries to curate."

        # Append to MEMORY.md
        new_section = "\n\n## Auto-curated (" + now.strftime("%Y-%m-%d %H:%M") + ")\n\n"
        for date_str, entry in curated[:20]:  # Cap at 20 entries
            new_section += f"- [{date_str}] {entry}\n"

        MEMORY_DIR.mkdir(exist_ok=True)
        with open(MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(new_section)

        summary = f"Curated {len(curated)} entries from last {days_back} days → MEMORY.md"
        log.info(f"[MEM] {summary}")
        return summary


# Module-level singleton
memory_manager = MemoryManager()
