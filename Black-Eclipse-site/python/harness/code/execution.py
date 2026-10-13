"""Bounded, reproducible analysis execution — Phase 3's sandbox, aimed at a task.

This module never decides what is TRUE. It decides what was COMPUTED, records
exactly enough to re-derive it, and hands the result to a renderer that is
forbidden to present it as retrieved data.

The one dangerous line, stated once: a code sandbox can trivially produce a
plausible-looking number from invented inputs. The provenance rule (§6.2) is what
keeps such a number from ever being mistaken for a retrieved one:

  * every execution output is ``kind="computed"`` — there is NO code path that
    produces ``retrieved`` from an execution;
  * a computed number WITH no provenance record renders ``UNAVAILABLE``, never a
    bare number (fail-closed);
  * a computed number CANNOT enter a research claim — the only legal path is
    re-expression through ``research/calculations.py``, which is an explicit act,
    never an automatic promotion.

The import check is a real AST walk over the source — never ``eval``/``exec`` and
never a regex over the raw string as the guard.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from . import sandbox as sandbox_mod
from .commands import VENDORED_RELPATH, _resolve_executable

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

# The explicit, small import allowlist. A module outside it is refused by the AST
# inspection. `numpy`/`pandas` are present in the vendored interpreter; a missing
# optional module fails the RUN honestly (an import error), never silently.
IMPORT_ALLOWLIST: tuple[str, ...] = (
    "math", "statistics", "decimal", "fractions", "datetime", "json", "csv",
    "itertools", "functools", "collections", "typing", "re", "random",
    "numpy", "pandas",
)

DEFAULT_TIMEOUT_S: int = 120
DEFAULT_MEMORY_MB: int = 2048
MAX_OUTPUT_BYTES: int = 200_000
MAX_SOURCE_CHARS: int = 20_000
# Resource limits applied to every analysis run (R3-02). The wall-clock timeout
# is always enforced; these bound a runaway analysis in cpu/memory/processes.
MAX_PROCESSES: int = 64
MAX_CPU_SECONDS: int = 600

# Refusal codes (stable, testable). `SANDBOX_UNAVAILABLE` is Phase 3's.
SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"
ANALYSIS_NOT_ENABLED = "ANALYSIS_NOT_ENABLED"
IMPORT_NOT_ALLOWED = "IMPORT_NOT_ALLOWED"
INPUT_INVALID = "INPUT_INVALID"
OUTPUT_TOO_LARGE = "OUTPUT_TOO_LARGE"
TIMED_OUT = "TIMED_OUT"
SOURCE_INVALID = "SOURCE_INVALID"


class AnalysisError(ValueError):
    """A structured analysis refusal. ``code`` is stable and testable."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


# ── Provenance (§6.2) ────────────────────────────────────────────────────────

ProvenanceKind = Literal["retrieved", "computed"]


@dataclass(frozen=True)
class Provenance:
    """Where a number came from. A computed number is ALWAYS kind="computed"."""

    kind: ProvenanceKind
    label: str                       # plain words for the surface
    detail: str                      # the method / period sentence
    source_digest: Optional[str] = None   # computed only
    citation: Optional[str] = None        # retrieved only

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "label": self.label, "detail": self.detail,
            "sourceDigest": self.source_digest, "citation": self.citation,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> Optional["Provenance"]:
        if not isinstance(raw, dict):
            return None
        kind = raw.get("kind")
        if kind not in ("retrieved", "computed"):
            return None
        if not raw.get("label") or not raw.get("detail"):
            return None
        return cls(
            kind=kind, label=str(raw["label"]), detail=str(raw["detail"]),
            source_digest=raw.get("sourceDigest") or raw.get("source_digest"),
            citation=raw.get("citation"),
        )


def computed_provenance(purpose: str, *, source_digest: str, detail: str = "") -> Provenance:
    """The ONE constructor for a computed provenance record."""
    return Provenance(
        kind="computed",
        label="Worked out by Eclipse",
        detail=(detail or purpose)[:300],
        source_digest=source_digest,
    )


# The fail-closed rule, stated once and enforced by the renderer.
UNAVAILABLE_COMPUTED = "UNAVAILABLE"


def render_value(value: Any, provenance: Optional[Provenance]) -> dict[str, Any]:
    """Render a number with its provenance — the ONE renderer seam.

    A computed number without a provenance record is rendered ``UNAVAILABLE``,
    never a bare number: a missing record is a bug, and it fails closed.
    """
    if provenance is None:
        return {"status": UNAVAILABLE_COMPUTED, "value": None,
                "provenance": None, "reason": "this number has no record of where it came from"}
    if provenance.kind == "computed":
        return {"status": "computed", "value": value, "provenance": provenance.to_dict()}
    return {"status": "retrieved", "value": value, "provenance": provenance.to_dict()}


def is_evidence(provenance: Optional[Provenance]) -> bool:
    """Whether a value may enter a research claim. A computed number may NOT.

    The only legal route for a derivation to become evidence is re-expression
    through ``research/calculations.py`` — an explicit act, not this function.
    """
    return provenance is not None and provenance.kind == "retrieved"


# ── Contracts (§6.1) ─────────────────────────────────────────────────────────


class AnalysisInput(BaseModel):
    """Data the run already holds, passed as DATA — never interpolated into source."""

    model_config = _CAMEL

    name: str = Field(..., pattern=r"[a-z_][a-z0-9_]{0,40}")
    kind: Literal["series", "table", "scalar", "text"] = "series"
    value: Any
    provenance: Optional[str] = None


class AnalysisRequest(BaseModel):
    model_config = _CAMEL

    source: str = Field(..., max_length=MAX_SOURCE_CHARS)
    inputs: list[AnalysisInput] = Field(default_factory=list)
    purpose: str = Field(..., min_length=1, max_length=300)
    timeout_s: int = Field(DEFAULT_TIMEOUT_S, ge=1, le=600)


class ArtifactRef(BaseModel):
    model_config = _CAMEL

    name: str
    path: str
    sha256: str
    bytes: int
    media_type: str = "application/octet-stream"


class AnalysisResult(BaseModel):
    model_config = _CAMEL

    status: Literal["ok", "failed", "refused", "timed_out"]
    outputs: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    stderr: str = ""
    source_digest: str = ""
    input_digests: dict[str, str] = Field(default_factory=dict)
    interpreter: str = ""
    package_lock_digest: Optional[str] = None
    duration_ms: int = 0
    provenance: Optional[Provenance] = None
    code: Optional[str] = None

    def to_blob(self) -> dict[str, Any]:
        """Bounded JSON for the persisted `AnalysisRecord`."""
        return {
            "status": self.status,
            "outputs": _bounded_outputs(self.outputs),
            "artifacts": [a.model_dump(by_alias=True) for a in self.artifacts[:20]],
            "sourceDigest": self.source_digest,
            "inputDigests": self.input_digests,
            "interpreter": self.interpreter,
            "packageLockDigest": self.package_lock_digest,
            "durationMs": self.duration_ms,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "code": self.code,
        }


def _bounded_outputs(outputs: dict[str, Any]) -> dict[str, Any]:
    """Keep outputs JSON-safe and size-capped (a runaway result must not bloat)."""
    out: dict[str, Any] = {}
    for key, value in list(outputs.items())[:50]:
        try:
            text = json.dumps(value)
        except (TypeError, ValueError):
            out[key] = str(value)[:2_000]
            continue
        if len(text) > 20_000:
            out[key] = text[:20_000]
        else:
            out[key] = value
    return out


# ── Import inspection (AST, never eval) ──────────────────────────────────────

# Calls refused by NAME. Defense in depth with the restricted builtin set: each
# name is absent at runtime AND refused statically. `__import__` is kept in the
# builtin set only so an ALLOWLISTED `import` statement can execute.
_FORBIDDEN_CALL_NAMES = frozenset((
    "__import__", "importlib", "eval", "exec", "compile", "open", "os", "sys",
    "globals", "locals", "vars", "getattr", "setattr", "delattr", "dir",
    "breakpoint", "input",
))


def check_imports(source: str) -> list[str]:
    """Walk the source's imports with ``ast``; return what is NOT allowed.

    A syntax error raises ``AnalysisError(SOURCE_INVALID)``. Beyond the module
    allowlist this refuses: dynamic-import and reflection calls by name
    (``__import__``, ``eval``, ``getattr``, …), any dunder attribute access
    (``__class__``/``__globals__``/``__subclasses__`` escape chains), the bare
    name ``__builtins__``, and http(s) URL literals (which would let an allowed
    module like pandas fetch over the network).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise AnalysisError(SOURCE_INVALID, f"the analysis could not be read: {exc}") from exc
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in IMPORT_ALLOWLIST:
                    offenders.append(top)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module is None:
                offenders.append("<relative>")
            elif node.module:
                top = node.module.split(".")[0]
                if top not in IMPORT_ALLOWLIST:
                    offenders.append(top)
        elif isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name in _FORBIDDEN_CALL_NAMES:
                offenders.append(str(name))
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                offenders.append(f"{node.attr} (attribute)")
        elif isinstance(node, ast.Name):
            if node.id == "__builtins__":
                offenders.append("__builtins__")
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, str) and "://" in node.value:
                offenders.append("URL literal (network)")
    # De-duplicate, stable order.
    seen: list[str] = []
    for name in offenders:
        if name not in seen:
            seen.append(name)
    return seen


# ── Digests ──────────────────────────────────────────────────────────────────


def _digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:64]


def input_digest(value: Any) -> str:
    try:
        canonical = json.dumps(value, sort_keys=True, default=str)
    except (TypeError, ValueError):
        canonical = str(value)
    return _digest_text(canonical)


def package_lock_digest() -> str:
    """A digest of the resolved package set (name==version), for reproducibility."""
    lines: list[str] = []
    try:
        from importlib.metadata import distributions  # noqa: PLC0415

        for dist in distributions():
            try:
                lines.append(f"{dist.metadata['Name']}=={dist.version}")
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return ""
    lines.sort(key=lambda s: s.lower())
    return _digest_text("\n".join(lines))


def interpreter_path() -> str:
    """The VENDORED interpreter path (never PATH's python), or '' when absent."""
    resolved = _resolve_executable(VENDORED_RELPATH)
    return resolved or ""


# ── The runner ───────────────────────────────────────────────────────────────

_RUNNER_SOURCE = """\
import builtins, json, os, sys

# The analysis program runs with a RESTRICTED builtin set: no open/eval/exec/
# compile/input and no reflection helpers. `__import__` stays because `import`
# statements need it; the AST allowlist decides which imports are legal. This is
# what makes "no network" true by construction: no module that can open a socket
# is reachable, and reflection cannot rebuild one.
_ALLOWED_BUILTINS = (
    "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
    "callable", "chr", "complex", "dict", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "hasattr", "hash", "hex", "id", "int",
    "isinstance", "issubclass", "iter", "len", "list", "map", "max", "min",
    "next", "object", "oct", "ord", "pow", "print", "range", "repr",
    "reversed", "round", "set", "slice", "sorted", "str", "sum", "tuple",
    "type", "zip", "__import__", "__build_class__", "NotImplemented", "Ellipsis",
)

def _safe_builtins():
    allowed = {}
    for name in _ALLOWED_BUILTINS:
        value = getattr(builtins, name, None)
        if value is not None:
            allowed[name] = value
    for name in dir(builtins):
        value = getattr(builtins, name)
        if isinstance(value, type) and issubclass(value, BaseException):
            allowed.setdefault(name, value)
    return allowed

def _load_inputs(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)

def _write_artifact(name, data):
    # The ONLY way user code writes a deliverable: into the run's declared
    # `output/` folder. The name is sanitised to a bare filename.
    safe = os.path.basename(str(name))
    if not safe:
        return None
    path = os.path.join("output", safe)
    text = data if isinstance(data, str) else json.dumps(data, default=str)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return safe

def main():
    payload = _load_inputs(sys.argv[1])
    g = {
        "__name__": "__analysis__",
        "__builtins__": _safe_builtins(),
        "inputs": payload["inputs"],
        "write_artifact": _write_artifact,
    }
    src = payload["source"]
    code = compile(src, "<analysis>", "exec")
    exec(code, g)
    out = g.get("result")
    if out is None:
        out = {k: v for k, v in g.items() if not k.startswith("_") and k != "inputs" and k != "write_artifact"}
    with open(sys.argv[2], "w", encoding="utf-8") as handle:
        json.dump({"ok": True, "outputs": out}, handle, default=str)

main()
"""


def run_analysis(request: AnalysisRequest, *, output_dir: Optional[Path] = None) -> AnalysisResult:
    """Run one analysis in the Phase 3 sandbox. Records enough to re-derive it.

    The program runs in an ISOLATED staging directory (never the repo): its inputs
    arrive as DATA on file, its relative writes land in staging, and only files it
    declares as artefacts are collected. It has no path into the user's files, and
    no network by construction (module allowlist + restricted builtins + no URL
    literals), enforced on top of the OS process bounds.
    """
    t0 = time.monotonic()
    source_digest = _digest_text(request.source)

    # 1. Import allowlist (AST).
    offenders = check_imports(request.source)
    if offenders:
        return AnalysisResult(
            status="refused", code=IMPORT_NOT_ALLOWED, source_digest=source_digest,
            duration_ms=int((time.monotonic() - t0) * 1000),
            stderr=f"disallowed source element(s): {', '.join(offenders)}",
        )

    # 2. Inputs validated against their declared kind (DATA, never source).
    try:
        inputs, digests = _prepare_inputs(request.inputs)
    except AnalysisError as exc:
        return AnalysisResult(
            status="refused", code=exc.code, source_digest=source_digest,
            duration_ms=int((time.monotonic() - t0) * 1000), stderr=exc.reason,
        )

    # 3. The isolation primitive must exist (Phase 3 honesty rule).
    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        return AnalysisResult(
            status="refused", code=SANDBOX_UNAVAILABLE, source_digest=source_digest,
            input_digests=digests, duration_ms=int((time.monotonic() - t0) * 1000),
            stderr="no isolation primitive is available on this computer",
        )

    interpreter = interpreter_path()
    if not interpreter:
        return AnalysisResult(
            status="refused", code=SANDBOX_UNAVAILABLE, source_digest=source_digest,
            input_digests=digests, duration_ms=int((time.monotonic() - t0) * 1000),
            stderr="the analysis interpreter is not installed",
        )

    # 4. Write the payload + runner to a temp dir OUTSIDE the workspace, then run.
    with tempfile.TemporaryDirectory(prefix="be-analysis-") as tmp:
        stage = Path(tmp)
        payload_path = stage / "payload.json"
        out_path = stage / "out.json"
        runner_path = stage / "runner.py"
        payload_path.write_text(
            json.dumps({"source": request.source, "inputs": inputs}), encoding="utf-8"
        )
        runner_path.write_text(_RUNNER_SOURCE, encoding="utf-8")
        # Relative writes land in the staging dir only (cwd), never the repo. The
        # program writes a deliverable into `output/`; only those files are
        # collected.
        (stage / "output").mkdir(exist_ok=True)

        spec = sandbox_mod.RunSpec(
            argv=[interpreter, str(runner_path), str(payload_path), str(out_path)],
            cwd=stage, env=sandbox_mod.build_env(),
            timeout_s=request.timeout_s, output_cap_bytes=MAX_OUTPUT_BYTES, network=False,
            # R3-02: the declared limits are now ENFORCED, not just declared.
            # CPU is a TOTAL-burn guard across the process tree, deliberately
            # above the wall-clock timeout so the wall clock stays the primary
            # bound for a single process.
            cpu_seconds=MAX_CPU_SECONDS,
            memory_mb=DEFAULT_MEMORY_MB,
            process_limit=MAX_PROCESSES,
        )
        raw = sandbox_mod.run(spec)

        duration_ms = int((time.monotonic() - t0) * 1000)
        if raw.timed_out:
            return AnalysisResult(
                status="timed_out", code=TIMED_OUT, source_digest=source_digest,
                input_digests=digests, interpreter=interpreter,
                package_lock_digest=package_lock_digest(), duration_ms=duration_ms,
                stderr=raw.output[:4_000],
            )
        outputs: dict[str, Any] = {}
        ok = False
        if out_path.is_file():
            try:
                parsed = json.loads(out_path.read_text(encoding="utf-8"))
                ok = bool(parsed.get("ok"))
                outputs = _bounded_outputs(parsed.get("outputs") or {})
            except (OSError, ValueError):
                ok = False
        if raw.exit_code != 0 or not ok:
            return AnalysisResult(
                status="failed", source_digest=source_digest, input_digests=digests,
                interpreter=interpreter, package_lock_digest=package_lock_digest(),
                duration_ms=duration_ms, stderr=raw.output[:4_000],
            )

        artifacts = _collect_artifacts(output_dir, stage) if output_dir else []

    return AnalysisResult(
        status="ok", outputs=outputs, artifacts=artifacts, source_digest=source_digest,
        input_digests=digests, interpreter=interpreter,
        package_lock_digest=package_lock_digest(), duration_ms=duration_ms,
        provenance=computed_provenance(request.purpose, source_digest=source_digest),
    )


def _prepare_inputs(items: list[AnalysisInput]) -> tuple[dict[str, Any], dict[str, str]]:
    values: dict[str, Any] = {}
    digests: dict[str, str] = {}
    for item in items:
        _validate_input(item)
        values[item.name] = item.value
        digests[item.name] = input_digest(item.value)
    return values, digests


def _validate_input(item: AnalysisInput) -> None:
    value = item.value
    if item.kind == "series":
        if not isinstance(value, list):
            raise AnalysisError(INPUT_INVALID, f"{item.name}: a series must be a list")
    elif item.kind == "table":
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise AnalysisError(INPUT_INVALID, f"{item.name}: a table must be a list of rows")
    elif item.kind == "scalar":
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise AnalysisError(INPUT_INVALID, f"{item.name}: a value must be a number or text")
    elif item.kind == "text":
        if not isinstance(value, str):
            raise AnalysisError(INPUT_INVALID, f"{item.name}: text must be a string")


def _collect_artifacts(output_dir: Path, stage: Path) -> list[ArtifactRef]:
    """Collect only the files the run wrote into its declared `output/` folder.

    The digest is the identity: identical bytes ⇒ identical digest. A file outside
    `output/` (a stray `__pycache__`, a cache) is NOT collected. Collected copies
    land under the run's artefact directory (gitignored).
    """
    refs: list[ArtifactRef] = []
    source_dir = stage / "output"
    if not source_dir.is_dir():
        return refs
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(source_dir.iterdir()):
        if not path.is_file():
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        name = path.name
        dest = output_dir / name
        try:
            dest.write_bytes(data)
        except OSError:
            continue
        refs.append(ArtifactRef(
            name=name, path=str(dest), sha256=digest, bytes=len(data),
            media_type=_media_type(name),
        ))
    return refs


def _media_type(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".csv"):
        return "text/csv"
    if lowered.endswith(".json"):
        return "application/json"
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".txt") or lowered.endswith(".md"):
        return "text/plain"
    return "application/octet-stream"


__all__ = [
    "ANALYSIS_NOT_ENABLED",
    "AnalysisError",
    "AnalysisInput",
    "AnalysisRequest",
    "AnalysisResult",
    "ArtifactRef",
    "DEFAULT_MEMORY_MB",
    "DEFAULT_TIMEOUT_S",
    "IMPORT_ALLOWLIST",
    "IMPORT_NOT_ALLOWED",
    "INPUT_INVALID",
    "MAX_OUTPUT_BYTES",
    "OUTPUT_TOO_LARGE",
    "Provenance",
    "SANDBOX_UNAVAILABLE",
    "TIMED_OUT",
    "UNAVAILABLE_COMPUTED",
    "check_imports",
    "computed_provenance",
    "input_digest",
    "interpreter_path",
    "is_evidence",
    "package_lock_digest",
    "render_value",
    "run_analysis",
]
