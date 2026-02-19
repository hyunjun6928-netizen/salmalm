"""SalmAlm HTML templates — thin loader over static/ files.

Templates are stored as plain HTML in salmalm/static/ for easier editing.
This module reads them and exposes the same module-level constants for
backward compatibility with ``from .templates import WEB_HTML`` etc.
"""
from pathlib import Path

_STATIC = Path(__file__).parent / 'static'


def _load(name: str) -> str:
    """Read a static HTML file, return empty string if missing."""
    p = _STATIC / name
    if p.exists():
        from . import __version__
        return p.read_text(encoding='utf-8').replace('{{VERSION}}', f'v{__version__}')
    return ''


WEB_HTML: str = _load('index.html')
ONBOARDING_HTML: str = _load('onboarding.html')
SETUP_HTML: str = _load('setup.html')
UNLOCK_HTML: str = _load('unlock.html')
DASHBOARD_HTML: str = _load('dashboard.html')
