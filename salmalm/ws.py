# Backward-compatibility shim — real module is salmalm.web.ws
import warnings as _w; _w.warn("ws is a shim; use salmalm.web.ws directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.web.ws")
_sys.modules[__name__] = _real
