# RAG & Knowledge Base

SalmAlm includes a zero-dependency RAG (Retrieval-Augmented Generation) system — no external vector DB, no embeddings API. Everything runs locally in SQLite.

## How It Works

```
User Query → Tokenize → BM25 + TF-IDF Hybrid Search → Top-K Chunks → Inject into Prompt
```

1. **Indexing**: Files are chunked (5 lines, 2-line overlap) and tokenized with Korean jamo decomposition + English stemming
2. **Search**: Hybrid BM25 (text weight 0.3) + TF-IDF cosine similarity (vector weight 0.7)
3. **Injection**: Top results are prepended to the system prompt as context

## What Gets Indexed

| Source | Auto-indexed | Tool |
|--------|-------------|------|
| Memory files (`~/SalmAlm/memory/`) | ✅ | `memory_write` |
| Notes | ✅ | `note` |
| Saved links | ✅ | `save_link` |
| Workspace files | On demand | `file_index` |
| Session transcripts | Optional | Config toggle |

## Configuration

Edit `~/SalmAlm/rag.json`:

```json
{
  "hybrid": {
    "enabled": true,
    "vectorWeight": 0.7,
    "textWeight": 0.3
  },
  "sessionIndexing": {
    "enabled": false,
    "retentionDays": 30
  },
  "chunkSize": 5,
  "chunkOverlap": 2,
  "reindexInterval": 120
}
```

## Korean Language Support

SalmAlm's RAG has first-class Korean support:

- **Jamo decomposition** — decomposes Hangul into consonants/vowels for fuzzy matching
- **Korean stemming** — strips common suffixes (은/는/이/가/을/를/에서/으로 etc.)
- **Synonym expansion** — 검색→찾기/탐색, 오류→에러/버그 etc.
- **Stop word filtering** — removes Korean particles and common English stop words

## Web UI

Access the RAG panel at **Settings → RAG & Knowledge** to:

- View index statistics (document count, chunk count, last indexed)
- Trigger manual reindex
- Configure hybrid search weights
- Enable/disable session indexing

## Related Tools

- `rag_search` — Direct semantic search
- `memory_write` / `memory_search` — Long-term memory CRUD
- `note` — Quick notes (auto-indexed)
- `save_link` — Save URLs with auto-fetched content
- `file_index` — Index workspace files on demand
