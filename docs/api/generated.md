# Auto-Generated API Reference
# 자동 생성 API 레퍼런스

Generated from source docstrings. Run `python docs/gen_api.py` to update.
소스 docstring에서 생성됨. `python docs/gen_api.py`를 실행하여 업데이트.

## core/ — Core — Engine, LLM, Session / 코어 — 엔진, LLM, 세션

### `salmalm.core.__init__`

#### `class _PkgProxy`



### `salmalm.core.core`

> SalmAlm core — audit, cache, usage, router, compaction, search,

#### `class ResponseCache`
> Simple TTL cache for LLM responses to avoid duplicate calls.

- `get(model, messages, session_id)`
  — Get a cached response by key, or None if expired/missing.
- `put(model, messages, response, session_id)`
  — Store a response in cache with TTL.

#### `class CostCapExceeded`
> Raised when cumulative API spend exceeds the cost cap.


#### `class ModelRouter`
> Routes queries to appropriate models based on complexity.

- `set_force_model(model)`
  — Set and persist model preference.
- `route(user_message, has_tools, iteration)`
  — Route a message to the best model based on intent classification.

#### `class TFIDFSearch`
> Lightweight TF-IDF + cosine similarity search. No external deps.

- `search(query, max_results)`
  — Search with TF-IDF + cosine similarity. Returns [(score, label, lineno, snippet)].

#### `class LLMCronManager`
> OpenClaw-style LLM cron with isolated session execution.

- `load_jobs()`
  — Load persisted cron jobs from file.
- `save_jobs()`
  — Persist cron jobs to file.
- `add_job(name, schedule, prompt, model, notify)`
  — Add a new LLM cron job.
- `remove_job(job_id)`
  — Remove a scheduled cron job by ID.
- `list_jobs()`
  — List all registered cron jobs with their schedules.
- `async tick()`
  — Check and execute due jobs. Also runs heartbeat if due.

#### `class Session`
> OpenClaw-style isolated session with its own context.

- `add_system(content)`
  — Add a system message to the session.
- `add_user(content)`
  — Add a user message to the session.
- `add_assistant(content)`
  — Add an assistant response to the session.
- `add_tool_results(results)`
  — Add tool results as a single user message with all results.

#### `class CronScheduler`
> OpenClaw-style cron scheduler with isolated session execution.

- `add_job(name, interval_seconds, callback)`
  — Add a new cron job with the given schedule and callback.
- `async run()`
  — Start the cron scheduler loop.
- `stop()`
  — Stop the cron scheduler loop.

#### `class HeartbeatManager`
> OpenClaw-style heartbeat: periodic self-check with HEARTBEAT.md.

- `get_prompt(cls)`
  — Read HEARTBEAT.md for the heartbeat checklist.
- `should_beat(cls)`
  — Check if it's time for a heartbeat.
- `get_state(cls)`
  — Get current heartbeat state (for tools/API).
- `update_check(cls, check_name)`
  — Record that a specific check was performed (email, calendar, etc).
- `time_since_check(cls, check_name)`
  — Seconds since a named check was last performed. None if never.
- `async beat(cls)`
  — Execute a heartbeat check in an isolated session.

- `audit_log(event, detail, session_id, detail_dict)`
  — Write an audit event to the security log (v1 chain + v2 structured).
- `audit_log_cleanup(days)`
  — Delete audit_log_v2 entries older than `days` days.
- `query_audit_log(limit, event_type, session_id)`
  — Query structured audit log entries.
- `close_all_db_connections()`
  — Close all tracked SQLite connections (for graceful shutdown).
- `check_cost_cap()`
  — Raise CostCapExceeded if cumulative cost exceeds the cap. 0 = disabled.
- `set_current_user_id(user_id)`
  — Set the current user_id for cost tracking (thread-local).
- `get_current_user_id()`
  — Get the current user_id from thread-local context.
- `track_usage(model, input_tokens, output_tokens, user_id)`
  — Record token usage and cost for a model call.
- `get_usage_report()`
  — Generate a formatted usage report with token counts and costs.
- `compact_messages(messages, model, session)`
  — Multi-stage compaction: trim tool results → drop old tools → summarize.
- `get_telegram_bot()`
  — Accessor for the Telegram bot instance (avoids direct global access).
- `set_telegram_bot(bot)`
  — Set the Telegram bot instance (called during startup).
- `get_session(session_id, user_id)`
  — Get or create a chat session by ID.
- `rollback_session(session_id, count)`
  — Roll back the last `count` user+assistant message pairs.
- `branch_session(session_id, message_index)`
  — Create a new session branching from session_id at message_index.

### `salmalm.core.engine`

> SalmAlm Intelligence Engine — TaskClassifier + IntelligenceEngine + process_message.

#### `class TaskClassifier`
> Classify user intent to determine execution strategy.

- `classify(cls, message, context_len)`
  — Classify user message intent and determine processing tier.

#### `class IntelligenceEngine`
> Core AI reasoning engine — surpasses OpenClaw's capabilities.

- `async run(session, user_message, model_override, on_tool, classification)`
  — Main execution loop — Plan → Execute → Reflect.

- `get_routing_config()`
  — Public getter for routing config (used by web API).
- `async process_message(session_id, user_message, model_override, image_data, on_tool)`
  — Process a user message through the Intelligence Engine pipeline.
- `estimate_tokens(text)`
  — Estimate tokens: Korean /2, English /4, mixed weighted.
- `estimate_cost(model, usage)`
  — Estimate cost in USD from usage dict.
- `record_response_usage(session_id, model, usage)`
  — Record per-response usage for /usage command.
- `begin_shutdown()`
  — Signal the engine to stop accepting new requests.
- `wait_for_active_requests(timeout)`
  — Wait for active requests to complete. Returns True if all done, False if timed out.

### `salmalm.core.exceptions`

> SalmAlm exception hierarchy.

#### `class SalmAlmError`
> Base exception for all SalmAlm errors.


#### `class LLMError`
> LLM API call or response errors.


#### `class ToolError`
> Tool execution errors.


#### `class AuthError`
> Authentication / authorization errors.


#### `class ConfigError`
> Configuration loading / validation errors.


#### `class SessionError`
> Session management errors.



### `salmalm.core.export`

> Conversation Export — export current session as Markdown, JSON, or HTML.

- `export_session(session, fmt)`
  — Export a session to the specified format.

### `salmalm.core.health`

> Health Endpoint — K8s readiness/liveness probe compatible.

- `get_health_report()`
  — Build comprehensive health report.

### `salmalm.core.image_resize`

> Auto-resize images for vision input to reduce token cost.

- `resize_image_b64(b64_data, mime, max_dim)`
  — Resize a base64-encoded image so its longest side <= max_dim.

### `salmalm.core.llm`

> SalmAlm LLM — Multi-provider API calls with caching and fallback.

- `call_llm(messages, model, tools, max_tokens, thinking)`
  — Call LLM API. Returns {'content': str, 'tool_calls': list, 'usage': dict}.
- `stream_anthropic(messages, model, tools, max_tokens, thinking)`
  — Stream Anthropic API responses token-by-token using raw urllib SSE.

### `salmalm.core.llm_loop`

> LLM call loop — streaming, failover, cooldowns, routing.

- `get_failover_config()`
  — Public getter for failover config (used by web API / settings).
- `save_failover_config(config)`
  — Save user's failover chain config.
- `async call_with_failover(messages, model, tools, max_tokens, thinking)`
  — LLM call with automatic failover on failure.
- `async try_llm_call(messages, model, tools, max_tokens, thinking)`
  — Single LLM call attempt. Sets _failed=True on exception.

### `salmalm.core.llm_task`

> Structured LLM output — JSON Schema validated LLM calls.

#### `class LLMTask`
> JSON Schema 검증 기반 구조화 LLM 호출.

- `async run(prompt, input_data, schema, model, max_tokens)`
  — LLM에 JSON-only 응답 요청, schema로 검증.


### `salmalm.core.memory`

> Enhanced Memory System — OpenClaw-style two-layer memory.

#### `class MemoryManager`
> OpenClaw-style memory management with auto-curation.

- `read(filename)`
  — Read a memory file. Supports MEMORY.md and memory/YYYY-MM-DD.md.
- `write(filename, content, append)`
  — Write to a memory file.
- `search(query, max_results)`
  — Search across all memory files using TF-IDF.
- `list_files()`
  — List all memory files.
- `load_session_context()`
  — Load today + yesterday memory for session startup injection.
- `flush_before_compaction(session)`
  — Save important context from session to daily log before compaction.
- `auto_curate(days_back)`
  — Scan recent daily logs and promote important entries to MEMORY.md.


### `salmalm.core.plugin_watcher`

> Plugin Hot-Reload — polling-based watcher for plugins/ directory.

#### `class PluginWatcher`
> Polling-based watcher for plugin hot-reload.

- `start()`
  — Start watching plugins/ directory in background.
- `stop()`
  — Stop the watcher.
- `running()`
- `reload_plugins(names)`
  — Reload specific plugins or all if names is None.
- `reload_all()`
  — Reload all plugins (for /plugins reload command).


### `salmalm.core.prompt`

- `ensure_personas_dir()`
  — Create personas directory and install built-in presets if missing.
- `list_personas()`
  — List all available personas.
- `get_persona(name)`
  — Get persona content by name.
- `create_persona(name, content)`
  — Create or update a custom persona.
- `delete_persona(name)`
  — Delete a custom persona (cannot delete built-in ones).
- `switch_persona(session_id, name)`
  — Switch active persona for a session. Returns persona content or None.
- `get_active_persona(session_id)`
  — Get the active persona name for a session.
- `get_user_soul()`
  — Read user SOUL.md from ~/.salmalm/SOUL.md. Returns empty string if not found.
- `set_user_soul(content)`
  — Write user SOUL.md to ~/.salmalm/SOUL.md.
- `reset_user_soul()`
  — Delete user SOUL.md (revert to default).
- `build_system_prompt(full, mode)`
  — Build system prompt from SOUL.md + context files.

### `salmalm.core.session_manager`

> Session management — pruning, compaction, cache TTL tracking.

- `prune_context(messages)`
  — Prune old tool_result messages before LLM call.

### `salmalm.core.shutdown`

> Graceful Shutdown Manager — drain LLM streams, cancel tools, flush sessions, notify WS.

#### `class ShutdownManager`
> Coordinates graceful shutdown across all subsystems.

- `is_shutting_down()`
- `async execute(timeout)`
  — Run the full shutdown sequence.


## tools/ — Tools — 58+ Built-in Tools / 도구 — 58개 이상 내장 도구

### `salmalm.tools.__init__`

#### `class _PkgProxy`



### `salmalm.tools.tool_handlers`

> SalmAlm tool handlers — thin shim delegating to tool_registry.

- `execute_tool(name, args)`
  — Execute a tool — delegates to tool_registry.

### `salmalm.tools.tool_registry`

> Tool registry — decorator-based tool dispatch replacing if-elif chain.

- `register(name)`
  — Decorator to register a tool handler function.
- `register_dynamic(name, handler, tool_def)`
  — Dynamically register a tool at runtime (for plugins).
- `unregister_dynamic(name)`
  — Remove a dynamically registered tool.
- `get_dynamic_tools()`
  — Return all dynamically registered tool definitions.
- `execute_tool(name, args)`
  — Execute a tool and return result string. Auto-dispatches to remote node if available.

### `salmalm.tools.tools`

> SalmAlm tool definitions — schema for all 32 tools.


### `salmalm.tools.tools_agent`

> Agent tools: sub_agent, skill_manage, plugin_manage, cron_manage, mcp_manage, node_manage.

- `handle_sub_agent(args)`
- `handle_skill_manage(args)`
- `handle_plugin_manage(args)`
- `handle_cron_manage(args)`
- `handle_mcp_manage(args)`
- `handle_node_manage(args)`
- `handle_rag_search(args)`

### `salmalm.tools.tools_browser`

> Browser tool.

- `handle_browser(args)`

### `salmalm.tools.tools_calendar`

> Google Calendar tools — granular calendar_list, calendar_add, calendar_delete.

- `handle_calendar_list(args)`
  — List upcoming calendar events.
- `handle_calendar_add(args)`
  — Add a calendar event.
- `handle_calendar_delete(args)`
  — Delete a calendar event.

### `salmalm.tools.tools_common`

> Shared helper functions for tool modules.


### `salmalm.tools.tools_email`

> Gmail tools — granular email_inbox, email_read, email_send, email_search.

- `handle_email_inbox(args)`
  — List recent inbox messages.
- `handle_email_read(args)`
  — Read a specific email by message_id.
- `handle_email_send(args)`
  — Send an email.
- `handle_email_search(args)`
  — Search emails with Gmail query syntax.

### `salmalm.tools.tools_exec`

> Exec tools: exec, python_eval, background session management.

- `handle_exec(args)`
- `handle_exec_session(args)`
  — Manage background exec sessions: list, poll, kill.
- `handle_python_eval(args)`

### `salmalm.tools.tools_file`

> File tools: read_file, write_file, edit_file, diff_files.

- `handle_read_file(args)`
- `handle_write_file(args)`
- `handle_edit_file(args)`
- `handle_diff_files(args)`

### `salmalm.tools.tools_google`

> Google tools: google_calendar, gmail.

- `handle_google_calendar(args)`
- `handle_gmail(args)`

### `salmalm.tools.tools_media`

> Media tools: image_generate, image_analyze, tts, stt, screenshot, tts_generate.

- `handle_image_generate(args)`
- `handle_image_analyze(args)`
- `handle_tts(args)`
- `handle_stt(args)`
- `handle_screenshot(args)`
- `handle_tts_generate(args)`

### `salmalm.tools.tools_memory`

> Memory tools: memory_read, memory_write, memory_search, usage_report.

- `handle_memory_read(args)`
- `handle_memory_write(args)`
- `handle_memory_search(args)`
- `handle_usage_report(args)`

### `salmalm.tools.tools_misc`

> Misc tools: reminder, workflow, file_index, notification, weather, rss_reader.

- `handle_reminder(args)`
- `handle_workflow(args)`
- `handle_file_index(args)`
- `handle_notification(args)`
- `handle_weather(args)`
- `handle_rss_reader(args)`

### `salmalm.tools.tools_patch`

> apply_patch tool — multi-file patch application.

- `apply_patch(patch_text, base_dir)`
  — Apply a multi-file patch.

### `salmalm.tools.tools_personal`

> Personal assistant tools — notes, expenses, saved links, pomodoro, routines, briefing.

- `handle_note(args)`
  — Personal notes / knowledge base.
- `handle_expense(args)`
  — Expense tracker.
- `handle_save_link(args)`
  — Save a link/article for later reading.
- `handle_pomodoro(args)`
  — Pomodoro timer.
- `handle_routine(args)`
  — Morning/evening routine automation.
- `handle_briefing(args)`
  — Generate daily briefing.

### `salmalm.tools.tools_reaction`

> SalmAlm Reaction Tools — Send emoji reactions across channels.

- `send_reaction(channel, message_id, emoji)`
  — Send an emoji reaction to a message.

### `salmalm.tools.tools_reminder`

> Enhanced reminder tools — natural language time parsing (KR+EN), recurring reminders.

- `parse_natural_time(text)`
  — Parse natural language time expression into datetime.
- `parse_repeat_pattern(text)`
  — Parse repeat pattern from text.

### `salmalm.tools.tools_system`

> System tools: system_monitor, health_check.

- `handle_system_monitor(args)`
- `handle_health_check(args)`

### `salmalm.tools.tools_util`

> Utility tools: hash_text, regex_test, json_query, clipboard, qr_code, translate.

- `handle_hash_text(args)`
- `handle_regex_test(args)`
- `handle_json_query(args)`
- `handle_clipboard(args)`
- `handle_translate(args)`
- `handle_qr_code(args)`

### `salmalm.tools.tools_web`

> Web tools: web_search, web_fetch, http_request.

- `handle_web_search(args)`
- `handle_web_fetch(args)`
- `handle_http_request(args)`

## features/ — Features — Commands, RAG, MCP / 기능 — 명령어, RAG, MCP

### `salmalm.features.a2a`

> SalmAlm Agent-to-Agent Protocol — inter-instance communication.

#### `class A2AProtocol`
> SalmAlm instance-to-instance negotiation protocol.

- `sign(payload, secret)`
  — HMAC-SHA256 signature over canonical JSON.
- `verify(payload, signature, secret)`
- `pair(url, shared_secret, peer_name)`
  — Register a peer instance.
- `unpair(peer_id)`
- `list_peers()`
- `build_request(action, params)`
  — Build an unsigned A2A request payload.
- `send(peer_id, action, params, timeout)`
  — Send an A2A request to a paired peer. Returns the response dict.
- `receive(body)`
  — Process an incoming A2A request. Returns response dict.
- `approve(request_id)`
  — Approve a pending inbox request.
- `reject(request_id)`
  — Reject a pending inbox request.


### `salmalm.features.abort`

> Abort Generation (생성 중지) — LibreChat style.

#### `class AbortController`
> Per-session abort flag for stopping LLM generation.

- `set_abort(session_id)`
- `is_aborted(session_id)`
- `clear(session_id)`
- `save_partial(session_id, text)`
- `get_partial(session_id)`


### `salmalm.features.agents`

#### `class SubAgent`
> Background task executor with notification on completion.

- `spawn(cls, task, model, notify_telegram, _depth)`
  — Spawn a background sub-agent. Returns agent ID.
- `list_agents(cls)`
  — List all sub-agents with their status, label, and runtime.
- `stop_agent(cls, agent_id)`
  — Stop a running sub-agent.
- `get_log(cls, agent_id, limit)`
  — Get sub-agent transcript.
- `get_info(cls, agent_id)`
  — Get detailed metadata for a sub-agent.
- `get_result(cls, agent_id)`
  — Get the result of a completed sub-agent run.
- `send_message(cls, agent_id, message)`
  — Send a follow-up message to a completed sub-agent's session.

#### `class SkillLoader`
> OpenClaw-style skill loader.

- `scan(cls)`
  — Scan skills directory, return list of available skills.
- `load(cls, skill_name)`
  — Load a skill's SKILL.md content.
- `match(cls, user_message)`
  — Auto-detect which skill matches the user's request. Returns skill content or None.
- `install(cls, url)`
  — Install a skill from a Git URL or GitHub shorthand (user/repo).
- `uninstall(cls, skill_name)`
  — Remove a skill directory.

#### `class PluginLoader`
> Discover and load tool plugins from plugins/*.py files.

- `scan(cls)`
  — Scan plugins/ directory and load all .py files as tool providers.
- `get_all_tools(cls)`
  — Return all tool definitions from all plugins.
- `execute(cls, tool_name, args)`
  — Execute a plugin tool by name.
- `reload(cls)`
  — Reload all plugins.

#### `class AgentConfig`
> Configuration and paths for a single agent (에이전트 설정).

- `save()`
- `display_name()`
- `model()`
- `soul_file()`
- `api_key()`
- `allowed_tools()`
  — None means all tools allowed.
- `to_dict()`

#### `class AgentManager`
> Manages multiple agents with routing by Telegram chat/user.

- `scan()`
  — Scan agents directory and load all agent configs.
- `resolve(chat_key)`
  — Resolve which agent handles a given chat key (e.g. 'telegram:12345').
- `get_agent(agent_id)`
  — Get agent config by ID.
- `get_session_id(agent_id, base_session_id)`
  — Get agent-scoped session ID.
- `create(agent_id, display_name, model)`
  — Create a new agent. 새 에이전트 생성.
- `delete(agent_id)`
  — Delete an agent (cannot delete 'main').
- `bind(chat_key, agent_id)`
  — Bind a chat to an agent. 채팅을 에이전트에 바인딩.
- `unbind(chat_key)`
  — Remove a chat binding.
- `list_agents()`
  — List all agents. 전체 에이전트 목록.
- `list_bindings()`
  — Return all chat→agent bindings.


### `salmalm.features.bookmarks`

> Message Bookmarks (메시지 북마크) — LobeChat style.

#### `class BookmarkManager`
> Manage message bookmarks across sessions.

- `add(session_id, message_index, content_preview, note, role)`
- `remove(session_id, message_index)`
- `list_all(limit)`
- `list_session(session_id)`
- `is_bookmarked(session_id, message_index)`


### `salmalm.features.briefing`

> Daily Briefing — morning/evening summary generator.

#### `class DailyBriefing`
> Generate daily briefing summaries.

- `generate(sections)`
  — Generate a full briefing. sections: list of section names to include.
- `configure(key, value)`
  — Update briefing config.


### `salmalm.features.commands`

> Extended slash command router (30+ commands).

#### `class CommandRouter`
> Central slash-command dispatcher.

- `register(command, handler)`
  — Register exact-match command.
- `register_prefix(prefix, handler)`
  — Register prefix-match command.
- `async dispatch(text, session)`
  — Dispatch a command string. Returns response or None.
- `parse_directives(text)`
  — Extract directive commands from message text.
- `find_inline_shortcuts(text)`
  — Find inline shortcut commands within a message.
- `get_completions()`
  — Return command list for autocomplete / /api/commands.

- `register_telegram_commands(bot_token)`
  — Register commands with Telegram's setMyCommands API.
- `get_router(engine_dispatch)`

### `salmalm.features.compare`

> Response Compare / Beam (응답 비교) — BIG-AGI style.

- `async compare_models(session_id, message, models)`

### `salmalm.features.dashboard_life`

> Life Dashboard — one-page overview of personal data from existing tools.

#### `class LifeDashboard`
> Aggregates data from personal tools into a unified dashboard.

- `generate_dashboard()`
- `text_summary(section)`
- `render_html()`

#### `class ProactiveDigest`
> Generates morning/evening digest messages.

- `morning_digest()`
- `evening_digest()`
- `should_send(hour)`

- `get_dashboard()`
- `get_digest()`

### `salmalm.features.deadman`

> Dead Man's Switch — triggers actions after prolonged user inactivity.

#### `class DeadManSwitch`
> Monitors user activity and triggers emergency actions on prolonged inactivity.

- `record_activity()`
  — Record user activity (message or command).
- `reset()`
  — Manually reset the timer.
- `status()`
  — Return current switch status.
- `format_status()`
- `setup(inactivity_days, warning_hours, actions, confirmation_required)`
- `disable()`
- `check(send_fn, user_name)`
  — Periodic check — called from heartbeat.
- `confirm_alive()`
  — User confirms they're alive after warning.
- `test(user_name)`
  — Simulate activation without actually sending anything.
- `handle_command(args, send_fn, user_name)`
  — Handle /deadman subcommands.


### `salmalm.features.docs`

- `generate_api_docs_html()`
  — Generate API documentation HTML page.

### `salmalm.features.doctor`

> SalmAlm Doctor — self-diagnosis and repair tool.

#### `class Doctor`
> SalmAlm 자가 진단 + 수복 도구.

- `run_all(auto_fix)`
  — 전체 진단 실행, 결과 리스트 반환.
- `check_config_integrity()`
  — 설정 파일 존재/유효성/권한 검사.
- `check_database_integrity()`
  — SQLite DB 무결성 (PRAGMA integrity_check).
- `check_session_integrity()`
  — 세션 파일 존재/크기/손상 검사.
- `check_api_keys()`
  — API 키 설정 여부.
- `check_port_availability()`
  — 서버 포트 사용 가능 여부.
- `check_disk_space()`
  — 디스크 여유 공간.
- `check_permissions()`
  — 설정 파일 권한 (600 권장).
- `check_oauth_expiry()`
  — OAuth 토큰 만료 임박 여부.
- `migrate_config()`
  — 구 설정 → 신 설정 자동 마이그레이션.


### `salmalm.features.edge_cases`

> Backward-compatibility shim — re-exports from decomposed modules.


### `salmalm.features.file_upload`

> Enhanced File Upload (파일 업로드 강화) — Open WebUI style.

- `validate_upload(filename, size_bytes)`
- `extract_pdf_text(data)`
- `process_uploaded_file(filename, data)`

### `salmalm.features.fork`

> Conversation Fork / Regenerate (대화 포크) — LibreChat style.

#### `class ConversationFork`
> Manage alternative responses at the same message index.

- `save_alternative(session_id, message_index, content, model, active)`
- `get_alternatives(session_id, message_index)`
- `switch_alternative(session_id, message_index, alt_id)`
- `async regenerate(session_id, message_index)`


### `salmalm.features.heartbeat`

> SalmAlm Heartbeat — Cache warming for Anthropic prompt caching.

#### `class CacheWarmer`
> Periodically warm Anthropic prompt cache to prevent TTL expiry.

- `start()`
  — Start the cache warming background thread.
- `stop()`
  — Stop the cache warming thread.
- `stats()`

#### `class HeartbeatManager`
> Heartbeat manager with active hours support.

- `reload()`
- `config()`
- `is_active_hours()`
  — Check if current time is within active hours.
- `should_heartbeat()`
  — Check if heartbeat should run now.

- `load_cache_config()`
  — Load cache config from ~/.salmalm/cache.json.
- `save_cache_config(config)`
  — Save cache config.

### `salmalm.features.hooks`

> SalmAlm Hooks System — 이벤트 훅 매니저 (Event Hook Manager).

#### `class HookManager`
> Manages event hooks — loads config, fires hooks asynchronously.

- `reload()`
  — Reload hooks from ~/.salmalm/hooks.json.
- `save()`
  — Save current hooks config.
- `register_plugin_hook(event, callback)`
  — Register a plugin callback for an event.
- `unregister_plugin_hooks(callbacks)`
  — Remove specific plugin callbacks.
- `fire(event, context)`
  — Fire an event — runs all registered hooks asynchronously (non-blocking).
- `list_hooks()`
  — Return all configured hooks.
- `test_hook(event)`
  — Test-fire a hook event with dummy context.
- `add_hook(event, command)`
  — Add a command to an event hook.
- `remove_hook(event, index)`
  — Remove a hook command by event and index.


### `salmalm.features.mcp`

#### `class MCPServer`
> MCP Server that exposes SalmAlm tools via JSON-RPC 2.0.

- `set_tools(tools, executor)`
  — Register tools and their executor function.
- `async handle_message(msg)`
  — Handle a single JSON-RPC message. Returns response or None for notifications.
- `async run_stdio()`
  — Run MCP server on stdin/stdout (for subprocess transport).

#### `class MCPClientConnection`
> A connection to a single external MCP server (stdio transport).

- `connect()`
  — Start the MCP server subprocess and initialize.
- `disconnect()`
  — Disconnect from an MCP server.
- `tools()`
  — List all available tools from connected MCP servers.
- `call_tool(name, arguments, timeout)`
  — Call a tool on the remote MCP server.
- `read_resource(uri)`
  — Read a resource from the remote MCP server.

#### `class MCPManager`
> Manages multiple MCP client connections + the server instance.

- `server()`
  — Get connection info for a specific MCP server.
- `add_server(name, command, env, cwd, auto_connect)`
  — Add and optionally connect to an external MCP server.
- `remove_server(name)`
  — Disconnect and remove an MCP server.
- `list_servers()`
  — List all configured MCP servers and their status.
- `get_all_tools()`
  — Get all tools from all connected MCP servers (for LLM tool lists).
- `call_tool(prefixed_name, arguments)`
  — Call an MCP tool by its prefixed name (mcp_servername_toolname).
- `save_config()`
  — Save server configurations to JSON.
- `load_config()`
  — Load and auto-connect configured MCP servers.
- `shutdown()`
  — Disconnect all clients.


### `salmalm.features.mcp_marketplace`

> MCP Marketplace — catalog, install, manage MCP servers.

#### `class MCPMarketplace`
> Manage MCP server catalog, installation, and lifecycle.

- `install(name, params)`
  — Install an MCP server from catalog.
- `remove(name)`
- `list_installed()`
- `catalog()`
- `status()`
- `search(query)`
- `auto_connect_all(retries)`
  — Connect all installed servers on startup.
- `get_catalog_json()`
  — Return catalog for /api/mcp/catalog.
- `get_installed_json()`
  — Return installed list for /api/mcp/installed.


### `salmalm.features.model_detect`

> Model Auto-Detection (모델 자동 감지) — Open WebUI style.

#### `class ModelDetector`
> Auto-detect available models from all configured providers.

- `detect_all(force)`


### `salmalm.features.mood`

> SalmAlm Mood-Aware Response — detects user emotion and adjusts response tone.

#### `class MoodDetector`
> Detects user mood from text using keywords, patterns, and emoji.

- `enabled()`
- `sensitivity()`
- `set_mode(mode)`
  — Set mood detection mode: on, off, sensitive.
- `detect(text)`
  — Detect mood from text. Returns (mood, confidence 0.0-1.0).
- `get_tone_injection(mood)`
  — Get tone injection string for system prompt.
- `record_mood(mood, confidence)`
  — Record mood to history.
- `get_status(text)`
  — Return current mood status.
- `generate_report(period)`
  — Generate mood report for the given period.


### `salmalm.features.nodes`

#### `class SSHNode`
> Remote node accessible via SSH.

- `run(command, timeout)`
  — Execute command on remote node.
- `status()`
  — Get node system status (CPU, memory, disk, uptime).
- `upload(local_path, remote_path)`
  — Upload file via SCP.
- `download(remote_path, local_path)`
  — Download file via SCP.
- `is_reachable()`
  — Quick ping check.

#### `class HTTPNode`
> Remote node accessible via HTTP agent protocol.

- `run(command, timeout)`
  — Execute a command on a remote node.
- `status()`
  — Get the status of a remote node.
- `upload(local_path, remote_path)`
  — Upload via HTTP (base64 in JSON — for small files).
- `is_reachable()`
  — Check if a remote node is reachable.

#### `class NodeManager`
> Manages all remote nodes.

- `load_config()`
  — Load nodes from nodes.json.
- `save_config()`
  — Save node configs to JSON.
- `add_ssh_node(name, host, user, port, key)`
  — Add an SSH node.
- `add_http_node(name, url, token)`
  — Add an HTTP agent node.
- `remove_node(name)`
  — Remove a registered remote node.
- `get_node(name)`
  — Get configuration for a specific node.
- `list_nodes()`
  — List all nodes with basic status.
- `run_on(name, command, timeout)`
  — Execute command on a specific node.
- `status_all()`
  — Get status of all nodes.
- `wake_on_lan(mac_address, broadcast, port)`
  — Send Wake-on-LAN magic packet.

#### `class GatewayRegistry`
> Gateway side: manages registered nodes that can execute tools remotely.

- `set_gateway_token(token)`
  — Set the gateway authentication token. Nodes must provide this to register.
- `register(node_id, url, token, capabilities, name)`
  — Register a node with the gateway. Requires auth_token if gateway_token is set.
- `heartbeat(node_id)`
  — Update node heartbeat timestamp.
- `unregister(node_id)`
  — Remove a node.
- `list_nodes()`
  — List all registered nodes with status.
- `find_node(tool_name)`
  — Find an online node that supports the given tool.
- `dispatch(node_id, tool_name, tool_args, timeout)`
  — Dispatch a tool call to a specific node.
- `dispatch_auto(tool_name, tool_args, timeout)`
  — Auto-find a node for this tool and dispatch. Returns None if no node available.

#### `class NodeAgent`
> Node side: lightweight agent that receives and executes tool calls from gateway.

- `register()`
  — Register this node with the gateway.
- `start_heartbeat(interval)`
  — Start background heartbeat to gateway.
- `stop()`
  — Stop the node manager and close connections.


### `salmalm.features.plugin_manager`

> SalmAlm Plugin Architecture — 디렉토리 기반 플러그인 시스템.

#### `class PluginInfo`
> Metadata and runtime state for a loaded plugin.

- `to_dict()`

#### `class PluginManager`
> Manages directory-based plugins with tool registration and hook integration.

- `scan_and_load()`
  — Scan ~/.salmalm/plugins/ and load all valid plugins.
- `get_all_tools()`
  — Return all tool definitions from enabled plugins.
- `list_plugins()`
  — Return list of all plugins with their status.
- `enable(name)`
  — Enable a plugin.
- `disable(name)`
  — Disable a plugin.
- `reload_all()`
  — Reload all plugins.


### `salmalm.features.presence`

> SalmAlm Presence System — Track connected clients.

#### `class PresenceEntry`

- `state()`
- `is_expired()`
- `touch()`
  — Update last activity and optional fields.
- `to_dict()`

#### `class PresenceManager`
> Track connected client instances with TTL-based expiry.

- `register(instance_id)`
  — Register or update a client instance.
- `heartbeat(instance_id)`
  — Update last activity for a client.
- `unregister(instance_id)`
- `get(instance_id)`
- `list_all(include_expired)`
  — List all presence entries.
- `count()`
- `count_by_state()`
- `clear()`


### `salmalm.features.prompt_vars`

> System Prompt Variables (시스템 프롬프트 변수) — LobeChat style.

- `substitute_prompt_variables(text, session_id, model, user)`

### `salmalm.features.provider_health`

> Provider Health Check (프로바이더 상태 확인) — Open WebUI style.

#### `class ProviderHealthCheck`
> Check health of all configured LLM providers.

- `check_all(force)`


### `salmalm.features.rag`

#### `class RAGEngine`
> Hybrid BM25 + TF-IDF vector retrieval engine with persistent SQLite index.

- `config()`
- `index_file(label, fpath)`
  — Index a single file.
- `reindex(force)`
  — Rebuild the index from source files.
- `search(query, max_results, min_score)`
  — Hybrid search (BM25 + Vector). Returns list of {score, source, line, text}.
- `build_context(query, max_chars, max_results)`
  — Build a context string for RAG injection into LLM prompts.
- `get_stats()`
  — Return index statistics.
- `close()`
  — Close the RAG database connection.

- `decompose_jamo(text)`
  — Decompose Korean syllables into jamo (초성/중성/종성).
- `simple_stem(word)`
  — Simple English suffix stripping.
- `expand_query(tokens)`
  — Expand query tokens with synonyms.
- `load_rag_config(config_path)`
  — Load rag.json config, falling back to defaults.
- `compute_tf(tokens)`
  — Compute term frequency vector (normalized).
- `cosine_similarity(v1, v2)`
  — Cosine similarity between two sparse vectors (dict-based).
- `inject_rag_context(messages, system_prompt, max_chars)`
  — Analyze recent messages and inject relevant RAG context into system prompt.

### `salmalm.features.screen_capture`

> Screen capture and Computer Use module.

#### `class ScreenCapture`
> Platform-aware screen capture using native tools.

- `capture_screen()`
  — Capture screen and return PNG bytes.
- `ocr_image(image_path)`
  — Run OCR on image using tesseract if available.
- `image_to_base64(png_bytes)`
- `capture_and_analyze(llm_func)`
  — Capture screen and optionally analyze with LLM Vision.

#### `class ScreenHistory`
> Manages periodic capture history (Rewind-style).

- `save_capture(png_bytes, ocr_text)`
  — Save a capture to history.
- `get_history(n)`
  — Get most recent N captures.
- `search(query)`
  — Search captures by OCR text.
- `start_watching()`
  — Start periodic capture.
- `stop_watching()`

#### `class ScreenManager`
> High-level interface for /screen commands.

- `capture(llm_func)`
- `watch(toggle)`
- `history(n)`
- `search(query)`


### `salmalm.features.self_evolve`

> SalmAlm Self-Evolving Prompt — learns user preferences from conversation patterns.

#### `class PatternAnalyzer`
> Analyzes conversation patterns using pure Python heuristics.

- `analyze_length_preference(messages)`
  — Analyze if user prefers concise or detailed responses.
- `analyze_time_patterns(messages)`
  — Analyze conversation tone by time of day.
- `analyze_topic_frequency(messages)`
  — Count topic categories from messages.
- `analyze_language_ratio(messages)`
  — Analyze Korean vs English ratio. 0.0=all EN, 1.0=all KR.
- `analyze_feedback_signals(messages)`
  — Detect positive/negative feedback patterns.
- `analyze_code_comment_preference(messages)`
  — Detect if user prefers or dislikes code comments.

#### `class PromptEvolver`
> Learns user preferences and evolves the system prompt over time.

- `record_conversation(messages)`
  — Record a conversation for pattern analysis.
- `should_suggest_evolution()`
  — Check if we should suggest evolving SOUL.md.
- `generate_rules()`
  — Generate auto-evolution rules from learned preferences.
- `apply_to_soul(soul_path)`
  — Apply auto-evolved rules to SOUL.md. Returns status message.
- `get_status()`
  — Return current evolution status.
- `get_history()`
  — Return evolution history.
- `reset()`
  — Reset all evolution data.


### `salmalm.features.session_groups`

> Session Groups (대화 주제 그룹) — LobeChat style.

#### `class SessionGroupManager`
> Manage session groups/folders for organizing conversations.

- `list_groups()`
- `create_group(name, color)`
- `update_group(group_id)`
- `delete_group(group_id)`
- `move_session(session_id, group_id)`


### `salmalm.features.shadow`

> SalmAlm Shadow Mode — learn user style and proxy-reply when absent.

#### `class ShadowMode`
> Learn user messaging style and generate proxy replies when absent.

- `learn(messages)`
  — Analyse *user* messages and build a style profile.
- `build_proxy_prompt(incoming_message)`
  — Build an LLM system prompt that mimics the user's style.
- `generate_proxy_response(incoming_message, confidence)`
  — Generate a proxy response. If confidence is below threshold, return a polite away message.
- `should_proxy()`
  — Return True if shadow mode is active and profile exists.
- `handle_command(args, session_messages)`
  — Handle /shadow subcommands. Returns response text.


### `salmalm.features.sla`

> SalmAlm SLA Engine — Uptime monitoring, latency tracking, watchdog.

#### `class SLAConfig`
> Runtime-reloadable SLA configuration from ~/.salmalm/sla.json.

- `load()`
  — Load config from disk. Creates default if missing.
- `save()`
  — Write current config to disk.
- `get(key, default)`
- `set(key, value)`
- `get_all()`
- `update(data)`

#### `class UptimeMonitor`
> Track server uptime, detect crashes, log downtime events.

- `init_db()`
  — Create uptime_log table if not exists.
- `on_startup()`
  — Called at server startup: check lockfile, record crash if needed.
- `on_shutdown()`
  — Called on graceful shutdown: remove lockfile.
- `record_downtime(start, end, duration, reason)`
  — Manually record a downtime event.
- `get_uptime_seconds()`
- `get_uptime_human()`
- `get_monthly_uptime_pct(year, month)`
  — Calculate uptime percentage for a given month.
- `get_daily_uptime_pct(date_str)`
  — Calculate uptime percentage for a given day.
- `get_recent_incidents(limit)`
  — Get recent downtime incidents.
- `get_stats()`
  — Full uptime stats for API/dashboard.

#### `class LatencyTracker`
> Track TTFT and total response time with ring buffer.

- `record(ttft_ms, total_ms, model, timed_out, session_id)`
  — Record a single request's latency.
- `should_failover()`
  — Check if consecutive timeouts warrant a model failover.
- `reset_timeout_counter()`
- `get_stats()`
  — Get latency statistics: P50/P95/P99 + histogram.

#### `class Watchdog`
> Background watchdog: periodic self-diagnosis + auto-recovery.

- `start()`
  — Start watchdog background thread.
- `stop()`
  — Stop watchdog.
- `get_last_report()`
  — Get the most recent watchdog report.
- `get_detailed_health()`
  — Detailed health report for /health detail command.


### `salmalm.features.smart_paste`

> Smart Paste (스마트 붙여넣기) — BIG-AGI style.

- `detect_paste_type(text)`

### `salmalm.features.split_response`

> SalmAlm A/B Split Response — dual-perspective answers.

#### `class SplitResponder`
> Generate dual-perspective responses for a single question.

- `available_modes()`
- `should_suggest_split(text)`
  — Check if the text contains patterns suggesting a split response.
- `set_custom(label_a, label_b, prompt_a, prompt_b)`
- `async generate(question, mode)`
  — Generate split responses. Returns dict with responses and metadata.
- `format_result(result)`
  — Format split result for display.
- `format_buttons()`
  — Return inline button descriptors.
- `suggest_button()`
  — Return a 'suggest split' inline button descriptor.
- `async merge(result)`
  — Merge two perspectives into a combined response.
- `async continue_with(result, choice, follow_up)`
  — Continue conversation with the chosen perspective.
- `handle_command(args)`
  — Handle /split subcommands (sync wrapper). Returns text.


### `salmalm.features.stability`

#### `class CircuitBreaker`
> Track error rates per component. Trip after threshold.

- `record_error(component, error)`
  — Record an error for a component.
- `record_success(component)`
  — Record successful operation — helps reset breaker.
- `is_tripped(component)`
  — Check if circuit breaker is open (too many errors).
- `get_status()`
  — Get all component statuses.

#### `class HealthMonitor`
> Comprehensive health monitoring and auto-recovery.

- `check_health()`
  — Run comprehensive health check. Returns health report.
- `async auto_recover()`
  — Attempt to recover crashed components.
- `startup_selftest()`
  — Run self-test on startup to verify all modules.

- `async watchdog_tick(monitor)`
  — Periodic watchdog check — run via cron every 5 minutes.

### `salmalm.features.stt`

> STT (Speech-to-Text) Manager — voice input via Web Speech API and OpenAI Whisper.

#### `class STTManager`
> Speech-to-text manager supporting Web Speech API and OpenAI Whisper.

- `enabled()`
- `web_enabled()`
- `telegram_voice()`
- `get_web_js()`
  — Return JavaScript snippet for Web Speech API integration.
- `transcribe(audio_data, filename, content_type)`
  — Transcribe audio using OpenAI Whisper API. Returns text or error.
- `handle_telegram_voice(file_data, file_name)`
  — Process a Telegram voice message. Returns transcribed text or None.


### `salmalm.features.summary_card`

> Conversation Summary Card (대화 요약 카드) — BIG-AGI style.

- `get_summary_card(session_id)`

### `salmalm.features.thoughts`

> SalmAlm Thought Stream — quick thought capture with SQLite storage and RAG integration.

#### `class ThoughtStream`
> Quick thought capture with SQLite storage.

- `add(content, mood)`
  — Add a thought. Returns the thought ID.
- `list_recent(n)`
  — List most recent N thoughts.
- `search(query)`
  — Search thoughts using RAG or simple LIKE.
- `by_tag(tag)`
  — Filter thoughts by tag.
- `timeline(date_str)`
  — Get thoughts for a specific date (YYYY-MM-DD). Defaults to today.
- `stats()`
  — Get thought statistics.
- `export_markdown()`
  — Export all thoughts as Markdown.
- `delete(thought_id)`
  — Delete a thought by ID.


### `salmalm.features.timecapsule`

> Time Capsule — schedule messages to your future self.

#### `class TimeCapsule`
> Manages time capsules stored in SQLite.

- `create(date_text, message, channel)`
  — Create a new time capsule.
- `list_pending()`
  — List capsules not yet delivered.
- `list_delivered()`
  — List already delivered capsules.
- `peek(capsule_id)`
  — Peek at a capsule (spoiler warning).
- `cancel(capsule_id)`
  — Cancel (delete) a pending capsule.
- `get_due_capsules(today)`
  — Get capsules due for delivery today.
- `mark_delivered(capsule_id)`
  — Mark a capsule as delivered.
- `deliver_due(send_fn, today)`
  — Deliver all due capsules. Returns list of delivery results.
- `handle_command(args, channel)`
  — Handle /capsule subcommands.


### `salmalm.features.transcript_hygiene`

> Transcript Hygiene — provider-specific session history sanitization.

#### `class TranscriptHygiene`
> Clean conversation history per provider rules before LLM API calls.

- `clean(messages)`
  — Return a sanitized copy of messages. Original is never modified.


### `salmalm.features.tray`

> Windows System Tray for SalmAlm — pure ctypes implementation.

- `is_windows()`
- `run_tray(port)`
  — Run SalmAlm with system tray icon (Windows only).

### `salmalm.features.usage`

> Token Usage Tracking (사용량 추적) — LibreChat style.

#### `class UsageTracker`
> Per-user, per-model token usage tracking with daily/monthly reports.

- `record(session_id, model, input_tokens, output_tokens, cost)`
- `daily_report(days)`
- `monthly_report(months)`
- `model_breakdown()`


### `salmalm.features.users`

> SalmAlm Users — Multi-tenant user management, quotas, per-user isolation.

#### `class QuotaExceeded`
> Raised when a user exceeds their daily or monthly cost quota.


#### `class UserManager`
> Multi-tenant user manager with quotas and data isolation.

- `multi_tenant_enabled()`
  — Check if multi-tenant mode is enabled.
- `enable_multi_tenant(enabled)`
  — Enable or disable multi-tenant mode.
- `get_config(key, default)`
  — Get a multi-tenant config value.
- `set_config(key, value)`
  — Set a multi-tenant config value.
- `ensure_quota(user_id)`
  — Create quota record for user if it doesn't exist.
- `check_quota(user_id)`
  — Check if user is within quota. Returns quota info.
- `record_cost(user_id, cost)`
  — Record cost against user quota.
- `set_quota(user_id, daily_limit, monthly_limit)`
  — Set quota limits for a user (admin only).
- `get_quota(user_id)`
  — Get quota info for a user.
- `reset_all_daily_quotas()`
  — Reset all users' daily quotas. Called at midnight.


### `salmalm.features.vault_chat`

> Encrypted Vault Chat — AES-256-GCM encrypted conversation store.

#### `class VaultChat`
> Encrypted vault for private notes and conversations.

- `is_setup()`
  — Check if vault has been set up (meta file exists).
- `setup(password)`
  — Initial vault setup — create password hash and empty encrypted DB.
- `change_password(old_password, new_password)`
  — Change vault password.
- `open(password)`
  — Unlock the vault.
- `close()`
  — Lock the vault — flush to disk and wipe key from memory.
- `is_open()`
- `vault_note(content, category)`
  — Add a note to the vault.
- `vault_list(category, limit)`
  — List vault entries.
- `vault_search(query)`
  — Search vault entries.
- `vault_delete(entry_id)`
  — Delete a vault entry.


### `salmalm.features.watcher`

> File Watcher + Auto-Index — polling-based file change detection with RAG re-indexing.

#### `class FileWatcher`
> Polling-based file watcher that detects created/modified/deleted files.

- `start()`
  — Start watching in a background thread.
- `stop()`
  — Stop the watcher.
- `running()`
- `get_watched_files()`
  — Return current tracked files and their mtimes.

#### `class RAGFileWatcher`
> FileWatcher that triggers RAG re-indexing on file changes.



### `salmalm.features.workflow`

> Workflow Engine — multi-step automation pipelines with variable substitution.

#### `class StepResult`

- `to_dict()`

#### `class WorkflowEngine`
> Execute multi-step workflows with variable substitution.

- `list_workflows()`
- `get_workflow(name)`
- `save_workflow(workflow)`
- `delete_workflow(name)`
- `run(name)`
- `execute(workflow)`
- `get_logs(name, limit)`
- `get_presets()`
- `install_preset(name)`

- `handle_workflow_command(text)`

## channels/ — Channels — Telegram, Discord / 채널 — 텔레그램, 디스코드

### `salmalm.channels.channel_router`

> SalmAlm Channel Router — Multi-channel message routing.

#### `class ChannelRouter`
> Routes messages between multiple channels and the agent engine.

- `register(name)`
  — Register a channel for routing.
- `unregister(name)`
- `set_handler(channel, handler)`
  — Set inbound message handler for a channel.
- `get_handler(channel)`
- `channels()`
- `is_enabled(name)`
- `route_outbound(channel, is_group)`
  — Send a message through the specified channel.
- `async route_inbound(channel, message, process_fn)`
  — Route an inbound message from a channel to the agent, return response.
- `list_channels()`
  — List all registered channels with status.
- `save_config()`
  — Persist current channel config.

- `format_for_channel(text, channel)`
  — Format text according to channel-specific rules.

### `salmalm.channels.discord_bot`

> SalmAlm Discord Bot — Pure stdlib Discord Gateway + HTTP API.

#### `class DiscordBot`
> Minimal Discord bot using Gateway WebSocket + REST API.

- `configure(token, owner_id)`
  — Configure the Discord bot with token and channel settings.
- `on_message(func)`
  — Decorator to register message handler.
- `send_message(channel_id, content, reply_to)`
  — Send a message to a channel.
- `send_typing(channel_id)`
  — Send typing indicator.
- `start_typing_loop(channel_id)`
  — Start a continuous typing indicator loop (refreshes every 8s).
- `add_reaction(channel_id, message_id, emoji)`
  — Add an emoji reaction to a Discord message.
- `async poll()`
  — Main gateway loop.
- `stop()`
  — Stop the Discord bot.


### `salmalm.channels.slack_bot`

> SalmAlm Slack Bot — Pure stdlib Slack integration.

#### `class SlackBot`
> Minimal Slack bot using Event API (webhook) + Web API (urllib).

- `configure(bot_token, signing_secret)`
  — Configure the Slack bot.
- `on_message(func)`
  — Register message handler.
- `send_message(channel, text)`
  — Send a message to a Slack channel.
- `add_reaction(channel, timestamp, emoji)`
  — Add an emoji reaction to a message.
- `get_bot_info()`
  — Fetch bot user info.
- `verify_request(timestamp, signature, body)`
  — Verify Slack request signature.
- `handle_event(payload)`
  — Handle an incoming Slack event.
- `update_message(channel, ts, text)`
  — Update an existing message.
- `delete_message(channel, ts)`
  — Delete a message.


### `salmalm.channels.telegram`

> SalmAlm Telegram bot.

#### `class TelegramBot`

- `configure(token, owner_id)`
  — Configure the Telegram bot with token and owner chat ID.
- `set_message_reaction(chat_id, message_id, emoji)`
  — React to a message with an emoji via setMessageReaction API.
- `send_message(chat_id, text, parse_mode, reply_markup, message_thread_id)`
  — Send a text message to a Telegram chat, with optional inline keyboard.
- `send_typing(chat_id)`
  — Send a typing indicator to a Telegram chat.
- `edit_message(chat_id, message_id, text, parse_mode)`
  — Edit an existing Telegram message.
- `set_webhook(url)`
  — Set Telegram webhook. Generates a secret_token for request verification.
- `delete_webhook()`
  — Delete Telegram webhook and return to polling mode.
- `verify_webhook_request(secret_token)`
  — Verify the X-Telegram-Bot-Api-Secret-Token header.
- `async handle_webhook_update(update)`
  — Process a single update received via webhook.
- `async poll()`
  — Long-polling loop for Telegram updates.


## security/ — Security — Crypto, Sandbox / 보안 — 암호화, 샌드박스

### `salmalm.security.__init__`

#### `class _PkgProxy`



### `salmalm.security.container`

> SalmAlm DI Container — Lightweight service registry.

#### `class Container`
> Lightweight DI container with lazy initialization.

- `register(name, factory)`
  — Register a lazy factory for a service.
- `set(name, instance)`
  — Set an already-created service instance.
- `get(name)`
  — Get a service, creating it lazily if needed.
- `replace(name, instance)`
  — Replace a service (for testing). Returns old instance.
- `has(name)`
  — Check if a service is registered.
- `reset()`
  — Clear all services (for testing).
- `vault()`
  — Get the Vault service instance.
- `router()`
  — Get the ModelRouter service instance.
- `auth_manager()`
  — Get the AuthManager service instance.
- `rate_limiter()`
  — Get the RateLimiter service instance.


### `salmalm.security.crypto`

> SalmAlm crypto — AES-256-GCM vault with HMAC-CTR fallback.

#### `class Vault`
> Encrypted key-value store for API keys and secrets.

- `is_unlocked()`
  — Whether the vault has been unlocked with a valid password.
- `create(password)`
  — Create a new vault with the given master password.
- `unlock(password)`
  — Unlock an existing vault. Returns True on success.
- `get(key, default)`
  — Get a stored value. Falls back to environment variable if not in vault.
- `set(key, value)`
  — Store a value (triggers re-encryption).
- `delete(key)`
  — Delete a key.
- `change_password(old_password, new_password)`
  — Change vault master password. Returns True on success.
- `keys()`
  — List all stored key names.


### `salmalm.security.exec_approvals`

> Exec approval system — allowlist/denylist + dangerous command detection.

#### `class BackgroundSession`
> Manages a background exec process.

- `start()`
  — Start the background process.
- `poll()`
  — Poll current status.
- `kill()`
  — Kill the background process.
- `list_sessions(cls)`
  — List all background sessions.
- `get_session(cls, session_id)`
  — Get a background session by ID.
- `kill_session(cls, session_id)`
  — Kill a specific background session.

- `check_approval(command)`
  — Check if a command needs approval.
- `check_env_override(env)`
  — Check if env dict tries to override blocked variables.

### `salmalm.security.sandbox`

> SalmAlm Sandboxing — Docker container or subprocess isolation.

#### `class SandboxResult`
> Result from a sandboxed execution.

- `output()`
  — Combined output suitable for display.

#### `class SandboxManager`
> Manages sandboxed command execution.

- `save_config()`
  — Persist current config to disk.
- `config()`
- `mode()`
  — Resolved execution mode.
- `is_dangerous(command)`
  — Check if a command matches dangerous patterns.
- `run(command, timeout, workspace, env, sandbox)`
  — Execute a command in the appropriate sandbox.
- `exec_command(command, timeout, sandbox)`
  — Execute command and return formatted output string.


### `salmalm.security.security`

> SalmAlm Security Module — OWASP compliance, security audit, hardening.

#### `class LoginRateLimiter`
> Per-key exponential backoff for login attempts.

- `check(key)`
  — Check if login attempt is allowed.
- `record_failure(key)`
  — Record a failed login attempt. 실패한 로그인 기록.
- `record_success(key)`
  — Clear attempts on successful login. 성공 시 시도 기록 초기화.
- `cleanup()`
  — Remove stale entries. 오래된 항목 정리.

#### `class SecurityAuditor`
> Generate OWASP Top 10 compliance report.

- `audit()`
  — Run full security audit. Returns report dict.
- `format_report()`
  — Format audit report as human-readable text.

- `redact_sensitive(text)`
  — 민감 정보를 [REDACTED]로 치환.
- `is_internal_ip(url)`
  — Check if URL resolves to internal/private IP.
- `sanitize_session_id(session_id)`
  — Sanitize session ID to prevent injection.
- `validate_input_size(data, max_size)`
  — Check input doesn't exceed size limit.

## utils/ — Utils — HTTP, Queue, Retry / 유틸리티 — HTTP, 큐, 재시도

### `salmalm.utils.async_http`

> Async HTTP client built on stdlib asyncio (no third-party deps).

#### `class AsyncHTTPResponse`
> Lightweight async HTTP response wrapper.

- `async read()`
  — Read entire response body (handles chunked transfer-encoding).
- `async json()`
- `async text()`
- `async iter_lines()`
  — Yield lines as they arrive (for SSE / streaming).
- `async iter_chunks(size)`
  — Yield raw byte chunks.

#### `class AsyncHTTPClient`
> Pure-stdlib asyncio HTTP/1.1 client.

- `async request(method, url)`
  — Send an HTTP/1.1 request and return an :class:`AsyncHTTPResponse`.
- `async get(url)`
- `async post(url)`
- `async post_json(url, data)`


### `salmalm.utils.browser`

#### `class CDPConnection`
> Low-level CDP WebSocket connection to Chrome.

- `async connect(ws_url)`
  — Connect to CDP WebSocket endpoint.
- `async disconnect()`
  — Disconnect from the browser WebSocket.
- `async send(method, params, timeout)`
  — Send CDP command and wait for response.
- `on_event(method, handler)`
  — Register event handler.

#### `class BrowserController`
> High-level browser automation API over CDP.

- `connected()`
  — Check if the browser connection is active.
- `async connect(tab_index)`
  — Connect to Chrome's first tab via CDP.
- `async disconnect()`
  — Disconnect from the browser WebSocket.
- `async navigate(url, wait_load)`
  — Navigate to URL. Returns {frameId, loaderId}.
- `async screenshot(full_page, format, quality)`
  — Take screenshot, return base64 encoded image.
- `async get_text()`
  — Extract page text content.
- `async get_html()`
  — Get page HTML.
- `async evaluate(expression, return_by_value)`
  — Execute JavaScript and return result.
- `async click(selector)`
  — Click an element by CSS selector.
- `async type_text(selector, text)`
  — Type text into an input element.

#### `class BrowserManager`
> Manages Chrome lifecycle — auto-detect, launch, connect, close.

- `find_chrome()`
  — Auto-detect Chrome/Chromium binary.
- `async launch(url, headless)`
  — Launch Chrome and connect via CDP.
- `controller()`
- `connected()`
- `async close()`
  — Disconnect and kill Chrome.
- `close_sync()`
  — Kill Chrome process (sync).

- `async browser_open(url)`
  — Open a URL. Launches Chrome if not connected.
- `async browser_screenshot()`
  — Take screenshot, return base64 PNG.
- `async browser_snapshot()`
  — Extract page text (accessibility tree approximation).
- `async browser_click(selector)`
  — Click element by CSS selector.
- `async browser_type(selector, text)`
  — Type text into element.
- `async browser_evaluate(js)`
  — Execute JavaScript and return result.
- `async browser_close()`
  — Close browser.

### `salmalm.utils.chunker`

> Smart block chunking — code fence aware, coalescing, human-like pacing.

#### `class ChunkerConfig`
> Configuration for EmbeddedBlockChunker.

- `effective_hard_cap()`
- `effective_max_lines()`
- `uses_plain_fallback()`

#### `class EmbeddedBlockChunker`
> Accumulates streaming text and emits Markdown-safe chunks.

- `buffer()`
- `chunk_count()`
- `feed(text)`
  — Feed a token/text fragment. May emit a chunk via callback.
- `check_idle()`
  — Check if idle timeout has elapsed and flush if needed.
- `flush()`
  — Flush any remaining buffer as the final chunk.
- `compute_delay()`
  — Compute human-like delay before sending the next chunk.
- `split_for_channel(text)`
  — Split a complete text into channel-appropriate messages.

- `load_config_from_file(path)`
  — Load streaming config from ~/.salmalm/streaming.json if it exists.

### `salmalm.utils.dedup`

> Message deduplication and channel-aware debouncing.

#### `class MessageDeduplicator`
> Deduplicates inbound messages using a TTL cache.

- `is_duplicate(channel, account, peer, message_id)`
  — Return True if this message was already seen within the TTL window.
- `size()`
- `clear()`

- `get_debounce_ms(channel)`
  — Get debounce time in ms for a channel.
- `should_skip_debounce(message, has_media)`
  — Return True if this message should skip debouncing.

### `salmalm.utils.file_logger`

> Structured file logger — JSON Lines format.

#### `class FileLogger`
> JSON Lines 파일 로거.

- `log(level, category, message)`
  — JSON 라인 로그 기록.
- `tail(lines, level)`
  — 최근 로그 조회.
- `search(query, days)`
  — 로그 검색.
- `cleanup(retain_days)`
  — 오래된 로그 삭제. Returns number of files removed.


### `salmalm.utils.logging_ext`

#### `class JSONFormatter`
> Format log records as JSON lines.

- `format(record)`
  — Format a log record with correlation ID prefix.

#### `class RequestLogger`
> Middleware-style request/response logger.

- `log_request(method, path, ip, user, status_code)`
  — Log a request with structured data.
- `get_metrics()`
  — Get request metrics (exclude internal durations list).

- `setup_production_logging(json_log, max_bytes, backup_count)`
  — Configure production-grade logging with rotation.
- `get_correlation_id()`
  — Get or create correlation ID for current request.
- `set_correlation_id(cid)`
  — Set the correlation ID for the current thread context.
- `safe_execute(func)`
  — Execute a function with graceful error recovery.
- `async safe_execute_async(coro, fallback, tag)`
  — Async version of safe_execute.

### `salmalm.utils.markdown_ir`

> Markdown IR — intermediate representation for cross-channel rendering.

#### `class StyleSpan`


#### `class LinkSpan`


#### `class CodeBlock`


#### `class TableData`


#### `class MarkdownIR`


- `parse(markdown)`
  — Parse markdown text into MarkdownIR.
- `render_telegram(ir, table_mode)`
  — Render IR to Telegram HTML.
- `render_discord(ir, table_mode)`
  — Render IR to Discord Markdown.
- `render_slack(ir, table_mode)`
  — Render IR to Slack mrkdwn format.
- `render_plain(ir)`
  — Render IR as plain text (no formatting).
- `chunk_ir(ir, max_chars)`
  — Split IR into chunks that don't break style spans.

### `salmalm.utils.migration`

> SalmAlm Agent Migration — Export/Import agent state (인격/기억/설정 이동).

#### `class AgentExporter`
> Export agent state to a ZIP file.

- `export_agent()`
  — Export agent state to ZIP bytes.

#### `class ImportResult`
> Result of an import operation.

- `to_dict()`
- `summary()`
  — Human-readable summary / 사람이 읽을 수 있는 요약.

#### `class AgentImporter`
> Import agent state from a ZIP file.

- `preview(zip_data)`
  — Preview what's in the ZIP without importing.
- `import_agent(zip_data)`
  — Import agent state from ZIP bytes.

- `quick_sync_export()`
  — Export core agent state as lightweight JSON.
- `quick_sync_import(data)`
  — Import core agent state from lightweight JSON.
- `export_agent(include_vault, include_sessions, include_data)`
  — Export agent state to ZIP bytes. Convenience wrapper.
- `import_agent(zip_data, conflict_mode)`
  — Import agent state from ZIP bytes. Convenience wrapper.
- `preview_import(zip_data)`
  — Preview ZIP contents without importing.
- `export_filename()`
  — Generate export filename with date.

### `salmalm.utils.queue`

> SalmAlm Message Queue — lane-based FIFO with 5 modes, overflow policies, concurrency control.

#### `class QueueMode`


#### `class DropPolicy`


#### `class QueuedMessage`


#### `class SessionOptions`
> Per-session overrides, set via /queue command.


#### `class QueueLane`
> Per-session FIFO lane with serial execution guarantee.

- `async enqueue(message, processor, cfg, channel)`
  — Main entry: enqueue message, apply mode logic, return result.
- `get_steer_event()`
  — Get/create the steer event for the current execution.
- `consume_steer()`
  — Consume a steered message (called at tool boundaries).
- `reset_options()`
  — Reset per-session overrides to defaults.

#### `class _SemaphoreContext`
> Async context manager for semaphore.


#### `class MessageQueue`
> Global message queue manager with lane-based concurrency control.

- `config()`
- `reload_config()`
- `async process(session_id, message, processor, channel)`
  — Process a message through the session's lane.
- `get_lane(session_id)`
  — Get lane without creating.
- `handle_queue_command(session_id, args)`
  — Handle /queue command. Returns user-facing response.
- `cleanup(max_idle)`
  — Remove idle session lanes.
- `active_sessions()`
- `main_semaphore()`
- `subagent_semaphore()`

- `load_config()`
  — Load queue config from ~/.salmalm/queue.json, falling back to defaults.
- `save_config(cfg)`
  — Persist config to ~/.salmalm/queue.json.
- `apply_overflow(pending, cap, policy)`
  — Enforce cap on pending list. Returns (trimmed_list, summary_or_none).

### `salmalm.utils.retry`

> SalmAlm Retry Policy — exponential backoff with jitter.

- `retry_with_backoff(fn)`
  — Decorator: retry function with exponential backoff + jitter.
- `async async_retry_with_backoff(coro_fn)`
  — Async version: retry an async callable with exponential backoff.
- `retry_call(fn)`
  — Functional retry: call fn with retry logic (not a decorator).

### `salmalm.utils.tls`

- `ensure_cert(cn, days)`
  — Generate self-signed certificate if not exists. Returns True if cert exists.
- `create_ssl_context()`
  — Create SSL context with the server certificate.
- `create_https_server(address, handler_class, ssl_context)`
  — Create a ThreadingHTTPServer with optional TLS.
- `get_cert_info()`
  — Get certificate info.

## web/ — Web — Server, WebSocket, OAuth / 웹 — 서버, 웹소켓, OAuth

### `salmalm.web.__init__`

#### `class _PkgProxy`



### `salmalm.web.auth`

> SalmAlm Auth — Multi-user authentication, session isolation, RBAC, rate limiting.

#### `class TokenManager`
> Stateless token creation/verification using HMAC-SHA256.

- `create(payload, expires_in)`
  — Create a signed token. Default expiry: 24h.
- `verify(token)`
  — Verify token signature and expiry. Returns payload or None.

#### `class RateLimitExceeded`


#### `class RateLimiter`
> Token bucket rate limiter per key (user_id or IP).

- `check(key, role)`
  — Check rate limit. Raises RateLimitExceeded if exceeded.
- `get_remaining(key)`
  — Get remaining requests allowed in the current rate limit window.
- `cleanup()`
  — Remove stale buckets (>1h inactive).

#### `class AuthManager`
> Multi-user authentication with SQLite backend.

- `create_user(username, password, role)`
  — Create a new user. Returns user info.
- `authenticate(username, password)`
  — Authenticate user. Returns user dict or None.
- `authenticate_api_key(api_key)`
  — Authenticate via API key (constant-time hash comparison).
- `create_token(user, expires_in)`
  — Create auth token for authenticated user.
- `verify_token(token)`
  — Verify auth token. Returns user info or None.
- `list_users()`
  — List all users (admin only).
- `delete_user(username)`
  — Delete a user account by username.
- `change_password(username, new_password)`
  — Change a user password. Returns True on success.
- `has_permission(user, action)`
  — Check if user has permission for action.

- `extract_auth(headers)`
  — Extract user from headers. Accepts dict (case-sensitive) or HTTPMessage (case-insensitive).

### `salmalm.web.oauth`

> OAuth subscription authentication for Anthropic and OpenAI.

#### `class AnthropicOAuth`

- `get_auth_url(redirect_uri, state)`
- `exchange_code(code, redirect_uri)`
- `refresh_token(refresh_token)`
- `is_expired(token_data)`
- `is_expiring_soon(token_data, threshold)`
- `auto_refresh(token_data)`

#### `class OpenAIOAuth`

- `get_auth_url(redirect_uri, state)`
- `exchange_code(code, redirect_uri)`
- `refresh_token(refresh_token)`
- `is_expired(token_data)`

#### `class OAuthManager`
> Manages OAuth tokens for multiple providers.

- `setup(provider, redirect_uri)`
- `handle_callback(code, state, redirect_uri)`
- `status()`
- `revoke(provider)`
- `refresh(provider)`
- `get_token(provider)`
  — Get access token for provider, auto-refreshing if needed.
- `get_api_status()`
  — Return status dict for /api/oauth/status.


### `salmalm.web.templates`

> SalmAlm HTML templates — thin loader over static/ files.


### `salmalm.web.web`

> SalmAlm Web UI — HTML + WebHandler.

#### `class WebHandler`
> HTTP handler for web UI and API.

- `log_message(format)`
  — Suppress default HTTP request logging.
- `do_PUT()`
  — Handle HTTP PUT requests.
- `do_OPTIONS()`
  — Handle CORS preflight requests.
- `do_GET()`
  — Handle HTTP GET requests.
- `do_POST()`
  — Handle HTTP POST requests.


### `salmalm.web.ws`

#### `class WSClient`
> Represents a single WebSocket connection.

- `async send_json(data)`
  — Send a JSON message as a WebSocket text frame.
- `async send_text(text)`
  — Send a text message to a connected WebSocket client.
- `async recv_frame()`
  — Read one WebSocket frame. Returns (opcode, payload) or None on close.
- `async close(code, reason)`
  — Send close frame and close connection.

#### `class WebSocketServer`
> Async WebSocket server that handles upgrade from raw TCP.

- `on_message(fn)`
  — Handle an incoming WebSocket message.
- `on_connect(fn)`
  — Handle a new WebSocket client connection.
- `on_disconnect(fn)`
  — Handle a WebSocket client disconnection.
- `async start()`
  — Start listening for WebSocket connections.
- `async shutdown()`
  — Graceful shutdown: notify clients with shutdown message, then close.
- `async stop()`
  — Stop the WebSocket server (alias for shutdown).
- `async broadcast(data, session_id)`
  — Send to all connected clients (or filtered by session).
- `client_count()`
  — Get the number of connected WebSocket clients.

#### `class StreamingResponse`
> Helper to stream LLM response chunks to a WS client.

- `async send_chunk(text)`
  — Send a text chunk (partial response).
- `async send_tool_call(tool_name, tool_input, result)`
  — Notify client about a tool call.
- `async send_thinking(text)`
  — Send thinking/reasoning chunk.
- `async send_done(full_text)`
  — Signal completion.
- `async send_error(error)`
  — Send an error message to a WebSocket client.


## salmalm/ — Top-level Modules / 최상위 모듈

### `salmalm.bootstrap`

> Server bootstrap — start all SalmAlm services.

- `async run_server()`
  — Main async entry point — boot all services.

### `salmalm.cli`

> CLI argument parsing for SalmAlm.

- `setup_workdir()`
  — Set working directory and load .env.
- `dispatch_cli()`
  — Handle CLI flags. Returns True if a flag was handled (caller should exit).

### `salmalm.config_manager`

> Centralized configuration manager for SalmAlm.

#### `class ConfigManager`
> 중앙집중 설정 관리자.

- `load(cls, name, defaults)`
  — 설정 파일 로드. name='mood' → ~/.salmalm/mood.json
- `save(cls, name, config)`
  — 설정 파일 저장.
- `resolve(cls, name, key, default)`
  — Resolve a single config value with full priority chain.
- `get(cls, name, key, default)`
  — 단일 키 조회 (resolve 사용).
- `set(cls, name, key, value)`
  — 단일 키 설정.
- `exists(cls, name)`
- `delete(cls, name)`
- `list_configs(cls)`
  — 모든 설정 파일 목록.
- `migrate(cls, name)`
  — 설정 파일 마이그레이션 실행.

- `set_cli_overrides(overrides)`
  — Set CLI argument overrides (called at startup).
