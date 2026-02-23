<div align="center">

# 😈 삶앎 (SalmAlm)

### AI 비서를 `pip install` 하나로

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)](https://pypi.org/project/salmalm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/hyunjun6928-netizen/salmalm/actions/workflows/ci.yml/badge.svg)](https://github.com/hyunjun6928-netizen/salmalm/actions)
[![Tests](https://img.shields.io/badge/tests-1%2C877%20passed-brightgreen)]()
[![Tools](https://img.shields.io/badge/tools-62-blueviolet)]()

**[English README](README.md)**

</div>

---

## 삶앎이 뭔가요?

**개인 AI 게이트웨이**입니다. 파이썬 패키지 하나로 웹 UI, 텔레그램/디스코드 봇, 62개 도구를 갖춘 AI 비서가 설치됩니다.

Docker 없음. Node.js 없음. 설정 파일 없음.

```bash
pip install salmalm
salmalm
# → http://localhost:18800
```

첫 실행 시 **설정 마법사** — API 키 붙여넣기, 모델 선택, 끝.

> ⚠️ **클론한 레포 디렉토리 안에서 `salmalm`을 실행하지 마세요** — 설치된 패키지 대신 로컬 소스를 임포트합니다. `~`이나 다른 디렉토리에서 실행하세요.

---

## 왜 삶앎인가?

| | 기능 | 삶앎 | ChatGPT | OpenClaw | Open WebUI |
|---|---|:---:|:---:|:---:|:---:|
| 🔧 | 설치 난이도 | `pip install` | N/A | npm + 설정 | Docker |
| 🤖 | 멀티 프로바이더 라우팅 | ✅ 자동 3티어 | ❌ | ✅ | ✅ |
| 🧠 | 메모리 (2계층 + 자동회상) | ✅ | ❌ | ✅ | ❌ |
| 🤖 | 서브에이전트 (생성/조종/알림) | ✅ | ❌ | ✅ | ❌ |
| 🌐 | 브라우저 자동화 (Playwright) | ✅ | ❌ | ✅ | ❌ |
| 🧠 | 확장 사고 (4단계) | ✅ | ❌ | ✅ | ❌ |
| 🔐 | 암호화 볼트 (AES-256-GCM) | ✅ | ❌ | ❌ | ❌ |
| 📱 | 텔레그램 + 디스코드 | ✅ | ❌ | ✅ | ❌ |
| 🧩 | MCP (Model Context Protocol) | ✅ | ❌ | ❌ | ✅ |
| 🦙 | 로컬 LLM (Ollama/LM Studio/vLLM) | ✅ | ❌ | ✅ | ✅ |
| 📦 | 제로 의존성* | ✅ | N/A | ❌ | ❌ |
| 💰 | 비용 최적화 (83% 절감) | ✅ | ❌ | ❌ | ❌ |

*\*stdlib 전용 코어. AES-256-GCM 볼트용 `cryptography`는 선택 설치*

---

## ⚡ 빠른 시작 (5분이면 충분합니다)

### Step 1: 설치 (30초)
```bash
pip install salmalm
```

### Step 2: 실행 (10초)
```bash
salmalm --open
# → 브라우저가 자동으로 열립니다 (http://localhost:18800)

# 또는 (editable install에서 console_script가 안 될 때):
python3 -m salmalm --open
```

### Step 3: API 키 입력 (2분)
1. 웹 UI의 **설정 마법사**가 자동으로 뜹니다
2. AI 제공사의 API 키를 붙여넣기 하세요:
   - [Anthropic Console](https://console.anthropic.com/) → API Keys
   - [OpenAI Platform](https://platform.openai.com/api-keys) → API Keys
   - 또는 [Google AI Studio](https://aistudio.google.com/apikey) → API Keys (무료 티어 있음!)
3. "Save" 클릭 → 끝!

### Step 4: 대화 시작 (바로!)
```
"오늘 날씨 어때?"          → 웹 검색 + 답변
"이 코드 리뷰해줘"         → 파일 읽기 + 분석
"/model sonnet"            → 모델 변경
"/help"                    → 전체 명령어 보기
```

> 💡 **자연어로 말하면 됩니다.** 62개 도구를 AI가 알아서 선택합니다.
> 명령어를 외울 필요 없이, 하고 싶은 걸 그냥 말하세요.

### 고급 옵션
```bash
salmalm --shortcut          # 바탕화면 바로가기 생성
salmalm doctor              # 자가진단
salmalm --update            # 자동 업데이트
SALMALM_PORT=8080 salmalm   # 포트 변경
```

### 지원 프로바이더

| 프로바이더 | 모델 | 설정 방법 |
|---|---|---|
| Anthropic | Claude Opus 4, Sonnet 4, Haiku 4.5 | 웹 UI → 설정 → API Keys |
| OpenAI | GPT-5.2, GPT-4.1, o3, o4-mini | 웹 UI → 설정 → API Keys |
| Google | Gemini 3 Pro/Flash, 2.5 Pro/Flash | 웹 UI → 설정 → API Keys |
| xAI | Grok-4, Grok-3 | 웹 UI → 설정 → API Keys |
| **로컬 LLM** | Ollama / LM Studio / vLLM | 웹 UI → 설정 → Local LLM |

**로컬 LLM 엔드포인트**: Ollama `localhost:11434/v1` · LM Studio `localhost:1234/v1` · vLLM `localhost:8000/v1`

---

## 🎯 기능 개요

### 핵심 AI
- **스마트 모델 라우팅** — 복잡도별 자동 선택 (간단→Haiku, 보통→Sonnet, 복잡→Opus)
- **확장 사고 모드** — 예산 제어 가능한 심층 추론
- **5단계 컨텍스트 압축** — 바이너리 제거 → 도구 트림 → 오래된 메시지 삭제 → 절단 → LLM 요약
- **프롬프트 캐싱** — Anthropic cache_control로 시스템 프롬프트 비용 90% 절감
- **모델 페일오버** — 프로바이더 간 지수 백오프 + 재시도
- **서브에이전트 시스템** — 격리된 세션에서 백그라운드 AI 워커 생성/조종/수집
- **무한 루프 감지** — 최근 6회 중 동일 (도구, 인자해시) 3회 반복 시 자동 중단
- **되돌릴 수 없는 액션 게이트** — 이메일 전송, 캘린더 삭제/생성 시 명시적 확인 필요

### 62개 내장 도구
웹 검색(Brave), 이메일(Gmail), 캘린더(Google), 파일 읽기/쓰기, 셸 실행, Python eval, 이미지 생성(DALL-E/Aurora), TTS/STT, 브라우저 자동화(Playwright), RAG 검색, QR 코드, 시스템 모니터, OS 네이티브 샌드박스, 메시 네트워킹, 캔버스 미리보기 등.

### 웹 UI
- 실시간 스트리밍 (WebSocket + SSE 폴백)
- 세션 분기, 롤백, 검색 (`Ctrl+K`), 명령 팔레트 (`Ctrl+Shift+P`)
- 다크/라이트 테마, **한국어/영어 전환** (설정에서 토글)
- 이미지 붙여넣기/드래그앤드롭 + 비전, 코드 구문 강조
- PWA 설치 가능, CSP 호환 (모든 JS는 외부 `app.js`)

### 채널
- **웹** — `localhost:18800` 풀 SPA
- **텔레그램** — 폴링 + 웹훅, 인라인 버튼
- **디스코드** — 스레드 지원, 멘션 응답

### 관리 패널
📈 대시보드 · 📋 세션 관리 · ⏰ 크론 작업 · 🧠 메모리 · 🔬 디버그 · 📋 로그 · 📖 문서

---

## ✨ 10가지 고유 기능

다른 어디에도 없는 삶앎만의 기능:

| # | 기능 | 설명 |
|---|---|---|
| 1 | **자기진화 프롬프트** | 대화에서 성격 규칙을 자동 생성 (FIFO, 최대 20개) |
| 2 | **데드맨 스위치** | N일간 비활성 시 자동 긴급 조치 |
| 3 | **그림자 모드** | AI가 스타일을 학습, 부재 시 대리 응답 |
| 4 | **라이프 대시보드** | 건강, 재무, 습관, 캘린더 통합 뷰 |
| 5 | **감정 인식 응답** | 감정 상태 감지 후 톤 자동 조절 |
| 6 | **암호화 볼트** | PBKDF2-200K + AES-256-GCM / HMAC-CTR |
| 7 | **에이전트 간 프로토콜** | 인스턴스 간 HMAC-SHA256 서명 통신 |
| 8 | **A/B 스플릿 응답** | 같은 질문에 두 모델의 관점 비교 |
| 9 | **타임 캡슐** | 미래의 자신에게 메시지 예약 |
| 10 | **생각 스트림** | 해시태그 검색/감정 추적이 되는 개인 저널 |

---

## 💰 비용 최적화

API 비용을 최소화하면서 품질을 유지하는 설계:

| 기능 | 효과 |
|---|---|
| 동적 도구 로딩 | 62개 → 대화 시 0개, 작업 시 7-12개만 전송 |
| 스마트 모델 라우팅 | 간단→Haiku($1), 보통→Sonnet($3), 복잡→Opus($15) |
| 도구 스키마 압축 | 7,749 → 693 토큰 (91% 감소) |
| 시스템 프롬프트 압축 | 762 → 310 토큰 |
| 의도별 max_tokens | 대화 512, 검색 1024, 코딩 4096 |
| 의도별 히스토리 트림 | 대화 10턴, 코딩 20턴 |
| 캐시 TTL | 동일 질문 캐시 (30분~24시간, 설정 가능) |

**결과: $7.09/일 → $1.23/일 (83% 절감, 일 100회 호출 기준)**

### 엔진 최적화 설정

웹 UI → **Engine Optimization** 패널에서 토글:

| 설정 | 기본값 | 설명 |
|---|---|---|
| 📋 Planning Phase | OFF | 실행 전 계획 단계 (Haiku로 저렴하게) |
| 🔍 Reflection | OFF | 응답 후 검증 단계 (비용 2배) |
| 🗜️ Compaction Threshold | 30K | 컨텍스트 압축 기준 토큰 수 |
| 🔄 Cache TTL | OFF | 동일 질문 캐시 시간 |
| 🔧 Max Tool Iterations | 25 | 도구 반복 실행 최대 횟수 |
| 💵 Daily Cost Cap | OFF | 일일 비용 한도 |

### 자동 모델 라우팅

**Auto Routing** 선택 시 메시지 복잡도에 따라 자동 모델 선택:

| 복잡도 | 기준 | 기본 모델 |
|---|---|---|
| ⚡ Simple | 인사, 잡담, 짧은 질문 | Haiku ($1/M tok) |
| 🔶 Moderate | 요약, 번역, 일반 질문 | Sonnet ($3/M tok) |
| 💎 Complex | 코딩, 설계, 500자+, thinking | Sonnet ($15/M tok) |

Settings → Auto Routing 패널에서 각 티어별 모델 변경 가능.

---

## 🔒 보안

**위험 기능은 기본 OFF** 정책:

| 기능 | 기본값 | 활성화 |
|---|---|---|
| 네트워크 바인딩 | `127.0.0.1` (로컬만) | `SALMALM_BIND=0.0.0.0` |
| 셸 연산자 | 차단 | `SALMALM_ALLOW_SHELL=1` |
| 홈 디렉토리 읽기 | 워크스페이스만 | `SALMALM_ALLOW_HOME_READ=1` |
| 볼트 폴백 | 비활성 | `SALMALM_VAULT_FALLBACK=1` |
| 플러그인 시스템 | 비활성 | `SALMALM_PLUGINS=1` |
| CLI OAuth 재사용 | 비활성 | `SALMALM_CLI_OAUTH=1` |
| 엄격한 CSP (nonce) | 활성 | `SALMALM_CSP_COMPAT=1` (레거시용) |

### 도구 위험 등급

외부 바인딩 시 **인증 없이 Critical 도구 차단**:

| 등급 | 도구 | 외부 (0.0.0.0) |
|---|---|---|
| 🔴 Critical | `exec`, `write_file`, `edit_file`, `python_eval`, `browser`, `email_send`, `gmail`, `google_calendar`, `calendar_delete`, `calendar_add` 등 14개 | 인증 필수 |
| 🟡 High | `http_request`, `read_file`, `memory_write`, `mesh`, `sub_agent` 등 9개 | 경고 후 허용 |
| 🟢 Normal | `web_search`, `weather`, `translate` 등 | 허용 |

### 보안 강화 항목

- **SSRF 방어** — DNS 핀닝 + 사설 IP 차단 (웹 도구 및 브라우저 모두)
- **되돌릴 수 없는 액션 게이트** — `gmail send`, `calendar delete/create`는 확인 필요
- **감사 로그 비밀값 제거** — 도구 인자에서 시크릿 자동 스크럽 (9개 패턴)
- **메모리 스크러빙** — API 키/토큰 저장 전 자동 삭제
- **경로 검증** — 모든 파일 작업에 `Path.is_relative_to()` 사용
- **세션 격리** — session_store에 user_id 컬럼, 내보내기는 본인 데이터만
- **CSRF 방어** — Origin 검증 + `X-Requested-With` 커스텀 헤더
- **중앙 인증 게이트** — 모든 `/api/` 경로는 인증 필수 (공개 경로 제외)
- **노드 디스패치** — HMAC-SHA256 서명 페이로드 + 타임스탬프 + 논스
- **150+ 보안 회귀 테스트** CI에서 실행

자세한 내용은 [`SECURITY.md`](SECURITY.md) 참조.

---

## 🦙 로컬 LLM 설정

OpenAI 호환 로컬 LLM 서버와 함께 사용:

| 서버 | 기본 엔드포인트 | 시작 방법 |
|---|---|---|
| **Ollama** | `http://localhost:11434/v1` | `ollama serve` 후 UI에서 모델 선택 |
| **LM Studio** | `http://localhost:1234/v1` | LM Studio에서 서버 시작 |
| **vLLM** | `http://localhost:8000/v1` | `vllm serve <model>` |

설정 → **Local LLM** → 엔드포인트 URL 붙여넣기 → 저장. API 키는 선택 사항.

모델 자동 발견: `/models`, `/v1/models`, `/api/tags` 엔드포인트를 순차 시도.

---

## 📱 텔레그램 설정

1. [@BotFather](https://t.me/BotFather)에게 `/newbot` 전송
2. 봇 이름과 username 입력
3. 받은 토큰 복사
4. 삶앎 웹 UI → 설정 → Telegram → 토큰 + Owner ID 입력
5. 재시작

Owner ID 확인: [@userinfobot](https://t.me/userinfobot)에게 아무 메시지 전송.

---

## 💬 디스코드 설정

1. [Discord Developer Portal](https://discord.com/developers/applications) → New Application
2. Bot 탭 → Reset Token → 토큰 복사
3. **Privileged Gateway Intents** → Message Content Intent ✅
4. OAuth2 → URL Generator → bot + 권한 선택:
   - Send Messages, Read Message History, Attach Files, Add Reactions
5. 생성된 URL로 서버에 봇 초대
6. 삶앎 웹 UI → 설정 → Discord → 토큰 + Guild ID 입력
7. 재시작

**사용법:** 서버에서 `@봇이름 질문` (멘션 필수). DM은 바로 응답.

---

## 🔑 Google OAuth 설정 (Gmail & 캘린더)

1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → OAuth 클라이언트 생성
2. **Gmail API** + **Google Calendar API** 활성화
3. 리디렉트 URI: `http://localhost:18800/api/google/callback`
4. Client ID + Secret을 설정 → API Keys에 저장
5. 채팅에서 `/oauth` 실행 → Google 로그인 링크 클릭

---

## 🔧 환경 변수

```bash
# 서버
SALMALM_PORT=18800         # 웹 서버 포트
SALMALM_BIND=127.0.0.1    # 바인드 주소
SALMALM_HOME=~/SalmAlm    # 데이터 디렉토리

# AI
SALMALM_PLANNING=1         # 계획 단계 (옵트인)
SALMALM_REFLECT=1          # 반성 패스 (옵트인)
SALMALM_MAX_TOOL_ITER=25   # 최대 도구 반복 횟수 (999=무제한)
SALMALM_COST_CAP=0         # 일일 비용 한도 (0=무제한)

# 보안
SALMALM_PLUGINS=1           # 플러그인 시스템 활성화
SALMALM_CLI_OAUTH=1         # CLI 토큰 재사용 허용
SALMALM_ALLOW_SHELL=1       # 셸 연산자 허용
SALMALM_ALLOW_HOME_READ=1   # 워크스페이스 외 파일 읽기
SALMALM_VAULT_FALLBACK=1    # cryptography 없이 HMAC-CTR 볼트
```

모든 설정은 웹 UI → 설정 패널에서도 변경 가능.

---

## 🏗️ 아키텍처

```
브라우저 ──WebSocket──► 삶앎 ──► Anthropic / OpenAI / Google / xAI / 로컬 LLM
   │                     │
   └──HTTP/SSE──►       ├── SQLite (세션, 사용량, 메모리, 감사)
                         ├── 스마트 모델 라우팅 (복잡도 기반)
텔레그램 ──►             ├── 도구 레지스트리 (62개, 위험 등급별)
디스코드 ──►             ├── 보안 미들웨어 (인증/CSRF/감사/속도제한)
                         ├── 서브에이전트 매니저
메시 피어 ──►           ├── 메시지 큐 (오프라인 + 재시도)
                         ├── 공유 비밀값 스크러빙 (security/redact.py)
                         ├── OS 네이티브 샌드박스 (bwrap/rlimit)
                         ├── 노드 게이트웨이 (HMAC 서명 디스패치)
                         ├── 플러그인 시스템 (옵트인)
                         └── 볼트 (PBKDF2 + AES-256-GCM / HMAC-CTR)
```

- **190개 모듈, ~40K 줄, 1,877개 테스트**
- 순수 Python 3.10+ 표준 라이브러리 — 프레임워크 없음, 무거운 의존성 없음
- 데이터는 `~/SalmAlm`에 저장 (`SALMALM_HOME`으로 변경 가능)

---

## 트러블슈팅

### ❌ Vault locked
- `~/SalmAlm/.vault_auto` 파일 존재 확인
- 없으면 웹 UI에서 비밀번호 입력하여 unlock
- WSL 환경에서는 `.vault_auto`가 자동 생성됨

### ❌ 텔레그램/디스코드가 시작 안 됨
- vault가 잠겨있으면 채널이 시작 안 됨 → 먼저 vault unlock
- 토큰이 vault에 저장되어 있는지 설정에서 확인

### ❌ 설치 후 버전이 안 올라감
```bash
pip install --upgrade salmalm
```

---

## 🤝 기여

[`CONTRIBUTING.md`](CONTRIBUTING.md) 참조.

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
pip install -e ".[dev]"
for f in tests/test_*.py; do python -m pytest "$f" -q --timeout=30; done
```

---

## 📄 라이선스

[MIT](LICENSE)

---

<div align="center">

**삶을 앎으로 — SalmAlm** 😈

</div>
