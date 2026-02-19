# Backward-compatibility shim — real module is salmalm.features.screen_capture
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.features.screen_capture")
_sys.modules[__name__] = _real
