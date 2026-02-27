"""Filesystem path constants."""

from __future__ import annotations

import os as _os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(_os.environ.get("SALMALM_HOME", "") or Path.home() / "SalmAlm")
MEMORY_DIR = DATA_DIR / "memory"
WORKSPACE_DIR = DATA_DIR
SOUL_FILE = DATA_DIR / "soul.md"
AGENTS_FILE = DATA_DIR / "agents.md"
MEMORY_FILE = DATA_DIR / "memory.md"
USER_FILE = DATA_DIR / "user.md"
TOOLS_FILE = DATA_DIR / "tools.md"
VAULT_FILE = DATA_DIR / ".vault.enc"
AUDIT_DB = DATA_DIR / "audit.db"
MEMORY_DB = DATA_DIR / "memory.db"
CACHE_DB = DATA_DIR / "cache.db"
LOG_FILE = DATA_DIR / "salmalm.log"
