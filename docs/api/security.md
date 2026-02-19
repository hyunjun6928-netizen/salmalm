# Security Module API
# 보안 모듈 API

The `salmalm.security` package provides OWASP-compliant security features.

`salmalm.security` 패키지는 OWASP 준수 보안 기능을 제공합니다.

## `salmalm.security.security`

Main security module — rate limiting, SSRF protection, SQL injection prevention, input sanitization.

메인 보안 모듈 — 요청 빈도 제한, SSRF 방지, SQL 인젝션 방지, 입력 새니타이제이션.

## `salmalm.security.crypto`

AES-256-GCM vault encryption for storing sensitive data (API keys, tokens).

민감 데이터(API 키, 토큰) 저장을 위한 AES-256-GCM 볼트 암호화.

## `salmalm.security.sandbox`

Sandboxed code execution environment for `python_eval` and other code tools.

`python_eval` 및 기타 코드 도구를 위한 샌드박스 실행 환경.

## `salmalm.security.container`

Container isolation for untrusted code execution.

신뢰할 수 없는 코드 실행을 위한 컨테이너 격리.

## `salmalm.security.exec_approvals`

Dangerous command approval system — prompts user before executing risky shell commands.

위험 명령어 승인 시스템 — 위험한 셸 명령 실행 전 사용자에게 확인 요청.
