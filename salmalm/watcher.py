# Backward-compatibility shim — real module is salmalm.features.watcher
import warnings as _w; _w.warn("watcher is a shim; use salmalm.features.watcher directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.watcher")
_sys.modules[__name__] = _real
