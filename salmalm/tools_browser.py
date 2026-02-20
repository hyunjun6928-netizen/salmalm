# Backward-compatibility shim — real module is salmalm.tools.tools_browser
import warnings as _w
_w.warn("tools_browser is a shim; use salmalm.tools.tools_browser directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.tools.tools_browser")
_sys.modules[__name__] = _real
