# Backward-compatibility shim — real module is salmalm.features.users
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.users")
_sys.modules[__name__] = _real
