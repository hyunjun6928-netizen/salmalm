# Backward-compatibility shim — real module is salmalm.features.timecapsule
import warnings as _w; _w.warn("timecapsule is a shim; use salmalm.features.timecapsule directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.timecapsule")
_sys.modules[__name__] = _real
