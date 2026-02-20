# Backward-compatibility shim — real module is salmalm.tools.tools_email
import warnings as _w; _w.warn("tools_email is a shim; use salmalm.tools.tools_email directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.tools.tools_email")
_sys.modules[__name__] = _real
