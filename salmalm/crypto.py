# Backward-compatibility shim — real module is salmalm.security.crypto
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.security.crypto")
_sys.modules[__name__] = _real
