"""Tests for Quick Actions feature."""
import asyncio

import pytest

from salmalm.features.quick_actions import QuickActionManager, handle_qa_command


@pytest.fixture
def qa(tmp_path):
    q = QuickActionManager(db_path=tmp_path / "test_qa.db")
    yield q
    q.close()


def test_add_action(qa):
    result = qa.add("morning", "/briefing && /habit remind")
    assert "등록" in result


def test_add_empty_name(qa):
    result = qa.add("", "/test")
    assert "❌" in result


def test_add_empty_command(qa):
    result = qa.add("test", "")
    assert "❌" in result


def test_add_duplicate_updates(qa):
    qa.add("test", "/cmd1")
    result = qa.add("test", "/cmd2")
    assert "업데이트" in result
    action = qa.get("test")
    assert action["commands"] == "/cmd2"


def test_get_action(qa):
    qa.add("morning", "/briefing && /habit remind")
    action = qa.get("morning")
    assert action is not None
    assert action["name"] == "morning"
    assert "/briefing" in action["commands"]


def test_get_nonexistent(qa):
    assert qa.get("없는액션") is None


def test_remove_action(qa):
    qa.add("test", "/cmd")
    result = qa.remove("test")
    assert "삭제" in result
    assert qa.get("test") is None


def test_remove_nonexistent(qa):
    result = qa.remove("없는액션")
    assert "❌" in result


def test_list_empty(qa):
    result = qa.list_all()
    assert "등록된 액션이 없습니다" in result


def test_list_with_actions(qa):
    qa.add("morning", "/briefing")
    qa.add("night", "/journal write 잘자")
    result = qa.list_all()
    assert "morning" in result
    assert "night" in result


def test_parse_chain():
    qa = QuickActionManager()
    chain = qa._parse_chain("/cmd1 && /cmd2 && /cmd3")
    assert len(chain) == 3
    assert chain[0] == "/cmd1"
    assert chain[1] == "/cmd2"


def test_parse_chain_single():
    qa = QuickActionManager()
    chain = qa._parse_chain("/single_command")
    assert len(chain) == 1


def test_parse_chain_quoted():
    qa = QuickActionManager()
    chain = qa._parse_chain('/briefing && /habit remind')
    assert len(chain) == 2


def test_run_no_dispatcher(qa):
    qa.add("test", "/cmd1")
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(qa.run("test"))
    assert "디스패처 미설정" in result
    loop.close()


def test_run_with_dispatcher(qa):
    qa.add("test", "/status")
    results = []

    async def mock_dispatch(cmd):
        return f"결과: {cmd}"

    qa.set_dispatcher(mock_dispatch)
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(qa.run("test"))
    assert "실행 결과" in result
    loop.close()


def test_run_nonexistent(qa):
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(qa.run("없는액션"))
    assert "❌" in result
    loop.close()


def test_usage_count(qa):
    qa.add("test", "/cmd")
    loop = asyncio.new_event_loop()
    loop.run_until_complete(qa.run("test"))
    loop.run_until_complete(qa.run("test"))
    action = qa.get("test")
    assert action["usage_count"] == 2
    loop.close()


def test_rename(qa):
    qa.add("old", "/cmd")
    result = qa.rename("old", "new")
    assert "이름 변경" in result
    assert qa.get("old") is None
    assert qa.get("new") is not None


def test_rename_nonexistent(qa):
    result = qa.rename("없는거", "새이름")
    assert "❌" in result


def test_rename_conflict(qa):
    qa.add("a", "/cmd1")
    qa.add("b", "/cmd2")
    result = qa.rename("a", "b")
    assert "❌" in result


def test_command_handler_list():
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(handle_qa_command("/qa"))
    assert result is not None
    loop.close()


def test_command_handler_add():
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(handle_qa_command("/qa add unique_test_cmd /status"))
    assert "등록" in result or "업데이트" in result
    loop.close()
