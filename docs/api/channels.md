# Channels Module API
# 채널 모듈 API

The `salmalm.channels` package handles multi-channel chat integrations.

`salmalm.channels` 패키지는 멀티채널 채팅 통합을 처리합니다.

## `salmalm.channels.channel_router`

Routes messages from any channel (Web, Telegram, Discord) to the core engine.

모든 채널(Web, Telegram, Discord)의 메시지를 코어 엔진으로 라우팅합니다.

## `salmalm.channels.telegram`

Telegram bot integration supporting both polling and webhook modes. Handles inline buttons, image uploads, voice messages, and all slash commands.

텔레그램 봇 통합 — 폴링 및 웹훅 모드 지원. 인라인 버튼, 이미지 업로드, 음성 메시지, 모든 슬래시 명령어 처리.

## `salmalm.channels.discord_bot`

Discord bot integration with guild support, slash commands, and message reactions.

디스코드 봇 통합 — 길드 지원, 슬래시 명령어, 메시지 리액션.

## `salmalm.channels.slack_bot`

Slack bot integration (experimental).

슬랙 봇 통합 (실험적).
