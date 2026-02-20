# Backward-compatibility shim — real module is salmalm.core.engine
import warnings as _w; _w.warn("engine is a shim; use salmalm.core.engine directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.core.engine")
_sys.modules[__name__] = _real
