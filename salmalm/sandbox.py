# Backward-compatibility shim — real module is salmalm.security.sandbox
import warnings as _w; _w.warn("sandbox is a shim; use salmalm.security.sandbox directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.security.sandbox")
_sys.modules[__name__] = _real
