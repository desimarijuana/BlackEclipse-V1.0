"""The kit library loader + renderer (Phase 9).

Reads `kit.json` manifests from `code/kits/<kit-id>/`, validates them, and REFUSES
to load a kit that:

  * has no acceptance test that ships WITH it (`tests/test_kit_<id>.py`),
  * declares a `produces` path with no corresponding template,
  * or emits an output outside its declared set at render time.

Rendering is pure string substitution of the declared inputs into the kit's
templates — it never executes anything.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .model import KitManifest

# The repo root that owns `python/tests/`. Resolved from this file, so the
# acceptance-test lookup never depends on the process working directory.
_HARNESS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TESTS_ROOT = os.path.join(os.path.dirname(_HARNESS_ROOT), "tests")


class KitLoadError(Exception):
    """A kit manifest or its required companion is invalid. Carries a stable code."""

    def __init__(self, code: str, message: str, *, kit_id: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.kit_id = kit_id


def kits_root() -> str:
    """The directory that holds the kit folders."""
    return os.path.dirname(os.path.abspath(__file__))


def library_root() -> str:
    """Alias for `kits_root` (mirrors `skills/loader.library_root`)."""
    return kits_root()


@dataclass(frozen=True)
class Kit:
    """A loaded kit: its manifest, its folder, and its template set."""

    manifest: KitManifest
    folder: str
    templates: dict[str, str] = field(default_factory=dict)  # produces-path -> template text

    @property
    def id(self) -> str:
        return self.manifest.id


def _acceptance_test_exists(kit_id: str) -> bool:
    return os.path.isfile(os.path.join(_TESTS_ROOT, f"test_kit_{kit_id}.py"))


_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def load_kit(folder: str) -> Kit:
    """Load + validate one kit folder. Raises `KitLoadError` on any violation."""
    manifest_path = os.path.join(folder, "kit.json")
    if not os.path.isfile(manifest_path):
        raise KitLoadError("KIT_NO_MANIFEST", "kit.json not found", kit_id=os.path.basename(folder))
    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError) as exc:
        raise KitLoadError("KIT_MANIFEST_INVALID", f"kit.json is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise KitLoadError("KIT_MANIFEST_INVALID", "kit.json must be a JSON object")
    # Accept the §6.1 `requires.inputs` shape.
    if "requires" in raw and isinstance(raw.get("requires"), dict):
        raw["requiresInputs"] = raw["requires"].get("inputs", [])
    try:
        manifest = KitManifest(**{k: v for k, v in raw.items() if k != "requires"})
    except Exception as exc:  # noqa: BLE001 - a malformed manifest is a load error
        raise KitLoadError("KIT_MANIFEST_INVALID", str(exc), kit_id=str(raw.get("id") or "")) from exc

    # A kit without its acceptance test does NOT load (§6.1).
    if not _acceptance_test_exists(manifest.id):
        raise KitLoadError(
            "KIT_NO_ACCEPTANCE_TEST",
            f"kit {manifest.id!r} has no acceptance test (python/tests/test_kit_{manifest.id}.py)",
            kit_id=manifest.id,
        )

    # Every declared output must have a template file that produces it.
    templates: dict[str, str] = {}
    for rel in manifest.produces:
        template_path = os.path.join(folder, "templates", rel.replace("/", os.sep) + ".tmpl")
        if not os.path.isfile(template_path):
            raise KitLoadError(
                "KIT_TEMPLATE_MISSING",
                f"kit {manifest.id!r} declares {rel!r} but has no template for it",
                kit_id=manifest.id,
            )
        with open(template_path, "r", encoding="utf-8") as handle:
            templates[rel] = handle.read()
    return Kit(manifest=manifest, folder=folder, templates=templates)


def load_catalog(root: Optional[str] = None) -> list[Kit]:
    """Walk the kit root and load every `kit.json`. Deterministic order."""
    root = root or kits_root()
    kits: list[Kit] = []
    if not os.path.isdir(root):
        return kits
    for name in sorted(os.listdir(root)):
        folder = os.path.join(root, name)
        if os.path.isdir(folder) and os.path.isfile(os.path.join(folder, "kit.json")):
            kits.append(load_kit(folder))
    return kits


def list_kits(root: Optional[str] = None) -> list[dict[str, Any]]:
    return [kit.manifest.public() for kit in load_catalog(root)]


def get_kit(kit_id: str, root: Optional[str] = None) -> Optional[Kit]:
    folder = os.path.join(root or kits_root(), str(kit_id))
    if not os.path.isfile(os.path.join(folder, "kit.json")):
        return None
    return load_kit(folder)


# ── Rendering ────────────────────────────────────────────────────────────────


def _render(text: str, values: dict[str, Any]) -> str:
    def _sub(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key not in values:
            raise KitLoadError("KIT_INPUT_MISSING", f"template needs {key!r}, which was not supplied")
        return str(values[key])

    return _TEMPLATE_RE.sub(_sub, text)


def _validate_inputs(manifest: KitManifest, values: dict[str, Any]) -> dict[str, Any]:
    """Validate the supplied values against the declared typed inputs."""
    declared = {i.name: i for i in manifest.inputs}
    unknown = set(values) - set(declared)
    if unknown:
        raise KitLoadError(
            "KIT_INPUT_INVALID",
            f"unknown input(s): {', '.join(sorted(unknown))}",
            kit_id=manifest.id,
        )
    resolved: dict[str, Any] = {}
    for name, spec in declared.items():
        if name not in values or values[name] in (None, ""):
            if spec.required:
                raise KitLoadError("KIT_INPUT_MISSING", f"input {name!r} is required", kit_id=manifest.id)
            continue
        value = values[name]
        if spec.kind == "choice":
            if str(value) not in spec.choices:
                raise KitLoadError(
                    "KIT_INPUT_INVALID",
                    f"{name!r} must be one of {', '.join(spec.choices)}",
                    kit_id=manifest.id,
                )
        elif spec.kind == "identifier":
            if not re.match(r"^[a-z][a-z0-9_]*$", str(value)):
                raise KitLoadError(
                    "KIT_INPUT_INVALID",
                    f"{name!r} must be a lowercase identifier",
                    kit_id=manifest.id,
                )
        elif spec.kind == "integer":
            try:
                int(value)
            except (TypeError, ValueError) as exc:
                raise KitLoadError("KIT_INPUT_INVALID", f"{name!r} must be a whole number") from exc
        elif spec.kind == "boolean":
            if not isinstance(value, bool):
                raise KitLoadError("KIT_INPUT_INVALID", f"{name!r} must be true or false", kit_id=manifest.id)
        resolved[name] = value
    return resolved


def render_kit(kit_id: str, values: dict[str, Any], root: Optional[str] = None) -> dict[str, str]:
    """Render the kit's templates to the declared output set.

    Returns `{declared_relative_path: rendered_text}`. NOTHING outside `produces`
    is ever returned — that is the closed-set guarantee.
    """
    kit = get_kit(kit_id, root)
    if kit is None:
        raise KitLoadError("KIT_UNKNOWN", f"no kit named {kit_id!r}", kit_id=kit_id)
    resolved = _validate_inputs(kit.manifest, values or {})
    # Derived, always-available values: the kit's naming input in common case
    # forms. The naming input is `source_name`/`name`, else the first declared
    # `*_name` identifier, else the kit id — so a kit picks its own slug.
    derived = dict(resolved)
    raw = _naming_value(kit.manifest, resolved)
    derived.setdefault("module_name", _slug(raw))
    derived.setdefault("class_name", _pascal(raw))
    # The declared paths may themselves carry placeholders; render them for the
    # closed-set comparison so `{{module_name}}` is compared as its concrete value.
    declared = {_render(rel, derived) for rel in kit.manifest.produces}
    out: dict[str, str] = {}
    for rel, template in kit.templates.items():
        # The output PATH itself may reference inputs (e.g. my_source.py).
        target = _render(rel, derived)
        out[target] = _render(template, derived)
    escaped = set(out) - declared
    if escaped:
        raise KitLoadError(
            "OUTPUT_OUTSIDE_DECLARED_SET",
            f"rendering produced undeclared output(s): {', '.join(sorted(escaped))}",
            kit_id=kit_id,
        )
    return out


def render_checks(kit_id: str, values: dict[str, Any], root: Optional[str] = None) -> list[dict[str, Any]]:
    """Render the kit's check args with the same substitutions as the files.

    A `checks[].args` path may reference `{{module_name}}` (or another input); it is
    rendered here so the command broker is handed a concrete path.
    """
    kit = get_kit(kit_id, root)
    if kit is None:
        raise KitLoadError("KIT_UNKNOWN", f"no kit named {kit_id!r}", kit_id=kit_id)
    resolved = _validate_inputs(kit.manifest, values or {})
    derived = dict(resolved)
    raw = _naming_value(kit.manifest, resolved)
    derived.setdefault("module_name", _slug(raw))
    derived.setdefault("class_name", _pascal(raw))

    def _sub(value: Any) -> Any:
        if isinstance(value, str):
            return _render(value, derived)
        if isinstance(value, list):
            return [_sub(v) for v in value]
        if isinstance(value, dict):
            return {k: _sub(v) for k, v in value.items()}
        return value

    checks: list[dict[str, Any]] = []
    for check in kit.manifest.checks:
        checks.append({
            "commandClass": check.command_class,
            "args": {key: _sub(val) for key, val in (check.args or {}).items()},
        })
    return checks


def _naming_value(manifest: KitManifest, resolved: dict[str, Any]) -> str:
    """The value the kit's naming placeholder derives from."""
    for key in ("source_name", "name"):
        if resolved.get(key):
            return str(resolved[key])
    for spec in manifest.inputs:
        if spec.kind == "identifier" and spec.name.endswith("_name") and resolved.get(spec.name):
            return str(resolved[spec.name])
    for spec in manifest.inputs:
        if spec.kind == "identifier" and resolved.get(spec.name):
            return str(resolved[spec.name])
    return manifest.id


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(text).strip().lower()).strip("_") or "generated"


def _pascal(text: str) -> str:
    return "".join(part.capitalize() for part in _slug(text).split("_") if part) or "Generated"


__all__ = [
    "Kit",
    "KitLoadError",
    "get_kit",
    "kits_root",
    "library_root",
    "list_kits",
    "load_catalog",
    "load_kit",
    "render_kit",
]
