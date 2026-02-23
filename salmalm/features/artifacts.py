"""Conversation Artifacts — auto-detect and save code/docs/JSON from conversations.

stdlib-only. Provides:
  - Auto-detect code blocks, markdown docs, JSON in assistant responses
  - /artifacts list — saved artifacts
  - /artifacts get <id> — retrieve artifact
  - /artifacts export — export all
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from salmalm.constants import BASE_DIR

log = logging.getLogger(__name__)

ARTIFACTS_DIR = BASE_DIR / "artifacts"
ARTIFACTS_DB = ARTIFACTS_DIR / "artifacts.json"

# Patterns for auto-detection
_CODE_BLOCK_RE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
_JSON_RE = re.compile(r"(?:^|\n)(\{[\s\S]*?\}|\[[\s\S]*?\])(?:\n|$)")
_MD_DOC_RE = re.compile(r"(?:^|\n)(#{1,3}\s+.+(?:\n(?!```).*){5,})", re.MULTILINE)


class ArtifactType:
    CODE = "code"
    JSON = "json"
    MARKDOWN = "markdown"
    DOCUMENT = "document"


class Artifact:
    """Single artifact."""

    __slots__ = ("id", "type", "language", "content", "preview", "session_id", "created_at", "metadata")

    def __init__(
        self,
        *,
        id: str,
        type: str,
        language: str = "",
        content: str,
        session_id: str = "",
        created_at: float = 0,
        metadata: Optional[Dict] = None,
    ):
        self.id = id
        self.type = type
        self.language = language
        self.content = content
        self.preview = content[:100].replace("\n", " ")
        self.session_id = session_id
        self.created_at = created_at or time.time()
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "language": self.language,
            "content": self.content,
            "preview": self.preview,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Artifact":
        return cls(
            id=d["id"],
            type=d["type"],
            language=d.get("language", ""),
            content=d["content"],
            session_id=d.get("session_id", ""),
            created_at=d.get("created_at", 0),
            metadata=d.get("metadata", {}),
        )


class ArtifactManager:
    """Manage conversation artifacts."""

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self._dir = storage_dir or ARTIFACTS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._dir / "artifacts.json"
        self._artifacts: Dict[str, Artifact] = {}
        self._load()

    def _load(self):
        if self._db_path.exists():
            try:
                data = json.loads(self._db_path.read_text(encoding="utf-8"))
                for d in data:
                    a = Artifact.from_dict(d)
                    self._artifacts[a.id] = a
            except Exception as e:
                log.warning(f"Failed to load artifacts: {e}")

    def _save(self):
        try:
            self._db_path.write_text(
                json.dumps([a.to_dict() for a in self._artifacts.values()], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            log.warning(f"Failed to save artifacts: {e}")

    def _make_id(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def add(
        self, type: str, content: str, language: str = "", session_id: str = "", metadata: Optional[Dict] = None
    ) -> Artifact:
        """Add an artifact."""
        aid = self._make_id(content)
        a = Artifact(id=aid, type=type, language=language, content=content, session_id=session_id, metadata=metadata)
        self._artifacts[aid] = a
        self._save()
        return a

    def get(self, artifact_id: str) -> Optional[Artifact]:
        return self._artifacts.get(artifact_id)

    def list_all(self, limit: int = 50) -> List[Artifact]:
        arts = sorted(self._artifacts.values(), key=lambda a: a.created_at, reverse=True)
        return arts[:limit]

    def remove(self, artifact_id: str) -> bool:
        if artifact_id in self._artifacts:
            del self._artifacts[artifact_id]
            self._save()
            return True
        return False

    def export_all(self) -> str:
        """Export all artifacts as JSON string."""
        return json.dumps([a.to_dict() for a in self._artifacts.values()], ensure_ascii=False, indent=2)

    def detect_and_save(self, text: str, session_id: str = "") -> List[Artifact]:
        """Auto-detect artifacts in text and save them."""
        saved = []

        # Code blocks
        for m in _CODE_BLOCK_RE.finditer(text):
            lang = m.group(1) or "text"
            code = m.group(2).strip()
            if len(code) > 20:  # skip trivial snippets
                a = self.add(ArtifactType.CODE, code, language=lang, session_id=session_id)
                saved.append(a)

        # JSON objects/arrays (only if no code blocks caught them)
        for m in _JSON_RE.finditer(text):
            candidate = m.group(1).strip()
            try:
                json.loads(candidate)
                if len(candidate) > 30:
                    a = self.add(ArtifactType.JSON, candidate, language="json", session_id=session_id)
                    saved.append(a)
            except (json.JSONDecodeError, ValueError):
                pass

        # Markdown documents (headings + substantial content)
        for m in _MD_DOC_RE.finditer(text):
            doc = m.group(1).strip()
            if len(doc) > 100:
                a = self.add(ArtifactType.MARKDOWN, doc, language="markdown", session_id=session_id)
                saved.append(a)

        return saved

    @property
    def count(self) -> int:
        return len(self._artifacts)


# Singleton
artifact_manager = ArtifactManager()


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def handle_artifacts_command(cmd: str, session=None, **kw) -> str:
    """Handle /artifacts list|get|export."""
    parts = cmd.strip().split()
    sub = parts[1] if len(parts) > 1 else "list"

    if sub == "list":
        arts = artifact_manager.list_all()
        if not arts:
            return "📦 No artifacts saved yet."
        lines = ["**Artifacts:**\n"]
        for a in arts:
            lines.append(f"• `{a.id}` [{a.type}] {a.language} — {a.preview}")
        return "\n".join(lines)

    if sub == "get":
        if len(parts) < 3:
            return "❌ Usage: `/artifacts get <id>`"
        art = artifact_manager.get(parts[2])
        if not art:
            return f"❌ Artifact `{parts[2]}` not found"
        return f"**Artifact {art.id}** [{art.type}] {art.language}\n```{art.language}\n{art.content}\n```"

    if sub == "export":
        export = artifact_manager.export_all()
        return f"```json\n{export}\n```"

    return "❌ Usage: `/artifacts list|get <id>|export`"


def register_commands(router) -> None:
    """Register /artifacts commands."""
    router.register_prefix("/artifacts", handle_artifacts_command)


def register_tools(registry_module=None) -> None:
    """Register artifact tools."""
    try:
        from salmalm.tools.tool_registry import register_dynamic

        register_dynamic(
            "artifacts_list",
            lambda args: handle_artifacts_command("/artifacts list"),
            {
                "name": "artifacts_list",
                "description": "List saved conversation artifacts",
                "input_schema": {"type": "object", "properties": {}},
            },
        )
    except Exception as e:
        log.warning(f"Failed to register artifact tools: {e}")
