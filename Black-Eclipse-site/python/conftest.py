"""Ensure the `harness` package is importable when pytest runs from any cwd."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
