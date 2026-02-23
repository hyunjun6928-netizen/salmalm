"""Agent tools: sub_agent, skill_manage, plugin_manage, cron_manage, mcp_manage, node_manage."""

import json
from salmalm.tools.tool_registry import register
from salmalm.core import SubAgent, SkillLoader


@register("sub_agent")
def handle_sub_agent(args: dict) -> str:
    """Handle sub agent."""
    action = args.get("action", "list")
    if action == "spawn":
        task = args.get("task", "")
        if not task:
            return "❌ Task is required"
        model = args.get("model")
        agent_id = SubAgent.spawn(task, model=model)
        return f"🤖 Sub-agent spawned: [{agent_id}]\nTask: {task[:100]}\nWill notify on completion."
    elif action == "list":
        agents = SubAgent.list_agents()
        if not agents:
            return "📋 No running sub-agents."
        lines = []
        for a in agents:
            icon = "🟢" if a["status"] == "running" else "✅" if a["status"] == "completed" else "❌"
            lines.append(f"{icon} [{a['id']}] {a['task']} — {a['status']}")
        return "\n".join(lines)
    elif action == "result":
        agent_id = args.get("agent_id", "")
        info = SubAgent.get_result(agent_id)
        if "error" in info:
            return f"❌ {info['error']}"
        status = info["status"]
        if status == "running":
            return f"⏳ [{agent_id}] Still running.\nStarted: {info['started']}"
        result = info.get("result", "(no result)")
        return f"{'✅' if status == 'completed' else '❌'} [{agent_id}] {status}\nStarted: {info['started']}\nFinished: {info['completed']}\n\n{result[:3000]}"
    elif action == "send":
        agent_id = args.get("agent_id", "")
        message = args.get("message", "")
        if not agent_id or not message:
            return "❌ agent_id and message are required"
        result = SubAgent.send_message(agent_id, message)
        return result
    elif action == "stop" or action == "kill":
        agent_id = args.get("agent_id", "all")
        return SubAgent.stop_agent(agent_id)
    elif action == "log":
        agent_id = args.get("agent_id", "")
        if not agent_id:
            return "❌ agent_id is required"
        limit = args.get("limit", 20)
        return SubAgent.get_log(agent_id, limit=limit)
    elif action == "info":
        agent_id = args.get("agent_id", "")
        if not agent_id:
            return "❌ agent_id is required"
        return SubAgent.get_info(agent_id)
    elif action == "steer":
        # OpenClaw-style steering: send guidance to a running/completed sub-agent
        agent_id = args.get("agent_id", "")
        message = args.get("message", "")
        if not agent_id or not message:
            return "❌ agent_id and message are required for steering"
        # Use the subagent_manager's steer if available, else fall back to send
        try:
            from salmalm.features.subagents import subagent_manager

            return subagent_manager.steer(agent_id, message)
        except Exception:
            return SubAgent.send_message(agent_id, message)
    return f"❌ Unknown action: {action}. Available: spawn, list, result, send, stop, log, info, steer"


@register("skill_manage")
def handle_skill_manage(args: dict) -> str:
    """Handle skill manage."""
    action = args.get("action", "list")
    if action == "list":
        skills = SkillLoader.scan()
        if not skills:
            return "📚 No skills registered.\nCreate a skill directory in skills/ and add SKILL.md."
        lines = []
        for s in skills:
            lines.append(f"📚 **{s['name']}** ({s['dir_name']})\n   {s['description']}\n   Size: {s['size']}chars")
        return "\n".join(lines)
    elif action == "load":
        skill_name = args.get("skill_name", "")
        content = SkillLoader.load(skill_name)
        if not content:
            return f'❌ Skill "{skill_name}" not found'
        return f"📚 Skill loaded: {skill_name}\n\n{content[:5000]}"
    elif action == "match":
        query = args.get("query", "")
        content = SkillLoader.match(query)
        if not content:
            return "No matching skill found."
        return f"📚 Auto-matched skill:\n\n{content[:5000]}"
    elif action == "install":
        url = args.get("url", "")
        if not url:
            return "❌ url is required (Git URL or GitHub shorthand user/repo)"
        return SkillLoader.install(url)
    elif action == "uninstall":
        skill_name = args.get("skill_name", "")
        if not skill_name:
            return "❌ skill_name is required"
        return SkillLoader.uninstall(skill_name)
    return f"❌ Unknown action: {action}"


@register("plugin_manage")
def handle_plugin_manage(args: dict) -> str:
    """Handle plugin manage."""
    from salmalm.core import PluginLoader

    action = args.get("action", "list")
    if action == "list":
        _tools = PluginLoader.get_all_tools()  # noqa: F841
        plugins = PluginLoader._plugins
        if not plugins:
            return "🔌 No plugins loaded. Add .py files to plugins/ directory."
        lines = ["🔌 **Plugins:**"]
        for name_, info in plugins.items():
            lines.append(f"  📦 {name_} — {len(info['tools'])} tools ({info['path']})")
            for t in info["tools"]:
                lines.append(f"    🔧 {t['name']}: {t['description'][:60]}")
        return "\n".join(lines)
    elif action == "reload":
        count = PluginLoader.reload()
        return f"🔌 Plugins reloaded: {count} tools loaded"
    return f"❌ Unknown action: {action}"


@register("cron_manage")
def handle_cron_manage(args: dict) -> str:
    """Handle cron manage."""
    from salmalm.core import _llm_cron

    if not _llm_cron:
        return "❌ LLM cron manager not initialized"
    action = args.get("action", "list")
    if action == "list":
        jobs = _llm_cron.list_jobs()
        if not jobs:
            return "⏰ No scheduled jobs."
        lines = ["⏰ **Scheduled Jobs:**"]
        for j in jobs:
            status = "✅" if j["enabled"] else "⏸️"
            lines.append(f"{status} [{j['id']}] {j['name']} — {j['schedule']} (runs: {j['run_count']})")
        return "\n".join(lines)
    elif action == "add":
        name_ = args.get("name", "Untitled")
        prompt = args.get("prompt", "")
        schedule = args.get("schedule", {})
        if not prompt:
            return "❌ prompt is required"
        if not schedule:
            return "❌ schedule is required (kind: cron/every/at)"
        model = args.get("model")
        job = _llm_cron.add_job(name_, schedule, prompt, model=model)
        return f"⏰ Job registered: [{job['id']}] {name_}"
    elif action == "remove":
        job_id = args.get("job_id", "")
        if _llm_cron.remove_job(job_id):
            return f"⏰ Job removed: {job_id}"
        return f"❌ Job not found: {job_id}"
    elif action == "toggle":
        job_id = args.get("job_id", "")
        for j in _llm_cron.jobs:
            if j["id"] == job_id:
                j["enabled"] = not j["enabled"]
                _llm_cron.save_jobs()
                return f"⏰ {j['name']}: {'enabled' if j['enabled'] else 'disabled'}"
        return f"❌ Job not found: {job_id}"
    return f"❌ Unknown action: {action}"


@register("mcp_manage")
def handle_mcp_manage(args: dict) -> str:
    """Handle mcp manage."""
    from salmalm.features.mcp import mcp_manager

    action = args.get("action", "list")
    if action == "list":
        servers = mcp_manager.list_servers()
        if not servers:
            return '🔌 No MCP servers connected. mcp_manage(action="add", name="...", command="...") to add.'
        lines = ["🔌 **MCP Servers:**"]
        for s in servers:
            status = "🟢" if s["connected"] else "🔴"
            lines.append(f"  {status} {s['name']} — {s['tools']} tools ({' '.join(s['command'])})")
        return "\n".join(lines)
    elif action == "add":
        sname = args.get("name", "")
        cmd_str = args.get("command", "")
        if not sname or not cmd_str:
            return "❌ name and command are required"
        cmd_list = cmd_str.split()
        env = args.get("env", {})
        ok = mcp_manager.add_server(sname, cmd_list, env=env)
        if ok:
            mcp_manager.save_config()
            tools_count = len([t for t in mcp_manager.get_all_tools() if t.get("_mcp_server") == sname])
            return f"🔌 MCP server added: {sname} ({tools_count} tools)"
        return f"❌ MCP server connection failed: {sname}"
    elif action == "remove":
        sname = args.get("name", "")
        mcp_manager.remove_server(sname)
        mcp_manager.save_config()
        return f"🔌 MCP server removed: {sname}"
    elif action == "tools":
        all_mcp = mcp_manager.get_all_tools()
        if not all_mcp:
            return "🔌 No MCP tools (no servers connected)"
        lines = [f"🔌 **MCP Tools ({len(all_mcp)}):**"]
        for t in all_mcp:
            lines.append(f"  🔧 {t['name']}: {t['description'][:80]}")
        return "\n".join(lines)
    return f"❌ Unknown action: {action}"


@register("node_manage")
def handle_node_manage(args: dict) -> str:
    """Handle node manage."""
    from salmalm.features.nodes import node_manager

    action = args.get("action", "list")
    if action == "list":
        nodes = node_manager.list_nodes()
        if not nodes:
            return '📡 No nodes registered. node_manage(action="add", name="...", host="...") to add'
        lines = ["📡 **Nodes:**"]
        for n in nodes:
            lines.append(f"  {'🔗' if n['type'] == 'ssh' else '🌐'} {n['name']} ({n.get('host', n.get('url', '?'))})")
        return "\n".join(lines)
    elif action == "add":
        nname = args.get("name", "")
        ntype = args.get("type", "ssh")
        if not nname:
            return "❌ name is required"
        if ntype == "ssh":
            host = args.get("host", "")
            if not host:
                return "❌ host is required"
            node_manager.add_ssh_node(
                nname, host, user=args.get("user", "root"), port=args.get("port", 22), key=args.get("key")
            )
            return f"📡 SSH node added: {nname}"
        elif ntype == "http":
            url = args.get("url", "")
            if not url:
                return "❌ url is required"
            node_manager.add_http_node(nname, url)
            return f"📡 HTTP node added: {nname}"
        return f"❌ Unknown type: {ntype}"
    elif action == "remove":
        nname = args.get("name", "")
        if node_manager.remove_node(nname):
            return f"📡 Node removed: {nname}"
        return f"❌ Node not found: {nname}"
    elif action == "run":
        nname = args.get("name", "")
        cmd = args.get("command", "")
        if not nname or not cmd:
            return "❌ name and command are required"
        result = node_manager.run_on(nname, cmd)
        return json.dumps(result, ensure_ascii=False)[:5000]
    elif action == "status":
        nname = args.get("name")
        if nname:
            node = node_manager.get_node(nname)
            if not node:
                return f"❌ Node not found: {nname}"
            return json.dumps(node.status(), ensure_ascii=False)[:3000]
        return json.dumps(node_manager.status_all(), ensure_ascii=False)[:5000]
    elif action == "wake":
        mac = args.get("mac", "")
        if not mac:
            return "❌ mac is required"
        result = node_manager.wake_on_lan(mac)
        return json.dumps(result, ensure_ascii=False)
    return f"❌ Unknown action: {action}"


@register("rag_search")
def handle_rag_search(args: dict) -> str:
    """Handle rag search."""
    from salmalm.features.rag import rag_engine

    query = args.get("query", "")
    if not query:
        return "❌ query is required"
    max_results = args.get("max_results", 5)
    results = rag_engine.search(query, max_results=max_results)
    if not results:
        return f'🔍 "{query}" No results for'
    lines = [f'🔍 **"{query}" Results ({len(results)}):**']
    for r in results:
        lines.append(f"\n📄 **{r['source']}** (L{r['line']}, score: {r['score']})")
        lines.append(r["text"][:300])
    stats = rag_engine.get_stats()
    lines.append(f"\n📊 Index: {stats['total_chunks']}chunks, {stats['unique_terms']}terms, {stats['db_size_kb']}KB")
    return "\n".join(lines)
