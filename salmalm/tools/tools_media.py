"""Media tools: image_generate, image_analyze, tts, stt, screenshot, tts_generate.

Delegates to the original tool_handlers.py implementations to avoid duplication.
These will be fully extracted in a future refactor.
"""
from salmalm.tool_registry import register


def _legacy(name, args):
    """Call legacy tool_handlers implementation."""
    from salmalm import tool_handlers as _th
    return _th._legacy_execute(name, args)


@register('image_generate')
def handle_image_generate(args: dict) -> str:
    return _legacy('image_generate', args)


@register('image_analyze')
def handle_image_analyze(args: dict) -> str:
    return _legacy('image_analyze', args)


@register('tts')
def handle_tts(args: dict) -> str:
    return _legacy('tts', args)


@register('stt')
def handle_stt(args: dict) -> str:
    return _legacy('stt', args)


@register('screenshot')
def handle_screenshot(args: dict) -> str:
    return _legacy('screenshot', args)


@register('tts_generate')
def handle_tts_generate(args: dict) -> str:
    return _legacy('tts_generate', args)
