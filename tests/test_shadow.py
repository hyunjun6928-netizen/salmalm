"""Tests for SalmAlm Shadow Mode."""
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from salmalm.features.shadow import ShadowMode, _PROFILE_PATH, _EMOJI_RE, _HONORIFIC_PATTERNS


@pytest.fixture
def shadow(tmp_path, monkeypatch):
    profile_path = tmp_path / "shadow_profile.json"
    monkeypatch.setattr("salmalm.shadow._PROFILE_PATH", profile_path)
    monkeypatch.setattr("salmalm.shadow._PROFILE_DIR", tmp_path)
    return ShadowMode()


@pytest.fixture
def sample_messages():
    return [
        {"role": "user", "content": "안녕하세요 오늘 날씨가 좋네요 😊", "timestamp": 1000},
        {"role": "assistant", "content": "네 좋습니다"},
        {"role": "user", "content": "프로젝트 진행 상황이 어떻게 되나요?", "timestamp": 1030},
        {"role": "user", "content": "회의는 언제 하면 좋을까요? 😊", "timestamp": 1090},
        {"role": "user", "content": "감사합니다 확인해볼게요", "timestamp": 1100},
        {"role": "user", "content": "내일 오전에 시간 되세요?", "timestamp": 1110},
        {"role": "assistant", "content": "됩니다"},
        {"role": "user", "content": "좋아요 그럼 내일 10시에 해요 😄", "timestamp": 1115},
        {"role": "user", "content": "자료 준비해올게요", "timestamp": 1120},
        {"role": "user", "content": "수고하세요!", "timestamp": 1125},
    ]


def test_initial_state(shadow):
    assert shadow.active is False
    assert shadow.confidence_threshold == 70
    assert shadow.profile == {}


def test_learn_builds_profile(shadow, sample_messages):
    profile = shadow.learn(sample_messages)
    assert profile["sample_count"] == 8
    assert profile["avg_message_length"] > 0
    assert isinstance(profile["frequent_words"], list)
    assert isinstance(profile["emoji_top"], list)
    assert profile["speech_style"] in ("해요체", "합쇼체", "해체", "하오체", "혼합")
    assert "learned_at" in profile


def test_learn_saves_to_disk(shadow, sample_messages, tmp_path):
    shadow.learn(sample_messages)
    path = tmp_path / "shadow_profile.json"
    assert path.exists()
    data = json.loads(path.read_text("utf-8"))
    assert data["sample_count"] == 8


def test_learn_empty_messages(shadow):
    profile = shadow.learn([])
    assert profile == {}


def test_command_on_off(shadow):
    result = shadow.handle_command("on")
    assert "활성화" in result
    assert shadow.active is True

    result = shadow.handle_command("off")
    assert "비활성화" in result
    assert shadow.active is False


def test_command_profile_empty(shadow):
    result = shadow.handle_command("profile")
    assert "프로필이 없습니다" in result


def test_command_profile_with_data(shadow, sample_messages):
    shadow.learn(sample_messages)
    result = shadow.handle_command("profile")
    assert "sample_count" in result
    assert "frequent_words" in result


def test_command_learn(shadow, sample_messages):
    result = shadow.handle_command("learn", session_messages=sample_messages)
    assert "학습 완료" in result
    assert "8개" in result


def test_command_test(shadow, sample_messages):
    shadow.learn(sample_messages)
    result = shadow.handle_command("test 오늘 회의 있나요?")
    assert "[테스트 프롬프트]" in result
    assert "Shadow Mode" in result


def test_command_test_no_profile(shadow):
    result = shadow.handle_command("test hello")
    assert "프로필이 없습니다" in result


def test_command_confidence(shadow):
    result = shadow.handle_command("confidence 50")
    assert "50" in result
    assert shadow.confidence_threshold == 50


def test_command_confidence_clamp(shadow):
    shadow.handle_command("confidence 150")
    assert shadow.confidence_threshold == 100
    shadow.handle_command("confidence 0")
    assert shadow.confidence_threshold == 0


def test_proxy_response_low_confidence(shadow, sample_messages):
    shadow.learn(sample_messages)
    shadow.active = True
    result = shadow.generate_proxy_response("hello", confidence=30)
    assert "자리를 비웠소" in result


def test_proxy_response_high_confidence(shadow, sample_messages):
    shadow.learn(sample_messages)
    shadow.active = True
    result = shadow.generate_proxy_response("hello", confidence=90)
    assert "스타일" in result  # returns the prompt


def test_should_proxy(shadow, sample_messages):
    assert shadow.should_proxy() is False
    shadow.active = True
    assert shadow.should_proxy() is False  # no profile
    shadow.learn(sample_messages)
    assert shadow.should_proxy() is True


def test_speed_detection_fast(shadow):
    msgs = [
        {"role": "user", "content": "hi", "timestamp": 100},
        {"role": "user", "content": "yo", "timestamp": 105},
        {"role": "user", "content": "ok", "timestamp": 110},
    ]
    profile = shadow.learn(msgs)
    assert profile["response_speed"] == "즉답"


def test_speed_detection_slow(shadow):
    msgs = [
        {"role": "user", "content": "hi", "timestamp": 100},
        {"role": "user", "content": "yo", "timestamp": 200},
        {"role": "user", "content": "ok", "timestamp": 300},
    ]
    profile = shadow.learn(msgs)
    assert profile["response_speed"] == "숙고"


def test_emoji_regex():
    assert _EMOJI_RE.search("hello 😊 world")
    assert not _EMOJI_RE.search("hello world")


def test_command_help(shadow):
    result = shadow.handle_command("")
    assert "/shadow on" in result
