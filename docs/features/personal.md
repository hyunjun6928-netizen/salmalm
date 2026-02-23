# Personal Assistant Features

SalmAlm is designed as a personal AI gateway — a single-user assistant with tools for everyday life management.

## Expense Tracking

Track daily expenses with automatic categorization:

```
"커피 5500원" → Category: food, Amount: 5500 KRW
```

- Daily/weekly/monthly summaries
- Category breakdown
- Budget alerts
- Export to JSON

**Tool**: `expense`

## Habit Tracking

Monitor daily habits and streaks:

- Check-in / check-out tracking
- Streak counting
- Weekly completion rates
- Multiple habit support

**Tool**: `habit`

## Link Saving

Save articles and URLs for later:

- Auto-fetches page title
- Extracts text content for RAG indexing
- Tag-based organization
- Full-text search across saved links

**Tool**: `save_link`

## Note Taking

Quick notes with full-text search:

```
/note Meeting notes: discussed Q1 roadmap...
```

- Auto-indexed for RAG retrieval
- Date-stamped
- Searchable via `rag_search`

**Tool**: `note`

## Reminders

Natural language reminders in Korean and English:

```
"30분 후 알려줘"     → 30 minutes from now
"내일 오전 9시"       → Tomorrow 9:00 AM
"in 2 hours"         → 2 hours from now
"next friday at 3pm" → Next Friday 15:00
```

- Cron-based scheduling
- Auto-disable after 5 consecutive failures
- Web notification support

**Tool**: `reminder`

## RSS Reader

Subscribe to and read RSS feeds:

```
/rss subscribe https://example.com/feed
/rss fetch
/rss list
```

- Multi-feed aggregation
- Article count limiting
- Feed management (subscribe/unsubscribe)

**Tool**: `rss_reader`

## Journal

Private journaling with mood tracking:

- Auto mood detection from text
- Date-organized entries
- Searchable via RAG

**Tool**: `journal`

## Weather

Quick weather checks:

```
"서울 날씨" → Current conditions + 3-day forecast
```

**Tool**: `weather`

## QR Code Generation

Generate QR codes from text or URLs:

```
"QR코드 만들어줘: https://example.com"
```

- SVG output (no external dependencies)
- Configurable size and error correction

**Tool**: `qr_code`

## Translation

Real-time translation between languages:

```
"이거 영어로 번역해줘: 안녕하세요"
```

Uses the configured LLM for high-quality translation.

**Tool**: `translate`
