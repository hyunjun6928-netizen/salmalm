"""SalmAlm HTML templates."""
from pathlib import Path

_STATIC = Path(__file__).resolve().parent.parent / "static"


def _load(name: str) -> str:
    p = _STATIC / name
    if not p.exists():
        return ""
    from salmalm import __version__
    import time as _t
    ts = str(int(_t.time()) // 3600)
    return p.read_text(encoding="utf-8").replace("{{VERSION}}", f"v{__version__}.{ts}")


_TEMPLATE_MAP = {
    "WEB_HTML": "index.html",
    "ONBOARDING_HTML": "onboarding.html",
    "SETUP_HTML": "setup.html",
    "UNLOCK_HTML": "unlock.html",
    "DASHBOARD_HTML": "dashboard.html",
}


def __getattr__(name: str):
    if name in _TEMPLATE_MAP:
        return _load(_TEMPLATE_MAP[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
