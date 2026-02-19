"""SalmAlm Self-Evolving Prompt — learns user preferences from conversation patterns."""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import KST

EVOLUTION_DIR = Path.home() / '.salmalm'
EVOLUTION_FILE = EVOLUTION_DIR / 'evolution.json'
EVOLUTION_HISTORY_FILE = EVOLUTION_DIR / 'evolution_history.json'

# How many conversations between auto-evolution suggestions
EVOLVE_INTERVAL = 20
MAX_AUTO_RULES = 20


def _ensure_dir():
    EVOLUTION_DIR.mkdir(parents=True, exist_ok=True)


# ── Korean character detection ──
_KR_RE = re.compile(r'[\uac00-\ud7af\u3130-\u318f]')
_EN_RE = re.compile(r'[a-zA-Z]')

# ── Topic keywords ──
_TOPIC_KEYWORDS = {
    'coding': ['코드', 'code', 'python', 'javascript', 'function', 'class', 'bug', 'error',
               'debug', '함수', '변수', 'variable', 'api', 'git', 'deploy', '배포'],
    'writing': ['글', 'write', 'essay', '작문', '문장', 'blog', '블로그', 'article', '기사'],
    'math': ['수학', 'math', 'calculate', '계산', 'equation', '방정식', 'formula'],
    'language': ['번역', 'translate', 'grammar', '문법', 'english', '영어', '한국어'],
    'work': ['업무', 'work', 'meeting', '회의', 'project', '프로젝트', 'deadline', '마감'],
    'personal': ['기분', 'feel', '감정', 'mood', '일상', 'daily', 'life', '생활'],
    'learning': ['배우', 'learn', 'study', '공부', 'tutorial', '강의', 'course'],
    'system': ['서버', 'server', 'docker', 'linux', 'ssh', 'deploy', 'infra', '인프라'],
}

# ── Feedback signals ──
_POSITIVE_SIGNALS = ['고마워', '감사', 'thanks', 'thank', 'perfect', '완벽', 'great', '좋아',
                     '훌륭', 'awesome', 'nice', '잘했', 'good', '맞아', 'exactly', '정확']
_NEGATIVE_SIGNALS = ['아니', 'no', 'wrong', '틀렸', '잘못', 'bad', '별로', '너무 길',
                     'too long', 'too short', '짧게', '길게', '다시', 'again', 'retry',
                     '이해 못', "don't understand", '복잡', 'complicated']


class PatternAnalyzer:
    """Analyzes conversation patterns using pure Python heuristics."""

    @staticmethod
    def analyze_length_preference(messages: List[Dict]) -> str:
        """Analyze if user prefers concise or detailed responses.
        
        Looks at user message lengths and feedback signals about length.
        Returns 'concise', 'detailed', or 'mixed'.
        """
        if not messages:
            return 'mixed'

        user_msgs = [m for m in messages if m.get('role') == 'user']
        if not user_msgs:
            return 'mixed'

        lengths = []
        for m in user_msgs:
            content = m.get('content', '')
            if isinstance(content, list):
                content = ' '.join(b.get('text', '') for b in content if isinstance(b, dict))
            lengths.append(len(str(content)))

        avg_len = sum(lengths) / len(lengths) if lengths else 0

        # Check for explicit length feedback
        short_signals = 0
        long_signals = 0
        for m in user_msgs:
            text = str(m.get('content', '')).lower()
            if any(s in text for s in ['짧게', 'short', 'brief', '간단히', 'concise', '요약']):
                short_signals += 1
            if any(s in text for s in ['자세히', 'detail', 'elaborate', '길게', 'explain more', '더 설명']):
                long_signals += 1

        if short_signals > long_signals and short_signals >= 2:
            return 'concise'
        if long_signals > short_signals and long_signals >= 2:
            return 'detailed'
        if avg_len < 30:
            return 'concise'
        if avg_len > 150:
            return 'detailed'
        return 'mixed'

    @staticmethod
    def analyze_time_patterns(messages: List[Dict]) -> Dict[str, str]:
        """Analyze conversation tone by time of day.
        
        Returns dict like {hour_range: mood_tendency}.
        """
        time_moods: Dict[str, List[str]] = {
            'dawn': [],      # 0-6
            'morning': [],   # 7-11
            'afternoon': [], # 12-17
            'evening': [],   # 18-23
        }

        for m in messages:
            ts = m.get('timestamp')
            if not ts:
                continue
            try:
                if isinstance(ts, (int, float)):
                    dt = datetime.fromtimestamp(ts, tz=KST)
                else:
                    dt = datetime.fromisoformat(str(ts))
                h = dt.hour
                text = str(m.get('content', '')).lower()

                if h < 7:
                    period = 'dawn'
                elif h < 12:
                    period = 'morning'
                elif h < 18:
                    period = 'afternoon'
                else:
                    period = 'evening'

                # Simple mood heuristic
                emotional_words = ['ㅠ', '힘들', 'tired', 'sad', '감성', '그리워']
                work_words = ['코드', 'code', 'bug', '업무', 'work', 'deploy', '서버']
                if any(w in text for w in emotional_words):
                    time_moods[period].append('emotional')
                elif any(w in text for w in work_words):
                    time_moods[period].append('business')
                else:
                    time_moods[period].append('neutral')
            except (ValueError, TypeError, OSError):
                continue

        result = {}
        for period, moods in time_moods.items():
            if moods:
                c = Counter(moods)
                result[period] = c.most_common(1)[0][0]
        return result

    @staticmethod
    def analyze_topic_frequency(messages: List[Dict]) -> Counter:
        """Count topic categories from messages."""
        topic_counts: Counter = Counter()
        for m in messages:
            if m.get('role') != 'user':
                continue
            text = str(m.get('content', '')).lower()
            for topic, keywords in _TOPIC_KEYWORDS.items():
                if any(kw in text for kw in keywords):
                    topic_counts[topic] += 1
        return topic_counts

    @staticmethod
    def analyze_language_ratio(messages: List[Dict]) -> float:
        """Analyze Korean vs English ratio. 0.0=all EN, 1.0=all KR."""
        kr_chars = 0
        en_chars = 0
        for m in messages:
            if m.get('role') != 'user':
                continue
            text = str(m.get('content', ''))
            kr_chars += len(_KR_RE.findall(text))
            en_chars += len(_EN_RE.findall(text))

        total = kr_chars + en_chars
        if total == 0:
            return 0.5
        return kr_chars / total

    @staticmethod
    def analyze_feedback_signals(messages: List[Dict]) -> Dict[str, int]:
        """Detect positive/negative feedback patterns."""
        positive = 0
        negative = 0
        for m in messages:
            if m.get('role') != 'user':
                continue
            text = str(m.get('content', '')).lower()
            if any(s in text for s in _POSITIVE_SIGNALS):
                positive += 1
            if any(s in text for s in _NEGATIVE_SIGNALS):
                negative += 1
        return {'positive': positive, 'negative': negative}

    @staticmethod
    def analyze_code_comment_preference(messages: List[Dict]) -> Optional[str]:
        """Detect if user prefers or dislikes code comments.
        
        Returns 'prefer', 'dislike', or None.
        """
        prefer = 0
        dislike = 0
        for m in messages:
            if m.get('role') != 'user':
                continue
            text = str(m.get('content', '')).lower()
            if any(s in text for s in ['주석 넣', '주석 추가', 'add comment', 'with comment', '주석 포함']):
                prefer += 1
            if any(s in text for s in ['주석 빼', '주석 없이', 'no comment', 'without comment', '주석 제거']):
                dislike += 1
        if prefer > dislike and prefer >= 2:
            return 'prefer'
        if dislike > prefer and dislike >= 2:
            return 'dislike'
        return None


class PromptEvolver:
    """Learns user preferences and evolves the system prompt over time."""

    def __init__(self):
        _ensure_dir()
        self.analyzer = PatternAnalyzer()
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if EVOLUTION_FILE.exists():
            try:
                return json.loads(EVOLUTION_FILE.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                pass
        return {
            'conversation_count': 0,
            'preferences': {},
            'auto_rules': [],
            'last_analysis': None,
            'created_at': datetime.now(KST).isoformat(),
        }

    def _save_state(self):
        _ensure_dir()
        EVOLUTION_FILE.write_text(json.dumps(self.state, ensure_ascii=False, indent=2),
                                   encoding='utf-8')

    def record_conversation(self, messages: List[Dict]):
        """Record a conversation for pattern analysis."""
        self.state['conversation_count'] = self.state.get('conversation_count', 0) + 1
        self._analyze_and_update(messages)
        self._save_state()

    def _analyze_and_update(self, messages: List[Dict]):
        """Run pattern analysis and update preferences."""
        prefs = self.state.get('preferences', {})

        prefs['length_preference'] = self.analyzer.analyze_length_preference(messages)
        prefs['time_patterns'] = self.analyzer.analyze_time_patterns(messages)

        topics = self.analyzer.analyze_topic_frequency(messages)
        # Merge with existing
        existing_topics = prefs.get('topic_frequency', {})
        for topic, count in topics.items():
            existing_topics[topic] = existing_topics.get(topic, 0) + count
        prefs['topic_frequency'] = existing_topics

        prefs['language_ratio'] = self.analyzer.analyze_language_ratio(messages)
        
        feedback = self.analyzer.analyze_feedback_signals(messages)
        existing_fb = prefs.get('feedback', {'positive': 0, 'negative': 0})
        prefs['feedback'] = {
            'positive': existing_fb.get('positive', 0) + feedback['positive'],
            'negative': existing_fb.get('negative', 0) + feedback['negative'],
        }

        comment_pref = self.analyzer.analyze_code_comment_preference(messages)
        if comment_pref:
            prefs['code_comments'] = comment_pref

        self.state['preferences'] = prefs
        self.state['last_analysis'] = datetime.now(KST).isoformat()

    def should_suggest_evolution(self) -> bool:
        """Check if we should suggest evolving SOUL.md."""
        count = self.state.get('conversation_count', 0)
        return count > 0 and count % EVOLVE_INTERVAL == 0

    def generate_rules(self) -> List[str]:
        """Generate auto-evolution rules from learned preferences."""
        prefs = self.state.get('preferences', {})
        rules = []

        lp = prefs.get('length_preference')
        if lp == 'concise':
            rules.append('사용자는 간결한 응답을 선호함')
        elif lp == 'detailed':
            rules.append('사용자는 상세한 응답을 선호함')

        cp = prefs.get('code_comments')
        if cp == 'prefer':
            rules.append('사용자는 코드에 주석을 선호함')
        elif cp == 'dislike':
            rules.append('사용자는 코드 주석을 선호하지 않음')

        lr = prefs.get('language_ratio', 0.5)
        if lr > 0.8:
            rules.append('사용자는 주로 한국어로 소통함 — 한국어로 응답할 것')
        elif lr < 0.2:
            rules.append('사용자는 주로 영어로 소통함 — 영어로 응답할 것')

        topics = prefs.get('topic_frequency', {})
        if topics:
            top = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:3]
            for topic, count in top:
                if count >= 5:
                    rules.append(f'사용자가 자주 묻는 주제: {topic}')

        tp = prefs.get('time_patterns', {})
        if tp.get('dawn') == 'emotional':
            rules.append('새벽 시간대에는 감성적인 톤으로 응답할 것')
        if tp.get('afternoon') == 'business':
            rules.append('오후 시간대에는 업무적인 톤으로 응답할 것')

        return rules

    def apply_to_soul(self, soul_path: Path) -> str:
        """Apply auto-evolved rules to SOUL.md. Returns status message."""
        rules = self.generate_rules()
        if not rules:
            return '📊 아직 충분한 패턴이 감지되지 않았습니다.'

        today = datetime.now(KST).strftime('%Y-%m-%d')

        # Read existing SOUL.md
        content = ''
        if soul_path.exists():
            content = soul_path.read_text(encoding='utf-8')

        # Remove old auto-evolved section
        content = re.sub(
            r'\n*<!-- auto-evolved-begin -->.*?<!-- auto-evolved-end -->\n*',
            '\n', content, flags=re.DOTALL
        )

        # Build new section
        rule_lines = []
        for r in rules[:MAX_AUTO_RULES]:
            rule_lines.append(f'<!-- auto-evolved: {today} -->\n- {r}')

        section = (
            '\n\n<!-- auto-evolved-begin -->\n'
            '## 🧬 Auto-Evolved Rules\n'
            + '\n'.join(rule_lines) +
            '\n<!-- auto-evolved-end -->\n'
        )

        content = content.rstrip() + section

        soul_path.parent.mkdir(parents=True, exist_ok=True)
        soul_path.write_text(content, encoding='utf-8')

        # Record history
        self._record_history(rules)

        self.state['auto_rules'] = rules[:MAX_AUTO_RULES]
        self._save_state()

        return f'✅ {len(rules)}개 규칙이 SOUL.md에 반영되었습니다.'

    def _record_history(self, rules: List[str]):
        history = []
        if EVOLUTION_HISTORY_FILE.exists():
            try:
                history = json.loads(EVOLUTION_HISTORY_FILE.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                pass
        history.append({
            'timestamp': datetime.now(KST).isoformat(),
            'rules': rules,
            'conversation_count': self.state.get('conversation_count', 0),
        })
        # Keep last 100 entries
        history = history[-100:]
        EVOLUTION_HISTORY_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')

    def get_status(self) -> str:
        """Return current evolution status."""
        prefs = self.state.get('preferences', {})
        count = self.state.get('conversation_count', 0)
        last = self.state.get('last_analysis', '없음')

        lines = [
            '🧬 **Self-Evolving Prompt Status**',
            f'📊 분석된 대화: {count}회',
            f'🕐 마지막 분석: {last}',
            '',
            '**학습된 선호도:**',
        ]

        lp = prefs.get('length_preference', '미감지')
        lines.append(f'• 응답 길이: {lp}')

        lr = prefs.get('language_ratio')
        if lr is not None:
            kr_pct = int(lr * 100)
            lines.append(f'• 언어 비율: 한국어 {kr_pct}% / 영어 {100 - kr_pct}%')

        cp = prefs.get('code_comments', '미감지')
        lines.append(f'• 코드 주석: {cp}')

        topics = prefs.get('topic_frequency', {})
        if topics:
            top3 = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:3]
            topic_str = ', '.join(f'{t}({c})' for t, c in top3)
            lines.append(f'• 주요 주제: {topic_str}')

        fb = prefs.get('feedback', {})
        if fb:
            lines.append(f'• 피드백: 👍{fb.get("positive", 0)} / 👎{fb.get("negative", 0)}')

        rules = self.state.get('auto_rules', [])
        if rules:
            lines.append(f'\n**자동 규칙** ({len(rules)}개):')
            for r in rules:
                lines.append(f'  - {r}')

        next_evolve = EVOLVE_INTERVAL - (count % EVOLVE_INTERVAL)
        lines.append(f'\n📈 다음 진화 제안까지: {next_evolve}회 대화')

        return '\n'.join(lines)

    def get_history(self) -> str:
        """Return evolution history."""
        if not EVOLUTION_HISTORY_FILE.exists():
            return '📜 진화 이력이 없습니다.'

        try:
            history = json.loads(EVOLUTION_HISTORY_FILE.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            return '📜 진화 이력을 읽을 수 없습니다.'

        if not history:
            return '📜 진화 이력이 없습니다.'

        lines = ['📜 **Evolution History**\n']
        for entry in history[-10:]:
            ts = entry.get('timestamp', '?')
            count = entry.get('conversation_count', '?')
            rules = entry.get('rules', [])
            lines.append(f'**{ts}** (대화 {count}회)')
            for r in rules:
                lines.append(f'  - {r}')
            lines.append('')

        return '\n'.join(lines)

    def reset(self) -> str:
        """Reset all evolution data."""
        self.state = {
            'conversation_count': 0,
            'preferences': {},
            'auto_rules': [],
            'last_analysis': None,
            'created_at': datetime.now(KST).isoformat(),
        }
        self._save_state()
        return '🔄 진화 데이터가 초기화되었습니다.'


# Singleton
prompt_evolver = PromptEvolver()
