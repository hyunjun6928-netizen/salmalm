# Backward-compatibility shim — real module is salmalm.core.memory
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.core.memory")
_sys.modules[__name__] = _real
