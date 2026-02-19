# Backward-compatibility shim — real module is salmalm.core.engine
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.core.engine")
_sys.modules[__name__] = _real
