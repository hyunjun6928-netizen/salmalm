"""Tests for lane-based message queue — 5 modes, overflow, concurrency control."""

import asyncio
import pytest
import time

from salmalm.queue import (
    QueueMode, DropPolicy, QueueLane, QueuedMessage, MessageQueue,
    apply_overflow, _merge_messages, _parse_duration_ms, SessionOptions,
    DEFAULT_CONFIG,
)


# ── Helpers ──

def make_queue(config=None) -> MessageQueue:
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    return MessageQueue(config=cfg)


async def echo_processor(session_id: str, message: str, **kw) -> str:
    return f"[{session_id}] {message}"


async def slow_processor(session_id: str, message: str, **kw) -> str:
    await asyncio.sleep(0.3)
    return f"[{session_id}] {message}"


def run(coro):
    """Run async test."""
    return asyncio.run(coro)


# ── 1. QueueMode enum ──

def test_queue_modes():
    assert QueueMode.COLLECT.value == "collect"
    assert QueueMode.STEER.value == "steer"
    assert QueueMode.FOLLOWUP.value == "followup"
    assert QueueMode.STEER_BACKLOG.value == "steer-backlog"
    assert QueueMode.INTERRUPT.value == "interrupt"
    assert len(QueueMode) == 5


# ── 2. DropPolicy enum ──

def test_drop_policies():
    assert DropPolicy.OLD.value == "old"
    assert DropPolicy.NEW.value == "new"
    assert DropPolicy.SUMMARIZE.value == "summarize"


# ── 3. Overflow — drop old ──

def test_overflow_drop_old():
    msgs = [QueuedMessage(text=f"msg{i}") for i in range(25)]
    result, summary = apply_overflow(msgs, cap=20, policy=DropPolicy.OLD)
    assert len(result) == 20
    assert result[0].text == "msg5"
    assert summary is None


# ── 4. Overflow — drop new ──

def test_overflow_drop_new():
    msgs = [QueuedMessage(text=f"msg{i}") for i in range(25)]
    result, summary = apply_overflow(msgs, cap=20, policy=DropPolicy.NEW)
    assert len(result) == 20
    assert result[-1].text == "msg19"
    assert summary is None


# ── 5. Overflow — summarize ──

def test_overflow_summarize():
    msgs = [QueuedMessage(text=f"msg{i}") for i in range(25)]
    result, summary = apply_overflow(msgs, cap=20, policy=DropPolicy.SUMMARIZE)
    assert len(result) == 21  # 1 summary + 20 kept
    assert "요약" in result[0].text or "summarized" in result[0].text
    assert summary is not None
    assert "msg0" in summary


# ── 6. No overflow ──

def test_overflow_no_overflow():
    msgs = [QueuedMessage(text=f"msg{i}") for i in range(10)]
    result, summary = apply_overflow(msgs, cap=20, policy=DropPolicy.OLD)
    assert len(result) == 10
    assert summary is None


# ── 7. Collect mode — debounce merges messages ──

def test_collect_mode_merge():
    async def _test():
        q = make_queue({"debounceMs": 100, "mode": "collect"})
        t1 = asyncio.ensure_future(q.process("s1", "hello", echo_processor))
        await asyncio.sleep(0.02)
        t2 = asyncio.ensure_future(q.process("s1", "world", echo_processor))
        results = await asyncio.gather(t1, t2)
        merged = [r for r in results if r]
        assert any("hello" in r and "world" in r for r in merged)
    run(_test())


# ── 8. Session serialization (followup mode) ──

def test_session_serialization():
    async def _test():
        q = make_queue({"debounceMs": 10, "mode": "followup"})
        order = []

        async def tracking_processor(sid, msg, **kw):
            order.append(f"start-{msg}")
            await asyncio.sleep(0.05)
            order.append(f"end-{msg}")
            return msg

        t1 = asyncio.ensure_future(q.process("s1", "A", tracking_processor))
        await asyncio.sleep(0.01)
        t2 = asyncio.ensure_future(q.process("s1", "B", tracking_processor))
        await asyncio.gather(t1, t2)
        # Serial: A finishes before B starts (or they got merged)
        if "start-A" in order and "start-B" in order:
            assert order.index("end-A") < order.index("start-B")
    run(_test())


# ── 9. Global concurrency semaphore ──

def test_global_concurrency():
    async def _test():
        q = make_queue({"debounceMs": 10, "mode": "followup", "maxConcurrent": {"main": 2, "subagent": 2}})
        active = {"count": 0, "max": 0}

        async def counting_processor(sid, msg, **kw):
            active["count"] += 1
            active["max"] = max(active["max"], active["count"])
            await asyncio.sleep(0.05)
            active["count"] -= 1
            return msg

        tasks = [asyncio.ensure_future(q.process(f"s{i}", f"msg{i}", counting_processor)) for i in range(4)]
        await asyncio.gather(*tasks)
        assert active["max"] <= 2
    run(_test())


# ── 10. /queue command — mode change ──

def test_queue_command_mode():
    q = make_queue()
    result = q.handle_queue_command("s1", "steer")
    assert "mode=steer" in result
    lane = q.get_lane("s1")
    assert lane.options.mode == QueueMode.STEER


# ── 11. /queue command — options combo ──

def test_queue_command_combo():
    q = make_queue()
    result = q.handle_queue_command("s1", "interrupt debounce:2s cap:25 drop:old")
    assert "mode=interrupt" in result
    assert "debounce=2000ms" in result
    assert "cap=25" in result
    assert "drop=old" in result


# ── 12. /queue reset ──

def test_queue_command_reset():
    q = make_queue()
    q.handle_queue_command("s1", "steer cap:50")
    lane = q.get_lane("s1")
    assert lane.options.mode == QueueMode.STEER
    result = q.handle_queue_command("s1", "reset")
    assert "✅" in result
    assert lane.options.mode is None
    assert lane.options.cap is None


# ── 13. /queue status ──

def test_queue_command_status():
    q = make_queue()
    result = q.handle_queue_command("s1", "")
    assert "mode:" in result
    assert "debounce:" in result
    assert "cap:" in result


# ── 14. Parse duration ──

def test_parse_duration():
    assert _parse_duration_ms("2s") == 2000
    assert _parse_duration_ms("500ms") == 500
    assert _parse_duration_ms("1.5s") == 1500
    assert _parse_duration_ms("bogus") is None


# ── 15. Interrupt mode ──

def test_interrupt_mode():
    async def _test():
        q = make_queue({"debounceMs": 10, "mode": "interrupt"})

        async def long_processor(sid, msg, **kw):
            try:
                await asyncio.sleep(10)
                return "should not finish"
            except asyncio.CancelledError:
                raise

        t1 = asyncio.ensure_future(q.process("s1", "old", long_processor))
        await asyncio.sleep(0.05)
        t2 = asyncio.ensure_future(q.process("s1", "new", echo_processor))
        result = await t2
        assert "new" in result
    run(_test())


# ── 16. Channel-specific mode ──

def test_channel_mode():
    async def _test():
        q = make_queue({"debounceMs": 50, "mode": "collect", "byChannel": {"telegram": "collect"}})
        result = await q.process("s1", "test", echo_processor, channel="telegram")
        assert "test" in result
    run(_test())


# ── 17. Merge messages ──

def test_merge_messages():
    msgs = [QueuedMessage(text="a"), QueuedMessage(text="b"), QueuedMessage(text="c")]
    assert _merge_messages(msgs) == "a\nb\nc"
    assert _merge_messages([QueuedMessage(text="solo")]) == "solo"


# ── 18. Cleanup idle lanes ──

def test_cleanup():
    q = make_queue()
    lane = q._get_lane("old_session")
    lane.last_active = time.time() - 7200
    q._cleanup_ts = 0
    q.cleanup(max_idle=3600)
    assert q.get_lane("old_session") is None


# ── 19. Subagent uses subagent semaphore ──

def test_subagent_semaphore():
    q = make_queue()
    lane = q._get_lane("agent:main:subagent:abc123")
    assert lane._global_sem is q._subagent_sem
    lane2 = q._get_lane("agent:main:main")
    assert lane2._global_sem is q._main_sem
