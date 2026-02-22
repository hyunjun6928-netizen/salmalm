# Backward-compatibility shim — real module is salmalm.utils.dedup
import warnings as _w

_w.warn("dedup is a shim; use salmalm.utils.dedup directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.utils.dedup")
_sys.modules[__name__] = _real
