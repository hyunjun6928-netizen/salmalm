# Multi-Model Routing
# 멀티모델 라우팅

## Overview / 개요

SalmAlm automatically selects the best LLM model based on task complexity, cost, and availability.

SalmAlm은 작업 복잡도, 비용, 가용성에 따라 최적의 LLM 모델을 자동 선택합니다.

## Supported Providers / 지원 프로바이더

- **Anthropic**: Claude Opus 4, Sonnet 4, Haiku
- **OpenAI**: GPT-4o, GPT-4, GPT-3.5-turbo
- **Google**: Gemini Pro, Gemini Flash
- **xAI**: Grok
- **OpenRouter**: Any model (200+)
- **Ollama**: Local models (Llama, Mistral, etc.)

## How It Works / 작동 방식

1. **Auto-detection** — scans configured API keys on startup / 시작 시 설정된 API 키 자동 감지
2. **Task routing** — complex tasks → Opus, simple tasks → Haiku / 복잡한 작업 → Opus, 간단한 작업 → Haiku
3. **Failover** — if primary model fails, falls back to next available with exponential backoff / 기본 모델 실패 시 지수 백오프로 다음 모델로 전환
4. **Manual override** — use `/model <name>` to force a specific model / `/model <이름>`으로 특정 모델 강제 지정

## Context Management / 컨텍스트 관리

- **Auto-compaction** at 80K tokens — summarizes old messages / 80K 토큰에서 자동 압축
- **Session pruning** — cleans up tool results / 도구 결과 정리
- **Token tracking** — real-time token usage display / 실시간 토큰 사용량 표시
