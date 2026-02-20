# Backward-compatibility shim — real module is salmalm.features.transcript_hygiene
import importlib as _importlib
import sys as _sys
_real = _importlib.import_module("salmalm.features.transcript_hygiene")
_sys.modules[__name__] = _real
