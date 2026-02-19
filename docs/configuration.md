# Configuration
# 설정

SalmAlm is configured via environment variables (`.env` file) and vault storage.

SalmAlm은 환경변수(`.env` 파일)와 볼트 저장소를 통해 설정됩니다.

## Environment Variables / 환경변수

### LLM API Keys / LLM API 키

At least one is required. / 최소 하나 필수.

| Variable / 변수 | Description / 설명 | Example / 예시 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | `sk-ant-...` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `XAI_API_KEY` | xAI (Grok) API key | `xai-...` |
| `GOOGLE_API_KEY` | Google Gemini API key | `AIza...` |
| `OPENROUTER_API_KEY` | OpenRouter API key | `sk-or-...` |
| `OLLAMA_URL` | Local Ollama endpoint | `http://localhost:11434/v1` |

### Server / 서버

| Variable / 변수 | Description / 설명 | Default / 기본값 |
|---|---|---|
| `SALMALM_PORT` | HTTP server port / HTTP 서버 포트 | `18800` |
| `SALMALM_BIND` | Bind address / 바인드 주소 | `127.0.0.1` |
| `SALMALM_VAULT_PW` | Vault encryption password / 볼트 암호화 비밀번호 | — |
| `PYTHONUNBUFFERED` | Unbuffered output / 버퍼 없는 출력 | `1` |

### Telegram / 텔레그램

| Variable / 변수 | Description / 설명 |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from @BotFather / @BotFather에서 받은 봇 토큰 |
| `TELEGRAM_OWNER_ID` | Owner's Telegram user ID / 소유자의 텔레그램 사용자 ID |

### Discord / 디스코드

| Variable / 변수 | Description / 설명 |
|---|---|
| `DISCORD_TOKEN` | Discord bot token / 디스코드 봇 토큰 |

### Web Search / 웹 검색

| Variable / 변수 | Description / 설명 |
|---|---|
| `BRAVE_SEARCH_API_KEY` | Brave Search API key / Brave 검색 API 키 |

### Google OAuth / 구글 OAuth

| Variable / 변수 | Description / 설명 |
|---|---|
| `GOOGLE_CLIENT_ID` | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret |
| `GOOGLE_REDIRECT_URI` | OAuth redirect URI |

## Vault Storage / 볼트 저장소

Sensitive data is stored in an AES-256-GCM encrypted vault (`.vault.enc`).

민감한 데이터는 AES-256-GCM 암호화 볼트(`.vault.enc`)에 저장됩니다.

Vault can store: / 볼트에 저장 가능:

- API keys / API 키
- OAuth tokens / OAuth 토큰
- Google refresh tokens / 구글 리프레시 토큰
- Any secrets / 기타 비밀 정보

Access vault via: / 볼트 접근 방법:

```
/vault list
/vault get <key>
/vault set <key> <value>
/vault delete <key>
```

## Configuration Files / 설정 파일

| File / 파일 | Purpose / 용도 |
|---|---|
| `.env` | Environment variables / 환경변수 |
| `.vault.enc` | Encrypted secrets vault / 암호화된 비밀 볼트 |
| `.token_secret` | Session token secret / 세션 토큰 시크릿 |
| `reminders.json` | Saved reminders / 저장된 리마인더 |
| `workflows.json` | Workflow definitions / 워크플로우 정의 |
| `rss_feeds.json` | RSS feed subscriptions / RSS 피드 구독 |
| `nodes.json` | Node registry / 노드 레지스트리 |
| `plugins/` | Plugin directory / 플러그인 디렉토리 |
| `skills/` | Skill definitions / 스킬 정의 |
| `memory/` | Memory storage / 메모리 저장소 |

## Database Files / 데이터베이스 파일

| File / 파일 | Purpose / 용도 |
|---|---|
| `audit.db` | Audit log (SQLite) / 감사 로그 |
| `auth.db` | Authentication data / 인증 데이터 |
| `personal.db` | Personal assistant data / 개인 비서 데이터 |
| `rag.db` | RAG vector store / RAG 벡터 저장소 |
