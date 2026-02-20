"""Tests for SalmAlm Doctor self-diagnosis tool."""
import json
import tempfile
from pathlib import Path
import pytest
from salmalm.features.doctor import Doctor, doctor, _status


def test_status_ok():
    s = _status(True, 'all good')
    assert s['status'] == 'ok'
    assert s['message'] == 'all good'


def test_status_issue():
    s = _status(False, 'bad', fixable=True, issue_id='test')
    assert s['status'] == 'issue'
    assert s['fixable'] is True
    assert s['issue_id'] == 'test'


def test_check_disk_space():
    d = Doctor()
    result = d.check_disk_space()
    assert result['status'] == 'ok'
    assert 'GB' in result['message']


def test_check_port_availability():
    d = Doctor()
    result = d.check_port_availability()
    assert result['status'] == 'ok'


def test_check_database_integrity_no_db():
    d = Doctor()
    result = d.check_database_integrity()
    # May or may not find dbs, but shouldn't crash
    assert 'status' in result


def test_check_config_integrity():
    d = Doctor()
    result = d.check_config_integrity()
    assert 'status' in result


def test_run_all():
    d = Doctor()
    results = d.run_all()
    assert len(results) == 8
    assert all('status' in r for r in results)


def test_repair_missing_dir():
    d = Doctor()
    # Just test that repair doesn't crash
    result = d.repair('nonexistent_issue')
    assert result is False


def test_format_report():
    d = Doctor()
    report = d.format_report()
    assert '🏥' in report
    assert 'checks passed' in report


def test_singleton():
    assert doctor is not None
    assert isinstance(doctor, Doctor)
