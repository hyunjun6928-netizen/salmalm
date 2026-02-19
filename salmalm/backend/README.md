# Backend/Engine Rules

## Files
- `engine.py` — TaskClassifier + IntelligenceEngine + `process_message()`
- `core.py` — Sessions, audit, usage tracking, cron, model router, compaction
- `llm.py` — Multi-provider LLM API calls (OpenAI/Anthropic/Google/xAI/Ollama)
- `tool_handlers.py` — Execution logic for all 32 tools
- `tools.py` — Tool schema definitions
- `prompt.py` — System prompt builder

## Request Flow
```
User message → engine.process_message()
  → TaskClassifier.classify() → pick model tier
  → build messages (system prompt + history + user)
  → llm.call_llm() → provider API
  → if tool_calls: execute_tool() → append result → re-call LLM
  → compact_messages() if history too long
  → return response
```

## LLM Provider Patterns
- All providers use `urllib.request` (no `requests` library).
- `asyncio.to_thread()` wraps sync urllib calls for async compatibility.
- Provider detection: parse `model` string as `provider/model-name`.
- Fallback chain: if primary model fails, try FALLBACK_MODELS list.
- Track usage after every call: `track_usage(model, input_tokens, output_tokens)`.

## Tool Execution
- Tools run in `execute_tool(name, args)` — synchronous function.
- File tools: path validation via `WORKSPACE_DIR` allowlist. No access outside.
- `python_eval`: runs in subprocess (`subprocess.run`, NOT `shell=True`).
- Tool timeout: 30s default. Long-running tools should stream progress.
- Unknown tool name → return error string, never raise.

## Sessions
- `get_session(id)` — creates or retrieves. Thread-safe.
- System prompt injected on creation (from `prompt.py`).
- `compact_messages()` — summarize old messages when history > threshold.
- Stale sessions (>2h inactive) cleaned up by heartbeat.

## Model Router
- `ModelRouter.route(message, has_tools)` — picks model by intent + tier.
- Force model: `/model <name>` command sets `force_model` override.
- Aliases: `claude`, `gpt`, `grok`, `gemini` resolve to full provider/model.

## Slash Commands
- Defined in `engine.py` `_handle_slash()`.
- Must return string response (never None).
- Add new: add `elif cmd == '/mycommand':` block + update `/help` text.
