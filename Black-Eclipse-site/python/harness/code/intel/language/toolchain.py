"""Toolchain detection — what is actually installed on this machine.

CIUE must never assume a language server (or a compiler, or a package manager)
exists. This module probes the host deterministically with `shutil.which` and
optionally folds in the terminal subsystem's own capability report, so the two
never disagree. Nothing is executed except the argument-free resolution that
`which` performs; no version string is invented.

`ToolchainReport.to_dict()` is the structured environment the LSP registry and the
`code_intel_status` tool expose.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

# Tool id → candidate executable names, newest first where aliases exist.
TOOL_EXECUTABLES: dict[str, tuple[str, ...]] = {
    # Node / JS / TS
    "node": ("node",),
    "npm": ("npm",),
    "pnpm": ("pnpm",),
    "yarn": ("yarn",),
    "bun": ("bun",),
    "npx": ("npx",),
    # Python
    "python": ("python", "python3"),
    "pip": ("pip", "pip3"),
    "uv": ("uv",),
    "poetry": ("poetry",),
    "conda": ("conda",),
    "pyright": ("pyright", "pyright-langserver"),
    # JVM
    "java": ("java",),
    "javac": ("javac",),
    # .NET
    "dotnet": ("dotnet",),
    # C / C++
    "gcc": ("gcc",),
    "clang": ("clang",),
    "clangd": ("clangd",),
    "cmake": ("cmake",),
    # Go
    "go": ("go",),
    "gopls": ("gopls",),
    # Rust
    "rustc": ("rustc",),
    "cargo": ("cargo",),
    "rust-analyzer": ("rust-analyzer",),
    # PHP
    "php": ("php",),
    "composer": ("composer",),
    # Language servers commonly installed as node/python packages
    "typescript-language-server": ("typescript-language-server",),
    "vscode-langservers-extracted": ("vscode-json-language-server",),
}

# Language server executables that may also be invoked via a package runner.
_SERVER_TOOLS = (
    "typescript-language-server", "pyright", "clangd", "gopls",
    "rust-analyzer", "typescript-language-server", "vscode-langservers-extracted",
)


@dataclass
class ToolchainReport:
    available: dict[str, str] = field(default_factory=dict)   # tool → resolved path
    missing: list[str] = field(default_factory=list)

    def has(self, tool: str) -> bool:
        return tool in self.available

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": dict(sorted(self.available.items())),
            "missing": sorted(self.missing),
            "languageServers": {t: self.available[t] for t in _SERVER_TOOLS if t in self.available},
        }


def _resolve(names: Iterable[str]) -> Optional[str]:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def detect_toolchain(*, extra_paths: Optional[Iterable[str]] = None) -> ToolchainReport:
    """Probe PATH for every tool CIUE can use. Deterministic; never raises."""
    report = ToolchainReport()
    for tool, names in TOOL_EXECUTABLES.items():
        path = _resolve(names)
        if path:
            report.available[tool] = path
        else:
            report.missing.append(tool)
    if extra_paths:
        for candidate in extra_paths:
            try:
                if Path(candidate).exists():
                    report.available.setdefault(Path(candidate).name, str(candidate))
            except OSError:
                continue
    return report


def terminal_capabilities() -> dict[str, Any]:
    """The terminal subsystem's host capabilities, when it is importable.

    Folding this in keeps CIUE's environment report consistent with the subsystem
    that will actually spawn a language server. A missing terminal subsystem is an
    empty report, never an error.
    """
    try:  # pragma: no cover - import wiring
        from ...terminal import shell_detect  # noqa: PLC0415

        return shell_detect.capabilities().to_dict()
    except Exception:  # noqa: BLE001 - terminal is optional for CIUE
        return {}


__all__ = [
    "TOOL_EXECUTABLES",
    "ToolchainReport",
    "detect_toolchain",
    "terminal_capabilities",
]
