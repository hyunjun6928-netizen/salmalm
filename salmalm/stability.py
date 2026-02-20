# Backward-compatibility shim — real module is salmalm.features.stability
import warnings as _w; _w.warn("stability is a shim; use salmalm.features.stability directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.stability")
_sys.modules[__name__] = _real
