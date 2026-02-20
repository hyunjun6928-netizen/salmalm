# Backward-compatibility shim — real module is salmalm.features.users
import warnings as _w
_w.warn("users is a shim; use salmalm.features.users directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.users")
_sys.modules[__name__] = _real
