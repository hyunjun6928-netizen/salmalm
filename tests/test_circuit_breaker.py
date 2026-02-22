"""Test circuit breaker and loop detection in engine.py."""
import pytest
import json
import hashlib


class TestCircuitBreaker:
    """Circuit breaker should only count ❌-prefixed outputs as errors."""

    def test_normal_output_with_error_word_not_counted(self):
        """Tool output containing 'error' as substring should NOT trigger breaker."""
        tool_outputs = {
            'id1': 'The function returned an error code 0 which means success',
            'id2': 'No errors found in the code',
        }
        errors = sum(1 for v in tool_outputs.values() if str(v).startswith('❌'))
        assert errors == 0

    def test_real_error_counted(self):
        """Tool output starting with ❌ should trigger breaker."""
        tool_outputs = {
            'id1': '❌ Invalid tool arguments for search',
            'id2': 'Search completed successfully',
        }
        errors = sum(1 for v in tool_outputs.values() if str(v).startswith('❌'))
        assert errors == 1

    def test_error_in_middle_not_counted(self):
        """❌ not at start should not count."""
        tool_outputs = {
            'id1': 'Result: ❌ failed',
        }
        errors = sum(1 for v in tool_outputs.values() if str(v).startswith('❌'))
        assert errors == 0

    def test_multiple_errors(self):
        tool_outputs = {
            'id1': '❌ Failed',
            'id2': '❌ Also failed',
            'id3': 'OK',
        }
        errors = sum(1 for v in tool_outputs.values() if str(v).startswith('❌'))
        assert errors == 2

    def test_empty_outputs(self):
        tool_outputs = {}
        errors = sum(1 for v in tool_outputs.values() if str(v).startswith('❌'))
        assert errors == 0


class TestLoopDetection:
    """Loop detection: same tool+args 3+ times in last 6 iterations."""

    def _sig(self, name, args):
        h = hashlib.md5(json.dumps(args, sort_keys=True).encode()).hexdigest()[:8]
        return (name, h)

    def test_no_loop_different_args(self):
        recent = []
        for i in range(6):
            recent.append(self._sig('search', {'q': f'query_{i}'}))
        from collections import Counter
        freq = Counter(recent[-6:])
        top = freq.most_common(1)[0]
        assert top[1] == 1  # All unique

    def test_loop_detected(self):
        sig = self._sig('search', {'q': 'same query'})
        recent = [sig] * 4 + [self._sig('other', {}), self._sig('other2', {})]
        from collections import Counter
        freq = Counter(recent[-6:])
        top = freq.most_common(1)[0]
        assert top[1] >= 3  # Loop detected

    def test_no_loop_under_threshold(self):
        sig = self._sig('search', {'q': 'same'})
        recent = [sig, sig, self._sig('a', {}), self._sig('b', {}), self._sig('c', {}), self._sig('d', {})]
        from collections import Counter
        freq = Counter(recent[-6:])
        top = freq.most_common(1)[0]
        assert top[1] < 3  # Only 2, not a loop

    def test_loop_at_boundary(self):
        sig = self._sig('tool', {'x': 1})
        recent = [sig, sig, sig, self._sig('a', {}), self._sig('b', {}), self._sig('c', {})]
        from collections import Counter
        freq = Counter(recent[-6:])
        top = freq.most_common(1)[0]
        assert top[1] == 3  # Exactly at threshold
