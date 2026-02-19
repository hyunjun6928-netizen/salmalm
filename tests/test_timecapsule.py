"""Tests for Time Capsule."""
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from salmalm.timecapsule import TimeCapsule, _parse_capsule_date, _split_date_message
from salmalm.constants import KST


@pytest.fixture
def capsule(tmp_path):
    return TimeCapsule(db_path=tmp_path / "capsules.db")


def test_create_iso_date(capsule):
    result = capsule.create("2026-08-15", "미래의 나에게")
    assert result["id"] == 1
    assert result["delivery_date"] == "2026-08-15"
    assert "타임캡슐" in result["message"]


def test_create_korean_months(capsule):
    result = capsule.create("6개월후", "반년 후의 나")
    assert result["id"] == 1
    now = datetime.now(tz=KST)
    expected_month = (now.month + 6 - 1) % 12 + 1
    assert str(expected_month).zfill(2) in result["delivery_date"]


def test_create_korean_days(capsule):
    result = capsule.create("30일후", "한달 후")
    expected = (datetime.now(tz=KST) + timedelta(days=30)).strftime("%Y-%m-%d")
    assert result["delivery_date"] == expected


def test_create_english_months(capsule):
    result = capsule.create("in 3 months", "see you")
    assert result["id"] == 1


def test_list_pending(capsule):
    capsule.create("2030-01-01", "msg1")
    capsule.create("2030-06-01", "msg2")
    rows = capsule.list_pending()
    assert len(rows) == 2
    assert rows[0][2] <= rows[1][2]  # ordered by date


def test_list_delivered_empty(capsule):
    assert capsule.list_delivered() == []


def test_peek(capsule):
    capsule.create("2030-01-01", "secret message")
    result = capsule.peek(1)
    assert result is not None
    assert result["message"] == "secret message"
    assert result["delivered"] is False


def test_peek_nonexistent(capsule):
    assert capsule.peek(999) is None


def test_cancel(capsule):
    capsule.create("2030-01-01", "to cancel")
    assert capsule.cancel(1) is True
    assert capsule.list_pending() == []


def test_cancel_nonexistent(capsule):
    assert capsule.cancel(999) is False


def test_get_due_capsules(capsule):
    capsule.create("2020-01-01", "overdue")
    capsule.create("2030-01-01", "future")
    due = capsule.get_due_capsules("2025-06-01")
    assert len(due) == 1
    assert due[0][1] == "overdue"


def test_deliver_due(capsule):
    capsule.create("2020-01-01", "배달할 메시지")
    send_fn = MagicMock()
    results = capsule.deliver_due(send_fn=send_fn, today="2025-06-01")
    assert len(results) == 1
    assert "타임캡슐이 도착했습니다" in results[0]["message"]
    assert "배달할 메시지" in results[0]["message"]
    send_fn.assert_called_once()
    # Should be marked delivered
    assert capsule.list_pending() == []


def test_mark_delivered(capsule):
    capsule.create("2020-01-01", "msg")
    capsule.mark_delivered(1)
    delivered = capsule.list_delivered()
    assert len(delivered) == 1


def test_handle_command_list_empty(capsule):
    result = capsule.handle_command("list")
    assert "없습니다" in result


def test_handle_command_create(capsule):
    result = capsule.handle_command("2030-12-25 메리 크리스마스!")
    assert "타임캡슐" in result


def test_handle_command_peek(capsule):
    capsule.create("2030-01-01", "peek test")
    result = capsule.handle_command("peek 1")
    assert "스포일러" in result


def test_handle_command_cancel(capsule):
    capsule.create("2030-01-01", "cancel test")
    result = capsule.handle_command("cancel 1")
    assert "취소" in result


def test_split_date_message():
    d, m = _split_date_message("2026-08-15 미래의 나에게")
    assert d == "2026-08-15"
    assert m == "미래의 나에게"

    d, m = _split_date_message("6개월후 반년후의 나에게")
    assert d == "6개월후"
    assert "반년" in m

    d, m = _split_date_message("in 3 months hello future me")
    assert d == "in 3 months"
    assert "hello" in m


def test_parse_invalid_date():
    with pytest.raises(ValueError):
        _parse_capsule_date("아무말")
