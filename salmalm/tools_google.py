# Backward-compatibility shim — real module is salmalm.tools.tools_google
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.tools.tools_google")
_sys.modules[__name__] = _real
