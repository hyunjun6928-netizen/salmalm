"""Tests for features/subagents.py"""
import time
import pytest


def test_subagent_task_creation():
    from salmalm.features.subagents import SubAgentTask
    task = SubAgentTask(description="test task")
    assert task.status == "pending"
    assert task.task_id
    assert task.elapsed_s == 0


def test_subagent_task_to_dict():
    from salmalm.features.subagents import SubAgentTask
    task = SubAgentTask(description="test task", model="anthropic/claude-sonnet")
    d = task.to_dict()
    assert d["description"] == "test task"
    assert d["model"] == "anthropic/claude-sonnet"
    assert d["status"] == "pending"


def test_subagent_manager_list_empty():
    from salmalm.features.subagents import SubAgentManager
    mgr = SubAgentManager()
    assert mgr.list_tasks() == []


def test_subagent_manager_kill_nonexistent():
    from salmalm.features.subagents import SubAgentManager
    mgr = SubAgentManager()
    result = mgr.kill("nonexistent")
    assert "not found" in result


def test_subagent_manager_kill_all_empty():
    from salmalm.features.subagents import SubAgentManager
    mgr = SubAgentManager()
    result = mgr.kill_all()
    assert "0" in result


def test_subagent_max_concurrent():
    from salmalm.features.subagents import SubAgentManager, SubAgentTask
    mgr = SubAgentManager()
    mgr._MAX_CONCURRENT = 0  # Block all
    task = mgr.spawn("test")
    assert task.status == "failed"
    assert "Max concurrent" in task.error
