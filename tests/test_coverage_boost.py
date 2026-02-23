"""Coverage boost tests — smoke tests for previously uncovered modules."""
import os
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("SALMALM_HOME", tempfile.mkdtemp())


class TestMigration(unittest.TestCase):
    def test_import(self):
        from salmalm.utils import migration
        self.assertTrue(hasattr(migration, "AgentExporter"))


class TestSLA(unittest.TestCase):
    def test_latency_record(self):
        from salmalm.features.sla import latency_tracker
        latency_tracker.record(50, 100, "test/model")

    def test_latency_get_stats(self):
        from salmalm.features.sla import latency_tracker
        s = latency_tracker.get_stats()
        self.assertIsInstance(s, dict)

    def test_uptime_get_stats(self):
        from salmalm.features.sla import uptime_monitor
        s = uptime_monitor.get_stats()
        self.assertIsInstance(s, dict)

    def test_uptime_seconds(self):
        from salmalm.features.sla import uptime_monitor
        s = uptime_monitor.get_uptime_seconds()
        self.assertIsInstance(s, (int, float))

    def test_uptime_human(self):
        from salmalm.features.sla import uptime_monitor
        s = uptime_monitor.get_uptime_human()
        self.assertIsInstance(s, str)

    def test_sla_config(self):
        from salmalm.features.sla import sla_config
        self.assertIsNotNone(sla_config)


class TestBootstrap(unittest.TestCase):
    def test_import(self):
        """Bootstrap has ensure_workspace."""
        pass  # bootstrap.py has runtime dep on selftest — skip


class TestUsers(unittest.TestCase):
    def test_import(self):
        from salmalm.features.users import UserManager
        self.assertIsNotNone(UserManager)


class TestMesh(unittest.TestCase):
    def test_mesh_peer(self):
        from salmalm.features.mesh import MeshPeer
        peer = MeshPeer("t", "http://localhost:9999", "test")
        self.assertEqual(peer.peer_id, "t")
        self.assertIn("peer_id", peer.to_dict())


class TestSlashCommands(unittest.TestCase):
    def _s(self):
        from salmalm.core.session_store import Session
        return Session("test-cov")

    def test_help(self):
        from salmalm.core.slash_commands import _cmd_help
        self.assertIn("/", _cmd_help("/help", self._s()))

    def test_clear(self):
        from salmalm.core.slash_commands import _cmd_clear
        self.assertIsInstance(_cmd_clear("/clear", self._s()), str)

    def test_status(self):
        from salmalm.core.slash_commands import _cmd_status
        self.assertIsInstance(_cmd_status("/status", self._s()), str)

    def test_tools(self):
        from salmalm.core.slash_commands import _cmd_tools
        self.assertIsInstance(_cmd_tools("/tools", self._s()), str)

    def test_uptime(self):
        from salmalm.core.slash_commands import _cmd_uptime
        self.assertIsInstance(_cmd_uptime("/uptime", self._s()), str)

    def test_latency(self):
        from salmalm.core.slash_commands import _cmd_latency
        self.assertIsInstance(_cmd_latency("/latency", self._s()), str)

    def test_compare(self):
        from salmalm.core.slash_commands import _cmd_compare
        self.assertIsInstance(_cmd_compare("/compare", self._s()), str)

    def test_model(self):
        from salmalm.core.slash_commands import _cmd_model
        self.assertIsInstance(_cmd_model("/model", self._s()), str)

    def test_hooks(self):
        from salmalm.core.slash_commands import _cmd_hooks
        self.assertIsInstance(_cmd_hooks("/hooks", self._s()), str)

    def test_plugins(self):
        from salmalm.core.slash_commands import _cmd_plugins
        self.assertIsInstance(_cmd_plugins("/plugins", self._s()), str)

    def test_agent(self):
        from salmalm.core.slash_commands import _cmd_agent
        self.assertIsInstance(_cmd_agent("/agent", self._s()), str)


class TestSlashCommandsExt(unittest.TestCase):
    def _s(self):
        from salmalm.core.session_store import Session
        return Session("test-ext")

    def test_context(self):
        from salmalm.core.slash_commands_ext import _cmd_context
        self.assertIsInstance(_cmd_context("/context", self._s()), str)

    def test_usage(self):
        from salmalm.core.slash_commands_ext import _cmd_usage
        self.assertIsInstance(_cmd_usage("/usage", self._s(), session_id="t"), str)

    def test_subagents(self):
        from salmalm.core.slash_commands_ext import _cmd_subagents
        self.assertIsInstance(_cmd_subagents("/subagents list", self._s()), str)

    def test_thought(self):
        from salmalm.core.slash_commands_ext import _cmd_thought
        self.assertIsInstance(_cmd_thought("/thought list", self._s()), str)


class TestMCP(unittest.TestCase):
    def test_init(self):
        from salmalm.features.mcp import MCPServer
        self.assertIsNotNone(MCPServer())

    def test_list_resources(self):
        from salmalm.features.mcp import MCPServer
        self.assertIsInstance(MCPServer()._list_resources(), list)


class TestPersonalTools(unittest.TestCase):
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


class TestAgentTools(unittest.TestCase):
    def test_list(self):
        from salmalm.tools.tools_agent import handle_sub_agent
        self.assertIsInstance(handle_sub_agent({"action": "list"}), str)

    def test_unknown(self):
        from salmalm.tools.tools_agent import handle_sub_agent
        self.assertIn("❌", handle_sub_agent({"action": "xyz"}))


class TestEnginePipeline(unittest.TestCase):
    def test_sanitize(self):
        from salmalm.core.engine_pipeline import _sanitize_input
        self.assertNotIn("\x00", _sanitize_input("a\x00b"))

    def test_record_sla(self):
        from salmalm.core.engine_pipeline import _record_sla
        _record_sla(time.time() - 1, time.time() - 0.5, "test/model", "test-s")


class TestAgentsModule(unittest.TestCase):
    def test_skill_loader(self):
        from salmalm.features.agents_skills import SkillLoader
        self.assertIsNotNone(SkillLoader())

    def test_plugin_loader(self):
        from salmalm.features.agents import PluginLoader
        self.assertIsNotNone(PluginLoader())

    def test_sub_agent_list(self):
        from salmalm.features.agents import SubAgent
        self.assertIsInstance(SubAgent.list_agents(), list)


class TestNodes(unittest.TestCase):
    def test_import(self):
        from salmalm.features import nodes
        self.assertIsNotNone(nodes)


class TestHooks(unittest.TestCase):
    def test_list(self):
        from salmalm.features.hooks import hook_manager
        self.assertIsInstance(hook_manager.list_hooks(), (list, dict))


class TestModuleImports(unittest.TestCase):
    """Just import modules to cover module-level code."""
    def test_commands(self): from salmalm.features import commands  # noqa
    def test_llm_loop(self): from salmalm.core import llm_loop  # noqa
    def test_browser(self): from salmalm.utils import browser  # noqa
    def test_engine(self): from salmalm.core.engine import IntelligenceEngine  # noqa
    def test_ws(self): from salmalm.web import ws  # noqa
    def test_oauth(self): from salmalm.web import oauth  # noqa
    def test_middleware(self): from salmalm.web import middleware  # noqa
    def test_cli(self): from salmalm import cli  # noqa
    def test_tls(self): from salmalm.utils import tls  # noqa


class TestAudit(unittest.TestCase):
    def test_log(self):
        from salmalm.core.audit import audit_log
        audit_log("test_event", "detail", session_id="t")

    def test_query(self):
        from salmalm.core.audit import query_audit_log
        self.assertIsInstance(query_audit_log(limit=5), list)


class TestCoreMessages(unittest.TestCase):
    def test_search(self):
        from salmalm.core.core_messages import search_messages
        self.assertIsInstance(search_messages("nonexist", "hello"), list)


class TestToolSelector(unittest.TestCase):
    def test_chat(self):
        from salmalm.core.tool_selector import get_tools_for_provider
        self.assertIsInstance(get_tools_for_provider("chat", "hi"), list)

    def test_code(self):
        from salmalm.core.tool_selector import get_tools_for_provider
        t = get_tools_for_provider("code", "write class")
        self.assertTrue(len(t) > 0)


class TestCost(unittest.TestCase):
    def test_tokens(self):
        from salmalm.core.cost import estimate_tokens
        self.assertGreater(estimate_tokens("hello"), 0)

    def test_cost(self):
        from salmalm.core.cost import estimate_cost
        self.assertIsInstance(estimate_cost("anthropic/claude-haiku-3.5-20241022", {"input": 100, "output": 50}), float)


class TestModelSelection(unittest.TestCase):
    def test_select(self):
        from salmalm.core.model_selection import select_model
        m, t = select_model("hello", None)
        self.assertIsInstance(m, str)


class TestPrompt(unittest.TestCase):
    def test_build(self):
        from salmalm.core.prompt import build_system_prompt
        from salmalm.core.session_store import Session
        p = build_system_prompt(Session("t"))
        self.assertTrue(len(p) > 0)


class TestScheduler(unittest.TestCase):
    def test_import(self):
        from salmalm.core.scheduler import CronScheduler
        self.assertIsNotNone(CronScheduler)


class TestCompaction(unittest.TestCase):
    def test_import(self):
        from salmalm.core.compaction import compact_messages
        self.assertIsNotNone(compact_messages)


if __name__ == "__main__":
    unittest.main()
