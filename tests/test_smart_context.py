"""Tests for salmalm.core.smart_context."""
import unittest

from salmalm.core.smart_context import (
    SmartContextWindow, ContextChunk, estimate_tokens,
    extract_keywords, relevance_score, handle_context_command,
)


class TestEstimateTokens(unittest.TestCase):
    def test_basic(self):
        assert estimate_tokens('hello world') >= 1

    def test_empty(self):
        assert estimate_tokens('') == 1

    def test_long(self):
        t = estimate_tokens('a' * 400)
        assert t == 100


class TestExtractKeywords(unittest.TestCase):
    def test_basic(self):
        kw = extract_keywords('Python programming language is great for data science')
        assert len(kw) > 0
        assert 'python' in kw or 'programming' in kw

    def test_stop_words_filtered(self):
        kw = extract_keywords('the and or but is are was')
        assert len(kw) == 0

    def test_korean(self):
        kw = extract_keywords('파이썬 프로그래밍 언어 활용')
        assert len(kw) > 0

    def test_empty(self):
        kw = extract_keywords('')
        assert kw == []


class TestRelevanceScore(unittest.TestCase):
    def test_full_match(self):
        score = relevance_score(['python', 'code'], 'python code example')
        assert score == 1.0

    def test_partial_match(self):
        score = relevance_score(['python', 'java', 'rust'], 'python code')
        assert 0.0 < score < 1.0

    def test_no_match(self):
        score = relevance_score(['xyz', 'abc'], 'python code')
        assert score == 0.0

    def test_empty_keywords(self):
        assert relevance_score([], 'text') == 0.0

    def test_empty_text(self):
        assert relevance_score(['a'], '') == 0.0


class TestContextChunk(unittest.TestCase):
    def test_basic(self):
        c = ContextChunk('memory', 'some content', relevance=0.8)
        assert c.source == 'memory'
        assert c.tokens > 0
        assert c.relevance == 0.8

    def test_repr(self):
        c = ContextChunk('test', 'x')
        assert 'ContextChunk' in repr(c)


class TestSmartContextWindow(unittest.TestCase):
    def test_default_budget(self):
        w = SmartContextWindow()
        assert w.budget == 8000

    def test_set_budget(self):
        w = SmartContextWindow()
        w.budget = 4000
        assert w.budget == 4000

    def test_budget_minimum(self):
        w = SmartContextWindow()
        w.budget = 10
        assert w.budget == 100  # minimum enforced

    def test_gather_context(self):
        w = SmartContextWindow(token_budget=1000)
        w.set_recent_messages([{'role': 'user', 'content': 'python programming'}])
        sources = [
            {'source': 'memory', 'content': 'python is a great programming language'},
            {'source': 'file', 'content': 'java spring boot tutorial'},
        ]
        chunks = w.gather_context(sources)
        assert len(chunks) > 0
        # python-related should rank higher
        assert chunks[0].source == 'memory'

    def test_budget_enforcement(self):
        w = SmartContextWindow(token_budget=10)  # very small
        sources = [
            {'source': 'a', 'content': 'x' * 1000},  # way over budget
        ]
        chunks = w.gather_context(sources)
        assert len(chunks) == 0  # can't fit

    def test_used_tokens(self):
        w = SmartContextWindow(token_budget=10000)
        w.set_recent_messages([{'role': 'user', 'content': 'test'}])
        w.gather_context([{'source': 'a', 'content': 'hello world'}])
        assert w.used_tokens > 0
        assert w.remaining_tokens < w.budget

    def test_clear(self):
        w = SmartContextWindow()
        w._injected = [ContextChunk('test', 'data')]
        w.clear()
        assert len(w._injected) == 0

    def test_build_context_string(self):
        w = SmartContextWindow()
        w._injected = [ContextChunk('mem', 'hello', relevance=0.5)]
        s = w.build_context_string()
        assert 'hello' in s
        assert 'mem' in s

    def test_build_context_empty(self):
        w = SmartContextWindow()
        assert w.build_context_string() == ''

    def test_show(self):
        w = SmartContextWindow()
        assert 'No context' in w.show()

    def test_analyze_topic_empty(self):
        w = SmartContextWindow()
        kw = w.analyze_topic()
        assert kw == []


class TestHandleCommand(unittest.TestCase):
    def test_show(self):
        result = handle_context_command('/context show')
        assert isinstance(result, str)

    def test_budget_display(self):
        result = handle_context_command('/context budget')
        assert 'budget' in result.lower() or 'tokens' in result.lower()

    def test_budget_set(self):
        result = handle_context_command('/context budget 5000')
        assert '✅' in result

    def test_budget_invalid(self):
        result = handle_context_command('/context budget abc')
        assert '❌' in result

    def test_clear(self):
        result = handle_context_command('/context clear')
        assert 'clear' in result.lower() or '🗑' in result

    def test_invalid_sub(self):
        result = handle_context_command('/context xyz')
        assert '❌' in result
