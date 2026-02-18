# 삶앎 (SalmAlm) 🧠

**개인용 AI 게이트웨이** — 2,400줄 Python 단일 파일로 ChatGPT급 AI 에이전트를 자기 컴퓨터에서 돌리세요.

## 왜 삶앎?

- 🔒 **내 데이터는 내 컴퓨터에** — 클라우드에 대화 저장 안 함
- 🧠 **멀티 LLM** — Anthropic, OpenAI, xAI, Google 모델 자유 전환
- 🔧 **도구 12개** — 파일 조작, 웹 검색, 이미지 생성, 음성 변환 등
- 💰 **토큰 최적화** — 3-tier 모델 라우팅으로 비용 절감
- 🔐 **AES-256-GCM 암호화** — API 키를 안전하게 보관

## 기능

| 기능 | 설명 |
|------|------|
| 💬 웹 채팅 | 브라우저에서 바로 사용 |
| 📱 텔레그램 봇 | 모바일에서 대화 |
| 🔧 도구 실행 | 셸 명령, 파일 편집, 코드 실행 |
| 🔍 웹 검색 | Brave Search API 연동 |
| 🖼️ 이미지 비전 | 사진 분석 (웹 + 텔레그램) |
| 🎨 이미지 생성 | xAI Aurora / OpenAI DALL-E |
| 🔊 TTS | 텍스트를 음성으로 변환 |
| 🎤 음성 인식 | 텔레그램 음성 → 텍스트 (Whisper) |
| 🧠 메모리 | 장기/단기 기억 시스템 |
| 📡 SSE 스트리밍 | 실시간 도구 상태 표시 |
| ⏰ 크론 스케줄러 | 주기적 작업 자동 실행 |
| 💾 세션 영속화 | 재시작해도 대화 유지 |
| 📊 비용 추적 | 모델별 토큰 사용량 + 비용 영구 기록 |

## 설치

```bash
# 1. 클론
git clone https://github.com/YOUR_USERNAME/salmalm.git
cd salmalm

# 2. (선택) cryptography 설치 (AES-256-GCM, 없으면 HMAC-CTR 폴백)
pip install cryptography

# 3. 실행
python3 server.py
```

브라우저에서 `http://127.0.0.1:18800` 접속 → 비밀번호 설정 → API 키 등록 → 사용 시작!

## API 키 설정

첫 실행 시 웹 UI에서 Vault를 생성하고, 설정 패널에서 API 키를 등록하세요:

| 키 | 설명 | 필수 |
|----|------|------|
| `anthropic_api_key` | Anthropic (Claude) | 권장 |
| `openai_api_key` | OpenAI (GPT, TTS, Whisper, DALL-E) | 권장 |
| `xai_api_key` | xAI (Grok, Aurora 이미지) | 선택 |
| `google_api_key` | Google (Gemini) | 선택 |
| `brave_api_key` | Brave Search | 선택 |

최소 1개 LLM 키만 있으면 동작합니다.

## 텔레그램 봇 연동

1. @BotFather에서 봇 생성 → 토큰 복사
2. 웹 UI 설정에서 텔레그램 토큰 + 본인 ID 입력
3. 서버 재시작 → 봇에 메시지 전송

## 자동 시작 (Linux)

```bash
# start.sh 예시
export SALMALM_VAULT_PW="your_password"
python3 server.py
```

## 커스터마이징

작업 디렉토리에 파일을 만들어서 AI 성격을 설정할 수 있습니다:

- `SOUL.md` — AI 페르소나 (성격, 말투, 규칙)
- `USER.md` — 사용자 정보
- `MEMORY.md` — 장기 기억
- `TOOLS.md` — 도구 사용 노트
- `AGENTS.md` — 행동 규칙

## 아키텍처

```
server.py (단일 파일, ~2,400줄)
├── Vault (AES-256-GCM 암호화 키 저장)
├── ModelRouter (3-tier 자동 라우팅)
├── LLM Providers (Anthropic/OpenAI/xAI/Google)
├── Tool Engine (12개 도구)
├── Session Manager (SQLite 영속화)
├── TelegramBot (long-polling)
├── WebHandler (HTTP + SSE)
├── CronScheduler (주기 작업)
└── Audit Log (SHA256 해시 체인)
```

## 라이선스

MIT

## 크레딧

삶앎(삶을 앎) — "삶을 아는 AI"
