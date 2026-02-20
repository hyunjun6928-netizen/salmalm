# Backward-compatibility shim — real module is salmalm.utils.logging_ext
import warnings as _w
_w.warn("logging_ext is a shim; use salmalm.utils.logging_ext directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.utils.logging_ext")
_sys.modules[__name__] = _real
