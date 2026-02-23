# Extended Thinking

SalmAlm supports extended thinking (chain-of-thought) for complex reasoning tasks, compatible with both Anthropic and OpenAI providers.

## How It Works

Extended thinking gives the LLM a dedicated "thinking" phase before responding. The model reasons step-by-step internally, then produces a final answer.

```
User Message → [Thinking Phase: budget_tokens of reasoning] → Final Response
```

## Thinking Levels

| Level | Budget Tokens | Use Case |
|-------|--------------|----------|
| `low` | 2,048 | Quick reasoning, simple logic |
| `medium` | 8,192 | Multi-step problems, analysis |
| `high` | 16,384 | Complex code, architecture |
| `xhigh` | 32,768 | Deep research, proofs |

## Provider Mapping

| Level | Anthropic | OpenAI |
|-------|-----------|--------|
| `low` | `budget_tokens: 2048` | `reasoning_effort: low` |
| `medium` | `budget_tokens: 8192` | `reasoning_effort: medium` |
| `high` | `budget_tokens: 16384` | `reasoning_effort: high` |
| `xhigh` | `budget_tokens: 32768` | — |

## Usage

### Commands

```
/think low      → Enable low thinking
/think high     → Enable high thinking
/think off      → Disable thinking
```

### Web UI

**Settings → Engine Optimization → Thinking Level** dropdown.

### Programmatic

```bash
curl -X POST http://localhost:18800/api/engine/settings \
  -H "Content-Type: application/json" \
  -d '{"thinking_level": "medium"}'
```

## Cost Considerations

Thinking tokens count toward usage. A `high` level request may use 16K+ additional tokens. Use `low` for everyday tasks and `high`/`xhigh` only when needed.

## How It Differs from OpenClaw

| Feature | SalmAlm | OpenClaw |
|---------|---------|----------|
| User control | Manual level selection | Auto-suggested |
| Levels | 4 (low/medium/high/xhigh) | 3 (low/medium/high) |
| Provider support | Anthropic + OpenAI | Anthropic only |
| Default | Off | Off |

## Temperature Interaction

When thinking is enabled, temperature is automatically set to 1.0 (Anthropic requirement). Your configured temperature applies to non-thinking requests.
