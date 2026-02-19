"""Tests for config migration system."""
import json
import pytest
from pathlib import Path
from salmalm.config_manager import ConfigManager, CONFIG_MIGRATIONS, _migrate_v1, _migrate_v2


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ConfigManager, 'BASE_DIR', tmp_path)
    return tmp_path


def test_migrate_v1_routing_keys(config_dir):
    config = {'simple': 'haiku', 'moderate': 'sonnet', 'complex': 'opus', 'other': 'val'}
    result = _migrate_v1(config)
    assert 'simple' not in result
    assert result['routing'] == {'simple': 'haiku', 'moderate': 'sonnet', 'complex': 'opus'}
    assert result['other'] == 'val'


def test_migrate_v1_no_routing_keys(config_dir):
    config = {'foo': 'bar'}
    result = _migrate_v1(config)
    assert result == {'foo': 'bar'}


def test_migrate_v2_adds_active_hours():
    config = {}
    result = _migrate_v2(config)
    assert 'active_hours' in result
    assert result['active_hours']['start'] == '08:00'
    assert result['timezone'] == 'Asia/Seoul'


def test_full_migration(config_dir):
    # Write a v0 config
    ConfigManager.save('channels', {'simple': 'haiku'})
    migrated = ConfigManager.migrate('channels')
    assert migrated is True
    config = ConfigManager.load('channels')
    assert config['_version'] == 2
    assert 'active_hours' in config


def test_no_migration_needed(config_dir):
    ConfigManager.save('channels', {'_version': 2, 'data': 'ok'})
    migrated = ConfigManager.migrate('channels')
    assert migrated is False


def test_migration_idempotent(config_dir):
    ConfigManager.save('channels', {'simple': 'haiku'})
    ConfigManager.migrate('channels')
    config1 = ConfigManager.load('channels')
    ConfigManager.migrate('channels')
    config2 = ConfigManager.load('channels')
    assert config1 == config2
