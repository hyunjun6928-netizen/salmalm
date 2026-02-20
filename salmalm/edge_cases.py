# Backward-compatibility shim — real module is salmalm.features.edge_cases
import warnings as _w; _w.warn("edge_cases is a shim; use salmalm.features.edge_cases directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.edge_cases")
_sys.modules[__name__] = _real
