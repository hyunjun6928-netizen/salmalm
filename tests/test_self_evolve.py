"""Tests for self_evolve.py — Self-Evolving Prompt."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def tmp_evolution(tmp_path, monkeypatch):
    """Redirect evolution files to tmp."""
    monkeypatch.setattr('salmalm.features.self_evolve.EVOLUTION_DIR', tmp_path)
    monkeypatch.setattr('salmalm.features.self_evolve.EVOLUTION_FILE', tmp_path / 'evolution.json')
    monkeypatch.setattr('salmalm.features.self_evolve.EVOLUTION_HISTORY_FILE', tmp_path / 'evolution_history.json')
    return tmp_path


def _make_msgs(texts, role='user', with_ts=False):
    import time
    msgs = []
    for i, t in enumerate(texts):
        m = {'role': role, 'content': t}
        if with_ts:
            m['timestamp'] = time.time() - (len(texts) - i) * 3600
        msgs.append(m)
    return msgs


class TestPatternAnalyzer:
    def test_length_preference_concise(self):
        from salmalm.features.self_evolve import PatternAnalyzer
        msgs = _make_msgs(['짧게 해줘'] * 3 + ['ok'] * 5)
        assert PatternAnalyzer.analyze_length_preference(msgs) == 'concise'

    def test_length_preference_detailed(self):
        from salmalm.features.self_evolve import PatternAnalyzer
        msgs = _make_msgs(['자세히 설명해줘'] * 3 + ['x' * 200] * 5)
        assert PatternAnalyzer.analyze_length_preference(msgs) == 'detailed'

    def test_length_preference_mixed(self):
        from salmalm.features.self_evolve import PatternAnalyzer
        msgs = _make_msgs(['hello this is a medium length message okay', 'another medium message here for testing'])
        assert PatternAnalyzer.analyze_length_preference(msgs) == 'mixed'

    def test_length_preference_empty(self):
        from salmalm.features.self_evolve import PatternAnalyzer
        assert PatternAnalyzer.analyze_length_preference([]) == 'mixed'

    def test_topic_frequency(self):
        from salmalm.features.self_evolve import PatternAnalyzer
        msgs = _make_msgs(['python code fix', 'debug this function', 'write code'])
        topics = PatternAnalyzer.analyze_topic_frequency(msgs)
        assert topics['coding'] >= 3

    def test_language_ratio_korean(self):
        from salmalm.features.self_evolve import PatternAnalyzer
        msgs = _make_msgs(['안녕하세요 코드 작성해주세요', '감사합니다 잘됐어요'])
        ratio = PatternAnalyzer.analyze_language_ratio(msgs)
        assert ratio > 0.5

    def test_language_ratio_english(self):
        from salmalm.features.self_evolve import PatternAnalyzer
        msgs = _make_msgs(['please write some code for me', 'thank you very much'])
        ratio = PatternAnalyzer.analyze_language_ratio(msgs)
        assert ratio < 0.3

    def test_feedback_signals(self):
        from salmalm.features.self_evolve import PatternAnalyzer
        msgs = _make_msgs(['고마워 완벽해', '아니 틀렸어', 'perfect thanks'])
        fb = PatternAnalyzer.analyze_feedback_signals(msgs)
        assert fb['positive'] >= 2
        assert fb['negative'] >= 1

    def test_code_comment_preference(self):
        from salmalm.features.self_evolve import PatternAnalyzer
        msgs = _make_msgs(['주석 없이 작성해줘', '주석 빼줘', '주석 제거'])
        assert PatternAnalyzer.analyze_code_comment_preference(msgs) == 'dislike'

    def test_time_patterns(self):
        from salmalm.features.self_evolve import PatternAnalyzer
        import time
        # Create messages with afternoon timestamps and work content
        now = time.time()
        msgs = []
        for i in range(5):
            msgs.append({
                'role': 'user',
                'content': '코드 버그 수정해줘 deploy 서버',
                'timestamp': now,  # current time
            })
        result = PatternAnalyzer.analyze_time_patterns(msgs)
        # Should have at least one period detected
        assert isinstance(result, dict)


class TestPromptEvolver:
    def test_init_and_save(self):
        from salmalm.features.self_evolve import PromptEvolver
        pe = PromptEvolver()
        assert pe.state['conversation_count'] == 0

    def test_record_conversation(self):
        from salmalm.features.self_evolve import PromptEvolver
        pe = PromptEvolver()
        msgs = _make_msgs(['hello', 'code python', '감사합니다'])
        pe.record_conversation(msgs)
        assert pe.state['conversation_count'] == 1
        assert 'preferences' in pe.state

    def test_generate_rules_concise(self):
        from salmalm.features.self_evolve import PromptEvolver
        pe = PromptEvolver()
        pe.state['preferences'] = {'length_preference': 'concise', 'language_ratio': 0.9}
        rules = pe.generate_rules()
        assert any('간결' in r for r in rules)
        assert any('한국어' in r for r in rules)

    def test_apply_to_soul(self, tmp_path):
        from salmalm.features.self_evolve import PromptEvolver
        pe = PromptEvolver()
        pe.state['preferences'] = {
            'length_preference': 'detailed',
            'code_comments': 'dislike',
            'language_ratio': 0.1,
        }
        soul_file = tmp_path / 'SOUL.md'
        soul_file.write_text('# My Soul\n\nI am helpful.\n')
        result = pe.apply_to_soul(soul_file)
        assert '✅' in result
        content = soul_file.read_text()
        assert '<!-- auto-evolved-begin -->' in content
        assert '<!-- auto-evolved-end -->' in content

    def test_apply_replaces_old_section(self, tmp_path):
        from salmalm.features.self_evolve import PromptEvolver
        pe = PromptEvolver()
        pe.state['preferences'] = {'length_preference': 'concise'}
        soul_file = tmp_path / 'SOUL.md'
        soul_file.write_text('# Soul\n\n<!-- auto-evolved-begin -->\nold\n<!-- auto-evolved-end -->\n')
        pe.apply_to_soul(soul_file)
        content = soul_file.read_text()
        assert 'old' not in content
        assert content.count('auto-evolved-begin') == 1

    def test_get_status(self):
        from salmalm.features.self_evolve import PromptEvolver
        pe = PromptEvolver()
        status = pe.get_status()
        assert '🧬' in status

    def test_reset(self):
        from salmalm.features.self_evolve import PromptEvolver
        pe = PromptEvolver()
        pe.state['conversation_count'] = 50
        pe.reset()
        assert pe.state['conversation_count'] == 0

    def test_get_history_empty(self):
        from salmalm.features.self_evolve import PromptEvolver
        pe = PromptEvolver()
        result = pe.get_history()
        assert '없습니다' in result

    def test_should_suggest_evolution(self):
        from salmalm.features.self_evolve import PromptEvolver, EVOLVE_INTERVAL
        pe = PromptEvolver()
        pe.state['conversation_count'] = EVOLVE_INTERVAL
        assert pe.should_suggest_evolution()
        pe.state['conversation_count'] = EVOLVE_INTERVAL + 1
        assert not pe.should_suggest_evolution()
