# Backward-compatibility shim — real module is salmalm.channels.channel_router
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.channels.channel_router")
_sys.modules[__name__] = _real
