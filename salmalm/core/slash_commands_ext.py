"""Extended slash commands: context, usage, thought, subagents."""

import json
import logging
import time
from typing import Any

log = logging.getLogger(__name__)

from salmalm.core.cost import estimate_tokens, estimate_cost  # noqa: E402
from salmalm.constants import VERSION
from salmalm.core.core import track_usage  # noqa: E402  # noqa: E402


def _cmd_context(cmd: str, session, **_):
    """Show context window token usage breakdown."""
    sub = cmd.strip().split()
    detail_mode = len(sub) > 1 and sub[1] == "detail"

    from salmalm.core.prompt import build_system_prompt

    sys_prompt = build_system_prompt(full=False)
    sys_tokens = estimate_tokens(sys_prompt)

    # Tool schemas
    tool_tokens = 0
    tool_text = ""
    tool_details = []
    try:
        from salmalm.tools import TOOL_DEFINITIONS

        for t in TOOL_DEFINITIONS:
            schema_text = json.dumps(
                {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
            )
            tool_details.append((t["name"], len(schema_text), estimate_tokens(schema_text)))
        tool_text = json.dumps(
            [
                {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
                for t in TOOL_DEFINITIONS
            ]
        )
        tool_tokens = estimate_tokens(tool_text)
    except Exception as e:  # noqa: broad-except
        TOOL_DEFINITIONS = []

    # Injected files breakdown
    from salmalm.constants import SOUL_FILE, AGENTS_FILE, MEMORY_FILE, USER_FILE, BASE_DIR
    from salmalm.core.prompt import USER_SOUL_FILE

    file_details = []
    for label, path in [
        ("SOUL.md", SOUL_FILE),
        ("USER_SOUL.md", USER_SOUL_FILE),
        ("AGENTS.md", AGENTS_FILE),
        ("MEMORY.md", MEMORY_FILE),
        ("USER.md", USER_FILE),
        ("TOOLS.md", BASE_DIR / "TOOLS.md"),
    ]:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            file_details.append((label, len(raw), estimate_tokens(raw)))

    # Conversation history
    history_text = ""
    for m in session.messages:
        c = m.get("content", "")
        if isinstance(c, str):
            history_text += c
        elif isinstance(c, list):
            for block in c:
                if isinstance(block, dict):
                    history_text += block.get("content", "") or block.get("text", "") or ""
    history_tokens = estimate_tokens(history_text)

    total = sys_tokens + tool_tokens + history_tokens

    lines = [
        f"""📊 **Context Window Usage**

| Component | Chars | ~Tokens |
|-----------|------:|--------:|
| System Prompt | {len(sys_prompt):,} | {sys_tokens:,} |
| Tool Schemas ({len(TOOL_DEFINITIONS)}) | {len(tool_text):,} | {tool_tokens:,} |
| Conversation ({len(session.messages)} msgs) | {len(history_text):,} | {history_tokens:,} |
| **Total** | | **{total:,}** |"""
    ]

    if detail_mode:
        lines.append("\n📁 **Injected Files**")
        for label, chars, tokens in sorted(file_details, key=lambda x: -x[2]):
            lines.append(f"  • {label}: {chars:,} chars / ~{tokens:,} tokens")

        lines.append("\n🔧 **Tool Schemas (top 10 by size)**")
        for name, chars, tokens in sorted(tool_details, key=lambda x: -x[2])[:10]:
            lines.append(f"  • {name}: {chars:,} chars / ~{tokens:,} tokens")

    lines.append("\n💡 Intent-based injection reduces tools to ≤15 per call.")
    lines.append("🔒 Prompt caching: system prompt + tool schemas marked ephemeral.")
    return "\n".join(lines)


def _cmd_usage(cmd: str, session, *, session_id="", **_) -> str:
    """Handle /usage tokens|full|cost|off commands."""
    parts = cmd.strip().split()
    sub = parts[1] if len(parts) > 1 else "tokens"
    from salmalm.core.slash_commands import _get_session_usage

    su = _get_session_usage(session_id)

    if sub == "off":
        su["mode"] = "off"
        return "📊 Usage footer: **OFF**"
    elif sub == "tokens":
        su["mode"] = "tokens"
        if not su["responses"]:
            return "📊 Usage tracking: **ON** (tokens mode). No responses yet."
        last = su["responses"][-1]
        return (
            f"📊 Usage mode: **tokens**\n"
            f"Last: in={last['input']:,} out={last['output']:,} "
            f"(cache_read={last['cache_read']:,} cache_write={last['cache_write']:,})"
        )
    elif sub == "full":
        su["mode"] = "full"
        if not su["responses"]:
            return "📊 Usage tracking: **ON** (full mode). No responses yet."
        lines = ["📊 **Usage (full)**\n"]
        for i, r in enumerate(su["responses"][-10:], 1):
            model_short = r["model"].split("/")[-1][:20]
            lines.append(f"{i}. {model_short} | in:{r['input']:,} out:{r['output']:,} | ${r['cost']:.4f}")
        lines.append(f"\n💰 Session total: **${su['total_cost']:.4f}**")
        return "\n".join(lines)
    elif sub == "cost":
        lines = ["💰 **Session Cost Summary**\n"]
        if not su["responses"]:
            lines.append("No API calls yet.")
        else:
            lines.append(f"Requests: {len(su['responses'])}")
            total_in = sum(r["input"] for r in su["responses"])
            total_out = sum(r["output"] for r in su["responses"])
            total_cache_read = sum(r["cache_read"] for r in su["responses"])
            total_cache_write = sum(r["cache_write"] for r in su["responses"])
            lines.append(
                f"Input tokens: {total_in:,} (cache read: {total_cache_read:,}, cache write: {total_cache_write:,})"
            )
            lines.append(f"Output tokens: {total_out:,}")
            lines.append(f"**Total cost: ${su['total_cost']:.4f}**")
            if total_cache_read > 0:
                # Estimate savings from cache
                pricing = _get_pricing(su["responses"][-1]["model"])
                saved = total_cache_read * (pricing["input"] - pricing["cache_read"]) / 1_000_000
                lines.append(f"💡 Cache savings: ~${saved:.4f}")
        return "\n".join(lines)
    else:
        return "📊 `/usage tokens|full|cost|off`"


def _subagent_list(SubAgent) -> str:
    """List active sub-agents."""
    agents = SubAgent.list_agents()
    if not agents:
        return "🤖 No active sub-agents."
    lines = ["🤖 **Sub-agents**\n"]
    for i, a in enumerate(agents, 1):
        icon = {"running": "🔄", "completed": "✅", "error": "❌", "stopped": "⏹"}.get(a["status"].split(".")[0], "❓")
        lines.append(
            f"{icon} #{i} `{a['id']}` — {a['label']} [{a['status']}] ({a['runtime_s']}s, ${a.get('estimated_cost', 0):.4f})"
        )
    return "\n".join(lines)


def _cmd_subagents(cmd: str, session, **_) -> str:
    """Handle /subagents commands: list, spawn, stop, steer, log, info, collect."""
    from salmalm.features.agents import SubAgent

    parts = cmd.split(maxsplit=2)
    sub = parts[1] if len(parts) > 1 else "list"
    arg = parts[2] if len(parts) > 2 else ""

    if sub == "list":
        return _subagent_list(SubAgent)

    elif sub == "spawn":
        if not arg:
            return "❌ Usage: /subagents spawn <task description>"
        # Parse optional --model flag
        model = None
        if " --model " in arg:
            arg, _, model = arg.rpartition(" --model ")
            model = model.strip() or None
        agent_id = SubAgent.spawn(arg.strip(), model=model)
        return f"🤖 Sub-agent spawned: `{agent_id}`\nTask: {arg[:100]}\nWill notify on completion."

    elif sub == "stop":
        if not arg:
            return "❌ Usage: /subagents stop <id|#N|all>"
        return SubAgent.stop_agent(arg)

    elif sub == "steer":
        # OpenClaw-style: send guidance to a running/completed sub-agent
        steer_parts = arg.split(maxsplit=1)
        agent_id = steer_parts[0] if steer_parts else ""
        message = steer_parts[1] if len(steer_parts) > 1 else ""
        if not agent_id or not message:
            return "❌ Usage: /subagents steer <id|#N> <message>"
        # Try subagent_manager first, fall back to SubAgent.send_message
        try:
            from salmalm.features.subagents import subagent_manager

            return subagent_manager.steer(agent_id, message)
        except Exception as e:  # noqa: broad-except
            return SubAgent.send_message(agent_id, message)

    elif sub == "log":
        log_parts = arg.split(maxsplit=1)
        agent_id = log_parts[0] if log_parts else ""
        limit = int(log_parts[1]) if len(log_parts) > 1 and log_parts[1].isdigit() else 20
        if not agent_id:
            return "❌ Usage: /subagents log <id|#N> [limit]"
        return SubAgent.get_log(agent_id, limit)

    elif sub == "info":
        if not arg:
            return "❌ Usage: /subagents info <id|#N>"
        return SubAgent.get_info(arg)

    elif sub == "collect":
        # OpenClaw-style: collect all completed results
        from salmalm.features.subagents import subagent_manager

        results = subagent_manager.collect_results(parent_session="web")
        if not results:
            return "📋 No uncollected sub-agent results."
        lines = ["📋 **Completed Sub-agent Results**\n"]
        for r in results:
            lines.append(
                f"✅ `{r['task_id']}` — {r['description']}\n"
                f"   {r['result'][:300]}{'...' if len(r.get('result', '')) > 300 else ''}"
            )
        return "\n".join(lines)

    return "❌ Usage: /subagents spawn|list|stop|steer|log|info|collect <args>"


def _cmd_thought(cmd: str, session, **_) -> str:
    """Cmd thought."""
    from salmalm.features.thoughts import thought_stream, _format_thoughts, _format_stats

    text = cmd.strip()
    # Remove /think prefix
    if text.startswith("/thought"):
        text = text[8:].strip()
    elif text.startswith("/think"):
        # Only handle /think subcommands here, not /think <question> for deep reasoning
        text = text[6:].strip()

    if not text:
        return "❌ Usage: /think <내용> | /think list | /think search <쿼리> | /think tag <태그> | /think stats"

    parts = text.split(None, 1)
    sub = parts[0]
    arg = parts[1].strip() if len(parts) > 1 else ""

    if sub == "list":
        n = int(arg) if arg.isdigit() else 10
        thoughts = thought_stream.list_recent(n)
        return _format_thoughts(thoughts, f"💭 **최근 {n}개 생각**\n")
    elif sub == "search":
        if not arg:
            return "❌ Usage: /think search <쿼리>"
        results = thought_stream.search(arg)
        return _format_thoughts(results, f"🔍 **검색: {arg}**\n")
    elif sub == "tag":
        if not arg:
            return "❌ Usage: /think tag <태그>"
        results = thought_stream.by_tag(arg)
        return _format_thoughts(results, f"🏷️ **태그: #{arg}**\n")
    elif sub == "timeline":
        results = thought_stream.timeline(arg if arg else None)
        date_label = arg if arg else "오늘"
        return _format_thoughts(results, f"📅 **타임라인: {date_label}**\n")
    elif sub == "stats":
        return _format_stats(thought_stream.stats())
    elif sub == "export":
        md = thought_stream.export_markdown()
        return md
    else:
        # It's a thought to record — detect mood first
        thought_text = text
        mood = "neutral"
        try:
            from salmalm.features.mood import mood_detector

            mood, _ = mood_detector.detect(thought_text)
        except Exception as e:  # noqa: broad-except
            log.debug(f"Suppressed: {e}")
        tid = thought_stream.add(thought_text, mood=mood)
        tags = ""
        import re as _re2

        found_tags = _re2.findall(r"#(\w+)", thought_text)
        if found_tags:
            tags = f" 🏷️ {', '.join('#' + t for t in found_tags)}"
        return f"💭 생각 #{tid} 기록됨{tags}"
