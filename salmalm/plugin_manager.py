# Backward-compatibility shim — real module is salmalm.features.plugin_manager
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.features.plugin_manager")
_sys.modules[__name__] = _real
