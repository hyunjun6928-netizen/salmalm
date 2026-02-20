"""Tests for advanced subagent management features."""
import json, time, threading
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSubAgentListAndMetadata:
    """Test /subagents list, info, log commands."""

    def test_list_empty(self):
        from salmalm.features.agents import SubAgent
        # Save and restore state
        old = SubAgent._agents.copy()
        SubAgent._agents.clear()
        try:
            result = SubAgent.list_agents()
            assert result == []
        finally:
            SubAgent._agents = old

    def test_list_with_agents(self):
        from salmalm.features.agents import SubAgent
        old = SubAgent._agents.copy()
        SubAgent._agents = {
            'sub-99': {
                'id': 'sub-99', 'task': 'test task', 'label': 'test',
                'status': 'completed', 'started': '2026-01-01T00:00:00',
                'started_ts': 1000.0, 'completed': '2026-01-01T00:00:10',
                'completed_ts': 1010.0, 'token_usage': {'input': 100, 'output': 200},
                'estimated_cost': 0.001, 'archived': False,
            }
        }
        try:
            result = SubAgent.list_agents()
            assert len(result) == 1
            assert result[0]['id'] == 'sub-99'
            assert result[0]['runtime_s'] == 10.0
            assert result[0]['estimated_cost'] == 0.001
        finally:
            SubAgent._agents = old

    def test_list_excludes_archived(self):
        from salmalm.features.agents import SubAgent
        old = SubAgent._agents.copy()
        SubAgent._agents = {
            'sub-100': {
                'id': 'sub-100', 'task': 'archived task', 'label': 'old',
                'status': 'completed.archived.123', 'started': '2026-01-01T00:00:00',
                'started_ts': 1000.0, 'completed': '2026-01-01T00:00:10',
                'completed_ts': 1010.0, 'token_usage': {}, 'estimated_cost': 0,
                'archived': True,
            }
        }
        try:
            result = SubAgent.list_agents()
            assert len(result) == 0
        finally:
            SubAgent._agents = old

    def test_get_info(self):
        from salmalm.features.agents import SubAgent
        old = SubAgent._agents.copy()
        SubAgent._agents = {
            'sub-50': {
                'id': 'sub-50', 'task': 'info test', 'label': 'info-label',
                'status': 'completed', 'model': 'opus',
                'started': '2026-01-01T00:00:00', 'started_ts': 1000.0,
                'completed': '2026-01-01T00:00:05', 'completed_ts': 1005.0,
                'token_usage': {'input': 50, 'output': 100},
                'estimated_cost': 0.002, 'transcript': [{'role': 'user', 'content': 'hi'}],
                'archived': False,
            }
        }
        try:
            info = SubAgent.get_info('sub-50')
            assert 'sub-50' in info
            assert 'info-label' in info
            assert 'opus' in info
            assert '5.0s' in info
        finally:
            SubAgent._agents = old

    def test_get_info_by_index(self):
        from salmalm.features.agents import SubAgent
        old = SubAgent._agents.copy()
        SubAgent._agents = {
            'sub-1': {'id': 'sub-1', 'task': 'first', 'label': 'first',
                      'status': 'completed', 'model': None,
                      'started': '2026-01-01', 'started_ts': 1000.0,
                      'completed': '2026-01-01', 'completed_ts': 1001.0,
                      'token_usage': {}, 'estimated_cost': 0,
                      'transcript': [], 'archived': False}
        }
        try:
            info = SubAgent.get_info('#1')
            assert 'sub-1' in info
        finally:
            SubAgent._agents = old

    def test_get_info_not_found(self):
        from salmalm.features.agents import SubAgent
        info = SubAgent.get_info('sub-nonexistent')
        assert '❌' in info


class TestSubAgentStop:
    def test_stop_running(self):
        from salmalm.features.agents import SubAgent
        old = SubAgent._agents.copy()
        SubAgent._agents = {
            'sub-10': {'id': 'sub-10', 'task': 't', 'status': 'running',
                       'started_ts': time.time(), 'completed': None, 'completed_ts': None}
        }
        try:
            result = SubAgent.stop_agent('sub-10')
            assert '⏹' in result
            assert SubAgent._agents['sub-10']['status'] == 'stopped'
        finally:
            SubAgent._agents = old

    def test_stop_not_running(self):
        from salmalm.features.agents import SubAgent
        old = SubAgent._agents.copy()
        SubAgent._agents = {
            'sub-11': {'id': 'sub-11', 'task': 't', 'status': 'completed',
                       'started_ts': 1000, 'completed': 'x', 'completed_ts': 1001}
        }
        try:
            result = SubAgent.stop_agent('sub-11')
            assert '⚠️' in result
        finally:
            SubAgent._agents = old

    def test_stop_all(self):
        from salmalm.features.agents import SubAgent
        old = SubAgent._agents.copy()
        SubAgent._agents = {
            'sub-20': {'id': 'sub-20', 'task': 't', 'status': 'running',
                       'started_ts': time.time(), 'completed': None, 'completed_ts': None},
            'sub-21': {'id': 'sub-21', 'task': 't', 'status': 'running',
                       'started_ts': time.time(), 'completed': None, 'completed_ts': None},
        }
        try:
            result = SubAgent.stop_agent('all')
            assert '2' in result
        finally:
            SubAgent._agents = old

    def test_stop_not_found(self):
        from salmalm.features.agents import SubAgent
        result = SubAgent.stop_agent('sub-999')
        assert '❌' in result


class TestSubAgentLog:
    def test_get_log_with_transcript(self):
        from salmalm.features.agents import SubAgent
        old = SubAgent._agents.copy()
        SubAgent._agents = {
            'sub-30': {'id': 'sub-30', 'task': 't', 'status': 'completed',
                       'result': 'done', 'transcript': [
                           {'role': 'user', 'content': 'do something'},
                           {'role': 'assistant', 'content': 'ok done'},
                       ]}
        }
        try:
            log = SubAgent.get_log('sub-30')
            assert '📜' in log
            assert 'do something' in log
        finally:
            SubAgent._agents = old

    def test_get_log_no_transcript(self):
        from salmalm.features.agents import SubAgent
        old = SubAgent._agents.copy()
        SubAgent._agents = {
            'sub-31': {'id': 'sub-31', 'task': 't', 'status': 'completed',
                       'result': 'some result', 'transcript': []}
        }
        try:
            log = SubAgent.get_log('sub-31')
            assert 'some result' in log
        finally:
            SubAgent._agents = old


class TestToolPolicy:
    def test_load_default_policy(self):
        from salmalm.features.agents import _load_tool_policy
        policy = _load_tool_policy()
        assert 'deny' in policy
        assert 'sub_agent' in policy['deny']

    def test_filter_tools(self):
        from salmalm.features.agents import _filter_tools_for_subagent
        tools = [
            {'name': 'exec', 'description': 'run'},
            {'name': 'sub_agent', 'description': 'spawn sub'},
            {'name': 'read_file', 'description': 'read'},
            {'name': 'browser', 'description': 'browse'},
        ]
        filtered = _filter_tools_for_subagent(tools)
        names = [t['name'] for t in filtered]
        assert 'exec' in names
        assert 'read_file' in names
        assert 'sub_agent' not in names
        assert 'browser' not in names


class TestMinimalPrompt:
    def test_minimal_mode(self):
        from salmalm.core.prompt import build_system_prompt
        prompt = build_system_prompt(mode='minimal')
        assert 'SubAgent' in prompt
        assert 'Workspace' in prompt
        # Should NOT contain SOUL/USER/HEARTBEAT content markers
        assert len(prompt) < 2000  # Minimal should be short
