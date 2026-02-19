# Web Module API
# 웹 모듈 API

The `salmalm.web` package implements the HTTP server and WebSocket handler.

`salmalm.web` 패키지는 HTTP 서버와 WebSocket 핸들러를 구현합니다.

## `salmalm.web.web`

HTTP request handler — serves the web UI, API endpoints, static files, and dashboard.

HTTP 요청 핸들러 — 웹 UI, API 엔드포인트, 정적 파일, 대시보드 제공.

**Key endpoints / 주요 엔드포인트:**

| Endpoint | Method | Description / 설명 |
|---|---|---|
| `/` | GET | Web UI / 웹 UI |
| `/api/health` | GET | Health check / 상태 점검 |
| `/api/chat` | POST | Send message / 메시지 전송 |
| `/api/sessions` | GET | List sessions / 세션 목록 |
| `/api/dashboard` | GET | Dashboard data / 대시보드 데이터 |
| `/api/google/auth` | GET | Google OAuth start / 구글 OAuth 시작 |
| `/api/google/callback` | GET | Google OAuth callback / 구글 OAuth 콜백 |

## `salmalm.web.ws`

WebSocket handler for real-time streaming responses.

실시간 스트리밍 응답을 위한 WebSocket 핸들러.

## `salmalm.web.auth`

Web authentication — session tokens, password verification, rate limiting.

웹 인증 — 세션 토큰, 비밀번호 검증, 요청 빈도 제한.

## `salmalm.web.oauth`

Google OAuth2 flow — authorization code exchange, token refresh.

Google OAuth2 흐름 — 인증 코드 교환, 토큰 갱신.

## `salmalm.web.templates`

HTML template generation for web UI pages (setup, unlock, main chat, dashboard).

웹 UI 페이지(설정, 잠금 해제, 메인 채팅, 대시보드)용 HTML 템플릿 생성.
