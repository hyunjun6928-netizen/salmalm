# Commands Reference
# 명령어 레퍼런스

SalmAlm provides 35+ slash commands for controlling the AI assistant directly from chat.

SalmAlm은 채팅에서 직접 AI 비서를 제어할 수 있는 35개 이상의 슬래시 명령어를 제공합니다.

## Thinking & Output / 사고 및 출력

| Command / 명령어 | Description / 설명 |
|---|---|
| `/think <off\|low\|medium\|high>` | Set thinking level / 사고 수준 설정 |
| `/verbose <on\|full\|off>` | Verbose output mode / 상세 출력 모드. Alias: `/v` |
| `/reasoning <on\|off\|stream>` | Show reasoning process / 추론 과정 표시 |

## Session Management / 세션 관리

| Command / 명령어 | Description / 설명 |
|---|---|
| `/new [model]` | New session (optional model hint) / 새 세션 (선택적 모델 지정) |
| `/reset` | Reset current session / 현재 세션 초기화 |
| `/stop` | Stop current execution + active subagents / 실행 중단 + 서브에이전트 중지 |
| `/clear` | Clear session / 세션 지우기 |
| `/compact` | Compact context / 컨텍스트 압축 |
| `/context` | Show context info / 컨텍스트 정보 표시 |
| `/branch` | Branch conversation / 대화 분기 |
| `/rollback` | Rollback to previous state / 이전 상태로 롤백 |

## Information / 정보

| Command / 명령어 | Description / 설명 |
|---|---|
| `/help` | Command help / 명령어 도움말 |
| `/commands` | Full command list / 전체 명령어 목록 |
| `/status` | Server/session status / 서버/세션 상태 |
| `/whoami` | Show current user ID / 현재 사용자 ID 표시. Alias: `/id` |
| `/usage` | Usage stats / 사용량 통계 |
| `/model [name]` | Show/set model / 모델 표시/설정 |
| `/thinking` | Thinking mode info / 사고 모드 정보 |
| `/queue` | Queue status / 큐 상태 |

## Features / 기능

| Command / 명령어 | Description / 설명 |
|---|---|
| `/skill <name> [input]` | Run skill directly / 스킬 직접 실행 |
| `/oauth <setup\|status\|revoke\|refresh>` | OAuth management / OAuth 관리 |
| `/screen [watch\|history\|search]` | Screen capture & analysis / 화면 캡처 및 분석 |
| `/mcp <install\|list\|catalog\|remove\|status\|search>` | MCP marketplace / MCP 마켓플레이스 |
| `/persona` | Persona management / 페르소나 관리 |
| `/vault` | Vault operations / 볼트 작업 |
| `/shadow` | Shadow mode / 섀도우 모드 |
| `/deadman` | Dead man switch / 데드맨 스위치 |
| `/capsule` | Time capsule / 타임캡슐 |
| `/split` | Split response / 응답 분할 |
| `/workflow` | Workflow management / 워크플로우 관리 |
| `/life` | Life dashboard / 라이프 대시보드 |
| `/a2a` | Agent-to-agent / 에이전트 간 통신 |
| `/evolve` | Self-evolution / 자기 진화 |
| `/mood` | Mood info / 감정 정보 |
| `/subagents` | List subagents / 서브에이전트 목록 |

## Aliases / 별칭

| Alias / 별칭 | Target / 대상 |
|---|---|
| `/t` | `/think` |
| `/v` | `/verbose` |
| `/id` | `/whoami` |

## Inline Shortcuts / 인라인 단축키

These commands can be used inside a larger message:

이 명령어들은 메시지 안에서도 사용할 수 있습니다:

`/help`, `/status`, `/whoami`, `/id`, `/commands`

## Directive Commands / 지시어 명령어

These are stripped from the message and applied as settings; the rest of the message is sent to the LLM:

이 명령어들은 메시지에서 분리되어 설정으로 적용되고, 나머지 메시지는 LLM으로 전송됩니다:

`/think`, `/t`, `/verbose`, `/v`, `/model`, `/reasoning`

Example / 예시:

```
/think high What is the meaning of life?
```

This sets thinking to "high" and sends "What is the meaning of life?" to the AI.

사고 수준을 "high"로 설정하고 "What is the meaning of life?"를 AI에 전송합니다.
