# Security & Vault
# 보안 및 볼트

## Overview / 개요

SalmAlm follows a **dangerous features default OFF** policy with defense-in-depth security.

삶앎은 **위험 기능 기본 OFF** 정책과 심층 방어 보안을 따릅니다.

## Security Features / 보안 기능

- **Encrypted Vault** — PBKDF2-200K + AES-256-GCM (or HMAC-CTR fallback) / 암호화 볼트
- **Tool Risk Tiers** — critical/high/normal classification, critical tools blocked on external bind without auth / 도구 위험 등급 분류, 외부 바인딩 시 인증 없이 critical 도구 차단
- **SSRF Defense** — DNS pinning + private IP block for web tools AND browser / 웹 도구 및 브라우저 SSRF 방어
- **Irreversible Action Gate** — email send, calendar delete/create require confirmation / 되돌릴 수 없는 액션 승인 필요
- **Audit Log Redaction** — secrets scrubbed from tool args (9 patterns) / 감사 로그 비밀값 자동 제거
- **Memory Scrubbing** — API keys auto-redacted before storage / 메모리 저장 전 API 키 자동 삭제
- **Path Validation** — `Path.is_relative_to()` for all file ops / 모든 파일 작업에 pathlib 검증
- **Session Isolation** — user_id scoping in session_store / 세션 스토어 사용자별 격리
- **Centralized Auth Gate** — all `/api/` routes require auth / 모든 API 경로 인증 필수
- **CSRF Defense** — Origin + `X-Requested-With` header / CSRF 방어
- **Node HMAC** — signed dispatch payloads with timestamp + nonce / 노드 HMAC 서명 디스패치
- **Secret Isolation** — API keys stripped from subprocess environments / 서브프로세스 환경에서 API 키 제거
- **Rate Limiting** — token bucket per-IP limiter / IP별 토큰 버킷 속도 제한
- **Exec Sandbox** — OS-native isolation (bubblewrap/rlimit) / OS 네이티브 격리
- **142+ security tests** in CI / CI에서 142+ 보안 테스트

## Vault Commands / 볼트 명령어

```
/vault list          # List stored keys / 저장된 키 목록
/vault get <key>     # Get a value / 값 가져오기
/vault set <key> <v> # Set a value / 값 설정
/vault delete <key>  # Delete a key / 키 삭제
```

## Env Variables / 환경 변수

| Variable | Default | Description |
|---|---|---|
| `SALMALM_BIND` | `127.0.0.1` | Bind address / 바인드 주소 |
| `SALMALM_ALLOW_SHELL` | OFF | Shell operators / 셸 연산자 |
| `SALMALM_ALLOW_HOME_READ` | OFF | Home dir read / 홈 디렉토리 읽기 |
| `SALMALM_VAULT_FALLBACK` | OFF | HMAC-CTR fallback / HMAC-CTR 폴백 |
| `SALMALM_PLUGINS` | OFF | Plugin system / 플러그인 시스템 |
| `SALMALM_CLI_OAUTH` | OFF | CLI token reuse / CLI 토큰 재사용 |
| `SALMALM_CSP_COMPAT` | OFF | Legacy CSP mode / 레거시 CSP 모드 |
| `SALMALM_ALLOW_ELEVATED` | OFF | Elevated exec on external bind / 외부 바인딩 시 관리자 명령 |

See [`SECURITY.md`](../../SECURITY.md) for full threat model.
