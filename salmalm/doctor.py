# Backward-compatibility shim — real module is salmalm.features.doctor
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.doctor")
_sys.modules[__name__] = _real
