# Backward-compatibility shim — real module is salmalm.utils.tls
import warnings as _w

_w.warn("tls is a shim; use salmalm.utils.tls directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.utils.tls")
_sys.modules[__name__] = _real
