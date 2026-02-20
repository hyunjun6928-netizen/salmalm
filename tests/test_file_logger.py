"""Tests for structured file logger."""
import json
import tempfile
from pathlib import Path
import pytest
from salmalm.utils.file_logger import FileLogger


@pytest.fixture
def logger(tmp_path):
    return FileLogger(log_dir=tmp_path / 'logs')


def test_log_creates_file(logger):
    logger.log('INFO', 'test', 'hello world')
    files = list(logger.LOG_DIR.glob('salmalm-*.log'))
    assert len(files) == 1


def test_log_json_format(logger):
    logger.log('ERROR', 'auth', 'login failed', user='test')
    files = list(logger.LOG_DIR.glob('salmalm-*.log'))
    line = files[0].read_text().strip()
    entry = json.loads(line)
    assert entry['level'] == 'ERROR'
    assert entry['category'] == 'auth'
    assert entry['message'] == 'login failed'
    assert entry['user'] == 'test'
    assert 'ts' in entry


def test_tail(logger):
    for i in range(10):
        logger.log('INFO', 'test', f'message {i}')
    entries = logger.tail(lines=5)
    assert len(entries) == 5


def test_tail_with_level_filter(logger):
    logger.log('INFO', 'test', 'info msg')
    logger.log('ERROR', 'test', 'error msg')
    entries = logger.tail(lines=50, level='ERROR')
    assert len(entries) == 1
    assert entries[0]['level'] == 'ERROR'


def test_search(logger):
    logger.log('INFO', 'auth', 'user logged in')
    logger.log('INFO', 'system', 'disk check ok')
    results = logger.search('logged in')
    assert len(results) == 1
    assert 'logged in' in results[0]['message']


def test_cleanup(logger):
    # Create an old log file
    old_file = logger.LOG_DIR / 'salmalm-2020-01-01.log'
    old_file.write_text('{"test": true}\n')
    removed = logger.cleanup(retain_days=30)
    assert removed == 1
    assert not old_file.exists()


def test_cleanup_keeps_recent(logger):
    logger.log('INFO', 'test', 'recent')
    removed = logger.cleanup(retain_days=30)
    assert removed == 0
    files = list(logger.LOG_DIR.glob('salmalm-*.log'))
    assert len(files) == 1
