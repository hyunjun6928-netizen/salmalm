"""SalmAlm Mood-Aware Response — detects user emotion and adjusts response tone."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Tuple

from salmalm.constants import KST, DATA_DIR
MOOD_DIR = DATA_DIR
MOOD_CONFIG_FILE = MOOD_DIR / "mood.json"
MOOD_HISTORY_FILE = MOOD_DIR / "mood_history.json"

# ── Mood categories ──
MOODS = ("happy", "sad", "angry", "anxious", "excited", "neutral", "tired", "frustrated")

# ── Korean emotion keywords ──
_KR_MOOD_KEYWORDS: Dict[str, List[str]] = {
    "happy": [
        "ㅋㅋ",
        "ㅎㅎ",
        "^^",
        "기쁘",
        "좋아",
        "행복",
        "최고",
        "대박",
        "신나",
        "굿",
        "잘됐",
        "감사",
        "고마워",
        "사랑",
        "♡",
        "뿌듯",
        "기분 좋",
    ],
    "sad": [
        "ㅠㅠ",
        "ㅜㅜ",
        "슬프",
        "슬퍼",
        "우울",
        "그리워",
        "외로",
        "눈물",
        "아프",
        "힘들",
        "지치",
        "괴로",
        "속상",
        "서글",
        "안타까",
    ],
    "angry": [
        "ㅡㅡ",
        "짜증",
        "화나",
        "열받",
        "미치",
        "빡치",
        "싫어",
        "짜증나",
        "화남",
        "분노",
        "어이없",
        "황당",
        "개빡",
    ],
    "anxious": ["걱정", "불안", "초조", "떨리", "긴장", "무서", "두려", "어떡", "어쩌지", "어떻게", "망할", "큰일"],
    "excited": ["!!!", "와아", "대박", "미쳤", "오오", "헐", "우와", "캬", "신난다", "기대", "두근", "설레"],
    "tired": ["피곤", "졸려", "힘들", "지친", "녹초", "기력", "잠와", "쉬고싶", "zzz", "으으", "아 진짜"],
    "frustrated": ["안돼", "안되", "왜이러", "답답", "막힘", "모르겠", "이해안", "포기", "못하겠", "도대체", "제발"],
}

# ── English emotion keywords ──
_EN_MOOD_KEYWORDS: Dict[str, List[str]] = {
    "happy": [
        "happy",
        "great",
        "awesome",
        "love",
        "wonderful",
        "fantastic",
        "joy",
        "amazing",
        "excellent",
        "perfect",
        "glad",
        "pleased",
        "yay",
        "woohoo",
    ],
    "sad": [
        "sad",
        "depressed",
        "down",
        "lonely",
        "heartbroken",
        "miss",
        "cry",
        "tears",
        "grief",
        "sorrow",
        "unhappy",
        "miserable",
    ],
    "angry": ["angry", "furious", "mad", "hate", "pissed", "annoyed", "rage", "outraged", "infuriating", "wtf", "damn"],
    "anxious": [
        "anxious",
        "worried",
        "nervous",
        "scared",
        "afraid",
        "panic",
        "stress",
        "stressed",
        "overwhelm",
        "dread",
        "fear",
    ],
    "excited": ["excited", "thrilled", "pumped", "stoked", "omg", "cant wait", "hyped", "lets go", "woo"],
    "tired": ["tired", "exhausted", "sleepy", "drained", "burned out", "burnout", "fatigue", "worn out", "ugh"],
    "frustrated": [
        "frustrated",
        "stuck",
        "confused",
        "don't understand",
        "doesn't work",
        "broken",
        "why",
        "impossible",
        "give up",
        "can't figure",
    ],
}

# ── Emoji mood mapping ──
_EMOJI_MOODS: Dict[str, str] = {
    "😀": "happy",
    "😃": "happy",
    "😄": "happy",
    "😁": "happy",
    "😆": "happy",
    "🥰": "happy",
    "😍": "happy",
    "🤩": "happy",
    "❤️": "happy",
    "💕": "happy",
    "😢": "sad",
    "😭": "sad",
    "😿": "sad",
    "💔": "sad",
    "🥺": "sad",
    "😠": "angry",
    "😡": "angry",
    "🤬": "angry",
    "💢": "angry",
    "😰": "anxious",
    "😨": "anxious",
    "😱": "anxious",
    "😥": "anxious",
    "🎉": "excited",
    "🥳": "excited",
    "🔥": "excited",
    "🚀": "excited",
    "✨": "excited",
    "😴": "tired",
    "🥱": "tired",
    "😩": "tired",
    "😫": "tired",
    "😤": "frustrated",
    "🤦": "frustrated",
    "😒": "frustrated",
}

# ── Tone map ──
MOOD_TONE_MAP: Dict[str, Dict[str, str]] = {
    "angry": {"style": "calm_empathetic", "inject": "차분하고 공감적으로 응답하시오"},
    "sad": {"style": "warm_supportive", "inject": "따뜻하고 지지적으로 응답하시오"},
    "anxious": {"style": "reassuring", "inject": "안심시키는 톤으로 응답하시오"},
    "excited": {"style": "enthusiastic", "inject": "함께 신나는 톤으로 응답하시오"},
    "tired": {"style": "gentle_brief", "inject": "부드럽고 간결하게 응답하시오"},
    "frustrated": {"style": "solution_focused", "inject": "해결 중심으로 빠르게 응답하시오"},
    "happy": {"style": "warm_positive", "inject": "밝고 긍정적인 톤으로 응답하시오"},
    "neutral": {"style": "balanced", "inject": ""},
}


def _ensure_dir():
    MOOD_DIR.mkdir(parents=True, exist_ok=True)


class MoodDetector:
    """Detects user mood from text using keywords, patterns, and emoji."""

    def __init__(self):
        _ensure_dir()
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        from salmalm.config_manager import ConfigManager

        return ConfigManager.load("mood", defaults={"enabled": True, "sensitivity": "normal"})

    def _save_config(self):
        from salmalm.config_manager import ConfigManager

        _ensure_dir()
        ConfigManager.save("mood", self.config)

    @property
    def enabled(self) -> bool:
        return self.config.get("enabled", True)

    @property
    def sensitivity(self) -> str:
        return self.config.get("sensitivity", "normal")

    def set_mode(self, mode: str) -> str:
        """Set mood detection mode: on, off, sensitive."""
        if mode == "off":
            self.config["enabled"] = False
            self._save_config()
            return "😶 감정 감지가 비활성화되었습니다."
        elif mode == "on":
            self.config["enabled"] = True
            self.config["sensitivity"] = "normal"
            self._save_config()
            return "😊 감정 감지가 활성화되었습니다. (일반 민감도)"
        elif mode == "sensitive":
            self.config["enabled"] = True
            self.config["sensitivity"] = "sensitive"
            self._save_config()
            return "🔍 감정 감지가 높은 민감도로 설정되었습니다."
        return "❌ Usage: /mood off|on|sensitive"

    def detect(self, text: str) -> Tuple[str, float]:
        """Detect mood from text. Returns (mood, confidence 0.0-1.0)."""
        if not self.enabled:
            return ("neutral", 0.0)

        text_lower = text.lower()
        scores: Counter = Counter()

        # Keyword matching - Korean
        for mood, keywords in _KR_MOOD_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[mood] += 1

        # Keyword matching - English
        for mood, keywords in _EN_MOOD_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[mood] += 1

        # Emoji matching
        for char in text:
            if char in _EMOJI_MOODS:
                scores[_EMOJI_MOODS[char]] += 1.5

        # Punctuation patterns
        excl_count = text.count("!")
        if excl_count >= 3:
            scores["excited"] += excl_count / 3

        ellipsis_count = text.count("...")
        if ellipsis_count >= 1:
            scores["sad"] += ellipsis_count * 0.5
            scores["anxious"] += ellipsis_count * 0.3

        question_count = text.count("?")
        if question_count >= 3:
            scores["anxious"] += question_count / 3

        # Caps ratio (for English text)
        alpha_chars = [c for c in text if c.isalpha() and ord(c) < 128]
        if len(alpha_chars) > 10:
            caps_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
            if caps_ratio > 0.7:
                scores["angry"] += 2

        # ㅋ repetition intensity
        kk_match = re.findall(r"ㅋ{2,}", text)
        for m in kk_match:
            if len(m) >= 5:
                scores["happy"] += 2
            else:
                scores["happy"] += 1

        # ㅠ repetition intensity
        yy_match = re.findall(r"[ㅠㅜ]{2,}", text)
        for m in yy_match:
            scores["sad"] += min(len(m), 4)

        # Sensitivity adjustment
        threshold = 1.0 if self.sensitivity == "sensitive" else 2.0

        if not scores:
            return ("neutral", 0.0)

        top_mood, top_score = scores.most_common(1)[0]
        if top_score < threshold:
            return ("neutral", top_score / threshold * 0.5)

        # Confidence: normalize score
        confidence = min(1.0, top_score / (threshold * 3))
        return (top_mood, confidence)

    def get_tone_injection(self, mood: str) -> str:
        """Get tone injection string for system prompt."""
        tone = MOOD_TONE_MAP.get(mood, {})
        return tone.get("inject", "")

    def record_mood(self, mood: str, confidence: float):
        """Record mood to history."""
        _ensure_dir()
        history = []
        if MOOD_HISTORY_FILE.exists():
            try:
                history = json.loads(MOOD_HISTORY_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        history.append(
            {
                "timestamp": datetime.now(KST).isoformat(),
                "mood": mood,
                "confidence": round(confidence, 2),
            }
        )

        # Keep last 1000 entries
        history = history[-1000:]
        MOOD_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_status(self, text: str = "") -> str:
        """Return current mood status."""
        mood, conf = self.detect(text) if text else ("neutral", 0.0)
        tone = MOOD_TONE_MAP.get(mood, {})

        lines = [
            "🎭 **Mood-Aware Status**",
            f"• 활성화: {'✅' if self.enabled else '❌'}",
            f"• 민감도: {self.sensitivity}",
        ]
        if text:
            lines.extend(
                [
                    f"• 감지된 감정: {mood} (신뢰도: {conf:.0%})",
                    f"• 적용 톤: {tone.get('style', 'none')}",
                ]
            )

        # Recent mood trend
        if MOOD_HISTORY_FILE.exists():
            try:
                history = json.loads(MOOD_HISTORY_FILE.read_text(encoding="utf-8"))
                recent = history[-20:]
                if recent:
                    mood_counts = Counter(e["mood"] for e in recent)
                    top3 = mood_counts.most_common(3)
                    trend = ", ".join(f"{m}({c})" for m, c in top3)
                    lines.append(f"• 최근 감정 트렌드: {trend}")
            except (json.JSONDecodeError, OSError):
                pass

        return "\n".join(lines)

    def generate_report(self, period: str = "week") -> str:
        """Generate mood report for the given period."""
        if not MOOD_HISTORY_FILE.exists():
            return "📊 감정 이력이 없습니다."

        try:
            history = json.loads(MOOD_HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return "📊 감정 이력을 읽을 수 없습니다."

        now = datetime.now(KST)
        if period == "week":
            cutoff = now - __import__("datetime").timedelta(days=7)
            label = "주간"
        else:
            cutoff = now - __import__("datetime").timedelta(days=30)
            label = "월간"

        filtered = []
        for e in history:
            try:
                ts = datetime.fromisoformat(e["timestamp"])
                if ts >= cutoff:
                    filtered.append(e)
            except (ValueError, KeyError):
                continue

        if not filtered:
            return f"📊 {label} 감정 데이터가 없습니다."

        mood_counts = Counter(e["mood"] for e in filtered)
        total = len(filtered)
        lines = [f"📊 **{label} 감정 리포트** ({total}건)\n"]
        for mood, count in mood_counts.most_common():
            pct = count / total * 100
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"{mood:12s} {bar} {pct:.0f}% ({count})")

        return "\n".join(lines)


# Singleton
mood_detector = MoodDetector()
