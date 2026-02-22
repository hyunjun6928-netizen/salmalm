# Backward-compatibility shim — real module is salmalm.features.docs
import warnings as _w

_w.warn("docs is a shim; use salmalm.features.docs directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.features.docs")
_sys.modules[__name__] = _real
