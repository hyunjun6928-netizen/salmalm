# Backward-compatibility shim — real module is salmalm.channels.channel_router
import warnings as _w
_w.warn("channel_router is a shim; use salmalm.channels.channel_router directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.channels.channel_router")
_sys.modules[__name__] = _real
