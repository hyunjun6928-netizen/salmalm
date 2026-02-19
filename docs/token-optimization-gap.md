# SalmAlm 토큰 최적화 갭 분석

> 비교 대상: OpenClaw (v2025) vs SalmAlm (v0.5.0)
> 분석일: 2026-02-20

---

## 1. Tool Schema 압축

### OpenClaw 방식
- `/context detail`로 도구별 스키마 크기 확인 가능
- 정책(tool policy)으로 세션/서브에이전트별 사용 도구 필터링
- 스키마는 매 런마다 필요한 것만 전송; 미사용 도구 제외 가능
- 도구 목록은 짧은 description + JSON schema 분리

### SalmAlm 현재 구현
- `tools.py`에 43개 도구 스키마를 **항상 전부** 전송
- 서브에이전트용 `subagent_tool_policy.json`으로 서브에이전트 도구 필터링 존재 (`features/agents.py:_filter_tools_for_subagent`)
- 메인 세션에서는 도구 필터링 없음
- 시스템 프롬프트(`prompt.py`)에도 43개 도구 목록을 텍스트로 중복 하드코딩

### 갭: **부분구현**
- 서브에이전트 필터링은 있으나, 메인 세션 도구 필터링 없음
- 시스템 프롬프트 내 도구 목록 텍스트 + JSON 스키마 이중 전송으로 ~2x 오버헤드

### 권장사항
1. `prompt.py`의 하드코딩된 도구 텍스트 목록 제거 — JSON 스키마가 이미 전송되므로 중복
2. 세션 컨텍스트에 따라 사용하지 않는 도구 스키마 제외 (예: google_calendar 미설정 시 해당 도구 제외)
3. `tools.py`에 `get_tools(context: dict) -> list` 패턴 도입하여 조건부 스키마 로딩

---

## 2. Image Auto-Resize

### OpenClaw 방식
- 문서에 명시적 기술 없으나, session pruning에서 이미지 블록은 prune 대상 제외
- 이미지 토큰은 API 수준(provider)에서 자동 처리

### SalmAlm 현재 구현
- `transcript_hygiene.py:_sanitize_images()` — 1MB 초과 이미지 감지만 하고 **리사이즈 안 함** (주석: "Can't resize without Pillow; just log")
- compaction 시 오래된 이미지는 `[Image attached]` 텍스트로 교체 (`core.py`)
- session pruning에서 이미지 블록 보호 (`_has_image_block`)

### 갭: **미구현**
- 대용량 이미지 감지는 하나 실제 리사이즈 불가

### 권장사항
1. Pillow 없이 구현하려면: base64 이미지의 해상도 추정 후 API 전송 시 `detail: "low"` 파라미터 사용 (OpenAI) 또는 크기 경고 메시지
2. stdlib만 사용 원칙 유지 시: 과도하게 큰 이미지(>1MB)는 전송 전 경고 또는 거부
3. compaction의 `[Image attached]` 교체 로직은 이미 좋음 — 이를 pruning 단계에서도 적용 (오래된 이미지 블록을 placeholder로 교체)

---

## 3. 응답 중단 시 Partial Credit

### OpenClaw 방식
- 문서에 명시적 기술 없음 (중단된 응답은 세션 히스토리에 그대로 유지)

### SalmAlm 현재 구현
- `engine.py:561-567` — abort controller로 중단 감지, partial 텍스트를 `⏹ [생성 중단됨]` 메시지와 함께 반환
- 중단된 응답의 partial 텍스트가 세션 히스토리에 **저장됨** (후속 요청에서 컨텍스트로 사용)

### 갭: **완전구현**
- 이미 partial 텍스트 보존 및 세션 반영 처리됨

### 권장사항
- 현재 구현 충분. 개선 여지: 중단된 tool_call의 결과를 synthetic `(cancelled)` 로 자동 삽입하면 Anthropic API 오류 방지에 도움

---

## 4. Transcript Hygiene

### OpenClaw 방식
- Session pruning이 오래된 tool result를 soft-trim(head+tail) 및 hard-clear 처리
- 이미지 블록 보호, keepLastAssistants 기반 cutoff
- 도구별 allow/deny 필터링
- in-memory only (디스크 미수정)

### SalmAlm 현재 구현
- `transcript_hygiene.py` — provider별 규칙 적용 (Anthropic: 연속 user 병합, orphan tool_result 제거, synthetic tool_result 삽입)
- `session_manager.py:prune_context()` — cache TTL 기반 pruning, soft-trim(4000자) + hard-clear(50K자), 이미지 보호
- compaction에서 tool result 500자 truncate, base64 이미지 교체

### 갭: **부분구현** (기능은 유사하나 세부 튜닝 부족)

### 차이점
| 항목 | OpenClaw | SalmAlm |
|------|----------|---------|
| Soft-trim headChars | 1500 | 1500 |
| Soft-trim tailChars | 1500 | 500 ← **불균형** |
| Hard-clear 임계값 | 50K (configurable) | 50K (하드코딩) |
| Tool allow/deny | 와일드카드 지원 | 없음 |
| Cache TTL pruning | provider별 configurable | 5분 고정 |
| 사용자 설정 가능 | yaml config | 불가 |

### 권장사항
1. `_PRUNE_TAIL`을 1500으로 증가 (session_manager.py) — tail에 중요 정보가 많음
2. 프루닝 설정을 환경변수/config로 노출: `SALMALM_PRUNE_TTL`, `SALMALM_PRUNE_SOFT_LIMIT` 등
3. 도구별 prune deny 지원 추가 (이미지 관련 도구 제외 등)

---

## 5. Session Pruning 전략 (Compaction 비교)

### OpenClaw 방식
- **Pruning**: in-memory, tool result만, cache-TTL 기반, 요청별 적용
- **Compaction**: LLM 요약 → JSONL에 persist, auto-compact on context overflow
- pre-compaction memory flush (중요 컨텍스트를 디스크에 보존)
- `/compact` 수동 + 자동 트리거

### SalmAlm 현재 구현
- **Pruning**: `session_manager.py:prune_context()` — cache-TTL 기반, soft/hard trim
- **Compaction**: `core.py:compact_messages()` — 3단계 (tool trim → old tool drop → LLM summarize)
  - Stage 1: tool result 500자 truncate + 이미지 placeholder
  - Stage 2: 오래된 tool 메시지 drop, user/assistant만 보존
  - Stage 3: LLM 요약 (threshold 초과 시)
  - 하드 리밋: 100 messages / 500K chars
- pre-compaction memory flush 구현됨 (`core/memory.py:flush_before_compaction`)

### 갭: **부분구현**

### 차이점
- OpenClaw: compaction 결과가 JSONL에 persist → 재시작 후에도 요약 유지
- SalmAlm: compaction이 in-memory로만 동작하는지 확인 필요 (세션 JSONL 없음)
- OpenClaw: cache-ttl pruning 후 TTL window reset으로 cache write cost 최적화
- SalmAlm: TTL reset 로직 있음 (`_record_api_call_time`)

### 권장사항
1. compaction 결과를 세션 파일에 persist (현재는 메모리에서만 유지되는 것으로 보임)
2. auto-compact 트리거를 engine의 LLM 호출 전 체크에 통합 (현재 compact_messages는 수동 호출 의존)
3. `/compact` 명령어 인자(focus area) 지원은 이미 있으나, 자동 트리거 시에도 smart focus 적용 검토

---

## 6. Streaming Latency (First-Token 최적화)

### OpenClaw 방식
- Anthropic SSE 스트리밍 기본
- Block streaming + coalescing으로 체감 응답 시간 최적화
- Telegram draft streaming (partial bubble update)
- Human-like pacing (800-2500ms 랜덤 딜레이)
- Non-Anthropic provider는 non-streaming fallback

### SalmAlm 현재 구현
- `llm.py:stream_anthropic()` — Anthropic SSE 스트리밍 구현 (urllib 기반)
- text_delta, thinking_delta, tool_use 이벤트 yield
- 비-Anthropic provider는 non-streaming 전체 응답 → single chunk yield
- Telegram bot에서 draft streaming 여부는 별도 확인 필요

### 갭: **부분구현**

### 차이점
- SalmAlm: Anthropic만 실시간 스트리밍, 나머지 provider는 전체 응답 대기
- Block coalescing/chunking 없음
- Telegram draft bubble update 미확인
- Human-like pacing 없음

### 권장사항
1. OpenAI/XAI provider도 SSE 스트리밍 지원 추가 (`stream: true` 파라미터)
2. Telegram에서 `editMessageText`로 progressive update 구현 (first-token 체감 시간 단축)
3. 스트리밍 timeout을 180초에서 provider별 분리 (간단한 쿼리에는 30초면 충분)

---

## 7. System Prompt 최적화

### OpenClaw 방식
- 시스템 프롬프트를 매 런마다 동적 조립
- Anthropic cache_control `ephemeral` 마킹으로 prompt caching 활용
- 도구 스키마에도 cache_control 마킹 (마지막 도구)
- 워크스페이스 파일 per-file 20K char truncation
- 스킬은 메타데이터만 (instruction은 on-demand read)
- Heartbeat로 cache warm 유지 (TTL 직전 호출)

### SalmAlm 현재 구현
- `prompt.py:build_system_prompt()` — 동적 조립
- per-file truncation 구현: `MAX_FILE_CHARS=15K`, `MAX_MEMORY_CHARS=5K`, `MAX_AGENTS_CHARS=2K`
- `_agents_loaded_full` 플래그로 AGENTS.md 재로드 시 축소
- Anthropic cache_control 구현 (`llm.py:_call_anthropic` — system + 마지막 tool)
- **문제점**: 시스템 프롬프트에 43개 도구 설명이 텍스트로 하드코딩 (~2000자) + JSON 스키마 별도 전송
- **문제점**: 정확한 시간 대신 timezone만 주입 (캐시 효율을 위한 의도적 선택 — 좋음 ✅)
- subagent용 minimal 모드 구현

### 갭: **부분구현**

### 주요 이슈
1. **도구 목록 이중 전송** — `prompt.py`의 `## 도구 (43개)` 섹션이 JSON 스키마와 중복 (~2000 토큰 낭비)
2. **시스템 프롬프트 크기** — 메타인지 프로토콜, 응답 품질 기준, Design Philosophy 등이 매 요청마다 전송
3. **cache_control 위치** — system prompt 전체를 하나의 cache block으로 처리 (OpenClaw는 더 세분화)

### 권장사항
1. **즉시 적용 (높은 ROI)**:
   - `prompt.py`의 `## 도구 (43개)` 텍스트 블록 제거 → JSON 스키마만으로 충분 (~500 토큰 절약)
   - `## Design Philosophy` 섹션을 SOUL.md로 이동 (system prompt에서 제거)
2. **중기**:
   - system prompt를 2개 cache block으로 분리: static(persona+rules) + dynamic(memory+time)
   - static 부분에 cache_control, dynamic은 uncached → cache hit rate 향상
3. **장기**:
   - 스킬 목록을 prompt에서 제거하고, 도구 호출로 on-demand 로딩 (OpenClaw 패턴)
   - Heartbeat에서 cache warm 유지 로직 추가

---

## 요약 매트릭스

| # | 항목 | 갭 상태 | 예상 토큰 절약 | 우선순위 |
|---|------|---------|---------------|---------|
| 1 | Tool schema 압축 | 부분구현 | ~500-1000 tok/req | 🔴 높음 |
| 2 | Image auto-resize | 미구현 | 가변 (이미지 시) | 🟡 중간 |
| 3 | Partial credit | 완전구현 | - | ✅ 완료 |
| 4 | Transcript hygiene | 부분구현 | ~200-500 tok/req | 🟡 중간 |
| 5 | Session pruning/compaction | 부분구현 | ~1000+ tok/session | 🟡 중간 |
| 6 | Streaming latency | 부분구현 | 0 (체감 속도) | 🟡 중간 |
| 7 | System prompt 최적화 | 부분구현 | ~500-800 tok/req | 🔴 높음 |

### 즉시 실행 가능한 Quick Wins
1. `prompt.py`에서 `## 도구 (43개)` 하드코딩 블록 제거 → **~500 tok/req 절약**
2. `_PRUNE_TAIL`을 500→1500으로 변경 → **pruning 품질 향상**
3. 미설정 도구(google_calendar 등) 스키마 조건부 제외 → **~200 tok/req 절약**
