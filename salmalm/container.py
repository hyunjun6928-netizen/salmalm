# Backward-compatibility shim — real module is salmalm.security.container
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.security.container")
_sys.modules[__name__] = _real
