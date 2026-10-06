"""The project analyzer — detect structure, frameworks and entry points.

`ProjectAnalyzer` composes `LanguageDetector` (languages/frameworks/manifests),
the index (file/symbol counts) and the fs git read into ONE structured project
map. It is the source of `ProjectInfo`, the `code_get_project_structure` payload
and the project id the whole engine keys on.

It does not hard-code one project layout: the map is derived from what is present
(apps/packages/services/libs monorepos, src/ layouts and single-package projects
all fall out of the same detector).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional

from .. import policy
from ..fs import git as fs_git
from .language.detect import LanguageDetector, LanguageInfo
from .models import ProjectInfo
from .persistence.index import CodeIndex


def project_id_for(root: Path, workspace_id: str = "") -> str:
    """A stable project id: the workspace id plus a digest of the real root.

    Stable across processes so the same folder always maps to the same index file
    and symbol ids; distinct across roots so two projects never collide.
    """
    real = str(Path(root).resolve()).casefold()
    digest = hashlib.sha256(real.encode("utf-8")).hexdigest()[:12]
    prefix = (workspace_id or "proj").replace(":", "_")
    return f"{prefix}_{digest}"


def project_instance_id(root: Path, workspace_id: str = "") -> str:
    """Alias for `project_id_for` used by the runtime's per-workspace state."""
    return project_id_for(root, workspace_id)


class ProjectAnalyzer:
    """Analyze one project root into a structured `ProjectInfo`."""

    def __init__(self, root: Path, project_id: str, *, workspace_id: str = "") -> None:
        self.root = Path(root)
        self.project_id = project_id
        self.workspace_id = workspace_id

    def detect_languages(self) -> LanguageInfo:
        return LanguageDetector(self.root, ignored_dirs=policy.IGNORED_DIRS).detect()

    def analyze(self, index: Optional[CodeIndex] = None) -> ProjectInfo:
        lang = self.detect_languages()
        info = ProjectInfo(
            root=str(self.root), project_id=self.project_id, workspace_id=self.workspace_id,
            languages=list(lang.languages), frameworks=list(lang.frameworks),
            package_managers=list(lang.package_managers), build_systems=list(lang.build_systems),
            entry_points=list(lang.entry_points), databases=list(lang.databases),
            monorepo=lang.monorepo, project_roots=list(lang.project_roots),
            tests=list(lang.tests), config_files=list(lang.config_files),
        )
        # Fold in the live language counts from the index (more accurate than a walk
        # once indexing has run), and keep the walk's order as the fallback.
        if index is not None:
            try:
                counted = index.languages()
                if counted:
                    info.languages = sorted(counted, key=lambda k: (-counted[k], k))
            except Exception:  # noqa: BLE001 - an index read must not break analysis
                pass
        return info

    def structure(self, index: Optional[CodeIndex] = None, *, max_entries: int = 400) -> dict[str, Any]:
        """The `getProjectStructure` payload: top-level shape + per-folder summary."""
        info = self.analyze(index)
        folders: dict[str, dict[str, Any]] = {}
        scanned = 0
        for dirpath, dirnames, filenames in self._walk_top():
            scanned += 1
            if scanned > max_entries:
                break
            rel = Path(dirpath).relative_to(self.root).as_posix()
            if rel == ".":
                rel = ""
            bucket = folders.setdefault(rel or ".", {"path": rel or ".", "files": 0, "languages": {}})
            for name in filenames:
                from .language.detect import SOURCE_LANGUAGES, detect_language

                language = detect_language(name)
                if language in SOURCE_LANGUAGES:
                    bucket["files"] += 1
                    bucket["languages"][language] = bucket["languages"].get(language, 0) + 1
        git = fs_git.summary(self.root)
        return {
            "project": info.to_dict(),
            "folders": [folders[key] for key in sorted(folders)],
            "git": {k: git.get(k) for k in ("available", "branch", "head", "dirty")},
            "index": index.status() if index is not None else None,
        }

    def _walk_top(self):
        import os

        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in policy.IGNORED_DIRS]
            depth = len(Path(dirpath).relative_to(self.root).parts)
            if depth >= 3:
                dirnames[:] = []
            yield dirpath, dirnames, filenames

    def dependencies_and_languages(self) -> dict[str, Any]:
        lang = self.detect_languages()
        return {
            "languages": lang.languages,
            "frameworks": lang.frameworks,
            "packageManagers": lang.package_managers,
            "buildSystems": lang.build_systems,
            "monorepo": lang.monorepo,
            "projectRoots": lang.project_roots,
        }


__all__ = ["ProjectAnalyzer", "project_id_for", "project_instance_id"]
