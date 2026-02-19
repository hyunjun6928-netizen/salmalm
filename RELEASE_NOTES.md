# v0.14.0 Release Notes / 릴리즈 노트

> Released: 2025-02 / 출시: 2025-02

---

## 🎉 Highlights / 하이라이트

- **56 built-in tools** (was 43) / 56개 내장 도구 (기존 43개에서 증가)
- **586 tests passing** / 586개 테스트 통과
- **OWASP Top 10 security audit** / OWASP Top 10 보안 감사 완료
- **Multi-tenant support** / 멀티테넌트 지원
- **SLA monitoring dashboard** / SLA 모니터링 대시보드

---

## 🆕 New Features / 신규 기능

### 🤖 AI Engine / AI 엔진
- Multi-model routing with auto-select (Opus/Sonnet/Haiku) / 멀티모델 자동 라우팅
- Extended thinking mode / 확장 사고 모드
- Context compaction at 80K tokens / 80K 토큰 시 컨텍스트 자동 압축
- Session pruning (tool result cleanup) / 세션 프루닝
- Model failover with exponential backoff / 지수 백오프 모델 자동 전환
- 13 new tools added / 13개 신규 도구 추가

### 💬 Chat & UI / 채팅 및 UI
- Inline buttons for web and Telegram / 웹 및 텔레그램 인라인 버튼
- Session branching & rollback / 세션 분기 및 롤백
- Message edit and delete / 메시지 편집 및 삭제
- Conversation search (`Ctrl+K`) / 대화 검색
- Command palette (`Ctrl+Shift+P`) / 커맨드 팔레트
- Code syntax highlighting (6 languages) / 코드 구문 강조
- Session groups & bookmarks / 세션 그룹 및 북마크
- Regenerate & response comparison / 응답 재생성 및 비교
- TTS support (Web Speech + OpenAI) / 음성 합성 지원
- PWA installable / PWA 설치 가능
- Dark/Light theme / 다크/라이트 테마

### 🔗 Integrations / 통합
- Discord integration / 디스코드 연동
- Google Calendar integration / 구글 캘린더 연동
- Gmail integration / 지메일 연동
- Google OAuth flow / 구글 OAuth 인증

### 🧑‍💼 Personal Assistant / 개인 비서
- Daily briefing (weather + calendar + email) / 데일리 브리핑
- Smart reminders (natural language, KR/EN) / 스마트 리마인더
- Notes & knowledge base / 메모 및 지식 베이스
- Expense tracker / 가계부
- Link saver with auto-summary / 링크 저장
- Pomodoro timer / 포모도로 타이머
- Morning/evening routines / 아침/저녁 루틴
- Quick translate / 빠른 번역

### 🏢 Enterprise / 엔터프라이즈
- Multi-tenant with user isolation / 멀티테넌트 사용자 격리
- Per-user quotas (daily/monthly) / 사용자별 쿼터
- Multi-agent routing / 다중 에이전트 라우팅
- Plugin architecture / 플러그인 아키텍처
- Event hooks system / 이벤트 훅 시스템
- Multi-persona (SOUL.md) / 멀티 페르소나
- Windows system tray / Windows 시스템 트레이
- Auto-update / 자동 업데이트

### 📊 SLA & Monitoring / SLA 및 모니터링
- Uptime monitoring (99.9% tracking) / 업타임 모니터링
- Response time SLA (P50/P95/P99) / 응답 시간 SLA
- Auto watchdog (self-healing) / 자동 워치독
- SLA dashboard / SLA 대시보드

---

## 🔒 Security / 보안

- OWASP Top 10 full compliance / OWASP Top 10 완전 준수
- Rate limiting (IP-based) / IP 기반 요청 빈도 제한
- SSRF protection / SSRF 방지
- SQL injection prevention / SQL 인젝션 방지
- AES-256-GCM vault encryption / AES-256-GCM 볼트 암호화
- Audit logging / 감사 로깅
- Graceful shutdown / 안전한 종료

---

## 🐛 Bug Fixes / 버그 수정

- Fixed WebSocket reconnection on network change / 네트워크 변경 시 웹소켓 재연결 수정
- Fixed session export encoding for Korean text / 한글 텍스트 세션 내보내기 인코딩 수정
- Fixed Telegram message splitting for long responses / 텔레그램 긴 응답 메시지 분할 수정
- Fixed memory leak in long-running sessions / 장시간 세션 메모리 누수 수정
- Fixed cron scheduler timezone handling / 크론 스케줄러 타임존 처리 수정

---

## 📊 Stats / 통계

| Metric | Value |
|---|---|
| Python | 21,823 lines |
| HTML | 2,586 lines |
| Tests | 586 (5,001 lines) |
| Tools | 56 |
| Modules | 54 |

---

## ⬆️ Upgrade / 업그레이드

```bash
pip install --upgrade salmalm
```

---

## 📦 Full Changelog / 전체 변경 로그

See [commits on main](https://github.com/hyunjun6928-netizen/salmalm/commits/main) for the complete history.
전체 변경 내역은 [main 브랜치 커밋](https://github.com/hyunjun6928-netizen/salmalm/commits/main)을 참고하세요.
