# Backward-compatibility shim — real module is salmalm.features.split_response
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.features.split_response")
_sys.modules[__name__] = _real
