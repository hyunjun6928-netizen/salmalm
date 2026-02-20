# Backward-compatibility shim — real module is salmalm.utils.dedup
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.utils.dedup")
_sys.modules[__name__] = _real
