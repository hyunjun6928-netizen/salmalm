# Backward-compatibility shim — real module is salmalm.utils.retry
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.utils.retry")
_sys.modules[__name__] = _real
