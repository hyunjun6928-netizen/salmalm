"""Centralized configuration manager for SalmAlm.

중앙집중 설정 관리자 — 단일 진실 소스(Single Source of Truth).
우선순위: CLI args > 환경변수 > config file > constants.py defaults
"""

import json
import logging
import os
import tempfile
from salmalm.constants import DATA_DIR

log = logging.getLogger(__name__)


# Runtime CLI overrides (populated by __main__ / entry points)
_cli_overrides: dict = {}


def set_cli_overrides(overrides: dict) -> None:
    """Set CLI argument overrides (called at startup)."""
    _cli_overrides.update(overrides)


class ConfigManager:
    """중앙집중 설정 관리자.

    Resolution order for ``resolve()``:
      1. CLI args (``_cli_overrides``)
      2. Environment variables (``SALMALM_<NAME>_<KEY>``)
      3. Config file (``~/.salmalm/<name>.json``)
      4. Caller-supplied *defaults* (typically from ``constants.py``)
    """

    BASE_DIR = DATA_DIR

    @classmethod
    def load(cls, name: str, defaults: dict = None) -> dict:
        """설정 파일 로드. name='mood' → ~/.salmalm/mood.json"""
        path = cls.BASE_DIR / f"{name}.json"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    config = json.load(f)
                if defaults:
                    merged = {**defaults, **config}
                    return merged
                return config
            except json.JSONDecodeError as e:
                log.warning("[CONFIG] Corrupt JSON in %s.json: %s — falling back to defaults", name, e)
            except OSError as e:
                log.warning("[CONFIG] Cannot read %s.json: %s — falling back to defaults", name, e)
        return dict(defaults) if defaults else {}

    @classmethod
    def save(cls, name: str, config: dict) -> None:
        """설정 파일 저장 (원자적 write — tempfile + fsync + rename).

        Prevents config file corruption if the process is killed during write.
        """
        cls.BASE_DIR.mkdir(parents=True, exist_ok=True)
        path = cls.BASE_DIR / f"{name}.json"
        tmp_fd, tmp_path = tempfile.mkstemp(dir=cls.BASE_DIR, suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @classmethod
    def resolve(cls, name: str, key: str, default=None):
        """Resolve a single config value with full priority chain.

        1. CLI args  2. Env var ``SALMALM_<NAME>_<KEY>``  3. Config file  4. *default*
        """
        # 1. CLI overrides
        cli_key = f"{name}.{key}"
        if cli_key in _cli_overrides:
            return _cli_overrides[cli_key]

        # 2. Environment variable
        env_key = f"SALMALM_{name.upper()}_{key.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            # Only attempt JSON parse if value looks structured — avoids exception
            # overhead on plain strings like SALMALM_FOO=hello (fired on every lookup).
            _first = env_val[0] if env_val else ""
            if _first in ('{', '[', '"') or _first.lstrip('-').isdigit() or env_val in ('true', 'false', 'null'):
                try:
                    return json.loads(env_val)
                except (json.JSONDecodeError, ValueError):
                    pass
            return env_val

        # 3. Config file
        config = cls.load(name)
        if key in config:
            return config[key]

        # 4. Caller-supplied default (constants.py value)
        return default

    @classmethod
    def get(cls, name: str, key: str, default=None):
        """단일 키 조회 (resolve 사용)."""
        return cls.resolve(name, key, default)

    @classmethod
    def set(cls, name: str, key: str, value: str) -> None:
        """단일 키 설정."""
        config = cls.load(name)
        config[key] = value
        cls.save(name, config)

    @classmethod
    def exists(cls, name: str) -> bool:
        """Exists."""
        return (cls.BASE_DIR / f"{name}.json").exists()

    @classmethod
    def delete(cls, name: str) -> bool:
        """Delete."""
        path = cls.BASE_DIR / f"{name}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    @classmethod
    def list_configs(cls) -> list:
        """모든 설정 파일 목록."""
        if not cls.BASE_DIR.exists():
            return []
        return [f.stem for f in cls.BASE_DIR.glob("*.json")]

    @classmethod
    def migrate(cls, name: str) -> bool:
        """설정 파일 마이그레이션 실행."""
        config = cls.load(name)
        current_version = config.get("_version", 0)
        migrated = False
        for migration in CONFIG_MIGRATIONS:
            if migration["version"] > current_version:
                config = migration["migrate"](config)
                config["_version"] = migration["version"]
                migrated = True
        if migrated:
            cls.save(name, config)
        return migrated


# ── Config Migrations ──


def _migrate_v1(config: dict) -> dict:
    """routing.json → channels.json 통합."""
    # If routing keys exist at top level, nest them under byChannel
    if "simple" in config or "moderate" in config or "complex" in config:
        routing = {}
        for k in ("simple", "moderate", "complex"):
            if k in config:
                routing[k] = config.pop(k)
        config.setdefault("routing", routing)
    return config


def _migrate_v2(config: dict) -> dict:
    """heartbeat.json active_hours 추가."""
    # Ensure active_hours defaults exist
    config.setdefault("active_hours", {"start": "08:00", "end": "24:00"})
    config.setdefault("timezone", "Asia/Seoul")
    return config


CONFIG_MIGRATIONS = [
    {
        "version": 1,
        "description": "routing.json → channels.json 통합",
        "migrate": _migrate_v1,
    },
    {
        "version": 2,
        "description": "heartbeat.json active_hours 추가",
        "migrate": _migrate_v2,
    },
]
