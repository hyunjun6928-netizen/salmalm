# Backward-compatibility shim — real module is salmalm.channels.telegram
import warnings as _w; _w.warn("telegram is a shim; use salmalm.channels.telegram directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.channels.telegram")
_sys.modules[__name__] = _real
