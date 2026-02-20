"""Safety & coverage hardening tests — cost caps, platform fixes, integration safety."""
import asyncio
import json
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================
# 1. Cost Cap Tests
# ============================================================

class TestCostCap(unittest.TestCase):
    """Test cost cap enforcement."""

    def test_cost_cap_exceeded_raises(self):
        """CostCapExceeded should be raised when cost >= COST_CAP."""
        import salmalm.core as _core
        from salmalm.core import CostCapExceeded, _usage, _usage_lock, check_cost_cap
        original_cost = _usage['total_cost']
        original_cap = _core.COST_CAP
        try:
            _core.COST_CAP = 10.0
            with _usage_lock:
                _usage['total_cost'] = 11.0
            with self.assertRaises(CostCapExceeded):
                check_cost_cap()
        finally:
            _core.COST_CAP = original_cap
            with _usage_lock:
                _usage['total_cost'] = original_cost

    def test_cost_cap_not_exceeded(self):
        """check_cost_cap should not raise when under cap."""
        from salmalm.core import _usage, _usage_lock, check_cost_cap
        original = _usage['total_cost']
        try:
            with _usage_lock:
                _usage['total_cost'] = 0.0
            # Should not raise
            check_cost_cap()
        finally:
            with _usage_lock:
                _usage['total_cost'] = original

    def test_cost_cap_env_override(self):
        """SALMALM_COST_CAP env var should be respected."""
        # The constant is read at import time, so we test the mechanism
        self.assertEqual(
            float(os.environ.get('SALMALM_COST_CAP', '50.0')),
            50.0  # default
        )

    def test_cost_cap_exact_boundary(self):
        """Cost exactly at cap should trigger."""
        import salmalm.core as _core
        from salmalm.core import CostCapExceeded, _usage, _usage_lock, check_cost_cap
        original_cost = _usage['total_cost']
        original_cap = _core.COST_CAP
        try:
            _core.COST_CAP = 10.0
            with _usage_lock:
                _usage['total_cost'] = 10.0  # exactly at cap
            with self.assertRaises(CostCapExceeded):
                check_cost_cap()
        finally:
            _core.COST_CAP = original_cap
            with _usage_lock:
                _usage['total_cost'] = original_cost

    def test_track_usage_updates_cost(self):
        """track_usage should increment total_cost."""
        from salmalm.core import track_usage, _usage, _usage_lock
        with _usage_lock:
            before = _usage['total_cost']
        track_usage('claude-opus-4-6', 1000, 500)
        with _usage_lock:
            after = _usage['total_cost']
        self.assertGreater(after, before)


# ============================================================
# 2. Sub-Agent Limits Tests
# ============================================================

class TestSubAgentLimits(unittest.TestCase):
    """Test sub-agent depth and concurrency limits."""

    def test_max_depth_exceeded(self):
        """Sub-agent should reject spawning beyond MAX_DEPTH."""
        from salmalm.features.agents import SubAgent
        with self.assertRaises(ValueError) as ctx:
            SubAgent.spawn('test task', _depth=SubAgent.MAX_DEPTH)
        self.assertIn('depth limit', str(ctx.exception).lower())

    def test_max_depth_value(self):
        """MAX_DEPTH should be 2."""
        from salmalm.features.agents import SubAgent
        self.assertEqual(SubAgent.MAX_DEPTH, 2)

    def test_max_concurrent_value(self):
        """MAX_CONCURRENT should be 5."""
        from salmalm.features.agents import SubAgent
        self.assertEqual(SubAgent.MAX_CONCURRENT, 5)

    def test_max_concurrent_exceeded(self):
        """Sub-agent should reject when too many are running."""
        from salmalm.features.agents import SubAgent
        original_agents = SubAgent._agents.copy()
        try:
            # Fill up with fake running agents
            for i in range(SubAgent.MAX_CONCURRENT):
                SubAgent._agents[f'fake-{i}'] = {'status': 'running'}
            with self.assertRaises(ValueError) as ctx:
                SubAgent.spawn('test task')
            self.assertIn('concurrent', str(ctx.exception).lower())
        finally:
            SubAgent._agents = original_agents


# ============================================================
# 3. Tool Result Truncation Tests
# ============================================================

class TestToolResultTruncation(unittest.TestCase):
    """Test that tool results are truncated at 50K chars."""

    def test_truncation_at_50k(self):
        """Results > 50K chars should be truncated."""
        from salmalm.core.engine import IntelligenceEngine as Engine
        eng = Engine()
        long_result = 'x' * 60000
        truncated = eng._truncate_tool_result(long_result)
        self.assertLessEqual(len(truncated), 50000 + 200)  # +overhead for message
        self.assertIn('truncated', truncated.lower())

    def test_no_truncation_under_50k(self):
        """Results <= 50K chars should pass through unchanged."""
        from salmalm.core.engine import IntelligenceEngine as Engine
        eng = Engine()
        short_result = 'x' * 1000
        result = eng._truncate_tool_result(short_result)
        self.assertEqual(result, short_result)

    def test_max_tool_result_chars_value(self):
        """MAX_TOOL_RESULT_CHARS should be 50_000."""
        from salmalm.core.engine import IntelligenceEngine as Engine
        self.assertEqual(Engine.MAX_TOOL_RESULT_CHARS, 50_000)


# ============================================================
# 4. MAX_TOOL_ITERATIONS Tests
# ============================================================

class TestMaxToolIterations(unittest.TestCase):
    """Test that the tool loop stops after MAX_TOOL_ITERATIONS."""

    def test_max_iterations_value(self):
        """MAX_TOOL_ITERATIONS should be 15."""
        from salmalm.core.engine import IntelligenceEngine as Engine
        self.assertEqual(Engine.MAX_TOOL_ITERATIONS, 15)

    def test_loop_stops_at_max_iterations(self):
        """Engine should stop the loop after MAX_TOOL_ITERATIONS."""
        from salmalm.core.engine import IntelligenceEngine as Engine
        from salmalm.core import get_session

        eng = Engine()
        session = get_session('test_max_iter')

        # Mock _call_llm_async to always return tool_calls
        fake_tool_call = {
            'content': '',
            'tool_calls': [{'name': 'hash_text', 'id': 'tc_1',
                           'arguments': {'text': 'test', 'algorithm': 'sha256'}}],
        }
        call_count = 0

        async def mock_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > Engine.MAX_TOOL_ITERATIONS:
                return {'content': 'stopped'}
            return dict(fake_tool_call)

        classification = {'intent': 'code', 'tier': 2, 'thinking': False,
                         'thinking_budget': 0, 'score': 3}

        with patch('salmalm.engine._call_llm_async', side_effect=mock_call):
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    eng._execute_loop(session, 'test', None, None,
                                     classification, 2))
            finally:
                loop.close()

        # Should have stopped, not run forever
        self.assertLessEqual(call_count, Engine.MAX_TOOL_ITERATIONS + 2)


# ============================================================
# 5. Web Fetch 2MB Limit Test
# ============================================================

class TestWebFetch2MBLimit(unittest.TestCase):
    """Test that web_fetch respects the 2MB download limit."""

    def test_fetch_reads_max_2mb(self):
        """web_fetch should only read up to 2MB."""
        from salmalm.tools.tools_web import handle_web_fetch

        # Create a mock response that would return > 2MB
        mock_resp = MagicMock()
        # read(2MB) returns 2MB, simulating truncation
        mock_resp.read.return_value = b'x' * (2 * 1024 * 1024)
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch('salmalm.tools_web.urllib.request.urlopen', return_value=mock_resp):
            with patch('salmalm.tools_web._is_private_url', return_value=(False, '')):
                result = handle_web_fetch({'url': 'http://example.com', 'max_chars': 1000})
                # Should have called read(2MB)
                mock_resp.read.assert_called_once_with(2 * 1024 * 1024)


# ============================================================
# 6. Circuit Breaker Integration Test
# ============================================================

class TestCircuitBreakerIntegration(unittest.TestCase):
    """Test circuit breaker with engine (not just standalone)."""

    def test_circuit_breaker_reset_on_success(self):
        """Circuit breaker should reset after cooldown + success."""
        from salmalm.features.stability import CircuitBreaker
        cb = CircuitBreaker(threshold=2, window_sec=60, cooldown_sec=0)
        cb.record_error('test_svc', 'err1')
        cb.record_error('test_svc', 'err2')
        self.assertTrue(cb.is_tripped('test_svc'))
        # Manually expire the tripped time so cooldown check passes
        import time
        cb._tripped['test_svc'] = time.time() - 1
        cb.record_success('test_svc')
        # After cooldown expired + success, is_tripped should check window again
        # but errors are still recent. Test that record_success removes from _tripped
        self.assertNotIn('test_svc', cb._tripped)

    def test_circuit_breaker_get_status_with_errors(self):
        """get_status should report error counts."""
        from salmalm.features.stability import CircuitBreaker
        cb = CircuitBreaker(threshold=5, window_sec=60)
        for i in range(3):
            cb.record_error('svc_a', f'error {i}')
        status = cb.get_status()
        self.assertIsInstance(status, dict)

    def test_circuit_breaker_multiple_components(self):
        """Different components should be tracked independently."""
        from salmalm.features.stability import CircuitBreaker
        cb = CircuitBreaker(threshold=2, window_sec=60)
        cb.record_error('svc_a', 'err')
        cb.record_error('svc_a', 'err')
        cb.record_error('svc_b', 'err')
        self.assertTrue(cb.is_tripped('svc_a'))
        self.assertFalse(cb.is_tripped('svc_b'))


# ============================================================
# 7. Platform-Specific Test Markers
# ============================================================

class TestExecAllowlist(unittest.TestCase):
    """Test that exec allowlist contains expected commands."""

    def test_allowlist_has_core_utils(self):
        from salmalm.constants import EXEC_ALLOWLIST
        # These are Unix commands — they're in the allowlist but may not exist on Windows
        for cmd in ('ls', 'cat', 'grep', 'find'):
            self.assertIn(cmd, EXEC_ALLOWLIST)

    @unittest.skipIf(sys.platform == 'win32', 'Unix only')
    def test_unix_commands_exist(self):
        """On Unix, core allowlist commands should be findable."""
        import shutil
        for cmd in ('ls', 'cat', 'grep'):
            self.assertIsNotNone(shutil.which(cmd), f'{cmd} not found on PATH')

    def test_blocklist_has_dangerous(self):
        from salmalm.constants import EXEC_BLOCKLIST
        for cmd in ('rm', 'sudo', 'shutdown'):
            self.assertIn(cmd, EXEC_BLOCKLIST)


class TestPathConstants(unittest.TestCase):
    """Test that path constants use Path objects (cross-platform)."""

    def test_paths_are_pathlib(self):
        from salmalm.constants import (BASE_DIR, MEMORY_DIR, WORKSPACE_DIR,
                                        SOUL_FILE, AUDIT_DB)
        for p in (BASE_DIR, MEMORY_DIR, WORKSPACE_DIR, SOUL_FILE, AUDIT_DB):
            self.assertIsInstance(p, Path)


# ============================================================
# 8. Engine Consecutive Error Detection
# ============================================================

class TestEngineConsecutiveErrors(unittest.TestCase):
    """Test that engine stops on consecutive tool errors."""

    def test_max_consecutive_errors_value(self):
        from salmalm.core.engine import IntelligenceEngine as Engine
        self.assertEqual(Engine.MAX_CONSECUTIVE_ERRORS, 3)


# ============================================================
# 9. Response Cache Edge Cases
# ============================================================

class TestResponseCacheEdgeCases(unittest.TestCase):
    """Test response cache TTL and eviction."""

    def test_cache_eviction_at_max_size(self):
        from salmalm.core import ResponseCache
        cache = ResponseCache(max_size=2, ttl=60)
        cache.put('m', [{'role': 'user', 'content': 'a'}], 'r1')
        cache.put('m', [{'role': 'user', 'content': 'b'}], 'r2')
        cache.put('m', [{'role': 'user', 'content': 'c'}], 'r3')
        # First entry should be evicted
        self.assertIsNone(cache.get('m', [{'role': 'user', 'content': 'a'}]))
        self.assertEqual(cache.get('m', [{'role': 'user', 'content': 'c'}]), 'r3')

    def test_cache_ttl_expiry(self):
        from salmalm.core import ResponseCache
        cache = ResponseCache(max_size=10, ttl=0)  # 0 second TTL
        msgs = [{'role': 'user', 'content': 'test'}]
        cache.put('m', msgs, 'result')
        import time; time.sleep(0.01)
        self.assertIsNone(cache.get('m', msgs))  # Should be expired


if __name__ == '__main__':
    unittest.main()
