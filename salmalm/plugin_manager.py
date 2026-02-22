# Backward-compatibility shim — real module is salmalm.features.plugin_manager
import warnings as _w

_w.warn("plugin_manager is a shim; use salmalm.features.plugin_manager directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys

_real = _importlib.import_module("salmalm.features.plugin_manager")
_sys.modules[__name__] = _real
