"""Tests for Dead Man's Switch."""
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from salmalm.deadman import DeadManSwitch, DEFAULT_CONFIG


@pytest.fixture
def tmp_paths(tmp_path):
    config = tmp_path / "deadman.json"
    state = tmp_path / "deadman_state.json"
    return config, state


@pytest.fixture
def switch(tmp_paths):
    return DeadManSwitch(config_path=tmp_paths[0], state_path=tmp_paths[1])


def test_default_config(switch):
    assert switch.config["enabled"] is False
    assert switch.config["inactivityDays"] == 3


def test_setup_enables(switch):
    result = switch.setup(inactivity_days=5, warning_hours=12)
    assert "설정 완료" in result
    assert switch.config["enabled"] is True
    assert switch.config["inactivityDays"] == 5


def test_disable(switch):
    switch.setup()
    result = switch.disable()
    assert "비활성화" in result
    assert switch.config["enabled"] is False


def test_record_activity_resets_warning(switch):
    switch.state["warning_sent"] = True
    switch.record_activity()
    assert switch.state["warning_sent"] is False
    assert switch.state["activated"] is False


def test_reset(switch):
    old_time = switch.state.get("last_activity", 0)
    time.sleep(0.01)
    switch.reset()
    assert switch.state["last_activity"] > old_time


def test_status_format(switch):
    switch.setup()
    text = switch.format_status()
    assert "활성" in text
    assert "마지막 활동" in text


def test_check_disabled(switch):
    result = switch.check()
    assert result["action"] == "none"
    assert result["reason"] == "disabled"


def test_check_within_threshold(switch):
    switch.setup(inactivity_days=3)
    result = switch.check()
    assert result["action"] == "none"
    assert result["reason"] == "within_threshold"


def test_check_warning(switch):
    switch.setup(inactivity_days=1, warning_hours=24)
    # Simulate old activity (> 0 hours ago, within warning window)
    switch.state["last_activity"] = time.time() - 3600  # 1 hour ago
    switch._save_state()
    # inactivity=1day, warning=24h → warning at 0h elapsed → should warn immediately
    send_fn = MagicMock()
    result = switch.check(send_fn=send_fn)
    assert result["action"] == "warning"
    send_fn.assert_called_once()


def test_check_activation(switch):
    switch.setup(inactivity_days=1)
    switch.state["last_activity"] = time.time() - 86400 * 2  # 2 days ago
    switch._save_state()
    result = switch.check()
    assert result["action"] == "activate"
    assert len(result["results"]) > 0


def test_already_activated_noop(switch):
    switch.setup()
    switch.state["activated"] = True
    switch._save_state()
    result = switch.check()
    assert result["action"] == "none"
    assert result["reason"] == "already_activated"


def test_confirm_alive(switch):
    switch.state["warning_sent"] = True
    result = switch.confirm_alive()
    assert "확인" in result
    assert switch.state["warning_sent"] is False


def test_test_dry_run(switch):
    switch.setup()
    results = switch.test()
    assert len(results) >= 1
    for r in results:
        assert r.get("dry_run") is True


def test_handle_command_status(switch):
    result = switch.handle_command("status")
    assert "비활성" in result


def test_handle_command_unknown(switch):
    result = switch.handle_command("foobar")
    assert "알 수 없는 명령" in result


def test_persistence(tmp_paths):
    s1 = DeadManSwitch(config_path=tmp_paths[0], state_path=tmp_paths[1])
    s1.setup(inactivity_days=7)

    s2 = DeadManSwitch(config_path=tmp_paths[0], state_path=tmp_paths[1])
    assert s2.config["enabled"] is True
    assert s2.config["inactivityDays"] == 7
