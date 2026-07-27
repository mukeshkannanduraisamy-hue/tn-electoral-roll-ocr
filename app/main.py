"""Root app.main wrapper for root-level Uvicorn invocation."""
import importlib
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
_api_dir = str(_root / "apps" / "api")

# Temporarily prioritize apps/api in sys.path and remove root app module from cache
if _api_dir in sys.path:
    sys.path.remove(_api_dir)
sys.path.insert(0, _api_dir)

# Remove wrapper modules from cache so Python loads apps/api/app
sys.modules.pop("app", None)
sys.modules.pop("app.main", None)

_real_main = importlib.import_module("app.main")
app = _real_main.app
