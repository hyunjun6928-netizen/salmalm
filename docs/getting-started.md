# Getting Started
# 시작하기

## Installation / 설치

### From PyPI / PyPI에서 설치

```bash
pip install salmalm
```

### With encryption support / 암호화 지원 포함

```bash
pip install salmalm[crypto]
```

### From source / 소스에서 설치

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
pip install -e .
```

## Configuration / 설정

### 1. Create `.env` file / `.env` 파일 생성

Copy the example and fill in your API keys.

예제를 복사하고 API 키를 입력하세요.

```bash
cp .env.example .env
```

### 2. Required: At least one LLM API key / 필수: LLM API 키 하나 이상

```ini
# Pick at least one / 최소 하나 선택
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
XAI_API_KEY=xai-...
GOOGLE_API_KEY=AIza...
OPENROUTER_API_KEY=sk-or-...

# Or use local Ollama / 또는 로컬 Ollama 사용
OLLAMA_URL=http://localhost:11434/v1
```

### 3. Optional: Integrations / 선택: 통합 설정

```ini
# Telegram bot / 텔레그램 봇
TELEGRAM_TOKEN=123456:ABC...
TELEGRAM_OWNER_ID=your_telegram_user_id

# Discord bot / 디스코드 봇
DISCORD_TOKEN=...

# Web search / 웹 검색
BRAVE_SEARCH_API_KEY=BSA...
```

## First Run / 첫 실행

```bash
python -m salmalm start
```

Or with the CLI:

```bash
salmalm
```

This will:

1. Start the web server on **http://localhost:18800** / 웹 서버 시작
2. Show a setup wizard if no password is set / 비밀번호 미설정 시 설정 마법사 표시
3. Auto-detect available LLM providers / 사용 가능한 LLM 프로바이더 자동 감지
4. Start Telegram/Discord bots if tokens are configured / 토큰 설정 시 봇 자동 시작

## Setup Wizard / 설정 마법사

On first access, you'll see a setup page where you can:

첫 접속 시 설정 페이지가 표시됩니다:

- Set a master password / 마스터 비밀번호 설정
- Configure API keys / API 키 설정
- Enable integrations / 통합 활성화

## Verify Installation / 설치 확인

```bash
# Check server health / 서버 상태 확인
curl http://localhost:18800/api/health

# In chat, try / 채팅에서 시도
/status
/help
```

## Next Steps / 다음 단계

- Read the [Commands Reference](commands.md) / [명령어 레퍼런스](commands.md) 참조
- Explore [58+ Tools](tools.md) / [66개의 도구](tools.md) 탐색
- Set up [Telegram/Discord](features/channels.md) / [텔레그램/디스코드](features/channels.md) 설정
- Configure [deployment](deployment.md) / [배포](deployment.md) 설정
