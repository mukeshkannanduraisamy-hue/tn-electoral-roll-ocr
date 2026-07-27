"""Root wrapper package for Render / root execution compatibility."""
import sys
from pathlib import Path

_api_dir = Path(__file__).resolve().parent.parent / "apps" / "api"
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))
