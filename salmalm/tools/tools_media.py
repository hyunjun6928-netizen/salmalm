"""Media tools: image_generate, image_analyze, tts, stt, screenshot, tts_generate.

Delegates to the original tool_handlers.py implementations to avoid duplication.
These will be fully extracted in a future refactor.
"""

from salmalm.tools.tool_registry import register


def _legacy(name: str, args):
    """Call legacy tool_handlers implementation."""
    from salmalm.tools import tool_handlers as _th

    return _th._legacy_execute(name, args)


@register("image_generate")
def handle_image_generate(args: dict) -> str:
    """Handle image generate."""
    return _legacy("image_generate", args)


@register("image_analyze")
def handle_image_analyze(args: dict) -> str:
    """Handle image analyze."""
    return _legacy("image_analyze", args)


@register("tts")
def handle_tts(args: dict) -> str:
    """Handle tts."""
    return _legacy("tts", args)


@register("stt")
def handle_stt(args: dict) -> str:
    """Handle stt."""
    return _legacy("stt", args)


@register("screenshot")
def handle_screenshot(args: dict) -> str:
    """Handle screenshot."""
    return _legacy("screenshot", args)


@register("tts_generate")
def handle_tts_generate(args: dict) -> str:
    """Handle tts generate."""
    return _legacy("tts_generate", args)
