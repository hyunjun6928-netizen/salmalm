# Backward-compatibility shim — real module is salmalm.channels.slack_bot
import warnings as _w
_w.warn("slack_bot is a shim; use salmalm.channels.slack_bot directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.channels.slack_bot")
_sys.modules[__name__] = _real
