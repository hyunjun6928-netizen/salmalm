# Backward-compatibility shim — real module is salmalm.features.vault_chat
import importlib as _importlib, sys as _sys
_real = _importlib.import_module("salmalm.features.vault_chat")
_sys.modules[__name__] = _real
