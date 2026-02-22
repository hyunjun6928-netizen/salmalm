# Backward-compatibility shim — real module is salmalm.features.tray
import warnings as _w

_w.warn("tray is a shim; use salmalm.features.tray directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.features.tray")
_sys.modules[__name__] = _real
