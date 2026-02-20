# Backward-compatibility shim — real module is salmalm.utils.markdown_ir
import warnings as _w
_w.warn("markdown_ir is a shim; use salmalm.utils.markdown_ir directly", DeprecationWarning, stacklevel=2)
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.utils.markdown_ir")
_sys.modules[__name__] = _real
