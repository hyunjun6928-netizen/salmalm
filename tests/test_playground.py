"""Tests for Code Playground feature."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

from salmalm.features.playground import CodePlayground, handle_play_command


@pytest.fixture
def playground(tmp_path):
    pg = CodePlayground(db_path=tmp_path / "test_play.db", timeout=5)
    yield pg
    pg.close()


def test_run_python_hello(playground):
    result = playground.run_python("print('hello')")
    assert result["exit_code"] == 0
    assert "hello" in result["output"]


def test_run_python_math(playground):
    result = playground.run_python("print(2 + 3)")
    assert result["exit_code"] == 0
    assert "5" in result["output"]


def test_run_python_error(playground):
    result = playground.run_python("raise ValueError('test')")
    assert result["exit_code"] != 0
    assert "ValueError" in result["error"]


def test_run_python_empty(playground):
    result = playground.run_python("")
    assert "error" in result


def test_run_python_timeout(playground):
    playground.timeout = 2
    result = playground.run_python("import time; time.sleep(10)")
    assert result["exit_code"] == -1
    assert "시간 초과" in result["error"]


def test_run_python_multiline(playground):
    code = "x = 5\ny = 10\nprint(x + y)"
    result = playground.run_python(code)
    assert result["exit_code"] == 0
    assert "15" in result["output"]


def test_run_js_if_available(playground):
    import shutil
    if not shutil.which("node"):
        result = playground.run_js("console.log('hi')")
        assert "Node.js" in result["error"]
    else:
        result = playground.run_js("console.log('hello from node')")
        assert result["exit_code"] == 0
        assert "hello from node" in result["output"]


def test_run_js_empty(playground):
    result = playground.run_js("")
    assert "error" in result


def test_history_empty(playground):
    result = playground.history()
    assert "비어있습니다" in result


def test_history_after_run(playground):
    playground.run_python("print('test')")
    result = playground.history()
    assert "히스토리" in result
    assert "python" in result.lower()


def test_clear_history(playground):
    playground.run_python("print(1)")
    result = playground.clear_history()
    assert "삭제" in result
    assert "비어있습니다" in playground.history()


def test_format_result_success(playground):
    record = {
        "lang": "python", "exit_code": 0,
        "output": "hello", "error": "", "exec_time_ms": 50.5
    }
    formatted = playground.format_result(record)
    assert "성공" in formatted
    assert "hello" in formatted
    assert "50ms" in formatted


def test_format_result_failure(playground):
    record = {
        "lang": "python", "exit_code": 1,
        "output": "", "error": "NameError", "exec_time_ms": 10
    }
    formatted = playground.format_result(record)
    assert "실패" in formatted
    assert "NameError" in formatted


def test_format_result_no_output(playground):
    record = {
        "lang": "python", "exit_code": 0,
        "output": "", "error": "", "exec_time_ms": 5
    }
    formatted = playground.format_result(record)
    assert "출력 없음" in formatted


def test_exec_time_recorded(playground):
    result = playground.run_python("print(1)")
    assert result["exec_time_ms"] > 0


def test_command_handler_help():
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(handle_play_command("/play"))
    assert "코드 실행" in result
    loop.close()


def test_history_limit(playground):
    for i in range(5):
        playground.run_python(f"print({i})")
    result = playground.history(limit=3)
    # Should show entries
    assert "히스토리" in result
