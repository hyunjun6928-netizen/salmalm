# Backward-compatibility shim — real module is salmalm.tools.tools_media
import warnings as _w; _w.warn("tools_media is a shim; use salmalm.tools.tools_media directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.tools.tools_media")
_sys.modules[__name__] = _real
