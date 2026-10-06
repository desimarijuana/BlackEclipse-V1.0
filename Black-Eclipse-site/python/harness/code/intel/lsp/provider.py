"""Language server providers — one description per server implementation.

A provider says how to find and launch ONE language server. CIUE never hard-codes
a single implementation; adding a language server is adding a provider to
`PROVIDERS` in `providers.py`. Detection is honest: `is_installed` really probes
the host, and a project that merely *could* be served reports
`LANGUAGE_SERVER_MISSING` rather than pretending to answer.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class LanguageServerSpec:
    """How to launch a language server."""

    provider_id: str
    languages: tuple[str, ...]
    # The argv to launch. The first element is resolved against PATH (or may be
    # an absolute path). `%ROOT%` in an argument is replaced with the workspace
    # root. No model-supplied text ever reaches this argv.
    argv: tuple[str, ...]
    # Alternate argv forms to try when the primary executable is missing (e.g. a
    # package-runner invocation). Each is tried in order.
    fallbacks: tuple[tuple[str, ...], ...] = ()
    initialization_options: dict[str, Any] = field(default_factory=dict)
    # A provider whose `is_installed` is a pure host probe (no per-project file
    # needed). Project detection still gates whether it is *started*.
    requires_project_file: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.provider_id,
            "languages": list(self.languages),
            "argv": list(self.argv),
            "installed": is_provider_installed(self),
        }


class LanguageServerProvider:
    """The provider contract.

    A provider is stateless; `LSPManager` owns the running processes. Subclasses
    (or the shipped `SpecProvider`) implement `spec()` and inherit the detection
    helpers.
    """

    provider_id: str = "base"
    languages: tuple[str, ...] = ()

    def spec(self, root: Path) -> Optional[LanguageServerSpec]:
        raise NotImplementedError

    def detect(self, root: Path) -> bool:
        """Whether this provider should serve `root` (its files are present)."""
        return True

    def is_installed(self) -> bool:
        spec = self.spec(Path("."))
        return bool(spec and _resolve_argv(spec))

    def create_client(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError


class SpecProvider(LanguageServerProvider):
    """A provider backed by a static `LanguageServerSpec`."""

    def __init__(self, provider_id: str, languages: tuple[str, ...], server_spec: LanguageServerSpec) -> None:
        self.provider_id = provider_id
        self.languages = languages
        self.server_spec = server_spec

    def spec(self, root: Path) -> Optional[LanguageServerSpec]:
        return self.server_spec

    def is_installed(self) -> bool:
        return bool(_resolve_argv(self.server_spec))


def _resolve_argv(spec: LanguageServerSpec) -> Optional[list[str]]:
    """Resolve a launch argv against PATH, honoring `%ROOT%`, or return None.

    The primary form is tried first; each fallback is tried on its own terms.
    Returns the resolved (ready-to-launch) argv, or None when nothing is present.
    """
    forms = (spec.argv, *spec.fallbacks)
    for form in forms:
        if not form:
            continue
        program = form[0]
        resolved = shutil.which(program) or (program if Path(program).exists() else None)
        if resolved:
            argv = [resolved, *form[1:]]
            return argv
    return None


def resolve_launch_argv(spec: LanguageServerSpec, root: Path) -> Optional[list[str]]:
    resolved = _resolve_argv(spec)
    if resolved is None:
        return None
    return [arg.replace("%ROOT%", str(root)) for arg in resolved]


def is_provider_installed(spec: LanguageServerSpec) -> bool:
    return _resolve_argv(spec) is not None


__all__ = [
    "LanguageServerProvider",
    "LanguageServerSpec",
    "SpecProvider",
    "is_provider_installed",
    "resolve_launch_argv",
]
