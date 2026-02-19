"""SalmAlm Shadow Mode — learn user style and proxy-reply when absent."""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from salmalm.crypto import log

_PROFILE_DIR = Path.home() / ".salmalm"
_PROFILE_PATH = _PROFILE_DIR / "shadow_profile.json"

# Patterns for speech style detection
_HONORIFIC_PATTERNS = {
    "해요체": re.compile(r"(해요|에요|이에요|세요|네요|죠)\b"),
    "합쇼체": re.compile(r"(합니다|입니다|습니다|됩니다)\b"),
    "해체": re.compile(r"(해|야|지|거든|잖아|인데)\b"),
    "하오체": re.compile(r"(하오|시오|구려|소)\b"),
}

_EMOJI_RE = re.compile(
    r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF"
    r"\U00002702-\U000027B0\U0000FE00-\U0000FE0F"
    r"\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
    r"\U00002600-\U000026FF\U0000200D]+",
    re.UNICODE,
)

_SPLIT_SUGGEST_PATTERNS = re.compile(
    r"(어떻게\s*생각|장단점|비교해\s*줘|찬반|pros\s*and\s*cons)", re.IGNORECASE
)

# Stop words to exclude from frequent-word analysis
_STOP_WORDS = frozenset(
    "은는이가을를에서의도와로으로만도까지부터"
    "그 이 저 것 수 더 잘 좀 안 못 다 또".split()
)


class ShadowMode:
    """Learn user messaging style and generate proxy replies when absent."""

    def __init__(self) -> None:
        self.active: bool = False
        self.confidence_threshold: int = 70
        self.suffix: str = " [Shadow Mode]"
        self.profile: Dict[str, Any] = {}
        self._load_profile()

    # ── Profile persistence ──────────────────────────────────

    def _load_profile(self) -> None:
        try:
            if _PROFILE_PATH.exists():
                self.profile = json.loads(_PROFILE_PATH.read_text("utf-8"))
                self.confidence_threshold = self.profile.get(
                    "confidence_threshold", 70
                )
        except Exception as exc:
            log.warning("shadow: failed to load profile: %s", exc)

    def _save_profile(self) -> None:
        try:
            _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            self.profile["confidence_threshold"] = self.confidence_threshold
            _PROFILE_PATH.write_text(
                json.dumps(self.profile, ensure_ascii=False, indent=2), "utf-8"
            )
        except Exception as exc:
            log.warning("shadow: failed to save profile: %s", exc)

    # ── Learning ─────────────────────────────────────────────

    def learn(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyse *user* messages and build a style profile."""
        user_msgs: List[str] = [
            m["content"]
            for m in messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ]
        if not user_msgs:
            return self.profile

        # Average message length
        lengths = [len(m) for m in user_msgs]
        avg_len = sum(lengths) / len(lengths)

        # Frequent words
        word_counter: Counter = Counter()
        for msg in user_msgs:
            tokens = re.findall(r"[가-힣a-zA-Z0-9]+", msg)
            for t in tokens:
                if t.lower() not in _STOP_WORDS and len(t) > 1:
                    word_counter[t] += 1
        frequent_words = [w for w, _ in word_counter.most_common(30)]

        # Emoji usage
        emoji_counter: Counter = Counter()
        for msg in user_msgs:
            for match in _EMOJI_RE.finditer(msg):
                emoji_counter[match.group()] += 1
        emoji_top = [e for e, _ in emoji_counter.most_common(10)]

        # Response speed pattern (gap analysis via timestamps if available)
        timestamps = [
            m.get("timestamp", 0)
            for m in messages
            if m.get("role") == "user" and m.get("timestamp")
        ]
        speed_label = "unknown"
        if len(timestamps) >= 2:
            gaps = [
                timestamps[i + 1] - timestamps[i]
                for i in range(len(timestamps) - 1)
                if timestamps[i + 1] > timestamps[i]
            ]
            if gaps:
                avg_gap = sum(gaps) / len(gaps)
                speed_label = "즉답" if avg_gap < 30 else "숙고"

        # Speech style detection
        style_scores: Dict[str, int] = {}
        for style_name, pat in _HONORIFIC_PATTERNS.items():
            count = sum(len(pat.findall(m)) for m in user_msgs)
            if count:
                style_scores[style_name] = count
        dominant_style = (
            max(style_scores, key=style_scores.get) if style_scores else "혼합"
        )

        # Sentence-start patterns
        start_counter: Counter = Counter()
        for msg in user_msgs:
            first_word = msg.strip().split()[0] if msg.strip() else ""
            if first_word:
                start_counter[first_word] += 1
        common_starts = [s for s, _ in start_counter.most_common(10)]

        self.profile = {
            "avg_message_length": round(avg_len, 1),
            "frequent_words": frequent_words,
            "emoji_top": emoji_top,
            "response_speed": speed_label,
            "speech_style": dominant_style,
            "speech_style_scores": style_scores,
            "common_starts": common_starts,
            "sample_count": len(user_msgs),
            "learned_at": time.time(),
            "confidence_threshold": self.confidence_threshold,
        }
        self._save_profile()
        return self.profile

    # ── Proxy response generation ────────────────────────────

    def build_proxy_prompt(self, incoming_message: str) -> str:
        """Build an LLM system prompt that mimics the user's style."""
        p = self.profile
        if not p:
            return ""
        lines = [
            "다음 사용자의 스타일을 모방하여 응답하시오.",
            f"- 평균 메시지 길이: {p.get('avg_message_length', '?')}자",
            f"- 말투: {p.get('speech_style', '혼합')}",
            f"- 자주 쓰는 단어: {', '.join(p.get('frequent_words', [])[:10])}",
            f"- 이모지: {' '.join(p.get('emoji_top', [])[:5])}",
            f"- 문장 시작 패턴: {', '.join(p.get('common_starts', [])[:5])}",
            f"- 응답 속도 경향: {p.get('response_speed', 'unknown')}",
            "",
            f"수신 메시지: {incoming_message}",
        ]
        return "\n".join(lines)

    def generate_proxy_response(
        self, incoming_message: str, confidence: int = 80
    ) -> str:
        """Generate a proxy response. If confidence is below threshold, return a polite away message."""
        if confidence < self.confidence_threshold:
            return f"주인이 자리를 비웠소.{self.suffix}"

        # In production this would call call_llm; here we build the prompt
        # and return a placeholder that the engine can feed to the LLM.
        prompt = self.build_proxy_prompt(incoming_message)
        if not prompt:
            return f"주인이 자리를 비웠소.{self.suffix}"

        # Return a structured dict-like marker so the caller knows to LLM-call
        return prompt  # caller should pass this to LLM and append self.suffix

    def should_proxy(self) -> bool:
        """Return True if shadow mode is active and profile exists."""
        return self.active and bool(self.profile)

    # ── Command handling ─────────────────────────────────────

    def handle_command(
        self, args: str, session_messages: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Handle /shadow subcommands. Returns response text."""
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        if sub == "on":
            self.active = True
            return "🌑 Shadow Mode 활성화 — 부재 중 대리 응답합니다."

        if sub == "off":
            self.active = False
            return "☀️ Shadow Mode 비활성화 — 복귀했습니다."

        if sub == "profile":
            if not self.profile:
                return "프로필이 없습니다. `/shadow learn`으로 학습하세요."
            return json.dumps(self.profile, ensure_ascii=False, indent=2)

        if sub == "learn":
            msgs = session_messages or []
            profile = self.learn(msgs)
            return f"학습 완료 — {profile.get('sample_count', 0)}개 메시지 분석됨."

        if sub == "test":
            if not rest:
                return "사용법: `/shadow test <메시지>`"
            prompt = self.build_proxy_prompt(rest)
            if not prompt:
                return "프로필이 없습니다. 먼저 `/shadow learn`을 실행하세요."
            return f"[테스트 프롬프트]\n{prompt}{self.suffix}"

        if sub == "confidence":
            if not rest or not rest.isdigit():
                return f"현재 확신도 임계값: {self.confidence_threshold}\n사용법: `/shadow confidence <0-100>`"
            val = max(0, min(100, int(rest)))
            self.confidence_threshold = val
            if self.profile:
                self.profile["confidence_threshold"] = val
                self._save_profile()
            return f"확신도 임계값을 {val}(으)로 설정했습니다."

        return (
            "사용법:\n"
            "  /shadow on — 활성화\n"
            "  /shadow off — 비활성화\n"
            "  /shadow profile — 프로필 조회\n"
            "  /shadow learn — 재학습\n"
            "  /shadow test <메시지> — 테스트\n"
            "  /shadow confidence <0-100> — 임계값"
        )
