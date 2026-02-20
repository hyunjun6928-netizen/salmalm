# Backward-compatibility shim — real module is salmalm.tools.tools_web
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.tools.tools_web")
_sys.modules[__name__] = _real
