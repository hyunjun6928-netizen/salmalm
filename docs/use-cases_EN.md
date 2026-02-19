# Use Cases

## 1. 🤖 Telegram AI Assistant

Chat with your AI anytime from your phone — ask questions, analyze files, search the web.

### Setup

```env
# .env
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_TOKEN=123456:ABC...
TELEGRAM_OWNER_ID=your_telegram_id
BRAVE_API_KEY=BSA...
```

```bash
pip install salmalm
python -m salmalm
```

### What You Can Do

- 📝 Request code reviews → AI analyzes and suggests improvements
- 🔍 "Bitcoin price today?" → real-time web search answers
- 📄 Send a PDF/image → get a summary
- ⏰ `/cron daily 9am news summary` → scheduled tasks
- 💾 `/memo meeting at 3pm tomorrow` → save & search memos
- 👁️ Send a photo → `image_analyze` describes content, reads text (OCR)

---

## 2. 💻 Local Code Review Bot

Like GitHub Copilot, but it understands your entire codebase.

### Setup

```bash
pip install salmalm
python -m salmalm
# Open http://localhost:18800
# Enter your API key
```

### Workflow

1. Tell it a file path in chat:
   ```
   Review /home/user/project/main.py
   ```

2. AI reads the file and analyzes:
   - Potential bugs
   - Performance improvements
   - Security issues
   - Refactoring suggestions

3. Index your project docs with RAG:
   ```
   /rag index /home/user/project/docs/
   ```
   Then ask "What's the project architecture?" for document-grounded answers.

---

## 3. 🦙 Offline AI (Ollama)

No internet. No API keys. Fully local AI.

### Setup

```bash
# 1. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. Download models
ollama pull llama3.2        # 3GB, general chat
ollama pull codellama:13b   # 7GB, coding
ollama pull mistral         # 4GB, multipurpose

# 3. Run SalmAlm
pip install salmalm
python -m salmalm
# During onboarding, set Ollama URL: http://localhost:11434/v1
```

### Advantages

- 🔒 Data never leaves your machine
- 💰 Zero API cost
- 🌐 No internet required
- 🔄 Swap models freely (`/model ollama/llama3.2`)

### Limitations

- Slow without GPU (CPU inference: 10–30s per response)
- Local models lag behind Claude/GPT in quality
- Tool calling supported only by select models

---

## 4. 🏢 Team AI Gateway

Share an AI server across your team using the Gateway-Node architecture.

### Setup

```bash
# Main server (gateway)
SALMALM_VAULT_PW=team_secret python -m salmalm --host 0.0.0.0

# Remote worker (GPU server)
python -m salmalm --node --gateway-url http://gateway:18800
```

### Architecture

```
[Team browsers] → [Gateway server] → [LLM API]
                         ↓
                  [GPU Node (Ollama)]
```

- Gateway receives requests and routes to appropriate nodes
- GPU nodes handle heavy work (local models, code execution)
- API keys stored on gateway only (never exposed to team members)

---

## 5. 👁️ Image Analysis Workstation

Analyze images, screenshots, diagrams — locally or via cloud vision models.

### Setup

```bash
pip install salmalm
python -m salmalm
# Add an OpenAI or Anthropic API key with vision support
```

### What You Can Do

- Upload a screenshot → AI describes the UI and reads all text
- Send a diagram → get a structured explanation
- Paste a URL → `image_analyze` fetches and analyzes it
- OCR handwritten notes → extracted text in seconds
