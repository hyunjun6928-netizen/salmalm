# SalmAlm API Reference

Base URL: `http://localhost:18800`

## Authentication
All `/api/*` endpoints require authentication via `X-Session-Token` header or API key.

```
X-Session-Token: <token>
```

Or API key:
```
X-Api-Key: sk_<key>
```

## Endpoints

### Chat

#### POST /api/chat
Send a message and get a response.

**Request:**
```json
{
  "message": "Hello",
  "session": "web",
  "image_base64": null,
  "image_mime": "image/png"
}
```

**Response:**
```json
{
  "response": "Hello! How can I help?",
  "model": "anthropic/claude-sonnet-4-20250514"
}
```

#### POST /api/chat/stream
SSE streaming version of chat. Returns events:
- `status` — Processing status updates
- `tool` — Tool execution notifications
- `chunk` — Response text chunks
- `done` — Final complete response
- `close` — Stream end

### Sessions

#### GET /api/sessions
List all chat sessions.

**Response:**
```json
{
  "sessions": [
    {"id": "web", "title": "My conversation", "updated": "2026-02-19T12:00:00"}
  ]
}
```

#### POST /api/sessions/delete
Delete a session.

**Request:**
```json
{"session_id": "s_abc123"}
```

#### POST /api/sessions/rename
Rename a session.

**Request:**
```json
{"session_id": "s_abc123", "title": "New title"}
```

### Vault (Key Management)

#### POST /api/vault
Manage encrypted key storage.

**Actions:**
- `{"action": "keys"}` — List stored key names
- `{"action": "set", "key": "openai_api_key", "value": "sk-..."}` — Store a key
- `{"action": "get", "key": "openai_api_key"}` — Get a key value
- `{"action": "delete", "key": "openai_api_key"}` — Delete a key
- `{"action": "change_password", "old_password": "...", "new_password": "..."}` — Change vault password

### Status

#### GET /api/status
Get usage statistics and server status.

**Response:**
```json
{
  "usage": {
    "total_input": 15000,
    "total_output": 5000,
    "total_cost": 0.0234,
    "elapsed_hours": "2.5h",
    "by_model": {
      "anthropic/claude-sonnet-4-20250514": {"calls": 10, "cost": 0.02}
    }
  },
  "model": "auto",
  "version": "0.11.4"
}
```

### Speech-to-Text

#### POST /api/stt
Transcribe audio to text via Whisper.

**Request:**
```json
{
  "audio_base64": "<base64 encoded audio>",
  "language": "ko"
}
```

**Response:**
```json
{"text": "안녕하세요"}
```

### File Upload

#### POST /api/upload
Upload a file (multipart/form-data).

**Response:**
```json
{
  "ok": true,
  "info": "Uploaded: file.txt (1.2KB)",
  "image_base64": null,
  "image_mime": null
}
```

### Updates

#### GET /api/check-update
Check for new versions on PyPI.

#### POST /api/do-update
Run `pip install --upgrade salmalm`. Admin + loopback only.

### Health

#### GET /health
Health check endpoint. Returns 200 if server is running.

### PWA

#### GET /manifest.json
PWA manifest for installable web app.

#### GET /sw.js
Service worker (standalone PWA mode only).

#### GET /icon-192.svg, /icon-512.svg
App icons.

## Error Responses
```json
{"error": "Description of error"}
```

HTTP status codes:
- `200` — Success
- `400` — Bad request
- `401` — Unauthorized
- `403` — Forbidden (vault locked)
- `404` — Not found
- `500` — Internal server error
