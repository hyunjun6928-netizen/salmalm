# Backward-compatibility shim — real module is salmalm.channels.discord_bot
import warnings as _w; _w.warn("discord_bot is a shim; use salmalm.channels.discord_bot directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.channels.discord_bot")
_sys.modules[__name__] = _real
