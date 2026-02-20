# Backward-compatibility shim — real module is salmalm.web.auth
import warnings as _w; _w.warn("auth is a shim; use salmalm.web.auth directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.web.auth")
_sys.modules[__name__] = _real
