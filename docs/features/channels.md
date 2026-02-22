# Telegram & Discord

## Telegram Bot

### Setup

1. [@BotFather](https://t.me/BotFather) → `/newbot` → Copy token
2. Web UI → Settings → Telegram → Paste token + chat ID
3. Restart SalmAlm

### Features

| Feature | Description |
|---|---|
| 👀 Ack reaction | Shows processing indicator on message |
| 💬 Reply-to | Responses quote the original message |
| ⌨️ Typing indicator | Continuous typing while processing |
| 📝 Streaming preview | Draft message edited in real-time as tokens arrive |
| 📋 Command menu | 12 commands registered via setMyCommands |
| ✂️ Smart split | 4096-char chunks respecting code blocks and paragraphs |
| 🔘 Inline buttons | Clickable action buttons in responses |
| 🖼️ Media | Image, audio, document sending |
| 🎤 Voice | TTS voice message responses |
| 🌐 Webhook | Optional webhook mode for production |

### Commands

```
/start       — Status
/help        — Show commands
/usage       — Token usage & cost
/model       — Switch AI model
/briefing    — Daily briefing
/routine     — Morning/evening routine
/note        — Quick note
/remind      — Reminders
/expense     — Expense tracking
/cal         — Calendar
/mail        — Email
/clear       — Clear conversation
/compact     — Compress history
/tts on|off  — Toggle voice
```

### Group Chat

- Bot responds only when @mentioned or replied to
- Privacy mode must be disabled for full group visibility (BotFather → `/setprivacy`)
- Each group gets an isolated session

## Discord Bot

### Setup

1. [Developer Portal](https://discord.com/developers/applications) → New Application
2. Bot → Enable **Message Content Intent**
3. OAuth2 → `bot` + `applications.commands` → Generate URL → Add to server
4. Web UI → Settings → Discord → Paste token
5. Restart SalmAlm

### Features

| Feature | Description |
|---|---|
| 👀 Ack reaction | Shows processing indicator |
| 💬 Reply-to | Responses reference the original message |
| ⌨️ Typing indicator | Continuous typing (8s refresh) |
| 📝 Streaming preview | Draft message edited as tokens arrive |
| ✂️ Smart split | 2000-char chunks respecting paragraphs |

### Commands

```
/start    — Status
/help     — Show commands
/usage    — Token usage & cost
/model    — Switch AI model
/clear    — Clear conversation
/compact  — Compress history
```

### Behavior

- **DMs**: Bot responds to all messages
- **Guilds**: Bot responds only when @mentioned
- Each channel gets its own isolated session
