# -*- coding: utf-8 -*-
"""Makes `src/` importable from the test suite without installing the
project as a package."""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
