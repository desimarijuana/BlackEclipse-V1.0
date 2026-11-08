"""The landing pipeline (Phase 22 / S4).

A change is not "landed" because a file was copied. It is landed when the
project's own checks passed. This module turns that sentence into data and one
ordered, visible pipeline:

  typecheck -> tests -> size -> secrets -> (build, when the front end changed)
  -> docs obligation

Rules:

  * **The exit code is the judge.** A check that did not run is never "passed";
    it is `skipped` or `error` with a reason.
  * **Stop at the first required failure.** The remaining checks are reported as
    skipped, so a reader sees exactly where it stopped.
  * **No shell string.** Every command is a fixed argv list; an override file
    can add a check but cannot smuggle a shell.
  * **The plan is data.** ``.black-eclipse/land.json`` can replace the defaults;
    an invalid file falls back to the defaults and says so.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

MAX_CHECKS = 20
MAX_TIMEOUT_S = 3_600
DEFAULT_TIMEOUT_S = 900

#: A check is either a fixed command or the repo's documentation obligation.
CheckKind = str  # "command" | "docs"


@dataclass(frozen=True)
class LandCheck:
    id: str
    label: str
    kind: str
    argv: tuple[str, ...] = ()
    required: bool = True
    timeout_s: int = DEFAULT_TIMEOUT_S
    when: str = "always"  # "always" | "frontend"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "argv": list(self.argv),
            "required": self.required,
            "timeoutSeconds": self.timeout_s,
            "when": self.when,
        }


@dataclass(frozen=True)
class LandPlan:
    changed: tuple[str, ...]
    checks: tuple[LandCheck, ...]
    source: str  # "defaults" | "project" | "detected" | "none"
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed": list(self.changed),
            "checks": [check.to_dict() for check in self.checks],
            "source": self.source,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class CheckResult:
    id: str
    label: str
    status: str  # "passed" | "failed" | "error" | "skipped"
    exit_code: Optional[int]
    output_digest: str
    output_tail: str
    required: bool
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "exitCode": self.exit_code,
            "outputDigest": self.output_digest,
            "outputTail": self.output_tail,
            "required": self.required,
            "durationMs": self.duration_ms,
        }


@dataclass(frozen=True)
class LandResult:
    ok: bool
    results: tuple[CheckResult, ...]
    failed: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "failed": self.failed,
            "results": [result.to_dict() for result in self.results],
        }


def _norm(path: str) -> str:
    text = str(path or "").replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _default_checks(*, frontend: bool) -> list[LandCheck]:
    checks = [
        LandCheck("typecheck", "Typecheck", "command", ("npx", "tsc", "--noEmit"), timeout_s=600),
        LandCheck("tests", "Tests", "command", ("npm", "run", "test"), timeout_s=1_800),
        LandCheck("size", "Size budget", "command", ("npm", "run", "check:size"), timeout_s=300),
        LandCheck("secrets", "Secret scan", "command", ("npm", "run", "check:secrets"), timeout_s=300),
        LandCheck("docs", "Change log entry", "docs"),
    ]
    if frontend:
        checks.append(LandCheck(
            "build", "Build the app", "command", ("npm", "run", "build"),
            timeout_s=1_200, when="frontend",
        ))
    return checks


def _load_overrides(root: Optional[Path]) -> tuple[Optional[list[LandCheck]], list[str]]:
    if root is None:
        return None, []
    path = root / ".black-eclipse" / "land.json"
    if not path.is_file():
        return None, []
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return None, [f"land.json ignored: {exc}"]
    items = raw.get("checks") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        return None, ["land.json ignored: expected a non-empty list"]
    if len(items) > MAX_CHECKS:
        return None, [f"land.json ignored: more than {MAX_CHECKS} checks"]
    parsed: list[LandCheck] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return None, [f"land.json ignored: check {index} is not an object"]
        kind = str(item.get("kind") or "command")
        argv = item.get("argv") or []
        if kind not in ("command", "docs"):
            return None, [f"land.json ignored: check {index} has an unknown kind"]
        if kind == "command" and (
            not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv)
        ):
            return None, [f"land.json ignored: check {index} needs a string argv list"]
        try:
            timeout_s = int(item.get("timeoutSeconds") or DEFAULT_TIMEOUT_S)
        except (TypeError, ValueError):
            return None, [f"land.json ignored: check {index} has a bad timeout"]
        parsed.append(LandCheck(
            id=str(item.get("id") or f"check_{index}")[:80],
            label=str(item.get("label") or item.get("id") or f"Check {index + 1}")[:120],
            kind=kind,
            argv=tuple(argv),
            required=bool(item.get("required", True)),
            timeout_s=max(1, min(timeout_s, MAX_TIMEOUT_S)),
            when=str(item.get("when") or "always"),
        ))
    return parsed, []


def _declares_pytest(root: Path) -> bool:
    """True when the project itself declares pytest (or ships a conftest)."""
    if (root / "conftest.py").is_file():
        return True
    for name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "setup.cfg", "Pipfile"):
        path = root / name
        if not path.is_file():
            continue
        try:
            if "pytest" in path.read_text(encoding="utf-8", errors="replace").lower():
                return True
        except OSError:
            continue
    return False


def _is_harness_repo(root: Path) -> bool:
    """The repo Eclipse itself runs from keeps its own full landing pipeline."""
    return (root / "python" / "harness" / "main.py").is_file()


def _detect_checks(root: Path) -> tuple[list[LandCheck], list[str]]:
    """The project's own checks, discovered from its manifests. Pure, bounded.

    Fixed argv only (no shell string, no interpolation), deduplicated by id, and
    never invented for a stack that is not present. An unrecognised project gets
    NO checks and a warning — running Eclipse's checks in someone else's repo
    would be worse than saying nothing.
    """
    checks: list[LandCheck] = []
    warnings: list[str] = []
    seen: set[str] = set()

    def add(check_id: str, label: str, argv: tuple[str, ...], timeout_s: int = 900) -> None:
        if check_id in seen or len(checks) >= MAX_CHECKS:
            return
        seen.add(check_id)
        checks.append(LandCheck(check_id, label, "command", argv, timeout_s=timeout_s))

    package = root / "package.json"
    if package.is_file():
        scripts: dict[str, Any] = {}
        try:
            raw = json.loads(package.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict) and isinstance(raw.get("scripts"), dict):
                scripts = raw["scripts"]
        except (OSError, ValueError) as exc:
            warnings.append(f"package.json ignored: {exc}")
        if "typecheck" in scripts:
            add("typecheck", "Typecheck", ("npm", "run", "typecheck"))
        elif (root / "tsconfig.json").is_file():
            add("typecheck", "Typecheck", ("npx", "tsc", "--noEmit"), 600)
        if "test" in scripts:
            add("tests", "Tests", ("npm", "test"), 1_800)
        if "build" in scripts:
            add("build", "Build", ("npm", "run", "build"), 1_200)

    if (root / "Cargo.toml").is_file():
        add("tests", "Tests", ("cargo", "test", "--quiet"), 1_800)
    if (root / "go.mod").is_file():
        add("tests", "Tests", ("go", "test", "./..."), 1_800)
    if _declares_pytest(root):
        add("tests", "Tests", ("python", "-m", "pytest", "-q"), 1_800)

    makefile = root / "Makefile"
    if makefile.is_file():
        try:
            text = makefile.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if re.search(r"(?m)^test\s*:", text):
            add("tests", "Tests", ("make", "test"), 1_800)

    if (root / "docs" / "CHANGELOG.md").is_file():
        checks.append(LandCheck("docs", "Change log entry", "docs"))

    return checks, warnings


def plan_land_checks(files: list[str] | tuple[str, ...], root: Optional[Path] = None) -> LandPlan:
    """The ordered checks for a set of changed files. Pure.

    Precedence: an explicit `.black-eclipse/land.json` wins; the harness repo
    keeps its own pipeline; any other project gets checks discovered from its
    manifests; a project Eclipse cannot recognise gets none (with a warning).
    """
    changed = tuple(_norm(path) for path in files if str(path or "").strip())
    frontend = any(path.startswith("src/") for path in changed)
    overrides, warnings = _load_overrides(root)
    if overrides is not None:
        checks = [check for check in overrides if check.when != "frontend" or frontend]
        return LandPlan(changed, tuple(checks), "project", tuple(warnings))
    if root is not None and not _is_harness_repo(Path(root)):
        detected, detected_warnings = _detect_checks(Path(root))
        if detected:
            return LandPlan(changed, tuple(detected), "detected", tuple(warnings + detected_warnings))
        return LandPlan(
            changed, (), "none",
            tuple(warnings + ["No checks found for this project; add .black-eclipse/land.json."]),
        )
    return LandPlan(changed, tuple(_default_checks(frontend=frontend)), "defaults", tuple(warnings))


def docs_obligation(changed: list[str] | tuple[str, ...]) -> tuple[bool, str]:
    """A non-test change must carry a changelog entry. Deterministic and honest."""
    normalized = [_norm(path) for path in changed]
    if not normalized:
        return False, "No changed files were named, so the change log cannot be checked."
    touched = any(
        path == "docs/CHANGELOG.md"
        or path.endswith("/docs/CHANGELOG.md")
        or path.startswith("docs/changelog/")
        or "/docs/changelog/" in path
        for path in normalized
    )
    if touched:
        return True, "A changelog entry is part of this change."
    return False, "Add a dated entry to docs/CHANGELOG.md, or say why none is needed."


def _resolve_argv(argv: tuple[str, ...]) -> list[str]:
    """Resolve the executable and make a Windows .cmd runnable without a shell."""
    if not argv:
        return []
    exe = shutil.which(argv[0]) or argv[0]
    if os.name == "nt" and str(exe).lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", str(exe), *argv[1:]]
    return [str(exe), *argv[1:]]


def _subprocess_runner(check: LandCheck, root: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            _resolve_argv(check.argv), cwd=str(root), capture_output=True,
            text=True, timeout=check.timeout_s, shell=False,
        )
        return {
            "exitCode": completed.returncode,
            "output": (completed.stdout or "") + (completed.stderr or ""),
        }
    except subprocess.TimeoutExpired:
        return {"exitCode": None, "output": f"timed out after {check.timeout_s}s", "timedOut": True}
    except OSError as exc:
        return {"exitCode": None, "output": str(exc), "error": True}


def _digest(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:32]


def run_land_plan(
    plan: LandPlan,
    *,
    root: Path,
    runner: Optional[Callable[[LandCheck, Path], dict[str, Any]]] = None,
) -> LandResult:
    """Run the plan in order, stopping at the first required failure."""
    execute = runner or _subprocess_runner
    results: list[CheckResult] = []
    failed: Optional[str] = None
    for check in plan.checks:
        if failed is not None:
            results.append(CheckResult(
                check.id, check.label, "skipped", None, "", "", check.required, 0,
            ))
            continue
        if check.kind == "docs":
            ok, reason = docs_obligation(plan.changed)
            results.append(CheckResult(
                check.id, check.label, "passed" if ok else "failed", 0 if ok else 1,
                _digest(reason), reason, check.required, 0,
            ))
            if not ok and check.required:
                failed = check.id
            continue
        try:
            outcome = execute(check, root)
        except Exception as exc:  # noqa: BLE001 - an unrunnable check is an error
            outcome = {"exitCode": None, "output": str(exc), "error": True}
        code = outcome.get("exitCode")
        output = str(outcome.get("output") or "")
        if outcome.get("timedOut") or outcome.get("error") or code != 0:
            status = "error" if outcome.get("timedOut") or outcome.get("error") else "failed"
            results.append(CheckResult(
                check.id, check.label, status, code if isinstance(code, int) else None,
                _digest(output), output[-4_000:], check.required,
                int(outcome.get("durationMs") or 0),
            ))
            if check.required:
                failed = check.id
            continue
        results.append(CheckResult(
            check.id, check.label, "passed", 0, _digest(output), output[-1_500:],
            check.required, int(outcome.get("durationMs") or 0),
        ))
    return LandResult(ok=failed is None, results=tuple(results), failed=failed)


__all__ = [
    "CheckResult",
    "DEFAULT_TIMEOUT_S",
    "LandCheck",
    "LandPlan",
    "LandResult",
    "MAX_CHECKS",
    "MAX_TIMEOUT_S",
    "docs_obligation",
    "plan_land_checks",
    "run_land_plan",
]
