# Backward-compatibility shim — real module is salmalm.features.a2a
import warnings as _w

_w.warn("a2a is a shim; use salmalm.features.a2a directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.features.a2a")
_sys.modules[__name__] = _real
