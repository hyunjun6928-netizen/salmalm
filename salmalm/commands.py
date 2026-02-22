# Backward-compatibility shim — real module is salmalm.features.commands
import warnings as _w

_w.warn("commands is a shim; use salmalm.features.commands directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.features.commands")
_sys.modules[__name__] = _real
