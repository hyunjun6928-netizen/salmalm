# Backward-compatibility shim — real module is salmalm.tools.tools_browser
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.tools.tools_browser")
_sys.modules[__name__] = _real
