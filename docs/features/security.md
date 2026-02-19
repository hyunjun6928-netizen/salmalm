# Security & Vault
# 보안 및 볼트

## Overview / 개요

SalmAlm is OWASP Top 10 compliant with enterprise-grade security features.

SalmAlm은 엔터프라이즈급 보안 기능으로 OWASP Top 10을 준수합니다.

## Security Features / 보안 기능

- **AES-256-GCM vault** — encrypted storage for API keys and secrets / API 키 및 비밀 정보 암호화 저장
- **Rate limiting** — IP-based request throttling / IP 기반 요청 빈도 제한
- **SSRF protection** — blocks internal network access from tools / 도구에서 내부 네트워크 접근 차단
- **SQL injection prevention** — parameterized queries / 매개변수화된 쿼리
- **CSP nonce** — no unsafe-inline scripts / 안전하지 않은 인라인 스크립트 없음
- **Input sanitization** — XSS prevention / XSS 방지
- **Exec approval** — dangerous commands require user confirmation / 위험 명령어 사용자 확인 필요
- **Audit logging** — all actions logged to `audit.db` / 모든 작업 `audit.db`에 로깅
- **Sandboxed execution** — isolated code eval / 격리된 코드 실행
- **Graceful shutdown** — state preservation / 상태 보존

## Vault Commands / 볼트 명령어

```
/vault list          # List stored keys / 저장된 키 목록
/vault get <key>     # Get a value / 값 가져오기
/vault set <key> <v> # Set a value / 값 설정
/vault delete <key>  # Delete a key / 키 삭제
```
