# Multi-Model Routing

SalmAlm supports 6 AI providers with automatic task-based routing — the right model for each message.

## Supported Providers

| Provider | Models | Key |
|----------|--------|-----|
| Anthropic | Claude Haiku, Sonnet, Opus | `ANTHROPIC_API_KEY` |
| OpenAI | GPT-4o, GPT-4o-mini, o1 | `OPENAI_API_KEY` |
| Google | Gemini 2.5 Flash/Pro | `GOOGLE_API_KEY` |
| xAI | Grok | `XAI_API_KEY` |
| DeepSeek | DeepSeek Chat/Reasoner | `DEEPSEEK_API_KEY` |
| Local LLM | Ollama, LM Studio | `LOCAL_LLM_URL` |

## Auto Routing

When model is set to `auto`, SalmAlm classifies each message into complexity tiers:

### Classification

| Tier | Examples | Default Model |
|------|----------|---------------|
| **Simple** | Greetings, yes/no, short questions | Claude Haiku (12x cheaper) |
| **Moderate** | Explanations, summaries, analysis | Claude Sonnet |
| **Complex** | Multi-step code, architecture, debugging | Claude Sonnet |

Classification uses keyword matching + heuristics (code blocks, question complexity, message length).

### Cost Impact

```
Before (always Sonnet): ~$7.09/day
After (auto routing):   ~$1.23/day  → 83% savings
```

## Fixed Model

Set a specific model via:

- **Web UI**: Model panel dropdown
- **Command**: `/model anthropic/claude-sonnet-4-20250514`
- **API**: `POST /api/model/switch`

## Per-Session Override

Each session can have its own model:

```
/model sonnet    → This session uses Sonnet
/model auto      → Back to auto routing
```

## Provider Key Fallback

SalmAlm tries providers in order:

1. Vault-stored API key
2. Environment variable
3. CLI OAuth token (if `SALMALM_CLI_OAUTH=1`)

If a provider key is missing, that provider's models are excluded from routing candidates.

## Configuration

### Web UI

**Settings → Engine Optimization → Auto Routing** panel shows:

- Current tier assignments
- Per-tier model selection
- Cost comparison with OpenClaw
- Classification guide

### Environment Variables

```bash
SALMALM_DEFAULT_MODEL=anthropic/claude-sonnet-4-20250514
SALMALM_SIMPLE_MODEL=anthropic/claude-haiku-3.5-20241022
SALMALM_COMPLEX_MODEL=anthropic/claude-sonnet-4-20250514
```
