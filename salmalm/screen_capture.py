# Backward-compatibility shim — real module is salmalm.features.screen_capture
import warnings as _w

_w.warn("screen_capture is a shim; use salmalm.features.screen_capture directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.features.screen_capture")
_sys.modules[__name__] = _real
