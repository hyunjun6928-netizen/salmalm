# Backward-compatibility shim — real module is salmalm.features.shadow
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.shadow")
_sys.modules[__name__] = _real
