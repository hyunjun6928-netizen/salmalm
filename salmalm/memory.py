# Backward-compatibility shim — real module is salmalm.core.memory
import warnings as _w
_w.warn("memory is a shim; use salmalm.core.memory directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.core.memory")
_sys.modules[__name__] = _real
