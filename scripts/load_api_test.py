import types
import sys
import importlib.util

sys.path.insert(0, r"D:\tools\pymic")
mod = types.ModuleType("pymic")
mod.__path__ = [r"D:\tools\pymic\pymic"]
sys.modules["pymic"] = mod
spec = importlib.util.spec_from_file_location(
    "pymic.api", r"D:\tools\pymic\pymic\api.py"
)
if spec is None:
    raise ValueError("Failed to create module spec")
api = importlib.util.module_from_spec(spec)
if spec.loader is None:
    raise ValueError("Failed to get module loader")
spec.loader.exec_module(api)
print("Api loaded", hasattr(api, "Api"))
