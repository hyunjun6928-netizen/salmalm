# Backward-compatibility shim — real module is salmalm.tools.tools_common
import warnings as _w

_w.warn("tools_common is a shim; use salmalm.tools.tools_common directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.tools.tools_common")
_sys.modules[__name__] = _real
