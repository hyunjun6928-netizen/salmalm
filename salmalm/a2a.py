# Backward-compatibility shim — real module is salmalm.features.a2a
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.features.a2a")
_sys.modules[__name__] = _real
