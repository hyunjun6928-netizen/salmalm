"""SalmAlm Intelligence Engine — TaskClassifier + IntelligenceEngine + process_message."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from .constants import VERSION
from .crypto import log
from .core import router, compact_messages, get_session, _sessions
from .prompt import build_system_prompt
from .tools import execute_tool
from .llm import call_llm

# ============================================================
MODEL_ALIASES = {
    'auto': None,
    'claude': 'anthropic/claude-sonnet-4-20250514',
    'sonnet': 'anthropic/claude-sonnet-4-20250514',
    'opus': 'anthropic/claude-opus-4-6',
    'haiku': 'anthropic/claude-haiku-3.5-20241022',
    'gpt': 'openai/gpt-5.3-codex', 'gpt5': 'openai/gpt-5.3-codex',
    'gpt5.1': 'openai/gpt-5.1-codex', 'gpt4.1': 'openai/gpt-4.1',
    '4.1mini': 'openai/gpt-4.1-mini', '4.1nano': 'openai/gpt-4.1-nano',
    'o3': 'openai/o3', 'o3mini': 'openai/o3-mini', 'o4mini': 'openai/o4-mini',
    'grok': 'xai/grok-4', 'grok4': 'xai/grok-4',
    'grok3': 'xai/grok-3', 'grok3mini': 'xai/grok-3-mini',
    'gemini': 'google/gemini-3-pro-preview', 'flash': 'google/gemini-3-flash-preview',
    'deepseek': 'deepseek/deepseek-r1', 'r1': 'deepseek/deepseek-r1',
    'dschat': 'deepseek/deepseek-chat',
    'llama': 'meta-llama/llama-4-maverick', 'maverick': 'meta-llama/llama-4-maverick',
    'scout': 'meta-llama/llama-4-scout',
}


class TaskClassifier:
    """Classify user intent to determine execution strategy."""

    # Intent categories with weighted keywords
    INTENTS = {
        'code': {'keywords': ['code', 'implement', 'function', 'function', 'class', 
                               'bug', 'fix', 'refactor', 'refactor', 'debug',
                               'API', 'server', 'deploy', 'deploy', 'build'],
                 'tier': 3, 'thinking': True, 'max_tools': 30},
        'analysis': {'keywords': ['analyze', 'compare', 'review',
                                   'audit', 'security', 'performance'],
                     'tier': 3, 'thinking': True, 'max_tools': 20},
        'creative': {'keywords': ['write', 'story', 'poem',
                                   'translate', 'summarize'],
                     'tier': 2, 'thinking': False, 'max_tools': 10},
        'search': {'keywords': ['search', 'find', 'news',
                                 'latest', 'weather', 'price'],
                   'tier': 2, 'thinking': False, 'max_tools': 15},
        'system': {'keywords': ['file', 'exec', 'run', 'install',
                                 'process', 'disk', 'memory'],
                   'tier': 2, 'thinking': False, 'max_tools': 20},
        'memory': {'keywords': ['remember', 'memo', 'record',
                                 'diary', 'learn'],
                   'tier': 1, 'thinking': False, 'max_tools': 5},
        'chat': {'keywords': [], 'tier': 1, 'thinking': False, 'max_tools': 3},
    }

    @classmethod
    def classify(cls, message: str, context_len: int = 0) -> Dict[str, Any]:
        msg = message.lower()
        msg_len = len(message)
        scores = {}
        for intent, info in cls.INTENTS.items():
            score = sum(2 for kw in info['keywords'] if kw in msg)
            if intent == 'code' and any(c in message for c in ['```', 'def ', 'class ', '{', '}']):
                score += 3
            scores[intent] = score

        best = max(scores, key=scores.get) if any(scores.values()) else 'chat'
        if scores[best] == 0:
            best = 'chat'

        info = cls.INTENTS[best]
        # Escalate tier for long/complex messages
        tier = info['tier']
        if msg_len > 500:
            tier = max(tier, 2)
        if msg_len > 1500 or context_len > 40:
            tier = max(tier, 3)

        # Adaptive thinking budget
        thinking = info['thinking']
        thinking_budget = 0
        if thinking:
            if msg_len < 300:
                thinking_budget = 5000
            elif msg_len < 1000:
                thinking_budget = 10000
            else:
                thinking_budget = 16000

        return {
            'intent': best, 'tier': tier, 'thinking': thinking,
            'thinking_budget': thinking_budget,
            'max_tools': info['max_tools'], 'score': scores[best],
        }


class IntelligenceEngine:
    """Core AI reasoning engine — surpasses OpenClaw's capabilities.

    Architecture:
    1. CLASSIFY — Determine task type, complexity, required resources
    2. PLAN — For complex tasks, generate execution plan before acting
    3. EXECUTE — Run tool loop with parallel execution
    4. REFLECT — Self-evaluate response quality, retry if insufficient
    """

    # Planning prompt — injected before complex tasks
    PLAN_PROMPT = """Before answering, briefly plan your approach:
1. What is the user asking? (one sentence)
2. What tools/steps are needed? (bullet list)
3. What could go wrong? (potential issues)
4. Expected output format?
Then execute the plan."""

    # Reflection prompt — used to evaluate response quality
    REFLECT_PROMPT = """Evaluate your response:
- Did it fully answer the question?
- Are there errors or hallucinations?
- Is the code correct (if any)?
- Could the answer be improved?
If the answer is insufficient, improve it now. If satisfactory, return it as-is."""

    def __init__(self):
        self._tool_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='tool')

    def _get_tools_for_provider(self, provider: str) -> list:
        from .tools import TOOL_DEFINITIONS
        from .core import PluginLoader
        from .mcp import mcp_manager
        # Merge built-in + plugin + MCP tools (deduplicate by name)
        all_tools = list(TOOL_DEFINITIONS)
        seen = {t['name'] for t in all_tools}
        for t in PluginLoader.get_all_tools() + mcp_manager.get_all_tools():
            if t['name'] not in seen:
                all_tools.append(t)
                seen.add(t['name'])
        
        if provider == 'google':
            # Google Gemini: use OpenAI-compatible tool format
            return [{'name': t['name'], 'description': t['description'],
                     'parameters': t['input_schema']} for t in all_tools]
        elif provider in ('openai', 'xai', 'deepseek', 'meta-llama'):
            return [{'name': t['name'], 'description': t['description'],
                     'parameters': t['input_schema']} for t in all_tools]
        elif provider == 'anthropic':
            return [{'name': t['name'], 'description': t['description'],
                     'input_schema': t['input_schema']} for t in all_tools]
        return all_tools

    def _execute_tools_parallel(self, tool_calls: list, on_tool=None) -> dict:
        """Execute multiple tools in parallel, return {id: result}."""
        for tc in tool_calls:
            if on_tool:
                result = on_tool(tc['name'], tc['arguments'])
                # Handle async callbacks
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        task = loop.create_task(result)
                        task.add_done_callback(
                            lambda t: t.exception() if not t.cancelled() and t.exception() else None
                        )
                    except RuntimeError:
                        pass  # No running event loop

        if len(tool_calls) == 1:
            tc = tool_calls[0]
            return {tc['id']: execute_tool(tc['name'], tc['arguments'])}

        futures = {}
        for tc in tool_calls:
            f = self._tool_executor.submit(execute_tool, tc['name'], tc['arguments'])
            futures[tc['id']] = f
        outputs = {}
        for tc_id, f in futures.items():
            try:
                outputs[tc_id] = f.result(timeout=60)
            except Exception as e:
                outputs[tc_id] = f'❌ Tool execution error: {e}'
        log.info(f"⚡ Parallel: {len(tool_calls)} tools completed")
        return outputs

    def _append_tool_results(self, session, provider, result, tool_calls, tool_outputs):
        """Append tool call + results to session messages."""
        if provider == 'anthropic':
            content_blocks = []
            if result.get('content'):
                content_blocks.append({'type': 'text', 'text': result['content']})
            for tc in tool_calls:
                content_blocks.append({
                    'type': 'tool_use', 'id': tc['id'],
                    'name': tc['name'], 'input': tc['arguments']
                })
            session.messages.append({'role': 'assistant', 'content': content_blocks})
            session.add_tool_results([
                {'tool_use_id': tc['id'], 'content': tool_outputs[tc['id']]}
                for tc in tool_calls
            ])
        else:
            session.add_assistant(result.get('content', ''))
            for tc in tool_calls:
                session.messages.append({
                    'role': 'tool', 'tool_call_id': tc['id'],
                    'name': tc['name'], 'content': tool_outputs[tc['id']]
                })

    def _should_reflect(self, classification: dict, response: str, iteration: int) -> bool:
        """Determine if response needs self-reflection pass."""
        # Only reflect on complex tasks with significant responses
        if classification['intent'] not in ('code', 'analysis'):
            return False
        if iteration > 5:  # Already iterated a lot
            return False
        if len(response) < 100:  # Too short to be code/analysis
            return False
        if classification['score'] >= 3:  # High confidence complex task
            return True
        return False

    async def run(self, session, user_message: str,
                  model_override: str = None, on_tool=None,
                  classification: dict = None) -> str:
        """Main execution loop — Plan → Execute → Reflect."""

        if not classification:
            classification = TaskClassifier.classify(
                user_message, len(session.messages))

        tier = classification['tier']
        use_thinking = classification['thinking']
        thinking_budget = classification['thinking_budget']
        max_tools = classification['max_tools']

        log.info(f"🧠 Intent: {classification['intent']} (tier={tier}, "
                 f"think={use_thinking}, budget={thinking_budget}, "
                 f"max_tools={max_tools}, score={classification['score']})")

        # PHASE 1: PLANNING — inject plan prompt for complex tasks
        if classification['intent'] in ('code', 'analysis') and classification['score'] >= 2:
            # Inject planning instruction into the last user message context
            plan_msg = {'role': 'system', 'content': self.PLAN_PROMPT, '_plan_injected': True}
            session.messages.insert(-1, plan_msg)  # Before the user message

        # PHASE 2: EXECUTE — tool loop
        try:
          return await self._execute_loop(session, user_message, model_override,
                                           on_tool, classification, max_tools, tier)
        except Exception as e:
            log.error(f"Engine.run error: {e}")
            import traceback; traceback.print_exc()
            error_msg = f'❌ Processing error: {type(e).__name__}: {e}'
            session.add_assistant(error_msg)
            return error_msg

    async def _execute_loop(self, session, user_message, model_override,
                             on_tool, classification, max_tools, tier):
        use_thinking = classification['thinking']
        thinking_budget = classification['thinking_budget']
        for iteration in range(max_tools):
            model = model_override or router.route(
                user_message, has_tools=True, iteration=iteration)

            # Force tier upgrade for complex tasks
            if not model_override and tier == 3 and iteration == 0:
                model = router._pick_available(3)
            elif not model_override and tier == 2 and iteration == 0:
                model = router._pick_available(2)

            provider = model.split('/')[0] if '/' in model else 'anthropic'
            tools = self._get_tools_for_provider(provider)

            # Use thinking for first call on complex tasks
            think_this_call = (use_thinking and iteration == 0
                               and provider == 'anthropic'
                               and ('opus' in model or 'sonnet' in model))

            result = call_llm(session.messages, model=model, tools=tools,
                              thinking=think_this_call)

            # ── Token overflow: aggressive truncation + retry once ──
            if result.get('error') == 'token_overflow':
                msg_count = len(session.messages)
                # Keep system prompt + last 10 messages
                if msg_count > 12:
                    system_msgs = [m for m in session.messages if m['role'] == 'system'][:1]
                    recent_msgs = session.messages[-10:]
                    session.messages = system_msgs + recent_msgs
                    log.warning(f"🔪 Force-truncated: {msg_count} → {len(session.messages)} msgs")
                    # Retry with truncated context
                    result = call_llm(session.messages, model=model, tools=tools,
                                      thinking=think_this_call)
                    if result.get('error') == 'token_overflow':
                        # Still too long — nuclear option: keep only last 4
                        session.messages = (system_msgs or []) + session.messages[-4:]
                        log.warning(f"🔪🔪 Nuclear truncation: → {len(session.messages)} msgs")
                        result = call_llm(session.messages, model=model, tools=tools)
                        if result.get('error'):
                            session.add_assistant("⚠️ Context too large. Use /clear to reset.")
                            return "⚠️ Context too large. Use /clear to reset."
                elif msg_count > 4:
                    session.messages = session.messages[:1] + session.messages[-4:]
                    result = call_llm(session.messages, model=model, tools=tools)
                    if result.get('error'):
                        session.add_assistant("⚠️ Context too large. Use /clear to reset.")
                        return "⚠️ Context too large. Use /clear to reset."
                else:
                    session.add_assistant("⚠️ Context too large. Use /clear to reset.")
                    return "⚠️ Context too large. Use /clear to reset."

            if result.get('thinking'):
                log.info(f"🧠 Thinking: {len(result['thinking'])} chars")

            if result.get('tool_calls'):
                tool_outputs = self._execute_tools_parallel(
                    result['tool_calls'], on_tool)
                self._append_tool_results(
                    session, provider, result,
                    result['tool_calls'], tool_outputs)
                continue

            # Final response
            response = result.get('content', 'Could not generate a response.')

            # PHASE 3: REFLECT — self-evaluation for complex tasks
            if self._should_reflect(classification, response, iteration):
                log.info(f"🔍 Reflection pass on {classification['intent']} response")
                reflect_msgs = [
                    {'role': 'system', 'content': self.REFLECT_PROMPT},
                    {'role': 'user', 'content': f'Original question: {user_message[:500]}'},
                    {'role': 'assistant', 'content': response},
                    {'role': 'user', 'content': 'Evaluate and improve if needed.'}
                ]
                reflect_result = call_llm(reflect_msgs,
                                           model=router._pick_available(2),
                                           max_tokens=4000)
                improved = reflect_result.get('content', '')
                if improved and len(improved) > len(response) * 0.5 and len(improved) > 50:
                    # Only use reflection if it's substantive and not a degradation
                    # Skip if reflection is just "the answer is fine" or similar
                    skip_phrases = ['satisfactory', 'sufficient', 'correct', ]
                    if not any(p in improved[:100].lower() for p in skip_phrases):
                        response = improved
                    log.info(f"🔍 Reflection improved: {len(response)} chars")

            session.add_assistant(response)
            log.info(f"💬 Response ({result.get('model', '?')}): {len(response)} chars, "
                     f"iteration {iteration + 1}, intent={classification['intent']}")

            # Clean up planning message if added (use marker, not content comparison)
            session.messages = [m for m in session.messages
                                if not m.get('_plan_injected')]
            return response

        # Loop exhausted
        for m in reversed(session.messages):
            if m['role'] == 'assistant':
                content = m.get('content', '')
                if isinstance(content, str) and content:
                    return content + f"\n\n⚠️ (Tool execution limit reached ({max_tools}))"
                elif isinstance(content, list):
                    texts = [b['text'] for b in content if b.get('type') == 'text']
                    if texts:
                        return '\n'.join(texts) + f"\n\n⚠️ (Tool execution limit reached ({max_tools}))"
        return f"⚠️ Tool execution limit exceeded ({max_tools}). Please be more specific."


# Singleton
_engine = IntelligenceEngine()


async def process_message(session_id: str, user_message: str,
                          model_override: Optional[str] = None,
                          image_data: Optional[Tuple[str, str]] = None,
                          on_tool: Optional[Callable[[str, Any], None]] = None) -> str:
    """Process a user message through the Intelligence Engine pipeline."""
    session = get_session(session_id)

    # --- Slash commands (fast path, no LLM) ---
    cmd = user_message.strip()
    if cmd == '/clear':
        session.messages = [m for m in session.messages if m['role'] == 'system'][:1]
        return 'Conversation cleared.'
    if cmd == '/help':
        from .tools import TOOL_DEFINITIONS
        tool_count = len(TOOL_DEFINITIONS)
        return f"""😈 **SalmAlm v{VERSION}** — Personal AI Gateway

📌 **Commands**
/clear — Clear conversation
/help — This help
/model <name> — Change model
/think <question> — 🧠 Deep reasoning (Opus)
/plan <question> — 📋 Plan → Execute
/status — Usage + Cost
/tools — Tool list

🤖 **Model Aliases** (27)
claude, sonnet, opus, haiku, gpt, gpt5, o3, o4mini,
grok, grok4, gemini, flash, deepseek, llama, auto ...

🔧 **Tools** ({tool_count})
File R/W, code exec, web search, RAG search,
system monitor, cron jobs, image analysis, TTS ...

🧠 **Intelligence Engine**
Auto intent classification (7 levels) → Model routing → Parallel tools → Self-evaluation

💡 **Tip**: Just speak naturally. Read a file, search the web, write code, etc."""
    if cmd == '/status':
        return execute_tool('usage_report', {})
    if cmd == '/tools':
        from .tools import TOOL_DEFINITIONS
        lines = [f'🔧 **Tool List** ({len(TOOL_DEFINITIONS)})\n']
        for t in TOOL_DEFINITIONS:
            lines.append(f"• **{t['name']}** — {t['description'][:60]}")
        return '\n'.join(lines)
    if cmd.startswith('/think '):
        think_msg = cmd[7:].strip()
        if not think_msg:
            return 'Usage: /think <question>'
        session.add_user(think_msg)
        session.messages = compact_messages(session.messages)
        classification = {'intent': 'analysis', 'tier': 3, 'thinking': True,
                          'thinking_budget': 16000, 'max_tools': 30, 'score': 5}
        return await _engine.run(session, think_msg,
                                  model_override='anthropic/claude-opus-4-6',
                                  on_tool=on_tool, classification=classification)
    if cmd.startswith('/plan '):
        plan_msg = cmd[6:].strip()
        if not plan_msg:
            return 'Usage: /plan <task description>'
        session.add_user(plan_msg)
        session.messages = compact_messages(session.messages)
        classification = {'intent': 'code', 'tier': 3, 'thinking': True,
                          'thinking_budget': 10000, 'max_tools': 30, 'score': 5}
        return await _engine.run(session, plan_msg, model_override=model_override,
                                  on_tool=on_tool, classification=classification)
    if cmd.startswith('/model '):
        model_name = cmd[7:].strip()
        if model_name == 'auto':
            router.set_force_model(None)
            return 'Model changed: auto (auto-routing) — saved ✅'
        if '/' in model_name:
            router.set_force_model(model_name)
            return f'Model changed: {model_name} — saved ✅'
        if model_name in MODEL_ALIASES:
            resolved = MODEL_ALIASES[model_name]
            router.set_force_model(resolved)
            return f'Model changed: {model_name} → {resolved} — saved ✅'
        return f'Unknown model: {model_name}\\nAvailable: {", ".join(sorted(MODEL_ALIASES.keys()))}'

    # --- Normal message processing ---
    if image_data:
        b64, mime = image_data
        log.info(f"🖼️ Image attached: {mime}, {len(b64)//1024}KB base64")
        content = [
            {'type': 'image', 'source': {'type': 'base64', 'media_type': mime, 'data': b64}},
            {'type': 'text', 'text': user_message or 'Analyze this image.'}
        ]
        session.messages.append({'role': 'user', 'content': content})
    else:
        session.add_user(user_message)

    # Context management
    session.messages = compact_messages(session.messages)
    if len(session.messages) % 20 == 0:
        session.add_system(build_system_prompt(full=False))

    # RAG context injection — augment with relevant memory/docs
    try:
        from .rag import inject_rag_context
        for i, m in enumerate(session.messages):
            if m.get('role') == 'system':
                session.messages[i] = dict(m)
                session.messages[i]['content'] = inject_rag_context(
                    session.messages, m['content'], max_chars=2500)
                break
    except Exception as e:
        log.warning(f"RAG injection skipped: {e}")

    # Classify and run through Intelligence Engine
    classification = TaskClassifier.classify(user_message, len(session.messages))
    response = await _engine.run(session, user_message,
                              model_override=model_override,
                              on_tool=on_tool,
                              classification=classification)

    # ── Completion Notification Hook ──
    # Notify other channels when a task completes
    try:
        _notify_completion(session_id, user_message, response, classification)
    except Exception as e:
        log.error(f"Notification hook error: {e}")

    return response


def _notify_completion(session_id: str, user_message: str, response: str, classification: dict):
    """Send completion notifications to Telegram + Web chat."""
    from .core import _tg_bot
    from .crypto import vault

    # Only notify for complex tasks (tier 3 or high-score tool-using)
    tier = classification.get('tier', 1)
    intent = classification.get('intent', 'chat')
    score = classification.get('score', 0)
    if tier < 3 and score < 3:
        return  # Skip simple/medium tasks — avoid notification spam

    # Build summary
    task_preview = user_message[:80] + ('...' if len(user_message) > 80 else '')
    resp_preview = response[:150] + ('...' if len(response) > 150 else '')
    notify_text = f"✅ Task completed [{intent}]\n📝 Request: {task_preview}\n💬 Result: {resp_preview}"

    # Telegram notification (if task came from web)
    if session_id != 'telegram' and _tg_bot and _tg_bot.token:
        owner_id = vault.get('telegram_owner_id') if vault.is_unlocked else None
        if owner_id:
            try:
                _tg_bot.send_message(owner_id, f"🔔 SalmAlm webchat Task completed\n{notify_text}")
            except Exception as e:
                log.error(f"TG notify error: {e}")

    # Web notification (if task came from telegram)
    if session_id == 'telegram':
        # Store notification for web polling
        from .core import _sessions
        web_session = _sessions.get('web')
        if web_session:
            if not hasattr(web_session, '_notifications'):
                web_session._notifications = []
            web_session._notifications.append({
                'time': __import__('time').time(),
                'text': f"🔔 SalmAlm telegram Task completed\n{notify_text}"
            })
            # Keep max 20 notifications
            web_session._notifications = web_session._notifications[-20:]



