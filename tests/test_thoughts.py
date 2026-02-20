"""Tests for thoughts.py — Thought Stream."""
import json
from pathlib import Path

import pytest


@pytest.fixture
def thought_db(tmp_path):
    from salmalm.features.thoughts import ThoughtStream
    db = tmp_path / 'thoughts.db'
    return ThoughtStream(db_path=db)


class TestThoughtStream:
    def test_add_thought(self, thought_db):
        tid = thought_db.add('오늘 날씨가 좋다')
        assert tid >= 1

    def test_add_with_tags(self, thought_db):
        tid = thought_db.add('#python 코드 리팩토링 해야지 #todo')
        thoughts = thought_db.list_recent(1)
        assert thoughts[0]['tags'] == 'python,todo'

    def test_list_recent(self, thought_db):
        for i in range(5):
            thought_db.add(f'생각 {i}')
        recent = thought_db.list_recent(3)
        assert len(recent) == 3
        # Most recent first
        assert '4' in recent[0]['content']

    def test_search_like(self, thought_db):
        thought_db.add('파이썬 코드 작성')
        thought_db.add('자바스크립트 배우기')
        thought_db.add('파이썬 디버깅')
        results = thought_db.search('파이썬')
        assert len(results) == 2

    def test_by_tag(self, thought_db):
        thought_db.add('#work 회의 참석')
        thought_db.add('#personal 운동하기')
        thought_db.add('#work 보고서 작성')
        results = thought_db.by_tag('work')
        assert len(results) == 2

    def test_timeline(self, thought_db):
        thought_db.add('아침 생각')
        thought_db.add('점심 생각')
        from datetime import datetime
        from salmalm.constants import KST
        today = datetime.now(KST).strftime('%Y-%m-%d')
        results = thought_db.timeline(today)
        assert len(results) == 2

    def test_stats(self, thought_db):
        thought_db.add('#python 코딩')
        thought_db.add('#python #ai 머신러닝')
        thought_db.add('일반 생각')
        s = thought_db.stats()
        assert s['total'] == 3
        assert s['weekly'] == 3
        assert any(t[0] == 'python' for t in s['top_tags'])

    def test_export_markdown(self, thought_db):
        thought_db.add('첫번째 생각')
        thought_db.add('두번째 생각')
        md = thought_db.export_markdown()
        assert '# Thought Stream' in md
        assert '첫번째' in md

    def test_delete(self, thought_db):
        tid = thought_db.add('삭제할 생각')
        assert thought_db.delete(tid)
        assert not thought_db.delete(tid)

    def test_mood_recording(self, thought_db):
        tid = thought_db.add('행복한 생각', mood='happy')
        thoughts = thought_db.list_recent(1)
        assert thoughts[0]['mood'] == 'happy'

    def test_export_empty(self, thought_db):
        md = thought_db.export_markdown()
        assert 'No thoughts' in md


class TestFormatHelpers:
    def test_format_thoughts(self):
        from salmalm.features.thoughts import _format_thoughts
        thoughts = [{'id': 1, 'content': 'test', 'tags': 'a', 'mood': 'happy',
                      'created_at': '2026-02-20T10:00:00'}]
        result = _format_thoughts(thoughts)
        assert '#1' in result

    def test_format_thoughts_empty(self):
        from salmalm.features.thoughts import _format_thoughts
        assert '없습니다' in _format_thoughts([])

    def test_format_stats(self):
        from salmalm.features.thoughts import _format_stats
        s = {'total': 10, 'weekly': 3, 'top_tags': [('python', 5)]}
        result = _format_stats(s)
        assert '10' in result
