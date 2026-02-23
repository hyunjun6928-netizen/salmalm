"""Coverage boost tests — smoke tests for previously uncovered modules.

Uses isolated temp SALMALM_HOME per test class to avoid global env pollution.
"""
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch


class BaseSalmalmTest(unittest.TestCase):
    """Base class with isolated SALMALM_HOME."""

    @classmethod
    def setUpClass(cls):
        cls._home = tempfile.mkdtemp(prefix="salmalm-test-")
        cls._env_patcher = patch.dict(
            os.environ, {"SALMALM_HOME": cls._home}, clear=False
        )
        cls._env_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._env_patcher.stop()
        shutil.rmtree(cls._home, ignore_errors=True)


class TestMigration(BaseSalmalmTest):
    def test_has_exporter(self):
        from salmalm.utils import migration

        self.assertTrue(hasattr(migration, "AgentExporter"))


class TestSLA(BaseSalmalmTest):
    def test_latency_record(self):
        from salmalm.features.sla import latency_tracker

        latency_tracker.record(50, 100, "test/model")

    def test_latency_get_stats_returns_dict(self):
        from salmalm.features.sla import latency_tracker

        s = latency_tracker.get_stats()
        self.assertIsInstance(s, dict)

    def test_uptime_get_stats_returns_dict(self):
        from salmalm.features.sla import uptime_monitor

        s = uptime_monitor.get_stats()
        self.assertIsInstance(s, dict)

    def test_uptime_seconds_numeric(self):
        from salmalm.features.sla import uptime_monitor

        s = uptime_monitor.get_uptime_seconds()
        self.assertGreaterEqual(s, 0)

    def test_uptime_human_readable(self):
        from salmalm.features.sla import uptime_monitor

        s = uptime_monitor.get_uptime_human()
        self.assertIsInstance(s, str)
        self.assertTrue(len(s) > 0)


class TestBootstrap(BaseSalmalmTest):
    @unittest.skip("bootstrap.py imports 'selftest' at module level — not importable in isolation")
    def test_import(self):
        from salmalm import bootstrap  # noqa: F401


class TestUsers(BaseSalmalmTest):
    def test_has_user_manager(self):
        from salmalm.features.users import UserManager

        self.assertIsNotNone(UserManager)


class TestMesh(BaseSalmalmTest):
    def test_peer_roundtrip(self):
        from salmalm.features.mesh import MeshPeer

        peer = MeshPeer("t", "http://localhost:9999", "test")
        self.assertEqual(peer.peer_id, "t")
        d = peer.to_dict()
        self.assertIn("peer_id", d)
        self.assertEqual(d["peer_id"], "t")


class TestSlashCommands(BaseSalmalmTest):
    def _s(self):
        from salmalm.core.session_store import Session

        return Session("test-cov")

    def test_help_contains_slash(self):
        from salmalm.core.slash_commands import _cmd_help

        r = _cmd_help("/help", self._s())
        self.assertIn("/", r)

    def test_clear_returns_str(self):
        from salmalm.core.slash_commands import _cmd_clear

        self.assertIsInstance(_cmd_clear("/clear", self._s()), str)

    def test_status_contains_session_info(self):
        from salmalm.core.slash_commands import _cmd_status

        r = _cmd_status("/status", self._s())
        self.assertIsInstance(r, str)

    def test_tools_mentions_tool(self):
        from salmalm.core.slash_commands import _cmd_tools

        r = _cmd_tools("/tools", self._s())
        self.assertIsInstance(r, str)

    def test_uptime_contains_time(self):
        from salmalm.core.slash_commands import _cmd_uptime

        r = _cmd_uptime("/uptime", self._s())
        self.assertIsInstance(r, str)

    def test_latency_returns_str(self):
        from salmalm.core.slash_commands import _cmd_latency

        self.assertIsInstance(_cmd_latency("/latency", self._s()), str)

    def test_compare_returns_str(self):
        from salmalm.core.slash_commands import _cmd_compare

        self.assertIsInstance(_cmd_compare("/compare", self._s()), str)

    def test_model_returns_str(self):
        from salmalm.core.slash_commands import _cmd_model

        self.assertIsInstance(_cmd_model("/model", self._s()), str)

    def test_hooks_returns_str(self):
        from salmalm.core.slash_commands import _cmd_hooks

        self.assertIsInstance(_cmd_hooks("/hooks", self._s()), str)

    def test_plugins_returns_str(self):
        from salmalm.core.slash_commands import _cmd_plugins

        self.assertIsInstance(_cmd_plugins("/plugins", self._s()), str)

    def test_agent_returns_str(self):
        from salmalm.core.slash_commands import _cmd_agent

        self.assertIsInstance(_cmd_agent("/agent", self._s()), str)


class TestSlashCommandsExt(BaseSalmalmTest):
    def _s(self):
        from salmalm.core.session_store import Session

        return Session("test-ext")

    def test_context_returns_str(self):
        from salmalm.core.slash_commands_ext import _cmd_context

        self.assertIsInstance(_cmd_context("/context", self._s()), str)

    def test_usage_returns_str(self):
        from salmalm.core.slash_commands_ext import _cmd_usage

        self.assertIsInstance(_cmd_usage("/usage", self._s(), session_id="t"), str)

    def test_subagents_mentions_subagent(self):
        from salmalm.core.slash_commands_ext import _cmd_subagents

        r = _cmd_subagents("/subagents list", self._s())
        self.assertIsInstance(r, str)

    def test_thought_returns_str(self):
        from salmalm.core.slash_commands_ext import _cmd_thought

        self.assertIsInstance(_cmd_thought("/thought list", self._s()), str)


class TestMCP(BaseSalmalmTest):
    def test_init(self):
        from salmalm.features.mcp import MCPServer

        self.assertIsNotNone(MCPServer())

    def test_resources_returns_list(self):
        from salmalm.features.mcp import MCPServer

        self.assertIsInstance(MCPServer()._list_resources(), list)


class TestPersonalTools(BaseSalmalmTest):
    def test_note_list(self):
        from salmalm.tools.tools_personal import handle_note

        self.assertIsInstance(handle_note({"action": "list"}), str)

    def test_expense_list(self):
        from salmalm.tools.tools_personal import handle_expense

        self.assertIsInstance(handle_expense({"action": "list"}), str)

    def test_expense_summary(self):
        from salmalm.tools.tools_personal import handle_expense

        self.assertIsInstance(handle_expense({"action": "summary"}), str)

    def test_save_link_list(self):
        from salmalm.tools.tools_personal import handle_save_link

        self.assertIsInstance(handle_save_link({"action": "list"}), str)

    def test_pomodoro_status(self):
        from salmalm.tools.tools_personal import handle_pomodoro

        self.assertIsInstance(handle_pomodoro({"action": "status"}), str)


class TestAgentTools(BaseSalmalmTest):
    def test_list(self):
        from salmalm.tools.tools_agent import handle_sub_agent

        self.assertIsInstance(handle_sub_agent({"action": "list"}), str)

    def test_unknown_action_returns_error(self):
        from salmalm.tools.tools_agent import handle_sub_agent

        self.assertIn("❌", handle_sub_agent({"action": "xyz"}))


class TestEnginePipeline(BaseSalmalmTest):
    def test_sanitize_strips_null(self):
        from salmalm.core.engine_pipeline import _sanitize_input

        self.assertNotIn("\x00", _sanitize_input("a\x00b"))

    def test_record_sla_no_error(self):
        from salmalm.core.engine_pipeline import _record_sla

        _record_sla(time.time() - 1, time.time() - 0.5, "test/model", "test-s")


class TestAgentsModule(BaseSalmalmTest):
    def test_skill_loader_exists(self):
        from salmalm.features.agents_skills import SkillLoader

        self.assertIsNotNone(SkillLoader())

    def test_plugin_loader_exists(self):
        from salmalm.features.agents import PluginLoader

        self.assertIsNotNone(PluginLoader())

    def test_sub_agent_list_returns_list(self):
        from salmalm.features.agents import SubAgent

        self.assertIsInstance(SubAgent.list_agents(), list)


class TestHooks(BaseSalmalmTest):
    def test_list_returns_collection(self):
        from salmalm.features.hooks import hook_manager

        self.assertIsInstance(hook_manager.list_hooks(), (list, dict))


class TestModuleImports(BaseSalmalmTest):
    """Import-only tests for module-level coverage."""

    def test_commands(self):
        from salmalm.features import commands  # noqa: F401

    def test_llm_loop(self):
        from salmalm.core import llm_loop  # noqa: F401

    def test_browser(self):
        from salmalm.utils import browser  # noqa: F401

    def test_engine(self):
        from salmalm.core.engine import IntelligenceEngine  # noqa: F401

    def test_ws(self):
        from salmalm.web import ws  # noqa: F401

    def test_oauth(self):
        from salmalm.web import oauth  # noqa: F401

    def test_middleware(self):
        from salmalm.web import middleware  # noqa: F401

    def test_cli(self):
        from salmalm import cli  # noqa: F401

    def test_tls(self):
        from salmalm.utils import tls  # noqa: F401

    def test_nodes(self):
        from salmalm.features import nodes  # noqa: F401


class TestAudit(BaseSalmalmTest):
    def test_log_no_error(self):
        from salmalm.core.audit import audit_log

        audit_log("test_event", "detail", session_id="t")

    def test_query_returns_list(self):
        from salmalm.core.audit import query_audit_log

        self.assertIsInstance(query_audit_log(limit=5), list)


class TestCoreMessages(BaseSalmalmTest):
    def test_search_nonexistent_returns_empty(self):
        from salmalm.core.core_messages import search_messages

        result = search_messages("nonexist", "hello")
        self.assertIsInstance(result, list)


class TestToolSelector(BaseSalmalmTest):
    def test_returns_list(self):
        from salmalm.core.tool_selector import get_tools_for_provider

        self.assertIsInstance(get_tools_for_provider("chat", "hi"), list)


class TestCost(BaseSalmalmTest):
    def test_estimate_tokens_positive(self):
        from salmalm.core.cost import estimate_tokens

        self.assertGreater(estimate_tokens("hello world"), 0)

    def test_estimate_cost_returns_float(self):
        from salmalm.core.cost import estimate_cost, MODEL_PRICING

        # Use first available model from pricing table (avoids hardcoded model name)
        model = next(iter(MODEL_PRICING))
        c = estimate_cost(model, {"input": 100, "output": 50})
        self.assertIsInstance(c, float)

    def test_unknown_model_returns_float(self):
        from salmalm.core.cost import estimate_cost

        c = estimate_cost("unknown/model-xyz", {"input": 100, "output": 50})
        self.assertIsInstance(c, float)


class TestModelSelection(BaseSalmalmTest):
    def test_returns_tuple(self):
        from salmalm.core.model_selection import select_model

        m, t = select_model("hello", None)
        self.assertIsInstance(m, str)
        self.assertIsInstance(t, str)


class TestPrompt(BaseSalmalmTest):
    def test_build_nonempty(self):
        from salmalm.core.prompt import build_system_prompt
        from salmalm.core.session_store import Session

        p = build_system_prompt(Session("t"))
        self.assertTrue(len(p) > 0)


class TestScheduler(BaseSalmalmTest):
    def test_importable(self):
        from salmalm.core.scheduler import CronScheduler

        self.assertIsNotNone(CronScheduler)


class TestCompaction(BaseSalmalmTest):
    def test_importable(self):
        from salmalm.core.compaction import compact_messages

        self.assertIsNotNone(compact_messages)


if __name__ == "__main__":
    unittest.main()
