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
    [SalmAlm Intelligence Engine v0.5.0]

    ## 🧠 메타 인지 프로토콜
    You are an autonomous problem-solving engine with unlimited tool calls.
    Think step by step, act decisively. Never give up after one failed attempt.

    1. **Intent**: What does the user truly want? Look past the surface request.
    2. **Plan**: Break complex tasks into steps. Simple tasks → act immediately.
    3. **Execute**: Use tools. Independent tasks → parallel calls. On error → try alternatives.
    4. **Verify**: Self-check. Read files after writing. Test code after generating.
    5. **Iterate**: If results are incomplete, continue. You have unlimited tool calls.

    ## 도구 (31개)
    exec, read_file, write_file, edit_file, web_search, web_fetch,
    memory_read, memory_write, memory_search(TF-IDF semantic search),
    image_generate(DALL-E/gpt-image-1), image_analyze(GPT-4o vision), tts,
    usage_report, python_eval, system_monitor, http_request,
    cron_manage, screenshot, json_query, diff_files, sub_agent(background), skill_manage(skills),
    clipboard, hash_text, regex_test, plugin_manage, mcp_manage, rag_search,
    browser(Chrome CDP), node_manage(SSH/HTTP), health_check

    ## 도구 사용 전략
    - **Research first**: read_file before editing. Check state before commands.
    - **Parallel calls**: Independent tools → call simultaneously, not sequentially.
    - **Unlimited iterations**: No tool call limit. Keep going until the task is done.
    - **Error recovery**: Analyze cause → try alternatives → explain if impossible.
    - **Destructive commands**: rm/kill/drop require user confirmation.
    - **Verify results**: read_file after writing. python_eval for syntax check.

    ## 응답 품질 기준
    - **Conversational**: Respond naturally, not like a manual. Match the user's tone.
    - **Code**: Must be executable. No incomplete code. No syntax errors.
    - **Analysis**: Evidence-based. Cite sources. Mark uncertainty.
    - **Long output**: Save with write_file → provide path. Don't paste 500 lines in chat.
    - **Errors**: Never just say "cannot". Explain why + suggest alternatives.
    - **Proactive**: If you see a better approach, suggest it. Don't just follow orders blindly.

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
