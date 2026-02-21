<div align="center">

# 😈 삶앎 (SalmAlm)

### `pip install` 하나로 시작하는 AI 비서

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)](https://pypi.org/project/salmalm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/hyunjun6928-netizen/salmalm/actions/workflows/ci.yml/badge.svg)](https://github.com/hyunjun6928-netizen/salmalm/actions)
[![테스트](https://img.shields.io/badge/%ED%85%8C%EC%8A%A4%ED%8A%B8-1%2C710%20%ED%86%B5%EA%B3%BC-brightgreen)]()
[![도구](https://img.shields.io/badge/%EB%8F%84%EA%B5%AC-62%EA%B0%9C-blueviolet)]()
[![명령어](https://img.shields.io/badge/%EB%AA%85%EB%A0%B9%EC%96%B4-62%EA%B0%9C+-orange)]()

**[English README](README.md)**

</div>

---

## 삶앎이 뭐예요?

삶앎은 **개인용 AI 게이트웨이**입니다. Python 패키지 하나로 웹 UI, 텔레그램/디스코드 봇, 62개 도구, 다른 어디에도 없는 10가지 고유 기능을 갖춘 AI 비서를 설치할 수 있습니다.

Docker 필요 없음. Node.js 필요 없음. 설정 파일 필요 없음.

```bash
pip install salmalm
salmalm
# → http://localhost:18800
```

처음 실행하면 **설정 마법사**가 자동으로 열립니다 — API 키 입력하고, 모델 고르면 끝.

> ⚠️ **클론한 레포 디렉토리 안에서 `salmalm`을 실행하지 마세요** — Python이 설치된 패키지 대신 로컬 소스를 import합니다. `~` 등 다른 디렉토리에서 실행하세요.

---

## 왜 삶앎인가?

| | 기능 | 삶앎 | ChatGPT | OpenClaw | Open WebUI |
|---|---|:---:|:---:|:---:|:---:|
| 🔧 | 설치 난이도 | `pip install` | 해당없음 | npm + 설정 | Docker |
| 🤖 | 멀티 프로바이더 라우팅 | ✅ | ❌ | ✅ | ✅ |
| 🧠 | 자가 진화 프롬프트 | ✅ | ❌ | ❌ | ❌ |
| 👻 | 분신술 모드 | ✅ | ❌ | ❌ | ❌ |
| 💀 | 데드맨 스위치 | ✅ | ❌ | ❌ | ❌ |
| 🔐 | 암호화 금고 | ✅ | ❌ | ❌ | ❌ |
| 📱 | 텔레그램 + 디스코드 | ✅ | ❌ | ✅ | ❌ |
| 🧩 | MCP 마켓플레이스 | ✅ | ❌ | ❌ | ✅ |
| 📦 | 의존성 제로* | ✅ | 해당없음 | ❌ | ❌ |

*\*표준 라이브러리만 사용; 선택적으로 `cryptography` 패키지 사용 (없으면 순수 Python HMAC-CTR 폴백)*

---

## ⚡ 빠른 시작

```bash
# 설치
pip install salmalm

# 시작 (http://localhost:18800 에서 웹 UI 실행)
salmalm

# 브라우저 자동 열기
salmalm --open

# 바탕화면 바로가기 생성 (더블클릭으로 실행!)
salmalm --shortcut

# 최신 버전으로 업데이트
salmalm --update

# 포트 변경 / 외부 접근 허용
SALMALM_PORT=8080 salmalm
SALMALM_BIND=0.0.0.0 salmalm    # LAN 노출 (보안 섹션 참조)
```

### 바탕화면 바로가기

`salmalm --shortcut`을 한 번 실행하면 바탕화면에 아이콘이 생깁니다:

| 플랫폼 | 생성 파일 | 사용법 |
|---|---|---|
| **Windows** | 바탕화면에 `SalmAlm.bat` | 더블클릭 → 서버 시작 + 브라우저 열림 |
| **Linux** | 바탕화면에 `salmalm.desktop` | 더블클릭 → 서버 시작 + 브라우저 열림 |
| **macOS** | 바탕화면에 `SalmAlm.command` | 더블클릭 → 서버 시작 + 브라우저 열림 |

바로가기는 **버전과 무관**합니다 — 삶앎을 업데이트해도 아이콘은 그대로 동작합니다.

### 지원 프로바이더

| 프로바이더 | 모델 | 환경변수 |
|---|---|---|
| Anthropic | Claude Opus 4, Sonnet 4, Haiku 4.5 | `ANTHROPIC_API_KEY` |
| OpenAI | GPT-5.2, GPT-4.1, o3, o4-mini | `OPENAI_API_KEY` |
| Google | Gemini 3 Pro/Flash, 2.5 Pro/Flash | `GOOGLE_API_KEY` |
| xAI | Grok-4, Grok-3 | `XAI_API_KEY` |
| Ollama | 로컬 모델 전부 | `OLLAMA_URL` |

API 키는 환경변수 또는 웹 UI **설정 → API Keys**에서 입력 가능합니다.

---

## 🎯 기능 소개

### 핵심 AI
- **지능형 모델 라우팅** — 복잡도에 따라 모델 자동 선택 (간단→Haiku, 보통→Sonnet, 복잡→Opus), 전용 `model_selection` 모듈로 분리, 사용자 커스텀 라우팅 지원
- **확장 사고 모드** — 예산 제어가 가능한 심층 추론
- **5단계 컨텍스트 압축** — 바이너리 제거 → 도구 축소 → 이전 도구 삭제 → 장문 축약 → LLM 요약, `compaction_summaries` DB 테이블을 통한 세션 간 연속성 지원
- **프롬프트 캐싱** — Anthropic cache_control로 시스템 프롬프트 비용 90% 절감
- **모델 장애 전환** — 지수 백오프 + 일시적 오류(timeout/5xx/429) 1.5초 딜레이 자동 재시도
- **메시지 큐** — FIFO 오프라인 메시지 큐잉, 3단계 재시도 백오프, 데드 레터 처리; 모델 복구 시 자동 처리
- **서브에이전트 시스템** — 백그라운드 AI 워커 생성/조종/수집 (격리 세션); 8개 액션 (spawn, stop, list, log, info, steer, collect, status)
- **스트리밍 안정성** — 중단 시 부분 콘텐츠 보존; `AbortController`가 토큰 축적 후 취소 시 동결
- **캐시 인식 세션 정리** — Anthropic 프롬프트 캐시 TTL(5분) 인지, 60초 쿨다운

### 62개 내장 도구
웹 검색(Brave), 이메일(Gmail), 캘린더(Google), 파일 I/O, 셸 실행, Python 실행, 이미지 생성(DALL-E), TTS/STT, 브라우저 자동화(Playwright), RAG 검색, QR 코드, 시스템 모니터, OS 기본 샌드박스, 메시 네트워킹, 캔버스 프리뷰 등.

### 웹 UI
- 실시간 스트리밍 (WebSocket + SSE 폴백)
- WebSocket 재연결 + 세션 이어받기 (버퍼링된 메시지 자동 전송)
- 세션 분기, 롤백, 검색 (`Ctrl+K`)
- 커맨드 팔레트 (`Ctrl+Shift+P`)
- 메시지 편집/삭제/재생성
- 이미지 붙여넣기/드래그앤드롭 + 비전
- 코드 구문 강조
- 다크/라이트 테마 (라이트 기본), 한국어/영어 자동 감지
- PWA 설치 가능
- CSP 호환 — 모든 JS가 외부 `app.js`에, 인라인 이벤트 핸들러 없음
- 컨텍스트 압축 진행 표시 (✨ Compacting context...)

### 인프라
- **OS 기본 샌드박스** — bubblewrap (Linux) / sandbox-exec (macOS) / rlimit 폴백; 최강 티어 자동 감지
- **메시 네트워킹** — SalmAlm 인스턴스 간 P2P (작업 위임, 클립보드 공유, LAN UDP 자동 탐색, HMAC 인증)
- **캔버스** — 로컬 HTML/코드/차트 프리뷰 서버 (`:18803`)
- **브라우저 자동화** — Playwright 스냅샷/액트 패턴 (`pip install salmalm[browser]`)

### 채널
- **웹** — `localhost:18800`에서 풀기능 SPA
- **텔레그램** — 폴링 + 웹훅, 인라인 버튼 지원
- **디스코드** — 스레드 지원 봇

### 관리 패널
- **📈 대시보드** — 토큰 사용량, 비용 추적, 일별 추이 + 날짜 필터
- **📋 세션** — 검색, 삭제, 분기 표시 포함 세션 관리
- **⏰ 크론 작업** — AI 예약 작업 CRUD
- **🧠 메모리** — 에이전트 기억/성격 파일 브라우저
- **🔬 디버그** — 실시간 시스템 진단 (5개 카드, 자동 새로고침)
- **📋 로그** — 레벨 필터 서버 로그 뷰어
- **📖 문서** — 32개 명령어, 10개 고유 기능 내장 레퍼런스

---

## ✨ 다른 곳에 없는 10가지 고유 기능

ChatGPT, OpenClaw, Open WebUI 어디에도 없는 삶앎만의 기능:

| # | 기능 | 설명 |
|---|---|---|
| 1 | **자가 진화 프롬프트** | 대화에서 성격 규칙을 자동 생성 (FIFO, 최대 20개) |
| 2 | **데드맨 스위치** | N일간 비활성 시 자동 긴급 조치 |
| 3 | **분신술 모드** | AI가 당신의 말투를 학습, 부재 시 대리 응답 |
| 4 | **인생 대시보드** | 건강, 재정, 습관, 일정을 한 화면에 |
| 5 | **감정 인식 응답** | 감정 상태를 감지하여 톤 자동 조절 |
| 6 | **암호화 금고** | PBKDF2-200K + HMAC 인증 스트림 암호화 비밀 대화 |
| 7 | **AI간 프로토콜** | HMAC-SHA256 서명된 삶앎 인스턴스 간 통신 |
| 8 | **A/B 분할 응답** | 같은 질문에 두 모델의 관점을 동시에 |
| 9 | **타임캡슐** | 미래의 나에게 보내는 예약 메시지 |
| 10 | **생각 스트림** | 해시태그 검색 + 감정 추적 개인 일기 |

---

## 📋 명령어 (62개+)

<details>
<summary>전체 명령어 목록 보기</summary>

| 명령어 | 설명 |
|---|---|
| `/help` | 도움말 |
| `/status` | 세션 상태 |
| `/model <이름>` | 모델 전환 (opus/sonnet/haiku/gpt/auto) |
| `/think [레벨]` | 확장 사고 (low/medium/high) |
| `/compact` | 컨텍스트 압축 |
| `/context` | 토큰 수 분석 |
| `/usage` | 토큰 & 비용 추적 |
| `/persona <이름>` | 페르소나 전환 |
| `/branch` | 대화 분기 |
| `/rollback [n]` | 마지막 n개 메시지 되돌리기 |
| `/remind <시간> <메시지>` | 리마인더 설정 |
| `/expense <금액> <설명>` | 지출 기록 |
| `/pomodoro` | 집중 타이머 |
| `/note <텍스트>` | 빠른 메모 |
| `/link <url>` | 링크 저장 |
| `/routine` | 일일 루틴 |
| `/shadow` | 분신술 모드 |
| `/vault` | 암호화 금고 |
| `/capsule` | 타임캡슐 |
| `/deadman` | 데드맨 스위치 |
| `/a2a` | AI간 통신 |
| `/workflow` | 워크플로우 엔진 |
| `/mcp` | MCP 관리 |
| `/subagents` | 서브에이전트 (spawn, steer, collect, list, stop, log, info, status) |
| `/evolve` | 자가 진화 프롬프트 |
| `/mood` | 감정 감지 |
| `/split` | A/B 분할 응답 |
| `/cron` | 크론 작업 |
| `/bash <명령>` | 셸 실행 |
| `/screen` | 브라우저 제어 |
| `/life` | 인생 대시보드 |
| `/briefing` | 데일리 브리핑 |
| `/debug` | 실시간 시스템 진단 |
| `/security` | 보안 상태 요약 |
| `/plugins` | 플러그인 관리 |
| `/export` | 세션 데이터 내보내기 |
| `/soul` | AI 성격 파일 보기/편집 |
| `/config` | 설정 관리 |
| `/brave` | Brave 검색 설정 |
| `/approve` | 대기 중인 exec 명령 승인 |
| `/agent` | 에이전트 관리 |
| `/plan` | 다단계 계획 생성 |
| `/compare` | 모델 응답 비교 |
| `/hooks` | 웹훅 관리 |
| `/health` | 시스템 건강 점검 |
| `/bookmarks` | 저장된 링크 보기 |
| `/new` | 새 세션 |
| `/clear` | 현재 세션 초기화 |
| `/whoami` | 현재 사용자 정보 |
| `/tools` | 사용 가능한 도구 목록 |
| `/prune` | 컨텍스트 수동 정리 |
| `/skill` | 스킬 관리 |
| `/oauth` | OAuth 설정 (Gmail, 캘린더) |
| `/queue` | 메시지 큐 관리 |

</details>

---

## 🔒 보안

삶앎은 **위험 기능 기본 OFF** 정책을 따릅니다:

| 기능 | 기본값 | 활성화 방법 |
|---|---|---|
| 네트워크 바인딩 | `127.0.0.1` (루프백만) | `SALMALM_BIND=0.0.0.0` |
| 셸 연산자 (파이프, 리다이렉트, 체인) | 차단 | `SALMALM_ALLOW_SHELL=1` |
| 홈 디렉토리 파일 읽기 | 워크스페이스만 | `SALMALM_ALLOW_HOME_READ=1` |
| 금고 (`cryptography` 없을 때) | 비활성 | `SALMALM_VAULT_FALLBACK=1` (HMAC-CTR) |
| exec에서 인터프리터 실행 | 차단 | `/bash` 또는 `python_eval` 도구 사용 |
| 위험 exec 플래그 (find -exec, awk -f 등) | 차단 | 해당없음 (보안 강화, 우회 불가) |
| HTTP 요청 헤더 | 허용 목록만 | `SALMALM_HEADER_PERMISSIVE=1`로 차단 목록 모드 전환 |

### 헤더 보안

HTTP 요청 도구는 기본적으로 **허용 목록 모드**를 사용합니다 — 안전한 헤더(Accept, Content-Type, Authorization, User-Agent 등)만 허용됩니다. 알 수 없는 헤더는 거부됩니다.

`SALMALM_HEADER_PERMISSIVE=1`을 설정하면 차단 목록 모드로 전환됩니다 (위험한 헤더 Proxy-Authorization, X-Forwarded-For 등만 차단).

### 라우트 보안 미들웨어

모든 HTTP 라우트에 **보안 정책** (인증, 감사, CSRF, 요청 제한)이 `web/middleware.py`를 통해 자동 적용됩니다:

- **공개 라우트** (`/`, `/setup`, `/static/*`) — 인증 불필요
- **API 라우트** (`/api/*`) — 인증 필수, 쓰기 작업 감사, POST에 CSRF 적용
- **민감한 라우트** (`/api/vault/*`, `/api/admin/*`) — 항상 인증 + CSRF 필수

개발자가 실수로 인증을 빠뜨릴 수 없습니다 — 미들웨어 체인이 구조적으로 강제합니다.

### 도구 위험 등급

도구는 위험 수준별로 분류되며, **외부 네트워크 노출 시 인증 없는 위험 도구 실행이 차단**됩니다:

| 등급 | 도구 | 외부 노출 (0.0.0.0) |
|---|---|---|
| 🔴 위험 | exec, bash, file_write, file_delete, python_eval, browser_action, sandbox_exec | 인증 필수 |
| 🟡 주의 | http_request, send_email, file_read, mesh_task | 경고와 함께 허용 |
| 🟢 일반 | web_search, calendar, QR 등 | 허용 |

### 외부 노출 안전장치

`0.0.0.0`에 바인딩하면 삶앎이 자동으로:
- ⚠️ 관리자 비밀번호 미설정 시 경고
- ⚠️ 위험 도구 접근 가능 경고
- 미인증 세션에서 위험 도구 차단

### 추가 보안

- **SSRF 방어** — 모든 리다이렉트 홉에서 사설 IP 차단, 스킴 허용 목록, userinfo 차단, 10진 IP 정규화
- **셸 연산자 차단** — 파이프(`|`), 리다이렉트(`>`), 체인(`&&`, `||`, `;`)이 exec에서 기본 차단
- **Exec 인수 차단 목록** — 명령별 위험 플래그 차단: `find -exec`, `awk system()`, `tar --to-command`, `git clone/push`, `sed -i`, `xargs -I`
- **토큰 보안** — JWT `kid` 키 순환, `jti` 폐기, PBKDF2-200K 비밀번호 해싱
- **로그인 잠금** — DB 기반 영구 브루트포스 방어 + 자동 정리
- **감사 추적** — 변조 방지용 추가 전용 체크포인트 로그, 자동 크론 (6시간마다) + 정리 (30일)
- **요청 제한** — 인메모리 IP별 레이트 리미터 (60요청/분) API 라우트 적용
- **WebSocket Origin 검증** — 크로스 사이트 WebSocket 하이재킹 방지
- **CSP 호환 UI** — 인라인 스크립트/이벤트 핸들러 없음; 외부 `app.js` + ETag 캐싱; `SALMALM_CSP_NONCE=1`로 엄격 CSP 옵트인
- **Exec 리소스 제한** — 포그라운드 실행: CPU 타임아웃+5s, 1GB RAM, 100 fd, 50MB fsize (Linux/macOS)
- **도구별 타임아웃** — exec 120초, browser 90초, 기본 60초 wall-clock 제한
- **도구별 출력 제한** — exec 20K, browser 10K, HTTP 15K 글자 차등 제한
- **SQLite 강화** — WAL 저널 모드 + 5초 busy_timeout ("database is locked" 방지)
- **46개 보안 회귀 테스트** — SSRF 우회, 헤더 인젝션, exec 우회, 도구 등급, 라우트 정책

자세한 내용은 [`SECURITY.md`](SECURITY.md)를 참조하세요.

---

## 🔧 설정

```bash
# 서버
SALMALM_PORT=18800         # 웹 서버 포트
SALMALM_BIND=127.0.0.1    # 바인드 주소 (기본: 루프백만)
SALMALM_WS_PORT=18801     # 웹소켓 포트
SALMALM_HOME=~/SalmAlm    # 데이터 디렉토리 (DB, 금고, 로그, 메모리)

# AI
SALMALM_LLM_TIMEOUT=30    # LLM 요청 타임아웃 (초)
SALMALM_COST_CAP=0        # 월간 비용 상한 (0=무제한)
SALMALM_REFLECT=0          # 자기 성찰 패스 비활성화 (비용/지연 절감)

# 보안
SALMALM_VAULT_PW=...         # 시작 시 금고 자동 잠금해제
SALMALM_ALLOW_SHELL=1        # exec에서 셸 연산자 허용
SALMALM_ALLOW_HOME_READ=1    # 워크스페이스 외부 파일 읽기 허용
SALMALM_VAULT_FALLBACK=1     # cryptography 없이 HMAC-CTR 금고 허용
SALMALM_HEADER_PERMISSIVE=1  # HTTP 헤더: 허용 목록 대신 차단 목록 모드
SALMALM_CSP_NONCE=1          # nonce 기반 엄격 CSP
SALMALM_OPEN_BROWSER=1       # 서버 시작 시 브라우저 자동 열기

# 메시
SALMALM_MESH_SECRET=...   # 메시 피어 인증용 HMAC 시크릿
```

모든 설정은 웹 UI에서도 가능합니다.

---

## 🏗️ 아키텍처

```
브라우저 ──WebSocket──► 삶앎 서버 ──► Anthropic / OpenAI / Google / xAI / Ollama
   │                      │
   └──HTTP/SSE──►        ├── SQLite (세션, 사용량, 메모리, 감사)
                          ├── 모델 선택 (복잡도 기반 라우팅)
텔레그램 ──►              ├── 도구 레지스트리 (62개)
디스코드 ──►              ├── 크론 스케줄러 + 감사 크론
                          ├── 서브에이전트 매니저 (spawn/steer/collect)
메시 피어 ──►             ├── 메시지 큐 (오프라인 + 재시도 + 데드 레터)
                          ├── RAG 엔진 (TF-IDF + 코사인 유사도)
                          ├── OS 기본 샌드박스 (bwrap/unshare/rlimit)
                          ├── 캔버스 서버 (:18803)
                          ├── 보안 미들웨어 (라우트별 인증/감사/제한/CSRF)
                          ├── 플러그인 시스템
                          └── 금고 (PBKDF2 암호화)
```

- **231개 모듈**, **4만5천+ 줄**, **82개 테스트 파일**, **1,710개 테스트**
- 순수 Python 3.10+ 표준 라이브러리 — 프레임워크 없음, 무거운 의존성 없음
- 라우트 테이블 아키텍처 (GET 59개 + POST 63개 등록 핸들러)
- 기본 바인딩 `127.0.0.1` — 네트워크 노출은 명시적 opt-in
- 런타임 데이터는 `~/SalmAlm`에 저장 (`SALMALM_HOME`으로 변경 가능)
- 비용 추정 `core/cost.py`에 통합, 모델별 가격 정보
- 슬래시 명령어 `core/slash_commands.py`로 분리 (engine.py: 2007→1221줄)
- 모델 선택 `core/model_selection.py`로 분리
- 웹 UI JS `static/app.js`로 외부화 (index.html: 3016→661줄)

### 버전 관리

```bash
# 모든 소스 파일의 버전을 한 번에 변경 (pyproject.toml + __init__.py)
python scripts/bump_version.py 0.17.0

# CI가 자동으로 버전 일관성 검사
```

---

## 🐳 Docker (선택)

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
docker compose up -d
```

---

## 🔌 플러그인

`plugins/` 디렉토리에 `.py` 파일을 넣으면 시작 시 자동 인식됩니다:

```python
# plugins/my_plugin.py
TOOLS = [{
    'name': 'my_tool',
    'description': '인사하기',
    'input_schema': {'type': 'object', 'properties': {'name': {'type': 'string'}}}
}]

def handle_my_tool(args):
    return f"안녕하세요, {args.get('name', '세계')}!"
```

---

## 🤝 기여하기

자세한 가이드는 [`CONTRIBUTING.md`](CONTRIBUTING.md)를 참조하세요 (테스트 실행법, 코드 스타일, 아키텍처 개요 포함).

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
pip install -e ".[dev]"

# 테스트 실행 (파일별, CI 스타일)
for f in tests/test_*.py; do python -m pytest "$f" -q --timeout=30; done
```

---

## 📄 라이선스

[MIT](LICENSE)

---

<div align="center">

**삶앎** = 삶(Life) + 앎(Knowledge)

*당신의 삶을 이해하는 AI.*

</div>
