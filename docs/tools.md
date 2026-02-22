# Tools Catalog
# 도구 카탈로그

SalmAlm includes 66 built-in tools that the AI can use autonomously. No plugins required.

SalmAlm은 AI가 자율적으로 사용할 수 있는 66개의 내장 도구를 포함합니다. 플러그인이 필요 없습니다.

## Execution / 실행

| Tool / 도구 | Description / 설명 |
|---|---|
| `exec` | Execute shell commands (supports background, timeout, env) / 셸 명령 실행 |
| `exec_session` | Manage background sessions (list, poll, kill) / 백그라운드 세션 관리 |
| `python_eval` | Evaluate Python expressions / 파이썬 표현식 평가 |
| `sub_agent` | Spawn sub-agents for parallel tasks / 병렬 작업용 서브에이전트 생성 |

## File Operations / 파일 작업

| Tool / 도구 | Description / 설명 |
|---|---|
| `read_file` | Read file contents / 파일 내용 읽기 |
| `write_file` | Write content to file / 파일에 내용 쓰기 |
| `edit_file` | Edit file with search/replace / 파일 검색/교체 편집 |
| `diff_files` | Show diff between files / 파일 간 차이점 표시 |
| `apply_patch` | Apply unified diff patches / 통합 diff 패치 적용 |
| `file_index` | Index and search files / 파일 인덱스 및 검색 |

## Web & HTTP / 웹 및 HTTP

| Tool / 도구 | Description / 설명 |
|---|---|
| `web_search` | Search the web (Brave API) / 웹 검색 |
| `web_fetch` | Fetch and extract web page content / 웹 페이지 콘텐츠 가져오기 |
| `http_request` | Make HTTP requests / HTTP 요청 보내기 |
| `browser` | Browser automation / 브라우저 자동화 |
| `screenshot` | Take screenshots / 스크린샷 캡처 |

## Memory & Knowledge / 메모리 및 지식

| Tool / 도구 | Description / 설명 |
|---|---|
| `memory_read` | Read from memory store / 메모리 저장소에서 읽기 |
| `memory_write` | Write to memory store / 메모리 저장소에 쓰기 |
| `memory_search` | Search memory / 메모리 검색 |
| `rag_search` | RAG vector search / RAG 벡터 검색 |
| `note` | Create/manage notes / 메모 생성/관리 |

## Communication / 통신

| Tool / 도구 | Description / 설명 |
|---|---|
| `email_inbox` | List email inbox / 이메일 받은편지함 목록 |
| `email_read` | Read email / 이메일 읽기 |
| `email_send` | Send email / 이메일 전송 |
| `email_search` | Search emails / 이메일 검색 |
| `gmail` | Gmail-specific operations / Gmail 전용 작업 |
| `notification` | Send notifications / 알림 전송 |

## Calendar & Scheduling / 캘린더 및 일정

| Tool / 도구 | Description / 설명 |
|---|---|
| `google_calendar` | Google Calendar operations / 구글 캘린더 작업 |
| `calendar_list` | List calendar events / 캘린더 이벤트 목록 |
| `calendar_add` | Add calendar event / 캘린더 이벤트 추가 |
| `calendar_delete` | Delete calendar event / 캘린더 이벤트 삭제 |
| `reminder` | Set/manage reminders / 리마인더 설정/관리 |
| `cron_manage` | Manage cron schedules / 크론 일정 관리 |

## Personal Productivity / 개인 생산성

| Tool / 도구 | Description / 설명 |
|---|---|
| `briefing` | Daily briefing (weather + calendar + email) / 데일리 브리핑 |
| `expense` | Expense tracking / 가계부 |
| `save_link` | Save links with auto-summary / 링크 저장 (자동 요약) |
| `pomodoro` | Pomodoro timer / 포모도로 타이머 |
| `routine` | Morning/evening routines / 아침/저녁 루틴 |
| `weather` | Weather information / 날씨 정보 |

## Media / 미디어

| Tool / 도구 | Description / 설명 |
|---|---|
| `image_analyze` | Analyze images (vision) / 이미지 분석 (비전) |
| `image_generate` | Generate images / 이미지 생성 |
| `tts` | Text-to-speech / 텍스트 음성 변환 |
| `tts_generate` | Generate TTS audio file / TTS 오디오 파일 생성 |
| `stt` | Speech-to-text / 음성 텍스트 변환 |
| `qr_code` | Generate QR codes / QR 코드 생성 |

## Utilities / 유틸리티

| Tool / 도구 | Description / 설명 |
|---|---|
| `translate` | Translate text / 텍스트 번역 |
| `rss_reader` | Read RSS feeds / RSS 피드 읽기 |
| `hash_text` | Hash text (MD5, SHA256, etc.) / 텍스트 해시 |
| `regex_test` | Test regular expressions / 정규식 테스트 |
| `json_query` | Query JSON data / JSON 데이터 쿼리 |
| `clipboard` | Clipboard operations / 클립보드 작업 |

## System / 시스템

| Tool / 도구 | Description / 설명 |
|---|---|
| `system_monitor` | System resource monitoring / 시스템 리소스 모니터링 |
| `health_check` | Health check / 상태 점검 |
| `usage_report` | Usage statistics / 사용량 보고서 |
| `plugin_manage` | Manage plugins / 플러그인 관리 |
| `mcp_manage` | MCP server management / MCP 서버 관리 |
| `node_manage` | Node management / 노드 관리 |
| `skill_manage` | Skill management / 스킬 관리 |
| `workflow` | Workflow automation / 워크플로우 자동화 |

## Google Integration / 구글 통합

| Tool / 도구 | Description / 설명 |
|---|---|
| `google_calendar` | Google Calendar API / 구글 캘린더 API |
| `gmail` | Gmail API / Gmail API |
