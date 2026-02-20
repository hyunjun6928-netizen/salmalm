# Backward-compatibility shim — real module is salmalm.utils.browser
import warnings as _w
_w.warn("browser is a shim; use salmalm.utils.browser directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.utils.browser")
_sys.modules[__name__] = _real
