"""Response Compare / Beam (응답 비교) — BIG-AGI style."""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List


async def compare_models(session_id: str, message: str, models: List[str] = None) -> List[Dict]:
    """Compare models."""
    from salmalm.core.llm_loop import _call_llm_async
    from salmalm.core.prompt import build_system_prompt
    from salmalm.core import get_session

    if not models:
        from salmalm.constants import MODELS

        models = [MODELS.get("haiku", ""), MODELS.get("sonnet", "")]
        models = [m for m in models if m]

    _session = get_session(session_id)  # noqa: F841
    system_prompt = build_system_prompt(full=False)
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": message}]

    async def _call_one(model_id: str) -> Dict:
        """Call one."""
        t0 = time.time()
        try:
            result = await _call_llm_async(messages, model=model_id, max_tokens=4096)
            elapsed = int((time.time() - t0) * 1000)
            usage = result.get("usage", {})
            return {
                "model": model_id,
                "response": result.get("content", ""),
                "input_tokens": usage.get("input", 0),
                "output_tokens": usage.get("output", 0),
                "time_ms": elapsed,
                "error": None,
            }
        except Exception as e:
            return {
                "model": model_id,
                "response": "",
                "input_tokens": 0,
                "output_tokens": 0,
                "time_ms": int((time.time() - t0) * 1000),
                "error": str(e)[:200],
            }

    tasks = [_call_one(m) for m in models]
    results = await asyncio.gather(*tasks)
    return list(results)
