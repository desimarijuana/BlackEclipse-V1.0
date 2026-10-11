"""Approved dependency policy for Python strategies.

Strategies are expected to be self-contained or to use the numerical stack that
ships with the harness. Third-party imports are not installed on demand; an
unapproved import is reported (and can be refused) rather than silently resolved.
This keeps the runtime reproducible — the environment is pinned by the harness,
not mutated per run.
"""

from __future__ import annotations

import sys
from typing import Any

# The numerical/analysis stack that ships with the harness and is approved for
# strategy code. Extend deliberately; never install on demand inside a run.
APPROVED_THIRD_PARTY = frozenset({
    "numpy", "pandas", "polars", "scipy", "statsmodels", "sklearn", "sympy",
    "talib", "ta", "pandas_ta", "pyarrow", "numba", "matplotlib", "yaml",
})

_STDLIB = getattr(sys, "stdlib_module_names", set())


def classify_imports(imports: list[str] | set[str]) -> dict[str, Any]:
    """Split imports into stdlib / approved / unapproved and harness-local."""
    stdlib, approved, unapproved, local = [], [], [], []
    for module in sorted(imports):
        root = module.split(".")[0]
        if root == "harness":
            local.append(root)
        elif root in _STDLIB:
            stdlib.append(root)
        elif root in APPROVED_THIRD_PARTY:
            approved.append(root)
        else:
            unapproved.append(root)
    return {
        "stdlib": stdlib,
        "approved": approved,
        "unapproved": unapproved,
        "harness": local,
        "unapprovedDependencies": unapproved,
    }


__all__ = ["APPROVED_THIRD_PARTY", "classify_imports"]
