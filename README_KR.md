<div align="center">

# 😈 삶앎 (SalmAlm)

### AI 비서를 `pip install` 하나로

[![PyPI](https://img.shields.io/pypi/v/salmalm)](https://pypi.org/project/salmalm/)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue)](https://pypi.org/project/salmalm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**[English README](README.md)**

</div>

---

## 삶앎이 뭔가요?

**개인 AI 게이트웨이**입니다. 파이썬 패키지 하나로 웹 UI, 텔레그램 봇, 디스코드 봇, 62개 도구를 갖춘 AI 비서가 설치됩니다.

Docker 없음. Node.js 없음. 설정 파일 없음.

```bash
pip install salmalm
salmalm
# → http://localhost:18800
```

---

## 빠른 시작

```bash
# 설치
pipx install salmalm

# 실행
salmalm

# 브라우저에서 열기
# http://127.0.0.1:18800
```

첫 실행 시 마스터 비밀번호 설정 → API 키 입력 → 모델 선택 → 바로 사용 가능.

---

## 주요 기능

### 🤖 멀티 프로바이더
- **Anthropic** (Claude Opus, Sonnet, Haiku)
- **OpenAI** (GPT-5, GPT-4.1, o3, o4-mini)
- **Google** (Gemini 2.5 Pro/Flash, 3 Pro)
- **Groq** (Llama, Mixtral — 무료)
- **Ollama** (로컬 모델 — 무료)

### 📱 멀티 채널
웹 + 텔레그램 + 디스코드를 **동시에** 사용. 하나의 대화 기록 공유.

### 💰 비용 최적화 (핵심 차별점)

| 기능 | 효과 |
|------|------|
| 동적 도구 로딩 | 62개 도구 → 의도에 맞는 0~12개만 전송 |
| 스마트 모델 라우팅 | 잡담→Haiku($1), 코딩→Sonnet($3), 복잡→Opus($15) |
| 도구 스키마 압축 | 7,749 → 693 토큰 (91% 감소) |
| 시스템 프롬프트 압축 | 762 → 310 토큰 |
| 의도별 max_tokens | 잡담 512, 검색 1024, 코딩 4096 |
| 히스토리 트림 | 잡담 10턴, 코딩 20턴 |
| 캐시 TTL | 동일 질문 캐시 (30분~24시간) |

**결과: $7.09/day → $1.23/day (83% 절감, 하루 100회 호출 기준)**

### 🔧 62개 내장 도구
웹 검색, 파일 읽기/쓰기, 코드 실행, 스크린샷, 이미지 생성, TTS, 캘린더, 이메일 등.

### 🔐 보안
- API 키는 AES-256-GCM 암호화 vault에 저장
- 마스터 비밀번호 (선택)
- 로컬호스트 전용 기본 바인딩

---

## 엔진 최적화 설정

웹 UI의 **Engine Optimization** 패널에서 토글 가능:

| 설정 | 기본값 | 설명 |
|------|--------|------|
| 📋 Planning Phase | OFF | 실행 전 계획 단계 추가 (Haiku로 저렴하게) |
| 🔍 Reflection | OFF | 응답 후 검증 단계 (비용 2배) |
| 🗜️ Compaction Threshold | 30K | 컨텍스트 압축 기준 토큰 수 |
| 🔄 Cache TTL | OFF | 동일 질문 캐시 시간 |
| 📦 Batch API | OFF | 비대화형 작업 50% 할인 |
| 📄 File Pre-summarization | OFF | 5KB 이상 파일 요약 후 전달 |
| ⏹️ Streaming Early Stop | OFF | 완료 감지 시 스트리밍 조기 중단 |
| 🔧 Max Tool Iterations | 25 | 도구 반복 실행 최대 횟수 |
| 💵 Daily Cost Cap | OFF | 일일 비용 한도 |

---

## 자동 모델 라우팅

**Auto Routing** 선택 시 메시지 복잡도에 따라 자동 모델 선택:

| 복잡도 | 기준 | 기본 모델 |
|--------|------|-----------|
| ⚡ Simple | 인사, 잡담, 짧은 질문 | Haiku ($1/M tok) |
| 🔶 Moderate | 요약, 번역, 일반 질문 | Sonnet ($3/M tok) |
| 💎 Complex | 코딩, 설계, 500자+, thinking | Sonnet ($15/M tok) |

Settings → Auto Routing 패널에서 각 티어별 모델 변경 가능.

---

## 텔레그램 설정

1. [@BotFather](https://t.me/BotFather)에게 `/newbot` 전송
2. 봇 이름과 username 입력
3. 받은 토큰 복사
4. 삶앎 웹 UI → Settings → Telegram → 토큰 + Owner ID 입력
5. 재시작

Owner ID 확인: [@userinfobot](https://t.me/userinfobot)에게 아무 메시지 전송.

---

## 디스코드 설정

1. [Discord Developer Portal](https://discord.com/developers/applications) → New Application
2. Bot 탭 → Reset Token → 토큰 복사
3. **Privileged Gateway Intents** → Message Content Intent ✅
4. OAuth2 → URL Generator → bot 체크 → 권한 선택:
   - Send Messages, Read Message History, Attach Files, Add Reactions
5. 생성된 URL로 서버에 봇 초대 → 승인(Authorize) 클릭
6. 삶앎 웹 UI → Settings → Discord → 토큰 + Guild ID 입력
7. 재시작

**사용법:** 서버에서 `@봇이름 질문` (멘션 필수). DM은 바로 응답.

---

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `SALMALM_PORT` | 18800 | 웹 서버 포트 |
| `SALMALM_PLANNING` | 0 | Planning Phase 활성화 |
| `SALMALM_REFLECT` | 0 | Reflection 활성화 |
| `SALMALM_CACHE_TTL` | 0 | 캐시 TTL (초) |
| `SALMALM_BATCH_API` | 0 | Batch API 활성화 |
| `SALMALM_FILE_PRESUMMARY` | 0 | 파일 사전 요약 |
| `SALMALM_EARLY_STOP` | 0 | 스트리밍 조기 중단 |
| `SALMALM_MAX_TOOL_ITER` | 25 | 최대 도구 반복 횟수 (999=무제한) |
| `SALMALM_ALL_TOOLS` | 0 | 1이면 모든 도구 항상 전송 (비상용) |
| `SALMALM_LOG_LEVEL` | INFO | 로그 레벨 |

---

## 트러블슈팅

### ❌ Vault locked
서버 시작 시 vault가 자동 unlock 안 되는 경우:
- `~/SalmAlm/.vault_auto` 파일이 있는지 확인
- 없으면 웹 UI에서 비밀번호 입력하여 unlock
- WSL 환경에서는 `.vault_auto` 파일이 자동 생성됨

### ❌ Tool errors detected, stopping
- v0.18.18 이전 버전 버그. 업데이트: `pipx install salmalm --force`
- 정상 응답에 "error" 단어가 포함되면 오탐 발생했던 문제 (수정됨)

### ❌ 텔레그램/디스코드가 시작 안 됨
- vault가 잠겨있으면 채널이 시작 안 됨 → v0.18.15+ 에서 자동 unlock 추가
- 토큰이 vault에 저장되어 있는지 Settings에서 확인

### ❌ Auto Routing 선택해도 모델이 안 바뀜
- v0.18.17+ 에서 수정. `switch_model('auto')`가 provider 체크에 빠지던 버그

### ❌ 설치 후 버전이 안 올라감
```bash
pipx uninstall salmalm && pipx install salmalm
```

---

## 테스트

```bash
cd /tmp/salmalm
python3 -m pytest tests/ -v
```

---

## 라이선스

MIT License — 자유롭게 사용하세요.

---

<div align="center">

**삶을 앎으로 — SalmAlm** 😈

</div>
