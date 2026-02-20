# Backward-compatibility shim — real module is salmalm.features.edge_cases
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.edge_cases")
_sys.modules[__name__] = _real
