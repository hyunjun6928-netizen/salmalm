# Self-Evolution

SalmAlm's self-evolution system allows the AI to improve its own behavior over time through prompt refinement, memory curation, and conversation logging.

## Components

### 1. Auto Memory Curation

After context compaction, SalmAlm automatically reviews recent conversations and extracts key information into structured memory:

```
Compaction triggered → auto_curate() → Update memory files → Secret scrubbing
```

Memory files are stored in `~/SalmAlm/memory/` as markdown, organized by date.

### 2. Conversation Auto-Logging

Every conversation is automatically logged to daily files:

```
~/SalmAlm/memory/2025-01-15.md
~/SalmAlm/memory/2025-01-16.md
```

The AI can reference these for continuity across sessions.

### 3. Prompt Evolution

The optional prompt evolver (`SALMALM_EVOLVE=1`) analyzes conversation patterns and suggests system prompt improvements:

- Which instructions are effective
- Which get ignored or misunderstood
- What new directives might help

### 4. Soul File

`~/SalmAlm/soul.md` defines the AI's personality and behavior. The AI can read and (with permission) modify this file to adjust its own character over time.

## Security

- **Secret scrubbing**: API keys, tokens, and credentials are automatically stripped before writing to memory (7 regex patterns)
- **Memory isolation**: Each user's memory is scoped to their session
- **No external transmission**: All evolution happens locally

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `SALMALM_EVOLVE` | `0` | Enable prompt evolution |
| `SALMALM_REFLECT` | `0` | Enable post-response reflection |
| `SALMALM_PLANNING` | `0` | Enable task planning phase |

## Related Tools

- `memory_write` — Write to memory files
- `memory_search` — Semantic search across memory
- `soul_edit` — Modify the soul/personality file
