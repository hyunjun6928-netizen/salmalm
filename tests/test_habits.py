"""Tests for Habit Tracker feature."""
import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from salmalm.features.habits import HabitTracker, handle_habit_command


@pytest.fixture
def tracker(tmp_path):
    t = HabitTracker(db_path=tmp_path / "test_habits.db")
    yield t
    t.close()


def test_add_habit(tracker):
    result = tracker.add_habit("운동")
    assert "등록 완료" in result
    assert "운동" in result


def test_add_empty_habit(tracker):
    result = tracker.add_habit("")
    assert "❌" in result


def test_add_duplicate_habit(tracker):
    tracker.add_habit("독서")
    result = tracker.add_habit("독서")
    assert "활성화" in result


def test_check_habit(tracker):
    tracker.add_habit("코딩")
    result = tracker.check_habit("코딩", date="2026-02-20")
    assert "완료" in result
    assert "🔥" in result


def test_check_nonexistent_habit(tracker):
    result = tracker.check_habit("없는습관")
    assert "❌" in result


def test_check_duplicate(tracker):
    tracker.add_habit("운동")
    tracker.check_habit("운동", date="2026-02-20")
    result = tracker.check_habit("운동", date="2026-02-20")
    assert "이미" in result


def test_uncheck_habit(tracker):
    tracker.add_habit("독서")
    tracker.check_habit("독서", date="2026-02-20")
    result = tracker.uncheck_habit("독서", date="2026-02-20")
    assert "취소" in result


def test_streak_calculation(tracker):
    tracker.add_habit("운동")
    tracker.check_habit("운동", date="2026-02-18")
    tracker.check_habit("운동", date="2026-02-19")
    tracker.check_habit("운동", date="2026-02-20")
    streak = tracker._calc_streak("운동", "2026-02-20")
    assert streak == 3


def test_streak_broken(tracker):
    tracker.add_habit("운동")
    tracker.check_habit("운동", date="2026-02-18")
    # skip 02-19
    tracker.check_habit("운동", date="2026-02-20")
    streak = tracker._calc_streak("운동", "2026-02-20")
    assert streak == 1


def test_get_habits(tracker):
    tracker.add_habit("운동")
    tracker.add_habit("독서")
    habits = tracker.get_habits()
    assert "운동" in habits
    assert "독서" in habits


def test_remove_habit(tracker):
    tracker.add_habit("운동")
    result = tracker.remove_habit("운동")
    assert "삭제" in result
    assert "운동" not in tracker.get_habits()


def test_remove_nonexistent(tracker):
    result = tracker.remove_habit("없는습관")
    assert "❌" in result


def test_stats(tracker):
    tracker.add_habit("운동")
    tracker.check_habit("운동", date="2026-02-20")
    result = tracker.stats(days=7)
    assert "통계" in result
    assert "운동" in result


def test_stats_empty(tracker):
    result = tracker.stats()
    assert "등록된 습관이 없습니다" in result


def test_remind(tracker):
    tracker.add_habit("운동")
    tracker.add_habit("독서")
    tracker.check_habit("운동")
    result = tracker.remind()
    assert "✅" in result  # 운동 checked
    assert "⬜" in result  # 독서 unchecked


def test_remind_all_done(tracker):
    tracker.add_habit("운동")
    tracker.check_habit("운동")
    result = tracker.remind()
    assert "모든 습관 완료" in result


def test_progress_bar(tracker):
    bar = tracker._progress_bar(0.5, 10)
    assert "🟩" in bar
    assert "⬜" in bar
    assert len(bar) == 10  # 10 emoji chars


def test_today_summary(tracker):
    tracker.add_habit("운동")
    tracker.add_habit("독서")
    tracker.check_habit("운동")
    summary = tracker.today_summary()
    assert "운동" in summary["done"]
    assert "독서" in summary["pending"]
    assert summary["total"] == 2


def test_command_handler():
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(handle_habit_command("/habit"))
    assert result is not None
    loop.close()


def test_list_command(tracker):
    tracker.add_habit("운동")
    loop = asyncio.new_event_loop()
    # Use global tracker would need patching, just test the tracker method
    habits = tracker.get_habits()
    assert len(habits) == 1
    loop.close()
