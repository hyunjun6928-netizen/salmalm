# Backward-compatibility shim — real module is salmalm.features.shadow
import warnings as _w
_w.warn("shadow is a shim; use salmalm.features.shadow directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.shadow")
_sys.modules[__name__] = _real
