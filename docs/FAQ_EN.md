# FAQ (Frequently Asked Questions)

## Installation / Running

### Q: What Python version do I need?
Python 3.9+. 3.12+ recommended.

### Q: I installed via pip but `salmalm` command doesn't work
It's likely not on your PATH. Use `python -m salmalm` instead.

### Q: Errors on Windows
Use cmd.exe (not PowerShell). Avoid Korean/non-ASCII characters in folder paths.
```
python -m salmalm
```

### Q: How do I run with Docker?
```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
docker compose up -d
# → http://localhost:18800
```

---

## API Keys

### Q: Can I use it without an API key?
Yes. Install Ollama for a fully local, free LLM experience.
```bash
ollama pull llama3.2
python -m salmalm
# During onboarding, set Ollama URL: http://localhost:11434/v1
```

### Q: Where do I get API keys?
| Provider | URL |
|----------|-----|
| Anthropic (Claude) | https://console.anthropic.com/settings/keys |
| OpenAI (GPT) | https://platform.openai.com/api-keys |
| xAI (Grok) | https://console.x.ai |
| Google (Gemini) | https://aistudio.google.com/apikey |
| Brave Search | https://brave.com/search/api/ (free) |

### Q: Where are API keys stored?
Two options:
1. **`.env` file** — plaintext in project root (simple)
2. **Vault** — AES-256-GCM encrypted storage (secure)

`.env` takes priority over vault when both exist.

---

## Password / Vault

### Q: I forgot my password
Delete the vault file to reset:
- **Windows**: `del %USERPROFILE%\.salmalm\vault.enc`
- **Linux/Mac**: `rm ~/.salmalm/vault.enc`

Then run `python -m salmalm` to start fresh.
⚠️ This also deletes API keys stored in vault. Back them up in `.env` first.

### Q: I don't want a password
Choose "No, start right away" during first-run setup.
Already set one? Settings → 🔒 Master Password → "Remove Password"

### Q: Can I add a password later?
Yes. Settings → 🔒 Master Password → Set New Password

---

## Models / Usage

### Q: Which model should I use?
- **General chat**: Claude Sonnet or GPT-4.1 (best value)
- **Complex coding**: Claude Opus or o3 (top performance)
- **Fast responses**: Gemini Flash or GPT-4.1-nano (low cost)
- **Free**: Ollama + llama3.2 (local)

### Q: How do I switch models?
Web UI → Settings → Model dropdown, or type `/model anthropic/claude-opus-4-6` in chat.

### Q: How much does it cost?
Check Settings → Token Usage for real-time tracking.
Typical usage: $0.5–$2/day.

---

## Images

### Q: How do I generate images?
Just ask naturally in chat: "Draw a cat". Uses DALL-E or xAI Aurora. Requires an OpenAI API key.

### Q: How about image analysis?
Upload an image file or send a URL — the `image_analyze` tool handles it automatically.
Uses GPT-4o or Claude Vision.

---

## Troubleshooting

### Q: "Connection refused" error
Make sure the server is running. Run `python -m salmalm`, then visit http://localhost:18800.

### Q: Telegram bot not responding
1. Check `.env` for `TELEGRAM_TOKEN` and `TELEGRAM_OWNER_ID`
2. Another process polling with the same bot token will cause conflicts

### Q: How do I update?
```bash
python -m pip install --upgrade salmalm
python -m salmalm
```
Or use Web UI → Settings → Update → Check for Updates

### Q: Where are logs?
`~/.salmalm/salmalm.log` (or `salmalm.log` in the project directory)
