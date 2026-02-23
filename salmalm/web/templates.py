"""SalmAlm HTML templates — thin loader over static/ files.

Templates are stored as plain HTML in salmalm/static/ for easier editing.
Uses module-level __getattr__ so templates are re-read on every access
(no server restart needed during development).
"""

from pathlib import Path

_STATIC = Path(__file__).resolve().parent.parent / "static"


def _load(name: str) -> str:
    """Read a static HTML file, return empty string if missing."""
    p = _STATIC / name
    if p.exists():
        from salmalm import __version__

        return p.read_text(encoding="utf-8").replace("{{VERSION}}", f"v{__version__}")
    return ""


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
