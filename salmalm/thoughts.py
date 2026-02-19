"""SalmAlm Thought Stream — quick thought capture with SQLite storage and RAG integration."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import KST

THOUGHTS_DIR = Path.home() / '.salmalm'
THOUGHTS_DB = THOUGHTS_DIR / 'thoughts.db'


def _ensure_dir():
    THOUGHTS_DIR.mkdir(parents=True, exist_ok=True)


def _extract_tags(content: str) -> str:
    """Extract hashtags from content. Returns comma-separated tags."""
    tags = re.findall(r'#(\w+)', content)
    return ','.join(tags) if tags else ''


class ThoughtStream:
    """Quick thought capture with SQLite storage."""

    def __init__(self, db_path: Optional[Path] = None):
        _ensure_dir()
        self.db_path = db_path or THOUGHTS_DB
        self._ensure_db()

    def _ensure_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS thoughts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    tags TEXT DEFAULT '',
                    mood TEXT DEFAULT 'neutral',
                    created_at TEXT NOT NULL
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_thoughts_created
                ON thoughts(created_at)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_thoughts_tags
                ON thoughts(tags)
            ''')

    def add(self, content: str, mood: str = 'neutral') -> int:
        """Add a thought. Returns the thought ID."""
        tags = _extract_tags(content)
        now = datetime.now(KST).isoformat()

        with sqlite3.connect(str(self.db_path)) as conn:
            cur = conn.execute(
                'INSERT INTO thoughts (content, tags, mood, created_at) VALUES (?, ?, ?, ?)',
                (content, tags, mood, now)
            )
            thought_id = cur.lastrowid

        # Try RAG indexing
        self._index_thought(thought_id, content, tags)

        return thought_id

    def _index_thought(self, thought_id: int, content: str, tags: str):
        """Index thought in RAG engine."""
        try:
            from .rag import rag_engine
            label = f'thought:{thought_id}'
            rag_engine._index_text(label, content, time.time())
        except Exception:
            pass  # RAG indexing is optional

    def list_recent(self, n: int = 10) -> List[Dict]:
        """List most recent N thoughts."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                'SELECT * FROM thoughts ORDER BY created_at DESC LIMIT ?', (n,)
            ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str) -> List[Dict]:
        """Search thoughts using RAG or simple LIKE."""
        # Try RAG search first
        try:
            from .rag import rag_engine
            results = rag_engine.search(query)
            thought_ids = []
            for r in results:
                label = r.get('label', '')
                if label.startswith('thought:'):
                    try:
                        thought_ids.append(int(label.split(':')[1]))
                    except (ValueError, IndexError):
                        pass
            if thought_ids:
                placeholders = ','.join('?' * len(thought_ids))
                with sqlite3.connect(str(self.db_path)) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        f'SELECT * FROM thoughts WHERE id IN ({placeholders}) ORDER BY created_at DESC',
                        thought_ids
                    ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            pass

        # Fallback: simple LIKE search
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                'SELECT * FROM thoughts WHERE content LIKE ? ORDER BY created_at DESC LIMIT 20',
                (f'%{query}%',)
            ).fetchall()
        return [dict(r) for r in rows]

    def by_tag(self, tag: str) -> List[Dict]:
        """Filter thoughts by tag."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                'SELECT * FROM thoughts WHERE tags LIKE ? ORDER BY created_at DESC',
                (f'%{tag}%',)
            ).fetchall()
        return [dict(r) for r in rows]

    def timeline(self, date_str: Optional[str] = None) -> List[Dict]:
        """Get thoughts for a specific date (YYYY-MM-DD). Defaults to today."""
        if date_str is None:
            date_str = datetime.now(KST).strftime('%Y-%m-%d')

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM thoughts WHERE created_at LIKE ? ORDER BY created_at ASC",
                (f'{date_str}%',)
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        """Get thought statistics."""
        with sqlite3.connect(str(self.db_path)) as conn:
            total = conn.execute('SELECT COUNT(*) FROM thoughts').fetchone()[0]

            # Weekly count
            week_ago = (datetime.now(KST) - timedelta(days=7)).isoformat()
            weekly = conn.execute(
                'SELECT COUNT(*) FROM thoughts WHERE created_at >= ?', (week_ago,)
            ).fetchone()[0]

            # Tag frequency
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT tags FROM thoughts WHERE tags != ""').fetchall()

        tag_counter = {}
        for r in rows:
            for tag in dict(r)['tags'].split(','):
                tag = tag.strip()
                if tag:
                    tag_counter[tag] = tag_counter.get(tag, 0) + 1

        # Sort tags by frequency
        top_tags = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            'total': total,
            'weekly': weekly,
            'top_tags': top_tags,
        }

    def export_markdown(self) -> str:
        """Export all thoughts as Markdown."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                'SELECT * FROM thoughts ORDER BY created_at ASC'
            ).fetchall()

        if not rows:
            return '# Thought Stream\n\nNo thoughts recorded yet.'

        lines = ['# Thought Stream\n']
        current_date = ''
        for r in rows:
            d = dict(r)
            dt_str = d['created_at'][:10]
            if dt_str != current_date:
                current_date = dt_str
                lines.append(f'\n## {current_date}\n')

            time_str = d['created_at'][11:16] if len(d['created_at']) > 16 else ''
            tags = f' `{d["tags"]}`' if d['tags'] else ''
            mood_emoji = {'happy': '😊', 'sad': '😢', 'angry': '😠', 'anxious': '😰',
                         'excited': '🎉', 'tired': '😴', 'frustrated': '😤'}.get(d['mood'], '')
            lines.append(f'- **{time_str}** {mood_emoji} {d["content"]}{tags}')

        return '\n'.join(lines)

    def delete(self, thought_id: int) -> bool:
        """Delete a thought by ID."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cur = conn.execute('DELETE FROM thoughts WHERE id = ?', (thought_id,))
            return cur.rowcount > 0


def _format_thoughts(thoughts: List[Dict], title: str = '') -> str:
    """Format thought list for display."""
    if not thoughts:
        return '💭 기록된 생각이 없습니다.'

    lines = []
    if title:
        lines.append(title)
    for t in thoughts:
        dt = t['created_at'][:16] if len(t['created_at']) > 16 else t['created_at']
        tags = f' [{t["tags"]}]' if t.get('tags') else ''
        mood_emoji = {'happy': '😊', 'sad': '😢', 'angry': '😠', 'anxious': '😰',
                     'excited': '🎉', 'tired': '😴', 'frustrated': '😤'}.get(t.get('mood', ''), '')
        lines.append(f'#{t["id"]} {dt} {mood_emoji} {t["content"]}{tags}')
    return '\n'.join(lines)


def _format_stats(s: Dict) -> str:
    """Format stats for display."""
    lines = [
        '📊 **Thought Stats**',
        f'• 총 생각: {s["total"]}개',
        f'• 이번 주: {s["weekly"]}개',
    ]
    if s['top_tags']:
        tags_str = ', '.join(f'#{t}({c})' for t, c in s['top_tags'])
        lines.append(f'• 인기 태그: {tags_str}')
    return '\n'.join(lines)


# Singleton
thought_stream = ThoughtStream()
