# Backward-compatibility shim — real module is salmalm.features.self_evolve
import warnings as _w
_w.warn("self_evolve is a shim; use salmalm.features.self_evolve directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.self_evolve")
_sys.modules[__name__] = _real
