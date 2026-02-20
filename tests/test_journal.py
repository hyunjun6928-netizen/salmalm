"""Tests for AI Journal feature."""
import asyncio
from datetime import datetime

import pytest

from salmalm.features.journal import JournalManager, _detect_mood, handle_journal_command


@pytest.fixture
def journal(tmp_path):
    j = JournalManager(db_path=tmp_path / "test_journal.db")
    yield j
    j.close()


def test_write_entry(journal):
    result = journal.write("오늘은 좋은 하루였다")
    assert "작성 완료" in result


def test_write_empty(journal):
    result = journal.write("")
    assert "❌" in result


def test_write_with_mood_detection(journal):
    result = journal.write("정말 행복한 하루! ㅋㅋ")
    assert "happy" in result


def test_write_sad_mood(journal):
    result = journal.write("오늘 너무 슬프고 우울하다 ㅠㅠ")
    assert "sad" in result


def test_review_date(journal):
    journal.write("테스트 일지", date="2026-02-20")
    result = journal.review("2026-02-20")
    assert "테스트 일지" in result


def test_review_empty_date(journal):
    result = journal.review("2020-01-01")
    assert "일지가 없습니다" in result


def test_today(journal):
    journal.write("오늘의 기록")
    result = journal.today()
    # Should contain today's date or the entry
    assert result is not None


def test_mood_trend(journal):
    journal.write("행복한 하루", date="2026-02-20")
    journal.write("슬픈 하루 ㅠㅠ", date="2026-02-19")
    result = journal.mood_trend(days=7)
    assert "트렌드" in result


def test_mood_trend_empty(journal):
    result = journal.mood_trend(days=3)
    assert "트렌드" in result
    assert "기록 없음" in result


def test_generate_summary(journal):
    journal.write("오늘 코딩했다")
    result = journal.generate_today_summary()
    assert "자동 일지" in result


def test_generate_summary_empty(journal):
    result = journal.generate_today_summary()
    assert "기록된 일지가 없습니다" in result


def test_detect_mood_happy():
    mood, score = _detect_mood("오늘 기분 좋아 ㅋㅋ 행복하다")
    assert mood == "happy"
    assert score > 0.5


def test_detect_mood_sad():
    mood, score = _detect_mood("너무 슬프다 ㅠㅠ 우울해")
    assert mood == "sad"
    assert score < 0.5


def test_detect_mood_neutral():
    mood, score = _detect_mood("일반적인 텍스트입니다")
    assert mood == "neutral"
    assert score == 0.5


def test_detect_mood_english():
    mood, score = _detect_mood("I'm so happy and excited!")
    assert mood in ("happy", "excited")
    assert score > 0.5


def test_multiple_entries_same_day(journal):
    journal.write("아침 일지", date="2026-02-20")
    journal.write("저녁 일지", date="2026-02-20")
    entries = journal.get_entries_for_date("2026-02-20")
    assert len(entries) == 2


def test_get_entries_api(journal):
    journal.write("테스트", date="2026-02-20")
    entries = journal.get_entries_for_date("2026-02-20")
    assert len(entries) == 1
    assert entries[0]["content"] == "테스트"
    assert "mood" in entries[0]


def test_command_handler():
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(handle_journal_command("/journal"))
    assert result is not None
    loop.close()


def test_command_write():
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(handle_journal_command("/journal write 테스트"))
    assert "작성" in result
    loop.close()


def test_auto_generated_flag(journal):
    journal.generate_today_summary(conversations=["대화 내용"])
    today = datetime.now().strftime("%Y-%m-%d")
    entries = journal.get_entries_for_date(today)
    auto_entries = [e for e in entries if e["auto"]]
    assert len(auto_entries) >= 1
