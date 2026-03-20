"""Slash command handlers — extracted from engine.py for maintainability."""

from __future__ import annotations

import asyncio
from typing import Dict

from salmalm.constants import VERSION, COMMAND_MODEL, MODEL_ALIASES as _CONST_ALIASES  # noqa: F401

MODEL_ALIASES = {"auto": None, **_CONST_ALIASES}
from salmalm.core.cost import estimate_tokens, estimate_cost, MODEL_PRICING, get_pricing as _get_pricing  # noqa: F401
from salmalm.security.crypto import log  # noqa: F401
from salmalm.features.slash_commands_ext import (  # noqa: F401
    _cmd_context,
    _cmd_usage,
    _cmd_thought,
    _cmd_subagents,
    _subagent_list,
)


def _get_engine():
    """Lazy import to avoid circular dependency."""
    from salmalm.core.intelligence_engine import _get_engine as _ie_get_engine; _engine = _ie_get_engine()

    return _engine


def _get_router():
    """Lazy import router to avoid circular dependency."""
    from salmalm.core import router

    return router


def _lazy_compact_messages():
    """Lazy compact messages."""
    from salmalm.core import compact_messages

    return compact_messages


def _lazy_prune_context():
    """Lazy prune context."""
    from salmalm.core.session_manager import prune_context

    return prune_context


def _lazy_build_system_prompt(**kwargs):
    """Lazy build system prompt."""
    from salmalm.core.prompt import build_system_prompt

    return build_system_prompt(**kwargs)


# Session usage tracking (shared state)
_session_usage: Dict[str, dict] = {}


def _get_session_usage(session_id: str) -> dict:
    """Get session usage."""
    if session_id not in _session_usage:
        _session_usage[session_id] = {"responses": [], "mode": "off", "total_cost": 0.0}
    return _session_usage[session_id]


def record_response_usage(session_id: str, model: str, usage: dict) -> None:
    """Record per-response usage for /usage command."""
    su = _get_session_usage(session_id)
    cost = estimate_cost(model, usage)
    su["responses"].append(
        {
            "model": model,
            "input": usage.get("input", 0),
            "output": usage.get("output", 0),
            "cache_read": usage.get("cache_read_input_tokens", 0),
            "cache_write": usage.get("cache_creation_input_tokens", 0),
            "cost": cost,
        }
    )
    su["total_cost"] += cost


def _cmd_clear(cmd: str, session, **_) -> str:
    """Cmd clear."""
    session.messages = [m for m in session.messages if m["role"] == "system"][:1]
    return "Conversation cleared."


def _cmd_help(cmd: str, session, **_) -> str:
    """Cmd help."""
    from salmalm.tools import TOOL_DEFINITIONS

    tool_count = len(TOOL_DEFINITIONS)
    return f"""😈 **SalmAlm v{VERSION}** — Personal AI Gateway

💬 **대화 (Chat)**
/clear — 대화 초기화 (Clear conversation)
/model <name> — 모델 변경 (Switch model)
/model — 현재 모델 확인 (Current model)

🧠 **추론 (Reasoning)**
/think <질문> — 심층 추론 모드 (Deep reasoning)
/plan <질문> — 계획 수립 후 실행 (Plan → Execute)
/compare <질문> — 멀티모델 비교 (Multi-model compare)

📊 **모니터링 (Status)**
/status — 사용량 + 비용 (Usage & Cost)
/context — 컨텍스트 윈도우 (Context window)
/uptime — 가동 시간 (Uptime)
/latency — 응답 속도 (Latency)
/health detail — 상세 헬스 리포트

🛡️ **보안 & 관리 (Security)**
/security — 보안 감사 (Security audit)
/export — 데이터 내보내기 (Export data)

🤖 **에이전트 (Agents)**
/subagents spawn <task> — 서브에이전트 생성
/subagents list — 목록 보기
/subagents stop <id> — 중지

🧬 **개인화 (Personalization)**
/evolve — 프롬프트 자기진화 (Self-evolving prompt)
/mood — 감정 인식 응답 (Mood-aware)
/soul — 페르소나 설정 (Persona)
/thought <내용> — 생각 기록 (Record thought)

🔧 **도구 ({tool_count} Tools)**
파일 읽기/쓰기, 코드 실행, 웹 검색, RAG, 시스템 모니터, 크론, 이미지 분석, TTS ...

💡 그냥 자연어로 말하세요. "파일 읽어줘", "웹 검색해줘", "코드 짜줘" 등
   Just speak naturally — the AI handles tool selection automatically."""


def _cmd_status(cmd: str, session, **_):
    """Cmd status."""
    from salmalm.tools.tool_handlers import execute_tool

    return execute_tool("usage_report", {})


def _cmd_tools(cmd: str, session, **_):
    """Cmd tools."""
    from salmalm.tools import TOOL_DEFINITIONS

    lines = [f"🔧 **Tool List** ({len(TOOL_DEFINITIONS)})\n"]
    for t in TOOL_DEFINITIONS:
        lines.append(f"• **{t['name']}** — {t['description'][:60]}")
    return "\n".join(lines)


async def _cmd_think(cmd: str, session, *, on_tool=None, **_) -> str:
    """Cmd think."""
    think_msg = cmd[7:].strip()
    if not think_msg:
        return "Usage: /think <question>"
    # Route thought-stream subcommands
    _thought_subs = ("list", "search", "tag", "timeline", "stats", "export")
    first_word = think_msg.split(None, 1)[0].lower() if think_msg else ""
    if first_word in _thought_subs:
        return _cmd_thought(cmd, session)
    session.add_user(think_msg)
    session.messages = _lazy_compact_messages()(session.messages, session=session)
    classification = {"intent": "analysis", "tier": 3, "thinking": True, "thinking_budget": 16000, "score": 5}
    return await _get_engine().run(
        session,
        think_msg,
        model_override=COMMAND_MODEL,  # noqa: E128
        on_tool=on_tool,
        classification=classification,
    )  # noqa: E128


async def _cmd_plan(cmd: str, session, *, model_override=None, on_tool=None, **_) -> str:
    """Cmd plan."""
    plan_msg = cmd[6:].strip()
    if not plan_msg:
        return "Usage: /plan <task description>"
    session.add_user(plan_msg)
    session.messages = _lazy_compact_messages()(session.messages, session=session)
    classification = {"intent": "code", "tier": 3, "thinking": True, "thinking_budget": 10000, "score": 5}
    return await _get_engine().run(
        session, plan_msg, model_override=model_override, on_tool=on_tool, classification=classification
    )  # noqa: E128


def _cmd_uptime(cmd: str, session, **_):
    """Cmd uptime."""
    from salmalm.features.sla import uptime_monitor, sla_config  # noqa: F401

    stats = uptime_monitor.get_stats()
    target = stats["target_pct"]
    pct = stats["monthly_uptime_pct"]
    status_icon = "🟢" if pct >= target else ("🟡" if pct >= 99.0 else "🔴")
    lines = [
        "📊 **SalmAlm Uptime** / 업타임 현황\n",
        f"{status_icon} Current uptime: **{stats['uptime_human']}**",
        f"📅 Month ({stats['month']}): **{pct}%** (target: {target}%)",
        f"📅 Today: **{stats['daily_uptime_pct']}%**",
        f"🕐 Started: {stats['start_time'][:19]}",
    ]
    incidents = stats.get("recent_incidents", [])
    if incidents:
        lines.append(f"\n⚠️ Recent incidents ({len(incidents)}):")
        for inc in incidents[:5]:
            dur = f"{inc['duration_sec']:.0f}s" if inc["duration_sec"] else "?"
            lines.append(f"  • {inc['start'][:19]} — {inc['reason']} ({dur})")
    return "\n".join(lines)


def _cmd_latency(cmd: str, session, **_) -> str:
    """Cmd latency."""
    from salmalm.features.sla import latency_tracker

    stats = latency_tracker.get_stats()
    if stats["count"] == 0:
        return "📊 No latency data yet. / 레이턴시 데이터가 없습니다."
    tgt = stats["targets"]
    ttft = stats["ttft"]
    total = stats["total"]
    ttft_ok = "✅" if ttft["p95"] <= tgt["ttft_ms"] else "⚠️"
    total_ok = "✅" if total["p95"] <= tgt["response_ms"] else "⚠️"
    lines = [
        f"📊 **Latency Stats** / 레이턴시 통계 ({stats['count']} requests)\n",
        f"{ttft_ok} **TTFT** (Time To First Token):",
        f"  P50={ttft['p50']:.0f}ms  P95={ttft['p95']:.0f}ms  P99={ttft['p99']:.0f}ms  (target: <{tgt['ttft_ms']}ms)",
        f"{total_ok} **Total Response Time**:",
        f"  P50={total['p50']:.0f}ms  P95={total['p95']:.0f}ms  P99={total['p99']:.0f}ms  (target: <{tgt['response_ms']}ms)",
    ]
    if stats["consecutive_timeouts"] > 0:
        lines.append(f"⚠️ Consecutive timeouts: {stats['consecutive_timeouts']}")
    return "\n".join(lines)


def _cmd_health_detail(cmd: str, session, **_):
    """Cmd health detail."""
    from salmalm.features.sla import watchdog

    report = watchdog.get_detailed_health()
    status = report.get("status", "unknown")
    icon = {"healthy": "🟢", "degraded": "🟡", "unhealthy": "🔴"}.get(status, "⚪")
    lines = [f"{icon} **Health Report** / 상세 헬스 리포트\n", f"Status: **{status}**\n"]
    for name, check in report.get("checks", {}).items():
        s = check.get("status", "?")
        ci = {"ok": "✅", "warning": "⚠️", "error": "❌"}.get(s, "❔")
        extra = ""
        if "usage_mb" in check:
            extra = f" ({check['usage_mb']}MB/{check['limit_mb']}MB)"
        elif "usage_pct" in check:
            extra = f" ({check['usage_pct']}%/{check['limit_pct']}%)"
        elif "error" in check:
            extra = f" ({check['error'][:50]})"
        lines.append(f"{ci} {name}: {s}{extra}")
    return "\n".join(lines)


def _cmd_prune(cmd: str, session, **_) -> str:
    """Cmd prune."""
    _, stats = _lazy_prune_context()(session.messages)
    total = stats["soft_trimmed"] + stats["hard_cleared"] + stats["unchanged"]
    return (
        f"🧹 **Session Pruning Results**\n"
        f"• Soft-trimmed: {stats['soft_trimmed']}\n"
        f"• Hard-cleared: {stats['hard_cleared']}\n"
        f"• Unchanged: {stats['unchanged']}\n"
        f"• Total tool results scanned: {total}"
    )


def _cmd_usage_daily(cmd: str, session, **_) -> str:
    """Cmd usage daily."""
    from salmalm.features.edge_cases import usage_tracker

    report = usage_tracker.daily_report()
    if not report:
        return "📊 No usage data yet. / 아직 사용량 데이터가 없습니다."
    lines = ["📊 **Daily Usage Report / 일별 사용량**\n"]
    for r in report[:14]:
        lines.append(
            f"• {r['date']} | {r['model'].split('/')[-1]} | "
            f"in:{r['input_tokens']} out:{r['output_tokens']} | "
            f"${r['cost']:.4f} ({r['calls']} calls)"
        )
    return "\n".join(lines)


def _cmd_usage_monthly(cmd: str, session, **_) -> str:
    """Cmd usage monthly."""
    from salmalm.features.edge_cases import usage_tracker

    report = usage_tracker.monthly_report()
    if not report:
        return "📊 No usage data yet. / 아직 사용량 데이터가 없습니다."
    lines = ["📊 **Monthly Usage Report / 월별 사용량**\n"]
    for r in report:
        lines.append(
            f"• {r['month']} | {r['model'].split('/')[-1]} | "
            f"in:{r['input_tokens']} out:{r['output_tokens']} | "
            f"${r['cost']:.4f} ({r['calls']} calls)"
        )
    return "\n".join(lines)


def _cmd_bookmarks(cmd: str, session, **_) -> str:
    """Cmd bookmarks."""
    from salmalm.features.edge_cases import bookmark_manager

    bms = bookmark_manager.list_all(limit=20)
    if not bms:
        return "⭐ No bookmarks yet. / 아직 북마크가 없습니다."
    lines = ["⭐ **Bookmarks / 북마크**\n"]
    for b in bms:
        lines.append(
            f"• [{b['session_id']}#{b['message_index']}] "
            f"{b['preview'][:60]}{'...' if len(b.get('preview', '')) > 60 else ''}"
        )
    return "\n".join(lines)


def _cmd_compare(cmd: str, session, *, session_id="", **_) -> str:
    """Cmd compare."""
    compare_msg = cmd[9:].strip()
    if not compare_msg:
        return "Usage: /compare <message> — Compare responses from multiple models"
    from salmalm.features.edge_cases import compare_models

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                results = pool.submit(lambda: asyncio.run(compare_models(session_id, compare_msg))).result()
        else:
            results = loop.run_until_complete(compare_models(session_id, compare_msg))
    except Exception as e:  # noqa: broad-except
        results = asyncio.run(compare_models(session_id, compare_msg))
    lines = ["🔀 **Model Comparison / 모델 비교**\n"]
    for r in results:
        model_name = r["model"].split("/")[-1]
        if r.get("error"):
            lines.append(f"### ❌ {model_name}\n{r['error']}\n")
        else:
            lines.append(f"### 🤖 {model_name} ({r['time_ms']}ms)\n{r['response'][:500]}\n")
    return "\n".join(lines)


def _cmd_security(cmd: str, session, **_):
    """Cmd security."""
    from salmalm.security import security_auditor

    return security_auditor.format_report()


def _cmd_soul(cmd: str, session, **_) -> str:
    """Cmd soul."""
    from salmalm.core.prompt import get_user_soul, USER_SOUL_FILE

    content = get_user_soul()
    if content:
        return f"📜 **SOUL.md** (`{USER_SOUL_FILE}`)\n\n{content}"
    return f"📜 SOUL.md is not set. Create `{USER_SOUL_FILE}` or edit via Settings."


def _cmd_soul_reset(cmd: str, session, **_) -> str:
    """Cmd soul reset."""
    from salmalm.core.prompt import reset_user_soul, build_system_prompt

    reset_user_soul()
    session.add_system(build_system_prompt(full=True))
    return "📜 SOUL.md reset to default."


def _cmd_model(cmd: str, session, **_) -> str:
    """Cmd model."""
    model_name = cmd[7:].strip() if len(cmd) > 7 else ""
    if not model_name:
        current = getattr(session, "model_override", None) or "auto"
        return f"Current model: **{current}**\nUsage: `/model <name>` — e.g. `/model opus`, `/model auto`, `/model anthropic/claude-sonnet-4-6`"
    if model_name in ("auto", "opus", "sonnet", "haiku"):
        session.model_override = model_name if model_name != "auto" else "auto"
        if model_name == "auto":
            _get_router().set_force_model(None)
            return "Model: **auto** (cost-optimized routing) — saved ✅\n• simple → haiku ⚡ • moderate → sonnet • complex → opus 💎"
        labels = {"opus": "claude-opus-4-6 💎", "sonnet": "claude-sonnet-4-6", "haiku": "claude-haiku-4-5 ⚡"}
        return f"Model: **{model_name}** ({labels[model_name]}) — saved ✅"
    if "/" in model_name:
        _get_router().set_force_model(model_name)
        session.model_override = model_name
        return f"Model changed: {model_name} — saved ✅"
    if model_name in MODEL_ALIASES:
        resolved = MODEL_ALIASES[model_name]
        _get_router().set_force_model(resolved)
        session.model_override = resolved
        return f"Model changed: {model_name} → {resolved} — saved ✅"
    return (
        f"Unknown model: {model_name}\\nAvailable: auto, opus, sonnet, haiku, {', '.join(sorted(MODEL_ALIASES.keys()))}"
    )


def _cmd_tts(cmd: str, session, **_) -> str:
    """Cmd tts."""
    arg = cmd[4:].strip()
    if arg == "on":
        session.tts_enabled = True
        return "🔊 TTS: **ON** — 응답을 음성으로 전송합니다."
    elif arg == "off":
        session.tts_enabled = False
        return "🔇 TTS: **OFF**"
    else:
        status = "ON" if getattr(session, "tts_enabled", False) else "OFF"
        voice = getattr(session, "tts_voice", "alloy")
        return f"🔊 TTS: **{status}** (voice: {voice})\n`/tts on` · `/tts off` · `/voice alloy|nova|echo|fable|onyx|shimmer`"


def _cmd_voice(cmd: str, session, **_) -> str:
    """Cmd voice."""
    arg = cmd[6:].strip()
    valid_voices = ("alloy", "nova", "echo", "fable", "onyx", "shimmer")
    if arg in valid_voices:
        session.tts_voice = arg
        return f"🎙️ Voice: **{arg}** — saved ✅"
    return f"Available voices: {', '.join(valid_voices)}"


def _cmd_agent(cmd: str, session, *, session_id="", **_) -> str:
    """Cmd agent."""
    from salmalm.features.agents import agent_manager

    parts = cmd.split(maxsplit=2)
    sub = parts[1] if len(parts) > 1 else "list"
    if sub == "list":
        agents = agent_manager.list_agents()
        lines = ["🤖 **Agents** (에이전트 목록)\n"]
        for a in agents:
            lines.append(f"• **{a['id']}** — {a['display_name']}")
        bindings = agent_manager.list_bindings()
        if bindings:
            lines.append("\n📌 **Bindings** (바인딩)")
            for k, v in bindings.items():
                lines.append(f"• {k} → {v}")
        return "\n".join(lines)
    elif sub == "create" and len(parts) > 2:
        return agent_manager.create(parts[2])
    elif sub == "switch" and len(parts) > 2:
        chat_key = f"session:{session_id}"
        return agent_manager.switch(chat_key, parts[2])
    elif sub == "delete" and len(parts) > 2:
        return agent_manager.delete(parts[2])
    elif sub == "bind" and len(parts) > 2:
        bind_parts = parts[2].split()
        if len(bind_parts) == 2:
            return agent_manager.bind(bind_parts[0], bind_parts[1])
        return "❌ Usage: /agent bind <chat_key> <agent_id>"
    elif sub == "steer" and len(parts) > 2:
        steer_parts = parts[2].split(maxsplit=1)
        label = steer_parts[0] if steer_parts else ""
        message = steer_parts[1] if len(steer_parts) > 1 else ""
        if not label or not message:
            return "❌ Usage: /agent steer <label> <message>"
        from salmalm.features.agents import SubAgent
        result = SubAgent.steer(label=label, message=message)
        if result.get("ok"):
            return f"📡 Steered agent '{label}' ({result['agent_id']}): {result['status']}"
        return f"❌ {result.get('error', 'Steer failed')}"
    return "❌ Usage: /agent list|create|switch|delete|bind|steer <args>"


def _cmd_hooks(cmd: str, session, **_) -> str:
    """Cmd hooks."""
    from salmalm.features.hooks import hook_manager

    parts = cmd.split(maxsplit=2)
    sub = parts[1] if len(parts) > 1 else "list"
    if sub == "list":
        hooks = hook_manager.list_hooks()
        if not hooks:
            return "📋 No hooks configured. Edit ~/.salmalm/hooks.json"
        lines = ["🪝 **Hooks** (이벤트 훅)\n"]
        for event, info in hooks.items():
            cmds_list = info["commands"]
            pc = info["plugin_callbacks"]
            lines.append(f"• **{event}**: {len(cmds_list)} commands, {pc} plugin callbacks")
            for i, c in enumerate(cmds_list):
                lines.append(f"  [{i}] `{c[:60]}`")
        return "\n".join(lines)
    elif sub == "test" and len(parts) > 2:
        return hook_manager.test_hook(parts[2].strip())
    elif sub == "add" and len(parts) > 2:
        add_parts = parts[2].split(maxsplit=1)
        if len(add_parts) == 2:
            return hook_manager.add_hook(add_parts[0], add_parts[1])
        return "❌ Usage: /hooks add <event> <command>"
    elif sub == "reload":
        hook_manager.reload()
        return "🔄 Hooks reloaded"
    return "❌ Usage: /hooks list|test|add|reload"


def _cmd_plugins(cmd: str, session, **_) -> str:
    """Cmd plugins."""
    from salmalm.features.plugin_manager import plugin_manager

    parts = cmd.split(maxsplit=2)
    sub = parts[1] if len(parts) > 1 else "list"
    if sub == "list":
        plugins = plugin_manager.list_plugins()
        if not plugins:
            return "🔌 No plugins found. Add to ~/.salmalm/plugins/"
        lines = ["🔌 **Plugins** (플러그인)\n"]
        for p in plugins:
            status = "✅" if p["enabled"] else "❌"
            err = f" ⚠️ {p['error']}" if p.get("error") else ""
            lines.append(f"• {status} **{p['name']}** v{p['version']} — {p['description'][:40]}{err}")
            if p["tools"]:
                lines.append(f"  Tools: {', '.join(p['tools'])}")
        return "\n".join(lines)
    elif sub == "reload":
        return plugin_manager.reload_all()
    elif sub == "enable" and len(parts) > 2:
        return plugin_manager.enable(parts[2].strip())
    elif sub == "disable" and len(parts) > 2:
        return plugin_manager.disable(parts[2].strip())
    return "❌ Usage: /plugins list|reload|enable|disable <name>"


# ── Self-Evolving Prompt commands ──
def _cmd_evolve(cmd: str, session, **_) -> str:
    """Cmd evolve."""
    parts = cmd.strip().split(None, 2)
    sub = parts[1] if len(parts) > 1 else "status"
    from salmalm.features.self_evolve import prompt_evolver

    if sub == "status":
        return prompt_evolver.get_status()
    elif sub == "apply":
        from salmalm.core.prompt import USER_SOUL_FILE

        return prompt_evolver.apply_to_soul(USER_SOUL_FILE)
    elif sub == "reset":
        return prompt_evolver.reset()
    elif sub == "history":
        return prompt_evolver.get_history()
    return "❌ Usage: /evolve status|apply|reset|history"


# ── Mood-Aware commands ──


def _cmd_mood(cmd: str, session, **_) -> str:
    """Cmd mood."""
    parts = cmd.strip().split(None, 2)
    sub = parts[1] if len(parts) > 1 else "status"
    from salmalm.features.mood import mood_detector

    if sub == "status":
        # Use last user message for context
        last_msg = ""
        for m in reversed(session.messages):
            if m.get("role") == "user":
                last_msg = str(m.get("content", ""))
                break
        return mood_detector.get_status(last_msg)
    elif sub in ("off", "on", "sensitive"):
        return mood_detector.set_mode(sub)
    elif sub == "report":
        period = parts[2] if len(parts) > 2 else "week"
        return mood_detector.generate_report(period)
    return "❌ Usage: /mood status|off|on|sensitive|report [week|month]"


# ── Thought Stream commands ──


def _cmd_export_fn(cmd: str, session, **_) -> str:
    """Handle /export [md|json|html] command."""
    from salmalm.core.export import export_session

    parts = cmd.strip().split()
    fmt = parts[1] if len(parts) > 1 else "md"
    result = export_session(session, fmt=fmt)
    if result.get("ok"):
        return (
            f"📤 **Conversation exported**\n"
            f"Format: {fmt.upper()}\n"
            f"File: `{result['filename']}`\n"
            f"Size: {result['size']:,} bytes\n"
            f"Path: `{result['path']}`"
        )
    return f"❌ Export failed: {result.get('error', 'unknown error')}"


# Public alias
_cmd_export = _cmd_export_fn

# Exact-match slash commands
_SLASH_COMMANDS = {
    "/clear": _cmd_clear,
    "/help": _cmd_help,
    "/status": _cmd_status,
    "/tools": _cmd_tools,
    "/uptime": _cmd_uptime,
    "/latency": _cmd_latency,
    "/health detail": _cmd_health_detail,
    "/health_detail": _cmd_health_detail,
    "/prune": _cmd_prune,
    "/usage daily": _cmd_usage_daily,
    "/usage monthly": _cmd_usage_monthly,
    "/bookmarks": _cmd_bookmarks,
    "/security": _cmd_security,
    "/soul": _cmd_soul,
    "/soul reset": _cmd_soul_reset,
    "/context": _cmd_context,
    "/context detail": _cmd_context,
    "/model": _cmd_model,
    "/models": _cmd_model,
}

# Also add /usage to prefix commands

# Prefix-match slash commands (checked with startswith)
_SLASH_PREFIX_COMMANDS = [
    ("/usage", _cmd_usage),
    ("/think ", _cmd_think),
    ("/plan ", _cmd_plan),
    ("/compare ", _cmd_compare),
    ("/model ", _cmd_model),
    ("/tts", _cmd_tts),
    ("/voice", _cmd_voice),
    ("/subagents", _cmd_subagents),
    ("/agent", _cmd_agent),
    ("/hooks", _cmd_hooks),
    ("/plugins", _cmd_plugins),
    ("/evolve", _cmd_evolve),
    ("/mood", _cmd_mood),
    ("/thought", _cmd_thought),
    ("/export", _cmd_export_fn),
]


_OWNER_ONLY_PREFIXES = frozenset({
    "/evolve", "/hooks", "/agent create", "/agent delete",
    "/soul reset", "/export", "/import", "/backup", "/restore",
})


async def _dispatch_slash_command(cmd: str, session, session_id: str, model_override, on_tool, *, is_owner: bool = True):
    """Dispatch slash commands. Returns response string or None if not a command."""
    # Owner-only gate for destructive commands
    if not is_owner and any(cmd.startswith(p) for p in _OWNER_ONLY_PREFIXES):
        return "❌ This command requires owner privileges."
    # Exact match first
    handler = _SLASH_COMMANDS.get(cmd)
    if handler is not None:
        result = handler(cmd, session, session_id=session_id, model_override=model_override, on_tool=on_tool)
        if asyncio.iscoroutine(result):
            return await result
        return result

    # Prefix match
    for prefix, handler in _SLASH_PREFIX_COMMANDS:
        if cmd.startswith(prefix) or (not prefix.endswith(" ") and cmd == prefix.rstrip()):
            result = handler(cmd, session, session_id=session_id, model_override=model_override, on_tool=on_tool)
            if asyncio.iscoroutine(result):
                return await result
            return result

    return None
