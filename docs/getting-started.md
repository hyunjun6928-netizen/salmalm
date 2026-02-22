# Getting Started

## Installation

```bash
# pip
pip install salmalm

# pipx (recommended for CLI tools)
pipx install salmalm

# From source
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
pip install -e .
```

## First Launch

```bash
salmalm
```

1. **Setup Wizard** — Choose whether to set a master password
2. **Onboarding** — Paste your API keys (at least one provider)
3. **Main UI** — Start chatting at `http://localhost:18800`

### API Key Setup

You need at least one provider API key:

| Provider | Get API Key |
|---|---|
| Anthropic | [console.anthropic.com](https://console.anthropic.com) |
| OpenAI | [platform.openai.com](https://platform.openai.com/api-keys) |
| Google | [aistudio.google.com](https://aistudio.google.com/apikey) |
| xAI | [console.x.ai](https://console.x.ai) |

### Local LLM (No API Key Needed)

```bash
# Start Ollama
ollama serve
ollama pull llama3.2

# In SalmAlm Settings → Local LLM
# Endpoint: http://localhost:11434/v1
```

## CLI Options

```bash
salmalm                    # Default (port 18800)
salmalm --port 9000        # Custom port
salmalm --open             # Auto-open browser
salmalm --shortcut         # Create desktop shortcut
salmalm --update           # Self-update from PyPI
```

## Environment Variables

```bash
SALMALM_PORT=18800         # Web server port
SALMALM_BIND=127.0.0.1    # Bind address (0.0.0.0 for LAN)
SALMALM_HOME=~/SalmAlm    # Data directory
```

## Docker

```bash
git clone https://github.com/hyunjun6928-netizen/salmalm.git
cd salmalm
docker compose up -d
# → http://localhost:18800
```

## Telegram Bot Setup

1. Talk to [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy bot token
3. In SalmAlm web UI → Settings → Telegram → Paste token + your chat ID
4. Restart SalmAlm

## Discord Bot Setup

1. [Discord Developer Portal](https://discord.com/developers/applications) → New Application
2. Bot → Reset Token → Copy
3. OAuth2 → bot + applications.commands → Generate URL → Add to server
4. In SalmAlm web UI → Settings → Discord → Paste token
5. Restart SalmAlm

## Next Steps

- [Commands Reference](commands.md)
- [Tools Reference](tools.md)
- [Configuration](configuration.md)
- [Security](features/security.md)
