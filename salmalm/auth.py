# Backward-compatibility shim — real module is salmalm.web.auth
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.web.auth")
_sys.modules[__name__] = _real
