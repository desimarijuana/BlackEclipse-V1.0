"""User-facing messages for the optional capability packs.

The five heavy optional dependencies are imported lazily inside functions, so the
application runs without them. What it lacked was an *actionable* message: a
missing pack surfaced as ``ModuleNotFoundError: No module named 'playwright'``,
which tells a user nothing about what is missing or how to fix it.

This module is the single catalogue. Call ``unavailable(pack)`` when an import
fails, and ``available(pack)`` when probing capability.
"""

from __future__ import annotations

import importlib.util
from typing import Any

# Keep this in sync with `PACKS` in `scripts/desktop-package.js`.
PACKS: dict[str, dict[str, str]] = {
    "browser": {
        "label": "Browser automation",
        "modules": ("playwright",),
        "enables": "the browser tool: page automation, screenshots, form filling",
    },
    "ml": {
        "label": "Machine learning",
        "modules": ("xgboost", "sklearn", "scipy"),
        "enables": "model training and the ML adapters",
    },
    "documents": {
        "label": "Documents",
        "modules": ("pymupdf",),
        "enables": "PDF editing and document inspection",
    },
    "computer": {
        "label": "Computer control",
        "modules": ("winsdk",),
        "enables": "Windows UI automation and OCR (Windows only)",
    },
    "charts": {
        "label": "Server-side charts",
        "modules": ("plotly", "matplotlib"),
        "enables": "Python-rendered figures and Plotly charts",
    },
}

_INSTALL_HINT = (
    "Install it from Settings \u203a Components, or run "
    "`npm run desktop:packs install {pack}` and restart the app."
)


def missing_modules(pack: str) -> list[str]:
    """Which modules of a pack are not importable right now."""
    spec = PACKS.get(pack)
    if not spec:
        return []
    missing: list[str] = []
    for module in spec["modules"]:
        try:
            found = importlib.util.find_spec(module) is not None
        except Exception:  # noqa: BLE001 - a broken install is "missing"
            found = False
        if not found:
            missing.append(module)
    return missing


def available(pack: str) -> bool:
    """Whether every module of the pack can be imported."""
    return not missing_modules(pack)


def unavailable(pack: str, detail: str | None = None) -> str:
    """One sentence a user can act on. Never a traceback, never a lie."""
    spec = PACKS.get(pack)
    if not spec:
        return detail or f"The optional capability '{pack}' is not available."
    missing = missing_modules(pack)
    modules = ", ".join(missing) if missing else ", ".join(spec["modules"])
    parts = [
        f"{spec['label']} is not installed ({modules} missing), so {spec['enables']} is unavailable."
    ]
    if detail:
        parts.append(detail.rstrip(".") + ".")
    parts.append(_INSTALL_HINT.format(pack=pack))
    return " ".join(parts)


def describe_all() -> list[dict[str, Any]]:
    """Capability report for a diagnostics surface or a support request."""
    return [
        {
            "pack": name,
            "label": spec["label"],
            "available": available(name),
            "missing": missing_modules(name),
            "enables": spec["enables"],
        }
        for name, spec in PACKS.items()
    ]
