"""Tests for Focus Mode feature."""
import asyncio

import pytest

from salmalm.features.focus import FocusManager, FocusSession, handle_focus_command


@pytest.fixture
def fm():
    return FocusManager()


def test_start_focus(fm):
    result = fm.start("Python 프로젝트")
    assert "집중 모드 시작" in result
    assert "Python 프로젝트" in result


def test_start_empty_topic(fm):
    result = fm.start("")
    assert "❌" in result


def test_is_focused(fm):
    assert not fm.is_focused()
    fm.start("코딩")
    assert fm.is_focused()


def test_get_topic(fm):
    assert fm.get_topic() is None
    fm.start("React 개발")
    assert fm.get_topic() == "React 개발"


def test_end_focus(fm):
    fm.start("Python")
    result = fm.end()
    assert "종료" in result
    assert "Python" in result
    assert not fm.is_focused()


def test_end_when_not_focused(fm):
    result = fm.end()
    assert "집중 모드가 아닙니다" in result


def test_check_on_topic(fm):
    fm.start("Python")
    result = fm.check_message("Python에서 리스트 사용법")
    assert result is None  # On-topic, allowed


def test_check_off_topic(fm):
    fm.start("Python")
    result = fm.check_message("오늘 날씨가 어떤가요?")
    assert result is not None
    assert "집중 중" in result


def test_check_command_always_allowed(fm):
    fm.start("Python")
    result = fm.check_message("/status")
    assert result is None


def test_check_short_message_allowed(fm):
    fm.start("Python")
    result = fm.check_message("네")
    assert result is None  # Short messages allowed


def test_check_not_focused(fm):
    result = fm.check_message("아무 메시지")
    assert result is None  # Not focused, allow all


def test_message_counting(fm):
    fm.start("Python")
    fm.check_message("Python 코드 작성")
    fm.check_message("오늘 점심 뭐 먹지?")
    fm.check_message("Python 함수 만들기")

    session = fm._sessions["default"]
    assert session.total_messages == 3
    assert session.on_topic_count == 2
    assert session.off_topic_count == 1


def test_status_not_focused(fm):
    result = fm.status()
    assert "비활성" in result


def test_status_focused(fm):
    fm.start("AI 연구")
    result = fm.status()
    assert "AI 연구" in result
    assert "집중 모드" in result


def test_restart_overwrites(fm):
    fm.start("Python")
    fm.start("React")
    assert fm.get_topic() == "React"
    assert len(fm._history) == 1  # Old session in history


def test_history_summary_empty(fm):
    result = fm.history_summary()
    assert "히스토리가 없습니다" in result


def test_history_summary(fm):
    fm.start("Python")
    fm.end()
    result = fm.history_summary()
    assert "Python" in result


def test_session_duration():
    session = FocusSession("test")
    assert session.active
    assert session.duration_seconds >= 0
    session.end()
    assert not session.active


def test_session_to_dict():
    session = FocusSession("test")
    d = session.to_dict()
    assert d["topic"] == "test"
    assert "duration" in d


def test_multiple_users(fm):
    fm.start("Python", user_id="user1")
    fm.start("React", user_id="user2")
    assert fm.get_topic("user1") == "Python"
    assert fm.get_topic("user2") == "React"


def test_command_handler():
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(handle_focus_command("/focus"))
    assert result is not None
    loop.close()


def test_command_start():
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(handle_focus_command("/focus start Python"))
    assert "집중 모드 시작" in result
    loop.close()
