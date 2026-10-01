"""Finance-application scaffold kits (Phase 9).

A kit is DATA: the shape the repo already demands for one named artefact, plus the
tests that prove a generated instance satisfies it. A kit is **not** a code
snippet — it is the closed `produces` set, the typed inputs, the convention
statements, and the acceptance test that ships WITH it.

The user asks in words ("compare any two companies' margins"); Eclipse picks the
kit, fills it in, writes it into the disposable workspace (never the user's
checkout), runs the area's own check, and reports a job done with proof.
"""

from __future__ import annotations

from .loader import (
    KitLoadError,
    get_kit,
    kits_root,
    library_root,
    list_kits,
    load_catalog,
    load_kit,
    render_checks,
    render_kit,
)
from .model import KitCheck, KitInput, KitManifest

__all__ = [
    "KitCheck",
    "KitInput",
    "KitLoadError",
    "KitManifest",
    "get_kit",
    "kits_root",
    "library_root",
    "list_kits",
    "load_catalog",
    "load_kit",
    "render_checks",
    "render_kit",
]
