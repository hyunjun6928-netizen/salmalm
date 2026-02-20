# Backward-compatibility shim — real module is salmalm.features.mood
import warnings as _w
_w.warn("mood is a shim; use salmalm.features.mood directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.mood")
_sys.modules[__name__] = _real
