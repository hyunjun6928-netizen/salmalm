"""Skill loading and management."""

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path

log = logging.getLogger(__name__)

from salmalm.constants import WORKSPACE_DIR  # noqa: E402


class SkillLoader:
    """OpenClaw-style skill loader.

    Skills are self-contained folders with SKILL.md + optional scripts.
    SKILL.md uses YAML-like frontmatter:
        ---
        name: my-skill
        description: What this skill does
        metadata: {"openclaw": {"requires": {"bins": ["ffmpeg"]}}}
        ---
        Instructions for the agent...

    Pattern: scan descriptions at startup, read full content on demand.
    Auto-discovery from skills/ directory with gating support.
    """

    _cache: dict = {}
    _last_scan = 0
    _defaults_installed = False

    @classmethod
    def _install_defaults(cls):
        """Copy bundled default skills to workspace on first run."""
        if cls._defaults_installed:
            return
        cls._defaults_installed = True
        skills_dir = WORKSPACE_DIR / "skills"
        skills_dir.mkdir(exist_ok=True)
        import shutil

        pkg_dir = Path(__file__).resolve().parent.parent / "default_skills"
        if not pkg_dir.exists():
            return
        for src in pkg_dir.iterdir():
            if src.is_dir() and (src / "SKILL.md").exists():
                dest = skills_dir / src.name
                if not dest.exists():
                    shutil.copytree(str(src), str(dest))
                    log.info(f"[SKILL] Default skill installed: {src.name}")

    @classmethod
    def _parse_frontmatter(cls, content: str) -> dict:
        """Parse YAML-like frontmatter from SKILL.md (OpenClaw-compatible).

        Supports:
            ---
            name: value
            description: value
            metadata: {"json": "object"}
            ---
        """
        meta = {}
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            # No frontmatter — fall back to heading/paragraph parsing
            return meta

        _in_fm = True  # noqa: F841
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                break
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if key == "metadata":
                    try:
                        meta["metadata"] = json.loads(val)
                    except (json.JSONDecodeError, ValueError):
                        meta["metadata"] = val
                else:
                    meta[key] = val
        return meta

    @classmethod
    def _check_gates(cls, metadata: dict) -> bool:
        """Check if a skill's requirements are met (OpenClaw-style gating).

        Checks: required binaries on PATH, required env vars.
        """
        oc = metadata.get("openclaw", {}) if isinstance(metadata, dict) else {}
        if not oc:
            return True  # No gates = always eligible

        if oc.get("always"):
            return True

        requires = oc.get("requires", {})

        # Check required binaries
        bins = requires.get("bins", [])
        for b in bins:
            if not shutil.which(b):
                return False

        # Check anyBins (at least one must exist)
        any_bins = requires.get("anyBins", [])
        if any_bins and not any(shutil.which(b) for b in any_bins):
            return False

        # Check required env vars
        env_vars = requires.get("env", [])
        for e in env_vars:
            if not os.environ.get(e):
                return False

        return True

    @classmethod
    def scan(cls) -> list:
        """Scan skills directory, return list of available skills.

        OpenClaw pattern: only reads frontmatter (name + description).
        Full SKILL.md content loaded on demand via load().
        """
        cls._install_defaults()
        now = time.time()
        if cls._cache and now - cls._last_scan < 120:
            return list(cls._cache.values())

        skills_dir = WORKSPACE_DIR / "skills"
        if not skills_dir.exists():
            skills_dir.mkdir(exist_ok=True)
            return []

        cls._cache = {}
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                content = skill_md.read_text(encoding="utf-8", errors="replace")
                fm = cls._parse_frontmatter(content)

                name = fm.get("name", skill_dir.name)
                description = fm.get("description", "")

                # Fall back to heading/paragraph parsing if no frontmatter
                if not description:
                    for line in content.splitlines()[:10]:
                        if line.startswith("# "):
                            name = line[2:].strip()
                        elif line.startswith("> ") or (
                            line.strip() and not line.startswith("#") and not line.startswith("---")
                        ):
                            description = line.lstrip("> ").strip()
                            break

                # Gating: check if skill requirements are met
                metadata = fm.get("metadata", {})
                if isinstance(metadata, dict) and not cls._check_gates(metadata):
                    log.info(f"[SKILL] Gated out: {skill_dir.name} (missing requirements)")
                    continue

                cls._cache[skill_dir.name] = {
                    "name": name,
                    "dir_name": skill_dir.name,
                    "description": description,
                    "path": str(skill_md),
                    "size": len(content),
                    "metadata": metadata,
                    "has_scripts": any(skill_dir.glob("*.py")) or any(skill_dir.glob("*.sh")),
                }
            except Exception as e:  # noqa: broad-except
                log.debug(f"Suppressed: {e}")

        cls._last_scan = now  # type: ignore[assignment]
        log.info(f"[SKILL] Skills scanned: {len(cls._cache)} found")
        return list(cls._cache.values())

    @classmethod
    def load(cls, skill_name: str) -> str:
        """Load a skill's SKILL.md content."""
        cls.scan()
        skill = cls._cache.get(skill_name)
        if not skill:
            return None  # type: ignore[return-value]
        try:
            return Path(skill["path"]).read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # noqa: broad-except
            return None  # type: ignore[return-value]

    @classmethod
    def match(cls, user_message: str) -> str:
        """Auto-detect which skill matches the user's request. Returns skill content or None."""
        skills = cls.scan()
        if not skills:
            return None  # type: ignore[return-value]
        msg = user_message.lower()
        best_match = None
        best_score = 0
        for skill in skills:
            desc = skill["description"].lower()
            name = skill["name"].lower()
            # Simple keyword matching against skill description
            desc_words = set(re.findall(r"[\w가-힣]+", desc + " " + name))
            msg_words = set(re.findall(r"[\w가-힣]+", msg))
            overlap = len(desc_words & msg_words)
            if overlap > best_score:
                best_score = overlap
                best_match = skill
        if best_score >= 2:  # At least 2 keyword matches
            content = cls.load(best_match["dir_name"])  # type: ignore[index]
            if content:
                log.info(f"[LOAD] Skill matched: {best_match['name']} (score={best_score})")  # type: ignore[index]
                return content
        return None  # type: ignore[return-value]

    @classmethod
    def install(cls, url: str) -> str:
        """Install a skill from a Git URL or GitHub shorthand (user/repo)."""
        import shutil

        skills_dir = WORKSPACE_DIR / "skills"
        skills_dir.mkdir(exist_ok=True)

        # Support GitHub shorthand: user/repo or user/repo/path
        if not url.startswith("http"):
            parts = url.strip("/").split("/")
            if len(parts) >= 2:
                url = f"https://github.com/{parts[0]}/{parts[1]}.git"

        # Extract repo name for directory
        repo_name = url.rstrip("/").rstrip(".git").split("/")[-1]
        target = skills_dir / repo_name

        if target.exists():
            # Update existing
            result = subprocess.run(["git", "-C", str(target), "pull"], capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                cls._cache.clear()
                cls._last_scan = 0
                return f"📚 Skill updated: {repo_name}\n{result.stdout.strip()}"
            return f"❌ Git pull failed: {result.stderr[:200]}"

        # Fresh clone
        result = subprocess.run(
            ["git", "clone", "--depth=1", url, str(target)], capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return f"❌ Git clone failed: {result.stderr[:200]}"

        # Verify SKILL.md exists
        if not (target / "SKILL.md").exists():
            # Check subdirectories (monorepo with multiple skills)
            found = list(target.glob("*/SKILL.md"))
            if found:
                # Move each skill subfolder to skills/
                installed = []
                for skill_md in found:
                    skill_dir = skill_md.parent
                    dest = skills_dir / skill_dir.name
                    if not dest.exists():
                        shutil.move(str(skill_dir), str(dest))
                        installed.append(skill_dir.name)
                shutil.rmtree(str(target), ignore_errors=True)
                cls._cache.clear()
                cls._last_scan = 0
                return f"📚 Installed {len(installed)} skills: {', '.join(installed)}"
            else:
                shutil.rmtree(str(target), ignore_errors=True)
                return "❌ No SKILL.md found in repository"

        cls._cache.clear()
        cls._last_scan = 0
        return f"📚 Skill installed: {repo_name}"

    @classmethod
    def uninstall(cls, skill_name: str) -> str:
        """Remove a skill directory."""
        import shutil

        target = WORKSPACE_DIR / "skills" / skill_name
        if not target.exists():
            return f"❌ Skill not found: {skill_name}"
        shutil.rmtree(str(target), ignore_errors=True)
        cls._cache.pop(skill_name, None)
        return f"🗑️ Skill removed: {skill_name}"
