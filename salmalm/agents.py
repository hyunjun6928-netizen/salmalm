# Backward-compatibility shim — real module is salmalm.features.agents
import warnings as _w; _w.warn("agents is a shim; use salmalm.features.agents directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.agents")
_sys.modules[__name__] = _real
