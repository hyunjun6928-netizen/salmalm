# SLA & Monitoring

SalmAlm tracks performance metrics for every request — latency, token usage, cost, and error rates.

## Metrics Tracked

### Per-Request
- **Time to First Token (TTFT)** — milliseconds until first streaming chunk
- **Total latency** — end-to-end request time
- **Input/output tokens** — per model
- **Estimated cost** — based on model pricing

### Aggregate
- **Uptime** — server start time, total runtime
- **Request count** — total requests processed
- **Error rate** — failed requests / total
- **Model distribution** — which models handle which tiers

## Cost Tracking

SalmAlm estimates costs using built-in pricing tables:

| Model | Input ($/1M tok) | Output ($/1M tok) |
|-------|-------------------|---------------------|
| Claude Haiku 3.5 | $0.80 | $4.00 |
| Claude Sonnet 4 | $3.00 | $15.00 |
| GPT-4o | $2.50 | $10.00 |
| Gemini 2.5 Flash | $0.15 | $0.60 |

### Cost Cap

Set a daily spending limit:

```bash
SALMALM_COST_CAP=5.00  # $5/day limit
```

When the cap is reached, all LLM calls are blocked with a `CostCapExceeded` error until the next day.

## Commands

| Command | Description |
|---------|-------------|
| `/usage` | Token usage and cost summary |
| `/usage tokens` | Detailed token breakdown |
| `/usage cost` | Cost breakdown by model |
| `/latency` | Request latency statistics |
| `/uptime` | Server uptime |

## Web Dashboard

**Settings → Usage & Monitoring** shows:

- Daily/monthly usage charts
- Cost breakdown by model
- Latency percentiles (p50, p95, p99)
- Real-time request feed

### API Endpoints

```
GET /api/usage/daily    — Daily usage report
GET /api/usage/monthly  — Monthly aggregate
GET /api/metrics        — Prometheus-compatible metrics
GET /api/latency        — Latency statistics
GET /api/status         — Server health check
```

## Alerting

SalmAlm logs warnings when:

- Latency exceeds 10s (P95 threshold)
- Daily cost exceeds 80% of cap
- Error rate exceeds 5%
- Context window approaches model limit

## Circuit Breaker

The built-in circuit breaker detects:

- **Infinite loops** — 3+ identical (tool, args) in last 6 iterations
- **Provider failures** — consecutive 5xx errors trigger backoff
- **Cost overruns** — immediate halt on cap exceeded
