# Backward-compatibility shim — real module is salmalm.core.session_manager
import warnings as _w
_w.warn("session_manager is a shim; use salmalm.core.session_manager directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.core.session_manager")
_sys.modules[__name__] = _real
