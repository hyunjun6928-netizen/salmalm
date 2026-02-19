# Backward-compatibility shim — real module is salmalm.utils.logging_ext
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.utils.logging_ext")
_sys.modules[__name__] = _real
