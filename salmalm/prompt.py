# Backward-compatibility shim — real module is salmalm.core.prompt
import warnings as _w; _w.warn("prompt is a shim; use salmalm.core.prompt directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.core.prompt")
_sys.modules[__name__] = _real
