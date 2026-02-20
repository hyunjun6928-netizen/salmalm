# Backward-compatibility shim — real module is salmalm.features.nodes
import warnings as _w
_w.warn("nodes is a shim; use salmalm.features.nodes directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.nodes")
_sys.modules[__name__] = _real
