"""Project registry for the video pipeline (filesystem-backed).

A project is a stable id, a name, a KIND, a revision and a spec:

- ``title_card`` — the built-in BlackEclipse title card; its spec must be empty.
- ``storyboard`` — a versioned, validated scene specification (see
  ``video/spec.py``); revisions bump ``revision`` so a re-render is traceable.

Layout: ``<root>/projects/<id>.json`` — one file per project, atomic writes
(tmp + os.replace), ids format-checked so a project id can never traverse paths.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from ..persistence import now_iso
from .models import (
    PROJECT_SCHEMA_VERSION,
    SUPPORTED_PROJECT_KINDS,
    VideoError,
    new_project_id,
)
from .spec import validate_storyboard

_ID_RE = re.compile(r"^vprj_[0-9a-f]{16}$")
_MAX_SPEC_PROBLEMS_REPORTED = 8


class VideoProjectStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    # ── lifecycle ────────────────────────────────────────────────────────────

    def create(
        self, *, name: str, kind: str = "title_card", spec: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        clean_name = str(name or "").strip()
        if not clean_name or len(clean_name) > 200:
            raise VideoError("INVALID_INPUT", "a project needs a name (1-200 characters)")
        clean_kind = str(kind or "").strip().lower()
        if clean_kind not in SUPPORTED_PROJECT_KINDS:
            raise VideoError(
                "UNSUPPORTED_PROJECT_KIND",
                f"unknown project kind {kind!r}; supported: {', '.join(SUPPORTED_PROJECT_KINDS)}",
            )
        clean_spec = self._checked_spec(clean_kind, spec)
        project = {
            "id": new_project_id(),
            "name": clean_name,
            "kind": clean_kind,
            "spec": clean_spec,
            "schemaVersion": PROJECT_SCHEMA_VERSION,
            "revision": 1,
            "createdAt": now_iso(),
            "updatedAt": now_iso(),
        }
        self._write(project)
        return project

    def update(
        self, project_id: str, *, name: Optional[str] = None,
        spec: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Revise a project in place; the revision counter is bumped so a
        re-render is traceable without rebuilding anything."""
        project = self.get(project_id)
        if project is None:
            raise VideoError("PROJECT_NOT_FOUND", f"project {project_id!r} was not found")
        if name is not None:
            clean_name = str(name).strip()
            if not clean_name or len(clean_name) > 200:
                raise VideoError("INVALID_INPUT", "a project name must be 1-200 characters")
            project["name"] = clean_name
        if spec is not None:
            project["spec"] = self._checked_spec(str(project.get("kind") or ""), spec)
        project["revision"] = int(project.get("revision") or 1) + 1
        project["updatedAt"] = now_iso()
        self._write(project)
        return project

    def get(self, project_id: str) -> Optional[dict[str, Any]]:
        path = self._path(project_id)
        if path is None or not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - a corrupt record is data, not a crash
            raise VideoError("PROJECT_CORRUPT", f"project {project_id!r} could not be read: {exc}") from exc
        return data if isinstance(data, dict) else None

    def list(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        for path in sorted(self._root.glob("vprj_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - skip unreadable records, never crash a list
                continue
            if isinstance(data, dict):
                projects.append(data)
        projects.sort(key=lambda p: str(p.get("createdAt") or ""))
        return projects

    # ── validation ───────────────────────────────────────────────────────────

    def validate(self, project: dict[str, Any]) -> list[str]:
        """Spec-level problems only; environment checks live in the service."""
        problems: list[str] = []
        if not str(project.get("id") or ""):
            problems.append("the project has no id")
        if not str(project.get("name") or "").strip():
            problems.append("the project has no name")
        kind = str(project.get("kind") or "").strip().lower()
        if kind not in SUPPORTED_PROJECT_KINDS:
            problems.append(
                f"unsupported project kind {project.get('kind')!r}; supported: {', '.join(SUPPORTED_PROJECT_KINDS)}"
            )
            return problems
        if not isinstance(project.get("spec", {}), dict):
            problems.append("the project spec must be an object")
            return problems
        if kind == "storyboard":
            problems.extend(validate_storyboard(project.get("spec") or {}))
        elif project.get("spec"):
            problems.append("a title_card project takes no spec (use kind `storyboard` for scenes)")
        return problems

    # ── internals ────────────────────────────────────────────────────────────

    def _checked_spec(self, kind: str, spec: Optional[dict[str, Any]]) -> dict[str, Any]:
        if spec is not None and not isinstance(spec, dict):
            raise VideoError("INVALID_INPUT", "a project spec must be an object")
        clean_spec = dict(spec or {})
        if kind == "storyboard":
            problems = validate_storyboard(clean_spec)
            if problems:
                shown = problems[:_MAX_SPEC_PROBLEMS_REPORTED]
                extra = len(problems) - len(shown)
                detail = "; ".join(shown) + (f" (+{extra} more)" if extra > 0 else "")
                raise VideoError("INVALID_SPEC", detail)
        elif clean_spec:
            raise VideoError(
                "INVALID_INPUT",
                "a title_card project takes no spec; use kind `storyboard` for scene specs",
            )
        return clean_spec

    def _path(self, project_id: str) -> Optional[Path]:
        text = str(project_id or "").strip()
        if not _ID_RE.match(text):
            return None
        return self._root / f"{text}.json"

    def _write(self, project: dict[str, Any]) -> None:
        path = self._path(str(project.get("id") or ""))
        if path is None:
            raise VideoError("INVALID_INPUT", "refusing to write a project with an invalid id")
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)


__all__ = ["VideoProjectStore"]
