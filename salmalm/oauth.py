# Backward-compatibility shim — real module is salmalm.web.oauth
import warnings as _w; _w.warn("oauth is a shim; use salmalm.web.oauth directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.web.oauth")
_sys.modules[__name__] = _real
