"""Shared pytest configuration.

Puts the project root on sys.path so tests can import the ``src`` and
``backend`` packages the same way the application does (``from src.x import y``,
``from backend.x import y``), regardless of the directory pytest is invoked from.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
