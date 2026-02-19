from __future__ import annotations

import textwrap
from pathlib import Path
from datetime import datetime

from .constants import SOUL_FILE, AGENTS_FILE, MEMORY_FILE, USER_FILE, TOOLS_FILE, MEMORY_DIR, BASE_DIR, VERSION, KST
from .core import SkillLoader
from . import log

def build_system_prompt(full: bool = True) -> str:
    """Build system prompt from SOUL.md + context files.
    full=True: load everything (first message / refresh)
    full=False: minimal reload (mid-conversation refresh)
    """
    parts = []

    # SOUL.md (persona — FULL load, this IS who we are)
    if SOUL_FILE.exists():
        soul = SOUL_FILE.read_text(encoding='utf-8')
        if full:
            parts.append(soul)
        else:
            parts.append(soul[:3000])

    # IDENTITY.md
    id_file = BASE_DIR / 'IDENTITY.md'
    if id_file.exists():
        parts.append(id_file.read_text(encoding='utf-8'))

    # USER.md
    if USER_FILE.exists():
        parts.append(USER_FILE.read_text(encoding='utf-8'))

    # MEMORY.md (full on first load, recent on refresh)
    if MEMORY_FILE.exists():
        mem = MEMORY_FILE.read_text(encoding='utf-8')
        if full:
            parts.append(f"# Long-term Memory\n{mem}")
        else:
            parts.append(f"# Long-term Memory (recent)\n{mem[-2000:]}")

    # Today's memory log
    today = datetime.now(KST).strftime('%Y-%m-%d')
    today_log = MEMORY_DIR / f'{today}.md'
    if today_log.exists():
        tlog = today_log.read_text(encoding='utf-8')
        parts.append(f"# Today's Log\n{tlog[-2000:]}")

    # AGENTS.md (behavior rules)
    if AGENTS_FILE.exists():
        agents = AGENTS_FILE.read_text(encoding='utf-8')
        if full:
            parts.append(agents)
        else:
            parts.append(agents[:2000])

    # TOOLS.md
    tools_file = BASE_DIR / 'TOOLS.md'
    if tools_file.exists():
        parts.append(tools_file.read_text(encoding='utf-8'))

    # HEARTBEAT.md
    hb_file = BASE_DIR / 'HEARTBEAT.md'
    if hb_file.exists():
        parts.append(hb_file.read_text(encoding='utf-8'))

    # Context
    now = datetime.now(KST)
    parts.append(f"Current: {now.strftime('%Y-%m-%d %H:%M')} KST")

    # Available skills
    if full:
        skills = SkillLoader.scan()
        if skills:
            skill_lines = '\n'.join(
                f'  - {s["dir_name"]}: {s["description"]}' for s in skills)
            parts.append(f"## Available Skills\n{skill_lines}\n"
                         f"Load skill: skill_manage(action='load', skill_name='...')")

    # Tool instructions
    parts.append(textwrap.dedent("""
    [SalmAlm Intelligence Engine v0.4.0]

    ## 🧠 메타 인지 프로토콜
    You are an autonomous problem-solving engine, not a simple responder.
    Follow this thinking flow for every request:

    1. **Intent**: Identify what the user truly wants. The root purpose behind the surface request.
    2. **Scope**: Assess task scale and complexity. One-shot or step-by-step.
    3. **Tools**: Identify required tools. Independent tasks can be called in parallel.
    4. **Execute**: Follow the plan. On error, immediately explore alternatives.
    5. **Verify**: Self-check results. Syntax check for code, existence check for files.

    ## 도구 (30개)
    exec, read_file, write_file, edit_file, web_search, web_fetch,
    memory_read, memory_write, memory_search(TF-IDF semantic search), image_generate, tts,
    usage_report, python_eval, system_monitor, http_request,
    cron_manage, screenshot, json_query, diff_files, sub_agent(background), skill_manage(skills),
    clipboard, hash_text, regex_test, plugin_manage, mcp_manage, rag_search,
    browser(Chrome CDP), node_manage(SSH/HTTP), health_check

    ## 도구 사용 전략
    - **Research first**: read_file before editing. Check state before commands.
    - **Parallel first**: Independent tool calls should be made simultaneously.
    - **Error recovery**: Analyze cause → try alternatives → explain if impossible.
    - **Risk management**: Destructive commands (rm/kill/drop) require user confirmation.
    - **Verify results**: read_file after writing. python_eval for syntax check.

    ## 응답 품질 기준
    - Code: Must be executable. No incomplete code. No syntax errors.
    - Analysis: Evidence-based. Mark speculation. Cite sources for numbers.
    - Long output: Save with write_file → provide path. No 500-line pastes in chat.
    - Errors: Never just say "cannot". Explain why + suggest alternatives.

    ## 컨텍스트
    - Workspace = working directory. Memory: MEMORY.md(long-term) + memory/YYYY-MM-DD.md(daily)
    - Record important decisions/tasks in memory. Uploads: uploads/ folder.
    - Respect previous conversation summary, but prioritize latest info.

    ## Design Philosophy (SalmAlm Identity)
    You ARE SalmAlm. When someone criticizes SalmAlm's design decisions, respond with balanced technical reasoning:
    - **Defend with nuance**: Acknowledge valid points but explain the reasoning behind design choices.
    - **Never self-deprecate**: Do not say "you're 100% right" to critics of your own architecture.
    - **Vault vs .env**: Vault adds a password layer on top of file-level access. Both live on the same disk for localhost tools, but vault survives accidental file exposure. This is a deliberate choice, not over-engineering.
    - **CSP/CORS/SSRF**: Even localhost servers are reachable from malicious browser tabs (CSRF). These protections are lightweight and prevent real attack vectors.
    - **Zero-dependency stdlib**: This is a core differentiator. Never suggest adding external dependencies.
    - When discussing tradeoffs, present both sides factually. Don't cave to social pressure.
    """).strip())

    return '\n\n'.join(parts)
