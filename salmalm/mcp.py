# Backward-compatibility shim — real module is salmalm.features.mcp
import warnings as _w; _w.warn("mcp is a shim; use salmalm.features.mcp directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.mcp")
_sys.modules[__name__] = _real
