"""SalmAlm Agent Migration — Export/Import agent state (인격/기억/설정 이동).

Export: Pack agent personality, memory, config, sessions, data into a ZIP file.
Import: Restore agent state from a ZIP file with conflict resolution.
Quick Sync: Lightweight JSON export/import of core settings.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

from salmalm.constants import VERSION, BASE_DIR, MEMORY_DIR, VAULT_FILE, KST
from salmalm.security.crypto import log

# ── Paths ──────────────────────────────────────────────────────
_HOME_DIR = Path.home() / ".salmalm"
_PERSONAS_DIR = _HOME_DIR / "personas"
_MEMORY_HOME = _HOME_DIR / "memory"
_SESSIONS_DIR = _HOME_DIR / "sessions"
_PLUGINS_DIR = _HOME_DIR / "plugins"
_SKILLS_DIR = _HOME_DIR / "skills"

# Config files in ~/.salmalm/
_CONFIG_FILES = {
    "routing.json": _HOME_DIR / "routing.json",
    "failover.json": _HOME_DIR / "failover.json",
    "sla.json": _HOME_DIR / "sla.json",
    "briefing.json": _HOME_DIR / "briefing.json",
    "routines.json": _HOME_DIR / "routines.json",
    "hooks.json": _HOME_DIR / "hooks.json",
}

# Data files (SQLite DBs in BASE_DIR or ~/.salmalm/)
_DATA_FILES = {
    "notes.db": _HOME_DIR / "notes.db",
    "expenses.db": _HOME_DIR / "expenses.db",
    "bookmarks.db": _HOME_DIR / "bookmarks.db",
}

# Also check BASE_DIR for data files
_DATA_FILES_ALT = {
    "notes.db": BASE_DIR / "notes.db",
    "expenses.db": BASE_DIR / "expenses.db",
    "bookmarks.db": BASE_DIR / "bookmarks.db",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now_kst() -> str:
    return datetime.now(KST).isoformat()


def _get_agent_name() -> str:
    """Get agent name from SOUL.md or default."""
    try:
        from salmalm.core.prompt import get_user_soul

        soul = get_user_soul()
        if soul:
            for line in soul.split("\n")[:5]:
                if line.startswith("#"):
                    return line.lstrip("#").strip()
        return "SalmAlm Agent"
    except Exception:
        return "SalmAlm Agent"


# ============================================================
# AgentExporter — 에이전트 내보내기
# ============================================================


class AgentExporter:
    """Export agent state to a ZIP file."""

    def __init__(self, include_vault: bool = False, include_sessions: bool = True, include_data: bool = True):
        self.include_vault = include_vault
        self.include_sessions = include_sessions
        self.include_data = include_data
        self._includes: List[str] = []

    def export_agent(self) -> bytes:
        """Export agent state to ZIP bytes."""
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            self._includes = []

            # 1. SOUL.md
            self._export_soul(zf)

            # 2. Personas
            self._export_personas(zf)

            # 3. Memory
            self._export_memory(zf)

            # 4. Sessions
            if self.include_sessions:
                self._export_sessions(zf)

            # 5. Config
            self._export_config(zf)

            # 6. Data (notes, expenses, bookmarks)
            if self.include_data:
                self._export_data(zf)

            # 7. Plugins
            self._export_plugins(zf)

            # 8. Skills
            self._export_skills(zf)

            # 9. Vault (optional)
            if self.include_vault:
                self._export_vault(zf)

            # Manifest (last — includes checksum placeholder)
            manifest = {
                "version": VERSION,
                "exported_at": _now_kst(),
                "includes": self._includes,
                "checksum": "",  # filled below
                "agent_name": _get_agent_name(),
            }
            manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)
            zf.writestr("manifest.json", manifest_json)

        zip_bytes = buf.getvalue()

        # Compute checksum and re-inject into manifest
        checksum = f"sha256:{_sha256_bytes(zip_bytes)}"
        manifest["checksum"] = checksum
        manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)

        # Rewrite ZIP with updated manifest
        buf2 = BytesIO()
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zr:
            with zipfile.ZipFile(buf2, "w", zipfile.ZIP_DEFLATED) as zw:
                for item in zr.namelist():
                    if item == "manifest.json":
                        zw.writestr("manifest.json", manifest_json)
                    else:
                        zw.writestr(item, zr.read(item))

        log.info(f"[EXPORT] Agent exported: {len(self._includes)} sections, {len(buf2.getvalue()) // 1024}KB")
        return buf2.getvalue()

    def _export_soul(self, zf: zipfile.ZipFile):
        """Export SOUL.md."""
        try:
            from salmalm.core.prompt import get_user_soul, USER_SOUL_FILE  # noqa: F401

            soul = get_user_soul()
            if soul:
                zf.writestr("soul/SOUL.md", soul)
                self._includes.append("soul")
        except Exception as e:
            log.warning(f"[EXPORT] Soul export skipped: {e}")

    def _export_personas(self, zf: zipfile.ZipFile):
        """Export persona files."""
        if not _PERSONAS_DIR.exists():
            return
        count = 0
        for f in _PERSONAS_DIR.glob("*.md"):
            try:
                zf.writestr(f"personas/{f.name}", f.read_text(encoding="utf-8"))
                count += 1
            except Exception:
                pass
        if count:
            self._includes.append("personas")

    def _export_memory(self, zf: zipfile.ZipFile):
        """Export memory files from both locations."""
        count = 0
        for mem_dir in [MEMORY_DIR, _MEMORY_HOME]:
            if not mem_dir or not mem_dir.exists():
                continue
            for f in mem_dir.rglob("*.md"):
                try:
                    rel = f.relative_to(mem_dir)
                    zf.writestr(f"memory/{rel}", f.read_text(encoding="utf-8"))
                    count += 1
                except Exception:
                    pass
        # Also export MEMORY.md from BASE_DIR
        mem_file = BASE_DIR / "MEMORY.md"
        if mem_file.exists():
            try:
                zf.writestr("memory/MEMORY.md", mem_file.read_text(encoding="utf-8"))
                count += 1
            except Exception:
                pass
        if count:
            self._includes.append("memory")

    def _export_sessions(self, zf: zipfile.ZipFile):
        """Export session data from SQLite."""
        try:
            from salmalm.core import _get_db

            conn = _get_db()
            rows = conn.execute("SELECT session_id, messages, updated_at FROM session_store").fetchall()
            for r in rows:
                sid, msgs_json, updated = r[0], r[1], r[2]
                session_data = {
                    "session_id": sid,
                    "messages": json.loads(msgs_json) if msgs_json else [],
                    "updated_at": updated,
                }
                zf.writestr(f"sessions/{sid}.json", json.dumps(session_data, ensure_ascii=False, indent=1))
            if rows:
                self._includes.append("sessions")
        except Exception as e:
            log.warning(f"[EXPORT] Sessions export skipped: {e}")

    def _export_config(self, zf: zipfile.ZipFile):
        """Export configuration files."""
        count = 0
        for name, path in _CONFIG_FILES.items():
            if path.exists():
                try:
                    zf.writestr(f"config/{name}", path.read_text(encoding="utf-8"))
                    count += 1
                except Exception:
                    pass
        if count:
            self._includes.append("config")

    def _export_data(self, zf: zipfile.ZipFile):
        """Export data files (SQLite DBs)."""
        count = 0
        for name in _DATA_FILES:
            path = _DATA_FILES[name]
            if not path.exists():
                path = _DATA_FILES_ALT.get(name)
            if path and path.exists():
                try:
                    zf.writestr(f"data/{name}", path.read_bytes())
                    count += 1
                except Exception:
                    pass
        if count:
            self._includes.append("data")

    def _export_plugins(self, zf: zipfile.ZipFile):
        """Export installed plugins."""
        if not _PLUGINS_DIR.exists():
            return
        count = 0
        for plugin_dir in _PLUGINS_DIR.iterdir():
            if plugin_dir.is_dir():
                for f in plugin_dir.rglob("*"):
                    if f.is_file():
                        try:
                            rel = f.relative_to(_PLUGINS_DIR)
                            zf.writestr(f"plugins/{rel}", f.read_bytes())
                            count += 1
                        except Exception:
                            pass
        if count:
            self._includes.append("plugins")

    def _export_skills(self, zf: zipfile.ZipFile):
        """Export custom skills."""
        if not _SKILLS_DIR.exists():
            return
        count = 0
        for skill_dir in _SKILLS_DIR.iterdir():
            if skill_dir.is_dir():
                for f in skill_dir.rglob("*"):
                    if f.is_file():
                        try:
                            rel = f.relative_to(_SKILLS_DIR)
                            zf.writestr(f"skills/{rel}", f.read_bytes())
                            count += 1
                        except Exception:
                            pass
        if count:
            self._includes.append("skills")

    def _export_vault(self, zf: zipfile.ZipFile):
        """Export encrypted vault file."""
        if VAULT_FILE.exists():
            try:
                zf.writestr("vault/vault.enc", VAULT_FILE.read_bytes())
                self._includes.append("vault")
            except Exception:
                pass


# ============================================================
# AgentImporter — 에이전트 가져오기
# ============================================================


class ImportResult:
    """Result of an import operation."""

    def __init__(self):
        self.ok: bool = True
        self.imported: List[str] = []
        self.skipped: List[str] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.manifest: Dict[str, Any] = {}

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "imported": self.imported,
            "skipped": self.skipped,
            "errors": self.errors,
            "warnings": self.warnings,
            "manifest": self.manifest,
        }

    def summary(self) -> str:
        """Human-readable summary / 사람이 읽을 수 있는 요약."""
        parts = []
        if self.imported:
            parts.append(f"✅ Imported: {', '.join(self.imported)}")
        if self.skipped:
            parts.append(f"⏭️ Skipped: {', '.join(self.skipped)}")
        if self.warnings:
            parts.append(f"⚠️ Warnings: {'; '.join(self.warnings)}")
        if self.errors:
            parts.append(f"❌ Errors: {'; '.join(self.errors)}")
        return "\n".join(parts) or "✅ Import complete / 가져오기 완료"


class AgentImporter:
    """Import agent state from a ZIP file."""

    # conflict_mode: 'overwrite' | 'merge' | 'skip'
    def __init__(self, conflict_mode: str = "overwrite"):
        self.conflict_mode = conflict_mode

    def preview(self, zip_data: bytes) -> Dict[str, Any]:
        """Preview what's in the ZIP without importing.
        ZIP 파일 내용을 가져오기 전에 미리보기."""
        try:
            zf = zipfile.ZipFile(BytesIO(zip_data), "r")
        except zipfile.BadZipFile:
            return {"ok": False, "error": "Invalid ZIP file / 잘못된 ZIP 파일"}

        manifest = {}
        if "manifest.json" in zf.namelist():
            try:
                manifest = json.loads(zf.read("manifest.json"))
            except Exception:
                pass

        sections = set()
        files = []
        for name in zf.namelist():
            if name == "manifest.json":
                continue
            section = name.split("/")[0]
            sections.add(section)
            files.append(name)

        return {
            "ok": True,
            "manifest": manifest,
            "sections": sorted(sections),
            "file_count": len(files),
            "files": files[:50],  # Limit preview
            "size_bytes": len(zip_data),
        }

    def import_agent(self, zip_data: bytes) -> ImportResult:
        """Import agent state from ZIP bytes."""
        result = ImportResult()

        try:
            zf = zipfile.ZipFile(BytesIO(zip_data), "r")
        except zipfile.BadZipFile:
            result.ok = False
            result.errors.append("Invalid ZIP file / 잘못된 ZIP 파일")
            return result

        # Read and validate manifest
        if "manifest.json" in zf.namelist():
            try:
                result.manifest = json.loads(zf.read("manifest.json"))
            except Exception:
                result.warnings.append("Could not parse manifest.json")
        else:
            result.warnings.append("No manifest.json found / manifest.json 없음")

        # Version check
        export_ver = result.manifest.get("version", "0.0.0")
        try:
            from packaging.version import Version

            if Version(export_ver) > Version(VERSION):
                result.warnings.append(f"Export version ({export_ver}) is newer than current ({VERSION})")
        except Exception:
            # No packaging module — simple string comparison
            if export_ver > VERSION:
                result.warnings.append(f"Export version ({export_ver}) is newer than current ({VERSION})")

        # Import each section
        names = zf.namelist()
        if any(n.startswith("soul/") for n in names):
            self._import_soul(zf, result)
        if any(n.startswith("personas/") for n in names):
            self._import_personas(zf, result)
        if any(n.startswith("memory/") for n in names):
            self._import_memory(zf, result)
        if any(n.startswith("sessions/") for n in names):
            self._import_sessions(zf, result)
        if any(n.startswith("config/") for n in names):
            self._import_config(zf, result)
        if any(n.startswith("data/") for n in names):
            self._import_data(zf, result)
        if any(n.startswith("plugins/") for n in names):
            self._import_plugins(zf, result)
        if any(n.startswith("skills/") for n in names):
            self._import_skills(zf, result)
        if any(n.startswith("vault/") for n in names):
            self._import_vault(zf, result)

        zf.close()
        log.info(f"[IMPORT] Agent imported: {result.imported}, skipped: {result.skipped}")
        return result

    def _import_soul(self, zf: zipfile.ZipFile, result: ImportResult):
        try:
            soul_content = zf.read("soul/SOUL.md").decode("utf-8")
            from salmalm.core.prompt import set_user_soul

            set_user_soul(soul_content)
            result.imported.append("soul")
        except Exception as e:
            result.errors.append(f"soul: {e}")

    def _import_personas(self, zf: zipfile.ZipFile, result: ImportResult):
        try:
            _PERSONAS_DIR.mkdir(parents=True, exist_ok=True)
            count = 0
            for name in zf.namelist():
                if name.startswith("personas/") and name.endswith(".md"):
                    fname = name.split("/")[-1]
                    dest = _PERSONAS_DIR / fname
                    if dest.exists() and self.conflict_mode == "skip":
                        continue
                    dest.write_text(zf.read(name).decode("utf-8"), encoding="utf-8")
                    count += 1
            if count:
                result.imported.append(f"personas ({count})")
        except Exception as e:
            result.errors.append(f"personas: {e}")

    def _import_memory(self, zf: zipfile.ZipFile, result: ImportResult):
        try:
            count = 0
            for name in zf.namelist():
                if not name.startswith("memory/") or not name.endswith(".md"):
                    continue
                fname = name[len("memory/") :]
                if not fname:
                    continue
                # MEMORY.md goes to BASE_DIR
                if fname == "MEMORY.md":
                    dest = BASE_DIR / "MEMORY.md"
                else:
                    dest = MEMORY_DIR / fname
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() and self.conflict_mode == "skip":
                    continue
                if dest.exists() and self.conflict_mode == "merge":
                    # Append new content
                    existing = dest.read_text(encoding="utf-8")
                    new_content = zf.read(name).decode("utf-8")
                    if new_content not in existing:
                        dest.write_text(existing + "\n\n---\n\n" + new_content, encoding="utf-8")
                        count += 1
                else:
                    dest.write_text(zf.read(name).decode("utf-8"), encoding="utf-8")
                    count += 1
            if count:
                result.imported.append(f"memory ({count})")
        except Exception as e:
            result.errors.append(f"memory: {e}")

    def _import_sessions(self, zf: zipfile.ZipFile, result: ImportResult):
        try:
            from salmalm.core import _get_db

            conn = _get_db()
            count = 0
            for name in zf.namelist():
                if not name.startswith("sessions/") or not name.endswith(".json"):
                    continue
                data = json.loads(zf.read(name))
                sid = data.get("session_id", "")
                msgs = json.dumps(data.get("messages", []), ensure_ascii=False)
                updated = data.get("updated_at", _now_kst())
                # Check existing
                existing = conn.execute("SELECT session_id FROM session_store WHERE session_id=?", (sid,)).fetchone()
                if existing and self.conflict_mode == "skip":
                    continue
                if existing:
                    conn.execute(
                        "UPDATE session_store SET messages=?, updated_at=? WHERE session_id=?", (msgs, updated, sid)
                    )
                else:
                    conn.execute(
                        "INSERT INTO session_store (session_id, messages, updated_at) VALUES (?,?,?)",
                        (sid, msgs, updated),
                    )
                count += 1
            conn.commit()
            if count:
                result.imported.append(f"sessions ({count})")
        except Exception as e:
            result.errors.append(f"sessions: {e}")

    def _import_config(self, zf: zipfile.ZipFile, result: ImportResult):
        try:
            _HOME_DIR.mkdir(parents=True, exist_ok=True)
            count = 0
            for name in zf.namelist():
                if not name.startswith("config/"):
                    continue
                fname = name.split("/")[-1]
                if fname in _CONFIG_FILES:
                    dest = _CONFIG_FILES[fname]
                    dest.write_text(zf.read(name).decode("utf-8"), encoding="utf-8")
                    count += 1
            if count:
                result.imported.append(f"config ({count})")
        except Exception as e:
            result.errors.append(f"config: {e}")

    def _import_data(self, zf: zipfile.ZipFile, result: ImportResult):
        try:
            count = 0
            for name in zf.namelist():
                if not name.startswith("data/"):
                    continue
                fname = name.split("/")[-1]
                if fname in _DATA_FILES:
                    dest = _DATA_FILES[fname]
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.exists() and self.conflict_mode == "merge":
                        # For SQLite, merge is complex — just overwrite with warning
                        result.warnings.append(f"{fname}: merge not supported for DB files, overwriting")
                    dest.write_bytes(zf.read(name))
                    count += 1
            if count:
                result.imported.append(f"data ({count})")
        except Exception as e:
            result.errors.append(f"data: {e}")

    def _import_plugins(self, zf: zipfile.ZipFile, result: ImportResult):
        try:
            _PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
            count = 0
            for name in zf.namelist():
                if not name.startswith("plugins/") or name.endswith("/"):
                    continue
                rel = name[len("plugins/") :]
                dest = _PLUGINS_DIR / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(name))
                count += 1
            if count:
                result.imported.append(f"plugins ({count} files)")
        except Exception as e:
            result.errors.append(f"plugins: {e}")

    def _import_skills(self, zf: zipfile.ZipFile, result: ImportResult):
        try:
            _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
            count = 0
            for name in zf.namelist():
                if not name.startswith("skills/") or name.endswith("/"):
                    continue
                rel = name[len("skills/") :]
                dest = _SKILLS_DIR / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(name))
                count += 1
            if count:
                result.imported.append(f"skills ({count} files)")
        except Exception as e:
            result.errors.append(f"skills: {e}")

    def _import_vault(self, zf: zipfile.ZipFile, result: ImportResult):
        if "vault/vault.enc" not in zf.namelist():
            return
        if VAULT_FILE.exists() and self.conflict_mode == "skip":
            result.skipped.append("vault")
            return
        try:
            VAULT_FILE.write_bytes(zf.read("vault/vault.enc"))
            result.imported.append("vault")
            result.warnings.append(
                "Vault imported — you may need to unlock with the original password / "
                "볼트를 가져왔습니다 — 원래 비밀번호로 잠금해제가 필요할 수 있습니다"
            )
        except Exception as e:
            result.errors.append(f"vault: {e}")


# ============================================================
# Quick Sync — 빠른 동기화 (경량)
# ============================================================


def quick_sync_export() -> dict:
    """Export core agent state as lightweight JSON.
    핵심 에이전트 상태를 경량 JSON으로 내보내기."""
    data: Dict[str, Any] = {}

    # SOUL.md
    try:
        from salmalm.core.prompt import get_user_soul, get_active_persona

        data["soul"] = get_user_soul() or ""
    except Exception:
        data["soul"] = ""

    # Routing config
    try:
        from salmalm.core.engine import get_routing_config

        data["routing"] = get_routing_config()
    except Exception:
        data["routing"] = {}

    # Active persona
    try:
        from salmalm.core.prompt import get_active_persona  # noqa: F811

        data["persona"] = get_active_persona("default")
    except Exception:
        data["persona"] = "default"

    # Model override
    try:
        from salmalm.core import router

        data["model_override"] = router.force_model or "auto"
    except Exception:
        data["model_override"] = "auto"

    # Failover config
    try:
        from salmalm.core.engine import get_failover_config

        data["failover"] = get_failover_config()
    except Exception:
        data["failover"] = {}

    data["version"] = VERSION
    data["exported_at"] = _now_kst()

    return data


def quick_sync_import(data: dict):
    """Import core agent state from lightweight JSON.
    경량 JSON에서 핵심 에이전트 상태를 가져오기."""
    # SOUL.md
    if "soul" in data and data["soul"]:
        try:
            from salmalm.core.prompt import set_user_soul

            set_user_soul(data["soul"])
        except Exception as e:
            log.warning(f"[SYNC] Soul import failed: {e}")

    # Routing config
    if "routing" in data:
        try:
            from salmalm.core.engine import _save_routing_config

            _save_routing_config(data["routing"])
        except Exception as e:
            log.warning(f"[SYNC] Routing import failed: {e}")

    # Failover config
    if "failover" in data:
        try:
            from salmalm.core.engine import save_failover_config

            save_failover_config(data["failover"])
        except Exception as e:
            log.warning(f"[SYNC] Failover import failed: {e}")

    # Model override
    if "model_override" in data:
        try:
            from salmalm.core import router

            override = data["model_override"]
            router.set_force_model(override if override != "auto" else None)
        except Exception:
            pass

    log.info(f"[SYNC] Quick sync imported: {list(data.keys())}")


# ============================================================
# Convenience functions — 편의 함수
# ============================================================


def export_agent(include_vault: bool = False, include_sessions: bool = True, include_data: bool = True) -> bytes:
    """Export agent state to ZIP bytes. Convenience wrapper."""
    exporter = AgentExporter(include_vault=include_vault, include_sessions=include_sessions, include_data=include_data)
    return exporter.export_agent()


def import_agent(zip_data: bytes, conflict_mode: str = "overwrite") -> ImportResult:
    """Import agent state from ZIP bytes. Convenience wrapper."""
    importer = AgentImporter(conflict_mode=conflict_mode)
    return importer.import_agent(zip_data)


def preview_import(zip_data: bytes) -> dict:
    """Preview ZIP contents without importing."""
    importer = AgentImporter()
    return importer.preview(zip_data)


def export_filename() -> str:
    """Generate export filename with date."""
    date_str = datetime.now(KST).strftime("%Y-%m-%d")
    return f"salmalm-agent-export-{date_str}.zip"
