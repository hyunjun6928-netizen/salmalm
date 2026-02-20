# Backward-compatibility shim — real module is salmalm.features.dashboard_life
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.dashboard_life")
_sys.modules[__name__] = _real
