# Backward-compatibility shim — real module is salmalm.utils.file_logger
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.utils.file_logger")
_sys.modules[__name__] = _real
