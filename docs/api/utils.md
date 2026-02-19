# Utils Module API
# 유틸리티 모듈 API

The `salmalm.utils` package provides shared utility functions.

`salmalm.utils` 패키지는 공유 유틸리티 함수를 제공합니다.

## `salmalm.utils.async_http`

Async HTTP client built on `urllib` — supports GET/POST/PUT/DELETE with timeout and retry.

`urllib` 기반 비동기 HTTP 클라이언트 — 타임아웃과 재시도를 지원하는 GET/POST/PUT/DELETE.

## `salmalm.utils.chunker`

Message chunking for platforms with message length limits (Telegram: 4096 chars, Discord: 2000 chars).

메시지 길이 제한이 있는 플랫폼용 메시지 분할 (텔레그램: 4096자, 디스코드: 2000자).

## `salmalm.utils.dedup`

Message deduplication and debounce to prevent duplicate processing.

중복 처리를 방지하는 메시지 중복 제거 및 디바운스.

## `salmalm.utils.retry`

Retry with exponential backoff for transient failures.

일시적 오류에 대한 지수 백오프 재시도.

## `salmalm.utils.queue`

Async message queue for ordered processing.

순서 처리를 위한 비동기 메시지 큐.

## `salmalm.utils.file_logger`

File-based logging with rotation.

로테이션을 지원하는 파일 기반 로깅.

## `salmalm.utils.logging_ext`

Logging extensions — colored output, structured logging.

로깅 확장 — 색상 출력, 구조화된 로깅.

## `salmalm.utils.markdown_ir`

Markdown intermediate representation processor for cross-platform rendering.

크로스플랫폼 렌더링을 위한 Markdown 중간 표현 프로세서.

## `salmalm.utils.migration`

Data migration utilities for schema upgrades.

스키마 업그레이드를 위한 데이터 마이그레이션 유틸리티.

## `salmalm.utils.tls`

TLS certificate generation for HTTPS support.

HTTPS 지원을 위한 TLS 인증서 생성.

## `salmalm.utils.browser`

Browser utility functions for web automation tools.

웹 자동화 도구를 위한 브라우저 유틸리티 함수.
