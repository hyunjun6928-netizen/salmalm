# Backward-compatibility shim — real module is salmalm.tools.tool_registry
import warnings as _w

_w.warn("tool_registry is a shim; use salmalm.tools.tool_registry directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.tools.tool_registry")
_sys.modules[__name__] = _real
