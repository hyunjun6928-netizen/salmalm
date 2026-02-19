# Core Module API
# 코어 모듈 API

The `salmalm.core` package contains the central engine and session management.

`salmalm.core` 패키지는 중앙 엔진과 세션 관리를 포함합니다.

## `salmalm.core.core`

Main SalmAlm class — the central orchestrator that initializes all subsystems.

메인 SalmAlm 클래스 — 모든 서브시스템을 초기화하는 중앙 오케스트레이터.

## `salmalm.core.engine`

LLM orchestration engine handling message routing, tool calls, and response streaming.

메시지 라우팅, 도구 호출, 응답 스트리밍을 처리하는 LLM 오케스트레이션 엔진.

## `salmalm.core.llm`

LLM provider abstraction — supports Anthropic, OpenAI, Google, xAI, OpenRouter, Ollama.

LLM 프로바이더 추상화 — Anthropic, OpenAI, Google, xAI, OpenRouter, Ollama 지원.

## `salmalm.core.llm_loop`

Conversation loop handler — manages multi-turn interactions with tool use.

대화 루프 핸들러 — 도구 사용을 포함한 멀티턴 인터랙션 관리.

## `salmalm.core.llm_task`

Async LLM task runner for background processing.

백그라운드 처리를 위한 비동기 LLM 태스크 러너.

## `salmalm.core.prompt`

System prompt builder — constructs context-aware prompts with tool descriptions.

시스템 프롬프트 빌더 — 도구 설명을 포함한 컨텍스트 인식 프롬프트 생성.

## `salmalm.core.session_manager`

Session lifecycle management — create, switch, delete, branch, rollback.

세션 라이프사이클 관리 — 생성, 전환, 삭제, 분기, 롤백.

## `salmalm.core.memory`

Memory management for persistent storage across sessions.

세션 간 영속 저장을 위한 메모리 관리.

## `salmalm.core.health`

Health check endpoints for monitoring and SLA.

모니터링 및 SLA를 위한 상태 점검 엔드포인트.

## `salmalm.core.shutdown`

Graceful shutdown handler — saves state, closes connections, flushes logs.

안전한 종료 핸들러 — 상태 저장, 연결 종료, 로그 플러시.

## `salmalm.core.export`

Session export in JSON and Markdown formats.

JSON 및 Markdown 형식의 세션 내보내기.

---

!!! tip "Auto-generated details / 자동 생성 상세"
    Run `python docs/gen_api.py` to regenerate detailed class/function docs from docstrings.
    `python docs/gen_api.py`를 실행하면 docstring에서 상세한 클래스/함수 문서를 재생성합니다.
