"""Centralized configuration manager for SalmAlm.

중앙집중 설정 관리자 — 각 모듈의 _load_config/_save_config를 통합합니다.
"""
import json
from pathlib import Path


class ConfigManager:
    """중앙집중 설정 관리자."""

    BASE_DIR = Path.home() / '.salmalm'

    @classmethod
    def load(cls, name: str, defaults: dict = None) -> dict:
        """설정 파일 로드. name='mood' → ~/.salmalm/mood.json"""
        path = cls.BASE_DIR / f'{name}.json'
        if path.exists():
            try:
                with open(path, encoding='utf-8') as f:
                    config = json.load(f)
                if defaults:
                    merged = {**defaults, **config}
                    return merged
                return config
            except (json.JSONDecodeError, OSError):
                pass
        return dict(defaults) if defaults else {}

    @classmethod
    def save(cls, name: str, config: dict) -> None:
        """설정 파일 저장."""
        cls.BASE_DIR.mkdir(parents=True, exist_ok=True)
        path = cls.BASE_DIR / f'{name}.json'
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    @classmethod
    def get(cls, name: str, key: str, default=None):
        """단일 키 조회."""
        config = cls.load(name)
        return config.get(key, default)

    @classmethod
    def set(cls, name: str, key: str, value) -> None:
        """단일 키 설정."""
        config = cls.load(name)
        config[key] = value
        cls.save(name, config)

    @classmethod
    def exists(cls, name: str) -> bool:
        return (cls.BASE_DIR / f'{name}.json').exists()

    @classmethod
    def delete(cls, name: str) -> bool:
        path = cls.BASE_DIR / f'{name}.json'
        if path.exists():
            path.unlink()
            return True
        return False

    @classmethod
    def list_configs(cls) -> list:
        """모든 설정 파일 목록."""
        if not cls.BASE_DIR.exists():
            return []
        return [f.stem for f in cls.BASE_DIR.glob('*.json')]

    @classmethod
    def migrate(cls, name: str) -> bool:
        """설정 파일 마이그레이션 실행."""
        config = cls.load(name)
        current_version = config.get('_version', 0)
        migrated = False
        for migration in CONFIG_MIGRATIONS:
            if migration['version'] > current_version:
                config = migration['migrate'](config)
                config['_version'] = migration['version']
                migrated = True
        if migrated:
            cls.save(name, config)
        return migrated


# ── Config Migrations ──

def _migrate_v1(config: dict) -> dict:
    """routing.json → channels.json 통합."""
    # If routing keys exist at top level, nest them under byChannel
    if 'simple' in config or 'moderate' in config or 'complex' in config:
        routing = {}
        for k in ('simple', 'moderate', 'complex'):
            if k in config:
                routing[k] = config.pop(k)
        config.setdefault('routing', routing)
    return config


def _migrate_v2(config: dict) -> dict:
    """heartbeat.json active_hours 추가."""
    # Ensure active_hours defaults exist
    config.setdefault('active_hours', {'start': '08:00', 'end': '24:00'})
    config.setdefault('timezone', 'Asia/Seoul')
    return config


CONFIG_MIGRATIONS = [
    {
        'version': 1,
        'description': 'routing.json → channels.json 통합',
        'migrate': _migrate_v1,
    },
    {
        'version': 2,
        'description': 'heartbeat.json active_hours 추가',
        'migrate': _migrate_v2,
    },
]
