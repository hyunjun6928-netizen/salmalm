# Backward-compatibility shim — real module is salmalm.security.sandbox
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.security.sandbox")
_sys.modules[__name__] = _real
