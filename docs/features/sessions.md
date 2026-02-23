# Session Management

SalmAlm manages conversations as isolated sessions with automatic context window optimization.

## Session Lifecycle

```
New Message → Get/Create Session → Build Context → LLM Call → Store Response → Auto-compact if needed
```

Each session has:

- **Unique ID** — alphanumeric, auto-generated or named
- **Message history** — stored in SQLite (`session_store`)
- **Model override** — per-session model selection
- **User binding** — sessions belong to authenticated users (multi-user mode)

## Context Window Management

| Feature | Value | Configurable |
|---------|-------|-------------|
| Compaction threshold | 30K tokens | ✅ `SALMALM_COMPACTION` |
| History trim (chat) | Last 10 messages | ✅ via Engine Settings |
| History trim (creative) | Last 20 messages | ✅ |
| Tool result truncation | 20K chars max | ✅ |

### Auto-Compaction

When context exceeds the threshold, SalmAlm automatically:

1. Sends history to LLM with a compaction prompt
2. Replaces old messages with a compact summary
3. Preserves recent messages (last 4) for continuity
4. Triggers `auto_curate()` to update memory files

## Commands

| Command | Description |
|---------|-------------|
| `/context` | Show token usage breakdown |
| `/context full` | Detailed per-message token counts |
| `/clear` | Reset current session |
| `/sessions` | List all sessions |
| `/session <id>` | Switch to named session |
| `/export` | Export session as JSON |

## Web UI

The **Sessions** panel shows:

- Active sessions with titles and last activity
- Token usage per session
- One-click session switching
- Session deletion and export

## Session Store

Sessions persist in `~/SalmAlm/sessions.db` (SQLite). Schema:

```sql
CREATE TABLE session_store (
    session_id TEXT PRIMARY KEY,
    messages TEXT,        -- JSON array
    title TEXT,
    user_id INTEGER,
    created_at TEXT,
    updated_at TEXT
);
```

## Multi-User Sessions

When authentication is enabled, sessions are scoped per user. Each user sees only their own sessions. Admin users can view all sessions via the API.
