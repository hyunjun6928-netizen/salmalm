"""Context compaction — auto-summarize long conversations to save tokens."""

import hashlib
import json
import os
import re
import time
from typing import Callable, Dict, List, Optional, Tuple

from salmalm.constants import (
    COMPACTION_THRESHOLD,
    COMPLEX_INDICATORS,
    DATA_DIR,
    MODEL_TIERS,
    SIMPLE_QUERY_MAX_CHARS,
    TOOL_HINT_KEYWORDS,
)
from salmalm.security.crypto import log

def _persist_compaction_summary(session_id: str, summary: str) -> None:
    """Save compaction summary to DB for cross-session restoration.

    OpenClaw-style: when a session is restored after restart, the last
    compaction summary is injected so the AI retains prior context.
    """
    if not summary or not session_id:
        return
    try:
        from salmalm.core.core import _get_db; conn = _get_db()
        conn.execute("""CREATE TABLE IF NOT EXISTS compaction_summaries (
            session_id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL,
            message_count INTEGER DEFAULT 0
        )""")
        conn.execute(
            "INSERT OR REPLACE INTO compaction_summaries (session_id, summary, created_at) VALUES (?,?,?)",
            (session_id, summary[:10000], datetime.now(KST).isoformat()),
        )
        conn.commit()
    except Exception as e:
        log.warning(f"[PKG] Summary persist error: {e}")


def _restore_compaction_summary(session_id: str) -> Optional[str]:
    """Restore last compaction summary for a session (cross-session continuity)."""
    try:
        from salmalm.core.core import _get_db; conn = _get_db()
        row = conn.execute(
            "SELECT summary FROM compaction_summaries WHERE session_id=?",
            (session_id,),
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _msg_content_str(msg: dict) -> str:
    """Extract text content from a message (handles list content blocks)."""
    c = msg.get("content", "")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return str(c)


def compact_messages(
    messages: list,
    model: Optional[str] = None,
    session: Optional["Session"] = None,
    on_status: Optional[Callable] = None,
) -> list:
    """Multi-stage compaction: trim tool results → drop old tools → summarize.

    OpenClaw-quality compaction with 5 stages:
      1. Strip binary/image data from old messages
      2. Trim long tool results (keep first 500 chars)
      3. Drop old tool messages, keep user/assistant
      4. Truncate verbose old assistant messages
      5. LLM summarization of remaining old context

    Hard limits: max 100 messages, max 500K chars (≈125K tokens).
    Pre-compaction: flush memory to persistent store.
    Post-compaction: inject summary as system message, not user message.
    """
    # Empty conversation guard
    if not messages:
        return messages

    MAX_MESSAGES = 100
    MAX_CHARS = 500_000

    # OpenClaw-style: pre-compaction memory flush
    total_chars_check = sum(len(_msg_content_str(m)) for m in messages)
    if session and total_chars_check > COMPACTION_THRESHOLD * 0.8:  # noqa: F405
        try:
            memory_manager.flush_before_compaction(session)
        except Exception as e:
            log.warning(f"[MEM] Memory flush error: {e}")

    # Hard message count limit
    if len(messages) > MAX_MESSAGES:
        system_msgs = [m for m in messages if m["role"] == "system"][:1]
        recent = [m for m in messages if m["role"] != "system"][-40:]
        messages = system_msgs + recent
        log.warning(f"[CUT] Hard msg limit: truncated to {len(messages)} messages")

    total_chars = sum(len(_msg_content_str(m)) for m in messages)

    # Hard char limit — emergency truncation
    if total_chars > MAX_CHARS:
        system_msgs = [m for m in messages if m["role"] == "system"][:1]
        recent = [m for m in messages if m["role"] != "system"][-20:]
        messages = system_msgs + recent
        total_chars = sum(len(_msg_content_str(m)) for m in messages)
        log.warning(f"[CUT] Hard char limit: truncated to {len(messages)} msgs ({total_chars} chars)")

    if total_chars < COMPACTION_THRESHOLD:  # noqa: F405
        return messages

    # Notify UI that compaction is in progress
    if on_status:
        try:
            on_status("compacting", "✨ Compacting context...")
        except Exception as e:
            log.debug(f"Suppressed: {e}")

    log.info(f"[PKG] Compacting {len(messages)} messages ({total_chars} chars)")

    # Stage 1: Strip binary/image data from old messages
    trimmed = []
    for m in messages:
        if m["role"] == "user" and isinstance(m.get("content"), list):
            new_content = []
            for block in m["content"]:
                if isinstance(block, dict) and block.get("type") == "image":
                    new_content.append({"type": "text", "text": "[Image attached]"})
                elif isinstance(block, dict) and block.get("type") == "image_url":
                    new_content.append({"type": "text", "text": "[Image attached]"})
                else:
                    new_content.append(block)
            trimmed.append({**m, "content": new_content})
        else:
            trimmed.append(m)

    # Stage 2: Trim long tool results (keep first 500 chars)
    for i, m in enumerate(trimmed):
        if m["role"] == "tool" and len(_msg_content_str(m)) > 500:
            trimmed[i] = {**m, "content": _msg_content_str(m)[:500] + "\n... [truncated]"}
        # Also trim tool_result blocks inside user messages (Anthropic format)
        elif m["role"] == "user" and isinstance(m.get("content"), list):
            new_blocks = []
            for block in m["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    content = block.get("content", "")
                    if isinstance(content, str) and len(content) > 500:
                        new_blocks.append({**block, "content": content[:500] + "\n... [truncated]"})
                    else:
                        new_blocks.append(block)
                else:
                    new_blocks.append(block)
            trimmed[i] = {**m, "content": new_blocks}

    total_after_trim = sum(len(_msg_content_str(m)) for m in trimmed)
    if total_after_trim < COMPACTION_THRESHOLD:  # noqa: F405
        log.info(f"[PKG] Stage 2 sufficient: {total_chars} -> {total_after_trim} chars")
        return trimmed

    # Stage 3: Drop old tool messages entirely, keep last 10 messages
    system_msgs = [m for m in trimmed if m["role"] == "system"]
    non_system = [m for m in trimmed if m["role"] != "system"]
    recent = non_system[-10:]
    old = non_system[:-10]

    # Drop tool/tool_result messages from old, keep user/assistant
    old_important = [m for m in old if m["role"] in ("user", "assistant")]

    stage3 = system_msgs + old_important + recent
    total_after_drop = sum(len(_msg_content_str(m)) for m in stage3)
    if total_after_drop < COMPACTION_THRESHOLD:  # noqa: F405
        log.info(f"[PKG] Stage 3 sufficient: {total_chars} -> {total_after_drop} chars")
        return stage3

    # Stage 4: Truncate verbose old assistant messages (keep first 800 chars each)
    stage4_old = []
    for m in old_important:
        txt = _msg_content_str(m)
        if m["role"] == "assistant" and len(txt) > 800:
            stage4_old.append({**m, "content": txt[:800] + "\n... [compacted]"})
        elif m["role"] == "user" and len(txt) > 500:
            stage4_old.append({**m, "content": txt[:500] + "\n... [compacted]"})
        else:
            stage4_old.append(m)

    stage4 = system_msgs + stage4_old + recent
    total_after_trunc = sum(len(_msg_content_str(m)) for m in stage4)
    if total_after_trunc < COMPACTION_THRESHOLD:  # noqa: F405
        log.info(f"[PKG] Stage 4 sufficient: {total_chars} -> {total_after_trunc} chars")
        return stage4

    # Stage 5: LLM summarization of old context
    to_summarize = stage4_old
    if not to_summarize:
        return system_msgs + recent

    # Build structured summary input (preserve more context than before)
    summary_parts = []
    for m in to_summarize[-30:]:  # Up to 30 old messages
        role = m["role"]
        txt = _msg_content_str(m)[:400]
        if txt.strip():
            summary_parts.append(f"[{role}]: {txt}")

    summary_text = "\n".join(summary_parts)

    from salmalm.core.llm import call_llm

    # Pick cheapest available model for summarization (avoid hardcoded google)
    from salmalm.core.core import router; summary_model = router._pick_available(1)
    _summ_msgs = [
        {
            "role": "system",
            "content": (
                "Summarize the following conversation concisely but thoroughly. "
                "You MUST preserve:\n"
                "1. Key decisions and conclusions\n"
                "2. Task progress and what was accomplished\n"
                "3. Important facts, numbers, file paths, code context\n"
                "4. User preferences and constraints mentioned\n"
                "5. Any pending/blocked items\n"
                "Write in the same language as the conversation. "
                "Use 5-15 sentences. Do NOT start with 'The conversation...' — "
                "write as a factual summary that can serve as context for continued work."
            ),
        },
        {"role": "user", "content": summary_text},
    ]
    # Note: call_llm is sync (urllib). Always call directly since compact_messages
    # is invoked from sync context. If ever called from async, wrap in run_in_executor.
    try:
        summary_result = call_llm(_summ_msgs, model=summary_model, max_tokens=1200)
    except Exception as e:
        # Compaction LLM failed — fall back to stage 4 result (no summary)
        log.error(f"[PKG] Stage 5 LLM failed: {e} — using stage 4 result")
        return stage4

    summary_content = summary_result.get("content", "")
    if not summary_content or len(summary_content) < 20:
        log.warning("[PKG] Stage 5 produced empty/short summary — using stage 4 result")
        return stage4

    # Guard: if summary is longer than what it replaces, skip it
    original_chars = sum(len(_msg_content_str(m)) for m in to_summarize)
    if len(summary_content) > original_chars:
        log.warning(f"[PKG] Summary ({len(summary_content)}) > original ({original_chars}) — using stage 4")
        return stage4

    compacted = (
        system_msgs
        + [
            {
                "role": "system",
                "content": f"[Previous conversation summary — {len(to_summarize)} messages compacted]\n{summary_content}",
            }
        ]
        + recent
    )

    # Persist compaction summary for cross-session continuity
    if session:
        try:
            _persist_compaction_summary(getattr(session, "id", ""), summary_content)
        except Exception as e:
            log.warning(f"[PKG] Summary persistence error: {e}")

    log.info(
        f"[PKG] Stage 5 compacted: {len(messages)} -> {len(compacted)} messages, "
        f"{total_chars} → {sum(len(_msg_content_str(m)) for m in compacted)} chars"
    )

    # Auto-curate: promote important daily entries to MEMORY.md after compaction
    try:
        result = memory_manager.auto_curate(days_back=3)
        if "No new" not in result:
            log.info(f"[MEM] Post-compaction auto-curate: {result}")
    except Exception as e:
        log.warning(f"[MEM] Auto-curate error: {e}")

    return compacted


# ============================================================
import math  # noqa: F811


# TFIDFSearch extracted to salmalm/core/search.py
from salmalm.core.search import TFIDFSearch  # noqa: E402

_tfidf = TFIDFSearch()

# ============================================================
# LLM CRON MANAGER — Scheduled tasks with LLM execution
# ============================================================
# LLMCronManager extracted to salmalm/core/llm_cron.py
from salmalm.core.llm_cron import LLMCronManager  # noqa: E402



def _estimate_tokens(messages: list) -> int:
    """Estimate token count using chars/4 approximation (stdlib only)."""
    total_chars = sum(len(_msg_content_str(m)) for m in messages)
    return total_chars // 4


def estimate_tokens(text_or_messages) -> int:
    """Estimate tokens — accepts string or message list."""
    if isinstance(text_or_messages, str):
        return max(1, len(text_or_messages) // 4)
    return _estimate_tokens(text_or_messages)


# ── Enhanced compaction helpers (from original compaction.py) ──
from salmalm.core.cost import estimate_tokens  # noqa: F401


def _msg_text(msg: dict) -> str:
    """Extract text content from a message dict."""
    c = msg.get("content", "")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return str(c)


def _importance_score(msg: dict) -> float:
    """Score message importance for compaction prioritization (0-10 scale)."""
    role = msg.get("role", "")
    text = _msg_text(msg).lower()
    if role == "system":
        return 10.0
    if role == "tool":
        if "error" in text[:200]:
            return 3.0
        return 0.5
    # User preference/decision messages
    if any(
        kw in text
        for kw in (
            "always",
            "never",
            "remember",
            "decide",
            "conclusion",  # noqa: E127
            "important",
            "approved",
            "항상",
            "결정",
            "결론",
            "기억",
        )
    ):  # noqa: E127
        return 5.0 if role == "user" else 4.0
    if role == "user":
        return 3.0
    return 2.0


def _split_by_importance(messages: List[dict], keep_recent: int = 2) -> tuple:
    """Split messages into (system, old, recent) for compaction.

    Returns (system_msgs, old_msgs_to_summarize, recent_msgs_to_keep).
    """
    system = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]
    if len(non_system) <= keep_recent:
        return system, [], non_system
    recent = non_system[-keep_recent:]
    old = non_system[:-keep_recent]
    return system, old, recent


def _extract_key_facts(messages: List[dict]) -> List[str]:
    """Extract key facts from messages for summary."""
    facts = []
    for m in messages:
        text = _msg_text(m)
        if not text.strip() or len(text) < 10:
            continue
        # Preference/decision indicators
        indicators = (
            "always",
            "never",
            "remember",
            "must",
            "decided",
            "conclusion",
            "result",
            "error",
            "fixed",
            "created",
            "deleted",
            "updated",
            "use ",
            "prefer",
            "항상",
            "결정",
            "결론",
            "수정",
            "생성",
            "삭제",
        )
        lower = text.lower()
        if any(kw in lower for kw in indicators):
            # Use first 200 chars as the fact
            facts.append(text[:200].strip())
    return facts[:20]


def enhanced_compact(messages: List[dict], target_tokens: int = 4000, max_tokens: int = 0) -> List[dict]:
    """Enhanced compaction using importance scoring."""
    from salmalm.core.cost import estimate_tokens as _et

    limit = target_tokens or max_tokens or 4000
    total = sum(_et(_msg_text(m)) for m in messages)
    if total <= limit:
        return messages
    system, old, recent = _split_by_importance(messages, keep_recent=max(2, len(messages) // 3))
    facts = _extract_key_facts(old)
    summary_msg = {
        "role": "system",
        "content": f"[Compacted {len(old)} messages]\nKey facts: " + ("; ".join(facts) if facts else "None extracted"),
    }
    return system + [summary_msg] + recent
