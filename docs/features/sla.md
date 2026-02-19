# SLA & Monitoring
# SLA 및 모니터링

## Overview / 개요

SalmAlm tracks uptime, response times, and system health for production reliability.

SalmAlm은 프로덕션 안정성을 위해 업타임, 응답 시간, 시스템 상태를 추적합니다.

## Metrics / 메트릭

- **Uptime** — 99.9% target tracking / 99.9% 목표 추적
- **Response time** — P50/P95/P99 percentiles / P50/P95/P99 백분위
- **Tool call stats** — usage by tool / 도구별 사용량
- **Cost tracking** — by model / 모델별 비용 추적
- **Error rates** — by category / 카테고리별 오류율

## Dashboard / 대시보드

Access at `/dashboard` — auto-refreshes every 60 seconds.

`/dashboard`에서 접근 — 60초마다 자동 새로고침.

Features: / 기능:

- Tool calls bar chart (24h) / 도구 호출 막대 그래프 (24시간)
- Cost doughnut chart (by model) / 비용 도넛 차트 (모델별)
- Model stats table / 모델 통계 테이블
- Cron/plugin status / 크론/플러그인 상태

## Auto Watchdog / 자동 워치독

Self-healing watchdog that restarts the server if it becomes unresponsive.

서버가 응답하지 않으면 자동으로 재시작하는 자가 복구 워치독.

## Doctor / 진단

Run `/doctor` for a full system diagnostic.

`/doctor`를 실행하면 전체 시스템 진단을 수행합니다.
