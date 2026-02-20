# Backward-compatibility shim — real module is salmalm.features.deadman
import warnings as _w
_w.warn("deadman is a shim; use salmalm.features.deadman directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.deadman")
_sys.modules[__name__] = _real
