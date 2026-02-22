# Backward-compatibility shim — real module is salmalm.tools.tools_util
import warnings as _w

_w.warn("tools_util is a shim; use salmalm.tools.tools_util directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.tools.tools_util")
_sys.modules[__name__] = _real
