"""SalmAlm A/B Split Response — dual-perspective answers."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable, Dict, List, Optional, Tuple


# Split modes with (label_a, label_b, system_prompt_a, system_prompt_b)
SPLIT_MODES: Dict[str, Tuple[str, str, str, str]] = {
    "conservative_bold": (
        "보수적",
        "과감한",
        "가능한 한 보수적이고 신중한 관점에서 답변하시오. 리스크를 강조하고 안전한 선택을 추천하시오.",
        "과감하고 도전적인 관점에서 답변하시오. 기회를 강조하고 혁신적 선택을 추천하시오.",
    ),
    "short_long": (
        "짧은",
        "긴",
        "가능한 한 짧고 핵심만 답변하시오. 3문장 이내.",
        "상세하고 포괄적으로 답변하시오. 배경, 예시, 근거를 모두 포함하시오.",
    ),
    "technical_simple": (
        "기술적",
        "쉬운 설명",
        "전문 용어를 사용하여 기술적으로 정확하게 답변하시오.",
        "전문 지식이 없는 사람도 이해할 수 있도록 쉽게 설명하시오. 비유와 예시를 활용하시오.",
    ),
    "pros_cons": (
        "찬성",
        "반대",
        "이 주제에 대해 찬성하는 입장에서 강력한 논거를 제시하시오.",
        "이 주제에 대해 반대하는 입장에서 강력한 논거를 제시하시오.",
    ),
}

# Patterns that suggest a question might benefit from split response
_AUTO_DETECT_RE = re.compile(
    r"(어떻게\s*생각|장단점|비교해\s*줘|찬반|pros\s*and\s*cons|양면|두\s*가지)",
    re.IGNORECASE,
)


class SplitResponder:
    """Generate dual-perspective responses for a single question."""

    def __init__(self, llm_fn: Optional[Callable] = None) -> None:
        """
        Args:
            llm_fn: async callable(system_prompt, user_message) -> str
                     If None, a stub is used (for testing).
        """
        self._llm_fn = llm_fn
        self._last_question: str = ""
        self._last_mode: str = ""
        self._custom_perspectives: Tuple[str, str, str, str] = ("A", "B", "", "")

    @staticmethod
    def available_modes() -> List[str]:
        return list(SPLIT_MODES.keys()) + ["custom"]

    @staticmethod
    def should_suggest_split(text: str) -> bool:
        """Check if the text contains patterns suggesting a split response."""
        return bool(_AUTO_DETECT_RE.search(text))

    def set_custom(self, label_a: str, label_b: str, prompt_a: str, prompt_b: str) -> None:
        self._custom_perspectives = (label_a, label_b, prompt_a, prompt_b)

    def _get_mode_config(self, mode: str) -> Tuple[str, str, str, str]:
        if mode == "custom":
            return self._custom_perspectives
        return SPLIT_MODES.get(mode, SPLIT_MODES["conservative_bold"])

    async def generate(self, question: str, mode: str = "conservative_bold") -> Dict[str, Any]:
        """Generate split responses. Returns dict with responses and metadata."""
        self._last_question = question
        self._last_mode = mode
        label_a, label_b, prompt_a, prompt_b = self._get_mode_config(mode)

        if self._llm_fn:
            resp_a, resp_b = await asyncio.gather(
                self._llm_fn(prompt_a, question),
                self._llm_fn(prompt_b, question),
            )
        else:
            resp_a = f"[{label_a} 관점 응답 placeholder]"
            resp_b = f"[{label_b} 관점 응답 placeholder]"

        return {
            "mode": mode,
            "question": question,
            "response_a": {"label": label_a, "content": resp_a},
            "response_b": {"label": label_b, "content": resp_b},
        }

    def format_result(self, result: Dict[str, Any]) -> str:
        """Format split result for display."""
        a = result["response_a"]
        b = result["response_b"]
        return f"📌 관점 A ({a['label']}):\n{a['content']}\n\n📌 관점 B ({b['label']}):\n{b['content']}"

    def format_buttons(self) -> List[Dict[str, str]]:
        """Return inline button descriptors."""
        return [
            {"text": "A로 계속", "callback": "split_continue_a"},
            {"text": "B로 계속", "callback": "split_continue_b"},
            {"text": "합치기", "callback": "split_merge"},
        ]

    def suggest_button(self) -> Dict[str, str]:
        """Return a 'suggest split' inline button descriptor."""
        return {"text": "🔀 두 관점으로 보기", "callback": "split_suggest"}

    async def merge(self, result: Dict[str, Any]) -> str:
        """Merge two perspectives into a combined response."""
        a_content = result["response_a"]["content"]
        b_content = result["response_b"]["content"]
        question = result.get("question", "")

        if self._llm_fn:
            merge_prompt = (
                f"다음 두 관점을 종합하여 균형 잡힌 하나의 응답을 생성하시오.\n관점 A: {a_content}\n관점 B: {b_content}"
            )
            return await self._llm_fn(merge_prompt, question)
        return f"[종합] {a_content} + {b_content}"

    async def continue_with(self, result: Dict[str, Any], choice: str, follow_up: str) -> str:
        """Continue conversation with the chosen perspective."""
        key = "response_a" if choice == "a" else "response_b"
        perspective = result[key]
        label = perspective["label"]
        prev = perspective["content"]

        if self._llm_fn:
            prompt = (
                f"이전에 '{label}' 관점에서 다음과 같이 답변했다:\n{prev}\n\n같은 관점을 유지하여 후속 질문에 답하시오."
            )
            return await self._llm_fn(prompt, follow_up)
        return f"[{label} 관점 계속] {follow_up}"

    # ── Command handling ─────────────────────────────────────

    def handle_command(self, args: str) -> str:
        """Handle /split subcommands (sync wrapper). Returns text."""
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        if sub == "modes":
            lines = ["사용 가능한 모드:"]
            for name in self.available_modes():
                if name in SPLIT_MODES:
                    la, lb, _, _ = SPLIT_MODES[name]
                    lines.append(f"  • {name} — {la} vs {lb}")
                else:
                    lines.append(f"  • {name} — 사용자 지정")
            return "\n".join(lines)

        if not sub and self._last_question:
            # Re-split last question
            mode = self._last_mode or "conservative_bold"
            result = (
                asyncio.get_event_loop().run_until_complete(self.generate(self._last_question, mode))
                if self._last_question
                else {}
            )
            if result:
                return self.format_result(result)
            return "이전 질문이 없습니다."

        if sub and sub in (list(SPLIT_MODES.keys()) + ["custom"]):
            if not rest:
                return f"사용법: `/split {sub} <질문>`"
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        result = pool.submit(asyncio.run, self.generate(rest, sub)).result()
                else:
                    result = loop.run_until_complete(self.generate(rest, sub))
            except RuntimeError:
                result = asyncio.run(self.generate(rest, sub))
            return self.format_result(result)

        if sub:
            # Treat entire args as question with default mode
            question = args.strip()
            try:
                result = asyncio.run(self.generate(question))
            except RuntimeError:
                loop = asyncio.get_event_loop()
                result = loop.run_until_complete(self.generate(question))
            return self.format_result(result)

        return "사용법:\n  /split <모드> <질문> — 분할 응답\n  /split — 마지막 질문 재분할\n  /split modes — 모드 목록"
