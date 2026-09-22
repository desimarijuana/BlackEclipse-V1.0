"""Skill library loader — reads `skill.json` + `SKILL.md` folders from disk.

The library is the authoring format: a folder per skill with a machine-readable
`skill.json` (the manifest) and a human-readable `SKILL.md` (the procedure).
Loading is deliberately layered so progressive disclosure is possible:

  * `load_catalog()` reads only `skill.json` (metadata) — cheap, no prose.
  * `load_instructions(entry)` reads `SKILL.md` — only for a selected skill.

Nothing here executes a skill or trusts its prose; the manifest is validated by
pydantic, and existence of the instruction file is checked (never its content
semantics).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import ValidationError

from .manifest import SkillManifest


class SkillLoadError(Exception):
    """A skill folder could not be loaded (missing/invalid manifest)."""

    def __init__(self, location: str, message: str) -> None:
        super().__init__(f"{location}: {message}")
        self.location = location
        self.message = message


@dataclass
class LoadedSkill:
    """One library entry: a validated manifest + where its prose lives."""

    manifest: SkillManifest
    folder: str
    instructions_path: Optional[str]
    cases_path: Optional[str] = None

    def load_cases(self) -> list[dict[str, Any]]:
        """Read deterministic evaluation cases (`tests/cases.json`).

        Each case is `{caseId, name, kind, input?, expected?}`. Absent file ⇒
        an empty list (the skill simply has no attached cases).
        """
        if not self.cases_path or not os.path.isfile(self.cases_path):
            return []
        with open(self.cases_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            data = data.get("cases", [])
        if not isinstance(data, list):
            return []
        out: list[dict[str, Any]] = []
        for index, case in enumerate(data):
            if not isinstance(case, dict):
                continue
            out.append({
                "caseId": str(case.get("caseId") or case.get("id") or f"case-{index + 1}"),
                "name": str(case.get("name") or case.get("caseId") or f"case-{index + 1}"),
                "kind": str(case.get("kind") or "schema"),
                "input": case.get("input"),
                "expected": case.get("expected"),
            })
        return out

    def load_instructions(self, max_chars: int = 20_000) -> str:
        """Read the procedure text. Bounded so a runaway file cannot blow the
        prompt. Returns "" when the skill is manifest-only."""
        if not self.instructions_path or not os.path.isfile(self.instructions_path):
            return ""
        with open(self.instructions_path, "r", encoding="utf-8") as handle:
            return handle.read(max_chars)


def library_root() -> str:
    """The shipped skill library folder (`python/harness/skills/library`)."""
    return os.path.join(os.path.dirname(__file__), "library")


def _manifest_from_file(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise SkillLoadError(path, f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SkillLoadError(path, "skill.json must be a JSON object")
    return data


def load_skill_folder(folder: str) -> LoadedSkill:
    """Load and validate one skill folder. Raises `SkillLoadError`."""
    manifest_path = os.path.join(folder, "skill.json")
    if not os.path.isfile(manifest_path):
        raise SkillLoadError(folder, "skill.json not found")
    raw = _manifest_from_file(manifest_path)
    try:
        manifest = SkillManifest(**raw)
    except ValidationError as exc:
        raise SkillLoadError(manifest_path, f"invalid manifest: {exc}") from exc

    instructions_path: Optional[str] = None
    if manifest.instructions:
        candidate = os.path.join(folder, manifest.instructions)
        # An instruction file that is declared but missing is a load error — a
        # skill whose prose silently vanished must not be executable.
        if not os.path.isfile(candidate):
            raise SkillLoadError(
                manifest_path, f"declared instructions {manifest.instructions!r} not found"
            )
        instructions_path = candidate

    # An optional deterministic case file. It is validated for shape on load so
    # a malformed case file is surfaced rather than silently ignored.
    cases_path: Optional[str] = None
    candidate_cases = os.path.join(folder, "tests", "cases.json")
    if os.path.isfile(candidate_cases):
        try:
            with open(candidate_cases, "r", encoding="utf-8") as handle:
                json.load(handle)
        except json.JSONDecodeError as exc:
            raise SkillLoadError(candidate_cases, f"invalid cases JSON: {exc}") from exc
        cases_path = candidate_cases

    return LoadedSkill(
        manifest=manifest, folder=folder,
        instructions_path=instructions_path, cases_path=cases_path,
    )


def load_catalog(root: Optional[str] = None) -> list[LoadedSkill]:
    """Walk the library and load every `skill.json`. Folders without one are
    ignored (they may hold references/tests). A malformed manifest is surfaced
    as a `SkillLoadError`, not silently skipped — an operator must know."""
    root = root or library_root()
    loaded: list[LoadedSkill] = []
    if not os.path.isdir(root):
        return loaded
    for current, _dirs, files in os.walk(root):
        if "skill.json" in files:
            loaded.append(load_skill_folder(current))
    # Deterministic order so registration/first-wins is reproducible.
    loaded.sort(key=lambda item: item.manifest.id)
    return loaded


__all__ = [
    "LoadedSkill",
    "SkillLoadError",
    "library_root",
    "load_catalog",
    "load_skill_folder",
]
