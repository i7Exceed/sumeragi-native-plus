"""Repository paths for the Python tests (run: python3 -m unittest discover -s tests)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT / 'launcher', ROOT / 'scripts', ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
