# Backward-compatibility shim — real module is salmalm.features.self_evolve
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.self_evolve")
_sys.modules[__name__] = _real
