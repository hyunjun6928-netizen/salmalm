# Tools Module API
# 도구 모듈 API

The `salmalm.tools` package implements all 66 built-in tools.

`salmalm.tools` 패키지는 66개의 내장 도구를 모두 구현합니다.

## `salmalm.tools.tool_registry`

Decorator-based tool dispatch system replacing if-elif chains.

if-elif 체인을 대체하는 데코레이터 기반 도구 디스패치 시스템.

**Key functions / 주요 함수:**

- `register(name)` — Decorator to register a tool handler / 도구 핸들러 등록 데코레이터
- `dispatch(name, args)` — Dispatch tool call to registered handler / 등록된 핸들러로 도구 호출 디스패치

## `salmalm.tools.tools`

Tool definitions — JSON schemas for all 66 tools used in LLM system prompt.

도구 정의 — LLM 시스템 프롬프트에 사용되는 66개 내장 도구 JSON 스키마.

## Tool Handler Modules / 도구 핸들러 모듈

| Module / 모듈 | Tools / 도구 |
|---|---|
| `tools_file` | `read_file`, `write_file`, `edit_file`, `diff_files`, `file_index` |
| `tools_web` | `web_search`, `web_fetch`, `http_request` |
| `tools_exec` | `exec`, `exec_session`, `python_eval` |
| `tools_memory` | `memory_read`, `memory_write`, `memory_search`, `note` |
| `tools_system` | `system_monitor`, `health_check`, `usage_report` |
| `tools_personal` | `briefing`, `expense`, `save_link`, `pomodoro`, `routine` |
| `tools_calendar` | `google_calendar`, `calendar_list`, `calendar_add`, `calendar_delete` |
| `tools_email` | `email_inbox`, `email_read`, `email_send`, `email_search`, `gmail` |
| `tools_google` | Google API integrations |
| `tools_media` | `image_analyze`, `image_generate`, `tts`, `tts_generate`, `stt`, `qr_code` |
| `tools_browser` | `browser`, `screenshot` |
| `tools_agent` | `sub_agent` |
| `tools_misc` | `translate`, `rss_reader`, `hash_text`, `regex_test`, `json_query`, `weather` |
| `tools_patch` | `apply_patch` |
| `tools_reminder` | `reminder`, `cron_manage` |
| `tools_util` | `clipboard`, miscellaneous utilities |
| `tools_reaction` | Reaction/emoji tools |
| `tools_common` | Shared tool utilities |
