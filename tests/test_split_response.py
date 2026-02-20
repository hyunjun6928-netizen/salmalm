"""Tests for SalmAlm A/B Split Response."""
import asyncio

import pytest

from salmalm.features.split_response import SplitResponder, SPLIT_MODES, _AUTO_DETECT_RE


@pytest.fixture
def splitter():
    return SplitResponder()


@pytest.fixture
def splitter_with_llm():
    async def mock_llm(system_prompt, user_message):
        return f"[response for: {user_message[:20]}]"
    return SplitResponder(llm_fn=mock_llm)


def test_available_modes(splitter):
    modes = splitter.available_modes()
    assert "conservative_bold" in modes
    assert "custom" in modes
    assert len(modes) >= 5


def test_should_suggest_split():
    assert SplitResponder.should_suggest_split("이거 어떻게 생각해?")
    assert SplitResponder.should_suggest_split("장단점을 알려줘")
    assert SplitResponder.should_suggest_split("A와 B를 비교해줘")
    assert not SplitResponder.should_suggest_split("오늘 날씨 어때?")


def test_generate_placeholder(splitter):
    result = asyncio.run(splitter.generate("테스트 질문", "conservative_bold"))
    assert result["mode"] == "conservative_bold"
    assert result["response_a"]["label"] == "보수적"
    assert result["response_b"]["label"] == "과감한"
    assert "placeholder" in result["response_a"]["content"]


def test_generate_with_llm(splitter_with_llm):
    result = asyncio.run(splitter_with_llm.generate("AI의 미래는?", "pros_cons"))
    assert result["response_a"]["label"] == "찬성"
    assert "response for:" in result["response_a"]["content"]
    assert "response for:" in result["response_b"]["content"]


def test_format_result(splitter):
    result = asyncio.run(splitter.generate("test", "short_long"))
    formatted = splitter.format_result(result)
    assert "📌 관점 A" in formatted
    assert "📌 관점 B" in formatted
    assert "짧은" in formatted
    assert "긴" in formatted


def test_format_buttons(splitter):
    buttons = splitter.format_buttons()
    assert len(buttons) == 3
    assert buttons[0]["text"] == "A로 계속"
    assert buttons[2]["callback"] == "split_merge"


def test_suggest_button(splitter):
    btn = splitter.suggest_button()
    assert "🔀" in btn["text"]


def test_merge(splitter_with_llm):
    result = asyncio.run(splitter_with_llm.generate("test q", "conservative_bold"))
    merged = asyncio.run(splitter_with_llm.merge(result))
    assert isinstance(merged, str)
    assert len(merged) > 0


def test_merge_no_llm(splitter):
    result = asyncio.run(splitter.generate("test", "conservative_bold"))
    merged = asyncio.run(splitter.merge(result))
    assert "[종합]" in merged


def test_continue_with(splitter_with_llm):
    result = asyncio.run(splitter_with_llm.generate("original", "technical_simple"))
    follow = asyncio.run(splitter_with_llm.continue_with(result, "a", "더 자세히"))
    assert isinstance(follow, str)
    follow_b = asyncio.run(splitter_with_llm.continue_with(result, "b", "예시 줘"))
    assert isinstance(follow_b, str)


def test_custom_mode(splitter):
    splitter.set_custom("낙관", "비관", "낙관적으로", "비관적으로")
    result = asyncio.run(splitter.generate("경제 전망", "custom"))
    assert result["response_a"]["label"] == "낙관"
    assert result["response_b"]["label"] == "비관"


def test_command_modes(splitter):
    result = splitter.handle_command("modes")
    assert "conservative_bold" in result
    assert "보수적" in result


def test_command_help(splitter):
    result = splitter.handle_command("")
    assert "/split" in result


def test_all_modes_have_config():
    for mode_name, config in SPLIT_MODES.items():
        assert len(config) == 4
        label_a, label_b, prompt_a, prompt_b = config
        assert label_a and label_b and prompt_a and prompt_b
