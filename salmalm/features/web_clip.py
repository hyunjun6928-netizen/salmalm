"""Web Clipboard — clip URLs, extract content, search clips.

stdlib-only. Provides:
  - /clip <url> — scrape URL and save as note
  - /clip search <query> — search saved clips
  - Readability algorithm (stdlib HTML parsing)
  - Auto-add to RAG index
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional

from salmalm.constants import BASE_DIR

log = logging.getLogger(__name__)

CLIPS_DIR = BASE_DIR / "clips"
CLIPS_DB = CLIPS_DIR / "clips.json"


# ---------------------------------------------------------------------------
# Readability — simple HTML → text extraction
# ---------------------------------------------------------------------------


class _TagStripper(HTMLParser):
    """Simple HTML tag stripper with readability heuristics."""

    # Tags whose content should be removed entirely
    _SKIP_TAGS = frozenset(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript", "svg", "form"])
    _BLOCK_TAGS = frozenset(
        [
            "p",
            "div",
            "article",
            "section",
            "main",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "blockquote",
            "pre",
            "tr",
            "td",
            "th",
            "br",
            "hr",
        ]
    )

    def __init__(self):
        super().__init__()
        self.result: List[str] = []
        self._skip_depth = 0
        self._title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in self._BLOCK_TAGS:
            self.result.append("\n")

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in self._BLOCK_TAGS:
            self.result.append("\n")

    def handle_data(self, data: str):
        if self._in_title:
            self._title += data
        if self._skip_depth > 0:
            return
        self.result.append(data)

    def get_text(self) -> str:
        raw = "".join(self.result)
        # Collapse whitespace
        lines = []
        for line in raw.split("\n"):
            stripped = line.strip()
            if stripped:
                lines.append(stripped)
        return "\n".join(lines)

    def get_title(self) -> str:
        return self._title.strip()


def extract_readable(html_text: str) -> Dict[str, str]:
    """Extract readable text and title from HTML."""
    parser = _TagStripper()
    try:
        parser.feed(html_text)
    except Exception:
        pass
    text = parser.get_text()
    title = parser.get_title()
    return {"title": title, "text": text}


def fetch_url(url: str, timeout: int = 15) -> str:
    """Fetch URL content. Returns HTML string."""
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


# ---------------------------------------------------------------------------
# Clip storage
# ---------------------------------------------------------------------------


class WebClip:
    """A saved web clip."""

    __slots__ = ("id", "url", "title", "content", "created_at", "word_count")

    def __init__(self, *, id: str, url: str, title: str, content: str, created_at: float = 0):
        self.id = id
        self.url = url
        self.title = title
        self.content = content
        self.created_at = created_at or time.time()
        self.word_count = len(content.split())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            "word_count": self.word_count,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "WebClip":
        return cls(
            id=d["id"],
            url=d["url"],
            title=d.get("title", ""),
            content=d.get("content", ""),
            created_at=d.get("created_at", 0),
        )


class ClipManager:
    """Manage web clips."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self._dir = storage_dir or CLIPS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._dir / "clips.json"
        self._clips: Dict[str, WebClip] = {}
        self._load()

    def _load(self):
        if self._db_path.exists():
            try:
                data = json.loads(self._db_path.read_text(encoding="utf-8"))
                for d in data:
                    c = WebClip.from_dict(d)
                    self._clips[c.id] = c
            except Exception as e:
                log.warning(f"Failed to load clips: {e}")

    def _save(self):
        try:
            self._db_path.write_text(
                json.dumps([c.to_dict() for c in self._clips.values()], ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            log.warning(f"Failed to save clips: {e}")

    def _make_id(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:12]

    def clip_url(self, url: str) -> WebClip:
        """Fetch, extract, and save a URL."""
        html_text = fetch_url(url)
        extracted = extract_readable(html_text)
        cid = self._make_id(url)
        clip = WebClip(id=cid, url=url, title=extracted["title"], content=extracted["text"])
        self._clips[cid] = clip
        self._save()

        # Try to add to RAG
        self._index_clip(clip)

        return clip

    def add_clip(self, url: str, title: str, content: str) -> WebClip:
        """Manually add a clip without fetching."""
        cid = self._make_id(url)
        clip = WebClip(id=cid, url=url, title=title, content=content)
        self._clips[cid] = clip
        self._save()
        return clip

    def get(self, clip_id: str) -> Optional[WebClip]:
        return self._clips.get(clip_id)

    def list_all(self, limit: int = 50) -> List[WebClip]:
        clips = sorted(self._clips.values(), key=lambda c: c.created_at, reverse=True)
        return clips[:limit]

    def search(self, query: str) -> List[WebClip]:
        """Simple keyword search across clips."""
        q_lower = query.lower()
        keywords = q_lower.split()
        scored: List[tuple] = []
        for clip in self._clips.values():
            text = f"{clip.title} {clip.content}".lower()
            score = sum(1 for k in keywords if k in text)
            if score > 0:
                scored.append((score, clip))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:20]]

    def remove(self, clip_id: str) -> bool:
        if clip_id in self._clips:
            del self._clips[clip_id]
            self._save()
            return True
        return False

    def _index_clip(self, clip: WebClip):
        """Add clip to RAG index if available."""
        try:
            from salmalm.features.rag import rag_engine

            rag_engine.add_text(
                f"[WebClip] {clip.title}\n{clip.url}\n\n{clip.content[:2000]}",
                source=f"clip:{clip.id}",
            )
        except Exception:
            pass  # RAG may not be available

    @property
    def count(self) -> int:
        return len(self._clips)


# Singleton
clip_manager = ClipManager()


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def handle_clip_command(cmd: str, session=None, **kw) -> str:
    """Handle /clip <url> | /clip search <query> | /clip list."""
    parts = cmd.strip().split(maxsplit=2)

    if len(parts) < 2:
        return "❌ Usage: `/clip <url>` or `/clip search <query>` or `/clip list`"

    sub = parts[1]

    if sub == "list":
        clips = clip_manager.list_all()
        if not clips:
            return "📎 No clips saved yet."
        lines = ["**Web Clips:**\n"]
        for c in clips:
            lines.append(f"• `{c.id}` [{c.word_count}w] **{c.title or 'Untitled'}**\n  {c.url}")
        return "\n".join(lines)

    if sub == "search":
        query = parts[2] if len(parts) > 2 else ""
        if not query:
            return "❌ Usage: `/clip search <query>`"
        results = clip_manager.search(query)
        if not results:
            return f'🔍 No clips found for "{query}"'
        lines = [f'**Search: "{query}"** ({len(results)} results)\n']
        for c in results:
            preview = c.content[:100].replace("\n", " ")
            lines.append(f"• `{c.id}` **{c.title or 'Untitled'}** — {preview}…")
        return "\n".join(lines)

    if sub == "get" and len(parts) > 2:
        clip = clip_manager.get(parts[2])
        if not clip:
            return f"❌ Clip `{parts[2]}` not found"
        return f"**{clip.title}**\n{clip.url}\n\n{clip.content[:3000]}"

    # Assume it's a URL
    url = sub
    if not url.startswith("http"):
        url = "https://" + url
    try:
        clip = clip_manager.clip_url(url)
        preview = clip.content[:200].replace("\n", " ")
        return f"✅ Clipped: **{clip.title or 'Untitled'}** (`{clip.id}`)\n{clip.word_count} words\n\n{preview}…"
    except Exception as e:
        return f"❌ Failed to clip URL: {e}"


def register_commands(router):
    """Register /clip commands."""
    router.register_prefix("/clip", handle_clip_command)


def register_tools(registry_module=None):
    """Register web clip tools."""
    try:
        from salmalm.tools.tool_registry import register_dynamic

        register_dynamic(
            "web_clip",
            lambda args: handle_clip_command(f"/clip {args.get('url', '')}"),
            {
                "name": "web_clip",
                "description": "Clip a URL — fetch and extract readable content",
                "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            },
        )
        register_dynamic(
            "web_clip_search",
            lambda args: handle_clip_command(f"/clip search {args.get('query', '')}"),
            {
                "name": "web_clip_search",
                "description": "Search saved web clips",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            },
        )
    except Exception as e:
        log.warning(f"Failed to register web clip tools: {e}")
