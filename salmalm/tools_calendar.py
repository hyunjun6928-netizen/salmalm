# Backward-compatibility shim — real module is salmalm.tools.tools_calendar
import warnings as _w; _w.warn("tools_calendar is a shim; use salmalm.tools.tools_calendar directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.tools.tools_calendar")
_sys.modules[__name__] = _real
