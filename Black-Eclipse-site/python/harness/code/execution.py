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
from . import sandbox_tools as st
from .commands import VENDORED_RELPATH, _resolve_executable
from .sandbox_guard import GUARD_SOURCE

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
#: The result file is read only when it is this small: a program that writes a
#: huge result must not make the HOST allocate it (W14).
MAX_RESULT_BYTES: int = 4_000_000
#: The same bound for a collected artifact file.
MAX_ARTIFACT_BYTES: int = 64_000_000
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

    name: str = Field(..., pattern=r"[A-Za-z_][A-Za-z0-9_]{0,40}")
    kind: Literal["series", "table", "scalar", "text"] = "series"
    value: Any
    provenance: Optional[str] = None


class AnalysisRequest(BaseModel):
    model_config = _CAMEL

    source: str = Field(..., max_length=MAX_SOURCE_CHARS)
    inputs: list[AnalysisInput] = Field(default_factory=list)
    purpose: str = Field(..., min_length=1, max_length=300)
    timeout_s: int = Field(DEFAULT_TIMEOUT_S, ge=1, le=600)
    # Phase 18 (additive): extra top-level modules a DECLARED recipe needs (e.g.
    # the figure recipe's `io` + `matplotlib`). A caller cannot set this freely —
    # it comes from the recipe table, never from the model. The AST allowlist
    # stays the boundary; this only widens it by a NAMED, reviewed set.
    extra_imports: tuple[str, ...] = ()
    # Phase 3 (additive): permit the read-only `eclipse_tools` bindings. A caller
    # cannot set this freely either — `run_analysis` only honours it when a host
    # resolver is attached (the analysis_run path). With no resolver the import
    # is refused, so discovery is never activation.
    allow_tools: bool = False


class ArtifactRef(BaseModel):
    model_config = _CAMEL

    name: str
    path: str
    sha256: str
    bytes: int
    media_type: str = "application/octet-stream"


class FigurePayload(BaseModel):
    """Phase 18 (§6.1): the metadata of a figure that crossed the sandbox.

    A figure is a computed artifact, so it carries what it was drawn from (the
    named series and their point counts), the recorded seed when the computation
    was stochastic, and the `computed` label — the same honesty rule numbers
    follow. `is_evidence` is False for anything a figure carries: a picture is
    the easiest way to break the retrieved-vs-computed rule, so the label is
    part of the contract, not a caption.
    """

    model_config = _CAMEL

    kind: Literal["line", "histogram", "heatmap", "paths", "scatter"]
    label: str = "computed"
    artifact: Optional[str] = None
    series: list[dict[str, Any]] = Field(default_factory=list)
    seed: Optional[int] = None

    @property
    def is_evidence(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "label": self.label, "artifact": self.artifact,
            "series": list(self.series), "seed": self.seed, "isEvidence": False,
        }


class AnalysisResult(BaseModel):
    model_config = _CAMEL

    status: Literal["ok", "failed", "refused", "timed_out"]
    outputs: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    # Phase 18 (additive): the figure payload when a recipe drew one — the
    # plotted-series metadata that rides the run blob beside the numbers.
    figure: Optional[FigurePayload] = None
    # Read-only `eclipse_tools` calls this run resolved. Metadata only: names,
    # argument/result digests and status — NEVER a fetched payload (Phase 3 RPC).
    tool_calls: list[st.ToolCallRef] = Field(default_factory=list)
    stderr: str = ""
    source_digest: str = ""
    input_digests: dict[str, str] = Field(default_factory=dict)
    interpreter: str = ""
    package_lock_digest: Optional[str] = None
    duration_ms: int = 0
    # The resource telemetry the backend MEASURED (W14). `None` = unmeasurable
    # on this platform, never a fabricated zero. A memory/CPU/process kill is
    # named in `resource_limit`, so a limit breach is not reported as a plain
    # program error.
    cpu_ms: Optional[float] = None
    memory_peak_mb: Optional[float] = None
    process_count: Optional[int] = None
    resource_limit: Optional[str] = None
    exit_code: Optional[int] = None
    provenance: Optional[Provenance] = None
    code: Optional[str] = None

    def to_blob(self) -> dict[str, Any]:
        """Bounded JSON for the persisted `AnalysisRecord`."""
        return {
            "status": self.status,
            "outputs": _bounded_outputs(self.outputs),
            "artifacts": [a.model_dump(by_alias=True) for a in self.artifacts[:20]],
            "figure": self.figure.to_dict() if self.figure else None,
            "sourceDigest": self.source_digest,
            "inputDigests": self.input_digests,
            "toolCalls": [call.model_dump(by_alias=True) for call in self.tool_calls],
            "interpreter": self.interpreter,
            "packageLockDigest": self.package_lock_digest,
            "durationMs": self.duration_ms,
            "cpuMs": self.cpu_ms,
            "memoryPeakMb": self.memory_peak_mb,
            "processCount": self.process_count,
            "resourceLimit": self.resource_limit,
            "exitCode": self.exit_code,
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


def check_imports(
    source: str,
    extra_allowlist: tuple[str, ...] = (),
    *,
    tool_names: tuple[str, ...] = (),
    allow_url_literals: bool = False,
) -> list[str]:
    """Walk the source's imports with ``ast``; return what is NOT allowed.

    A syntax error raises ``AnalysisError(SOURCE_INVALID)``. Beyond the module
    allowlist this refuses: dynamic-import and reflection calls by name
    (``__import__``, ``eval``, ``getattr``, …), any dunder attribute access
    (``__class__``/``__globals__``/``__subclasses__`` escape chains), the bare
    name ``__builtins__``, and http(s) URL literals (which would let an allowed
    module like pandas fetch over the network).

    `extra_allowlist` widens the module set by a NAMED, reviewed tuple (the
    declared recipe's needs, e.g. the figure recipe's `io` + `matplotlib`).
    Every other rule — reflection, dunders, URL literals — still applies.

    `tool_names` is the read-only `eclipse_tools` binding set. When it is empty,
    `eclipse_tools` is not allowed at all; when non-empty the plain
    `import eclipse_tools` form is allowed and only those attributes may be
    called (no alias / from-import, so the static check is unambiguous).

    `allow_url_literals` is set ONLY by the host, and only for a run whose
    fetch channel is the host-mediated, policy-checked `web_page` binding. A URL
    literal is then just a string: the program still cannot open a socket
    (`socket`/`ssl` stay denied), so the URL can only be resolved through the
    host's SSRF-hardened transport.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise AnalysisError(SOURCE_INVALID, f"the analysis could not be read: {exc}") from exc
    allowed = frozenset(IMPORT_ALLOWLIST) | frozenset(extra_allowlist or ())
    tools_allowed = frozenset(tool_names or ())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top == "eclipse_tools":
                    if alias.name != "eclipse_tools" or alias.asname:
                        offenders.append("eclipse_tools (unsupported import form)")
                    elif top not in allowed:
                        offenders.append(top)
                    continue
                if top not in allowed:
                    offenders.append(top)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module is None:
                offenders.append("<relative>")
            elif node.module:
                top = node.module.split(".")[0]
                if top == "eclipse_tools":
                    offenders.append("eclipse_tools (unsupported import form)")
                    continue
                if top not in allowed:
                    offenders.append(top)
        elif isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name in _FORBIDDEN_CALL_NAMES:
                offenders.append(str(name))
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                offenders.append(f"{node.attr} (attribute)")
            elif isinstance(node.value, ast.Name) and node.value.id == "eclipse_tools":
                if node.attr not in tools_allowed:
                    offenders.append(f"eclipse_tools.{node.attr}")
        elif isinstance(node, ast.Name):
            if node.id == "__builtins__":
                offenders.append("__builtins__")
            elif node.id in _FORBIDDEN_CALL_NAMES:
                # A forbidden name used as a VALUE (an alias: `f = __import__`)
                # is the same escape as calling it — the runtime guard would
                # refuse it anyway, but a clear refusal beats a runtime
                # surprise.
                offenders.append(f"{node.id} (name)")
        elif isinstance(node, ast.Constant):
            if (
                not allow_url_literals
                and isinstance(node.value, str)
                and "://" in node.value
            ):
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


def _interpreter_site_packages() -> list[str]:
    """The site-packages directories of the interpreter that runs the code."""
    exe = interpreter_path()
    if not exe:
        return []
    root = Path(exe).parent
    out = [str(root / "Lib" / "site-packages"), str(root / "lib" / "site-packages")]
    return [p for p in out if Path(p).is_dir()]


def package_lock_digest() -> str:
    """A digest of the RESOLVED package set of the interpreter that runs code.

    The harness process's own distributions are NOT the sandbox's environment:
    hashing them would report an environment the computation never ran in. The
    digest therefore covers the interpreter's installed distributions (name and
    version), so two runs can be compared honestly.
    """
    lines: list[str] = []
    for directory in _interpreter_site_packages():
        try:
            entries = sorted(Path(directory).glob("*.dist-info"))
        except Exception:  # noqa: BLE001
            continue
        for entry in entries:
            stem = entry.name[: -len(".dist-info")]
            name, _, version = stem.rpartition("-")
            if not name:
                name, version = stem, ""
            lines.append(f"{name}=={version}")
    if not lines:
        return ""
    lines.sort(key=lambda s: s.lower())
    return _digest_text("\n".join(lines))


def interpreter_path() -> str:
    """The VENDORED interpreter path (never PATH's python), or '' when absent."""
    resolved = _resolve_executable(VENDORED_RELPATH)
    return resolved or ""


# ── The runner ───────────────────────────────────────────────────────────────

#: The prelude every sandboxed program runs under: the RESTRICTED BUILTINS, the
#: RUNTIME GUARD (the import allowlist + the audit hook + the path confinement)
#: and the read-only `eclipse_tools` channel.
#:
#: The AST allowlist in `check_imports` is a FIRST filter over the source; the
#: guard below is the ENFORCEMENT POINT a program cannot talk around: the
#: child's `__import__` is replaced by one that only imports an allowlisted
#: module, and an audit hook denies the file, process, native-code and network
#: operations a source check cannot see.
ANALYSIS_PRELUDE = GUARD_SOURCE + """\
import builtins, json, os, sys

# The analysis program runs with a RESTRICTED builtin set: no open/eval/exec/
# compile/input and no reflection helpers. `__import__` stays because `import`
# statements need it — but `_guard_install` REPLACES it with one that only
# imports an allowlisted module, so an alias buys nothing.
#
# HONEST SCOPE: this is a Python-level confinement (the program's own folder
# for reading, its own output folder for writing, no network, no other
# process, no native code). It is NOT an OS-level boundary: the child still
# runs as the host user. The path confinement and the audit hook are what make
# the program's own libraries obey it.
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
    # `output/` folder. The name is sanitised to a bare filename. Bytes (a
    # rendered figure) are written verbatim; anything else is text/JSON.
    safe = os.path.basename(str(name))
    if not safe:
        return None
    path = os.path.join("output", safe)
    if isinstance(data, (bytes, bytearray)):
        with open(path, "wb") as handle:
            handle.write(bytes(data))
        return safe
    text = data if isinstance(data, str) else json.dumps(data, default=str)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return safe

_TOOL_SENTINEL = 75

def _tool_module(names, memo, pending_path):
    # The host resolves a read; this module only RECORDS the request and stops.
    # The same program is replayed with the value in `memo`, so no live channel
    # exists between generated code and the host.
    import types
    module = types.ModuleType("eclipse_tools")
    module.__doc__ = "Read-only Eclipse data. Calls are resolved by the host."

    def _make(name):
        def _call(**kwargs):
            args = dict(kwargs)
            try:
                key = name + ":" + json.dumps(
                    args, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False,
                )
            except (TypeError, ValueError) as exc:
                raise TypeError("eclipse_tools arguments must be JSON values") from exc
            if key in memo:
                # A fresh copy: one call cannot mutate what a later call sees.
                return json.loads(json.dumps(memo[key]))
            with open(pending_path, "w", encoding="utf-8") as handle:
                json.dump({"name": name, "args": args}, handle,
                          ensure_ascii=False, allow_nan=False)
            sys.exit(_TOOL_SENTINEL)
        _call.__name__ = name
        _call.__qualname__ = "eclipse_tools." + name
        return _call

    for item in names:
        setattr(module, item, _make(str(item)))
    return module

"""

_RUNNER_SOURCE = ANALYSIS_PRELUDE + """

def main():
    payload = _load_inputs(sys.argv[1])
    for path in payload.get("extra_paths") or []:
        if path and path not in sys.path:
            sys.path.insert(0, path)
    g = {
        "__name__": "__analysis__",
        "__builtins__": _safe_builtins(),
        "inputs": payload["inputs"],
        "write_artifact": _write_artifact,
    }
    if payload.get("tool_bindings"):
        pending_path = payload.get("tool_pending_path")
        memo = payload.get("tool_memo") or {}
        if not isinstance(memo, dict) or not pending_path:
            raise ValueError("the analysis tool channel is incomplete")
        module = _tool_module(payload["tool_bindings"], memo, pending_path)
        sys.modules["eclipse_tools"] = module
        g["eclipse_tools"] = module
    # The guard goes in BEFORE the program runs: the guarded `__import__`, the
    # audit hook and the path confinement are the enforcement point.
    _guard_install(
        payload.get("import_allowlist") or [],
        payload.get("read_roots") or [],
        payload.get("write_roots") or [],
    )
    src = payload["source"]
    code = compile(src, "<analysis>", "exec")
    exec(code, g)
    out = g.get("result")
    if out is None:
        out = {
            k: v for k, v in g.items()
            if not k.startswith("_") and k not in ("inputs", "write_artifact", "eclipse_tools")
        }
    with open(sys.argv[2], "w", encoding="utf-8") as handle:
        json.dump({"ok": True, "outputs": out}, handle, default=str)

main()
"""


@dataclass(frozen=True)
class PreparedAnalysis:
    """A request that passed the AST, input and isolation gates.

    Shared by the one-shot runner and the persistent kernel so a request is
    validated identically regardless of which process model executes it.
    """

    source_digest: str
    allow_tools: bool
    tool_names: tuple[str, ...]
    inputs: dict[str, Any]
    input_digests: dict[str, str]
    interpreter: str
    managed_path: Optional[Path]
    extra_allowlist: tuple[str, ...]
    package_lock_digest: str
    #: The effective import allowlist, exactly as the RUNTIME guard enforces it.
    import_allowlist: tuple[str, ...] = ()


def prepare_analysis(
    request: AnalysisRequest,
    *,
    tool_resolver: Optional[st.ToolResolver] = None,
    tool_allowlist: Optional[tuple[str, ...]] = None,
    allow_url_literals: bool = False,
) -> PreparedAnalysis | AnalysisResult:
    """Validate a request and resolve the isolation primitive, or refuse it.

    This is the single pre-execution gate. A refusal is returned as a finished
    ``AnalysisResult``; a success carries everything both runners need.

    `tool_allowlist` is the HOST's choice of bindings (the analysis lane gets
    the data reads; the scraper lane gets the web binding). `None` keeps the
    analysis lane's own set.
    """
    t0 = time.monotonic()
    source_digest = _digest_text(request.source)
    allow_tools = bool(request.allow_tools) and tool_resolver is not None
    if request.allow_tools and tool_resolver is None:
        return AnalysisResult(
            status="refused", code=st.TOOL_NOT_ALLOWED, source_digest=source_digest,
            duration_ms=int((time.monotonic() - t0) * 1000),
            stderr="read-only data tools aren't available in this analysis",
        )

    managed_path: Optional[Path] = None
    managed_modules: list[str] = []
    try:
        from ..python_env.paths import installed_modules as _installed_modules  # noqa: PLC0415
        from ..python_env.paths import site_packages as _site_packages  # noqa: PLC0415

        managed_path = _site_packages()
        managed_modules = _installed_modules()
    except Exception:  # noqa: BLE001 - the managed environment is additive
        managed_path, managed_modules = None, []

    extra_allowlist = tuple(request.extra_imports) + tuple(managed_modules)
    if allow_tools:
        if tool_allowlist is None:
            tool_names = st.tool_names()
        else:
            try:
                tool_names = st.select_tool_names(tool_allowlist)
            except ValueError as exc:
                return AnalysisResult(
                    status="refused", code=st.TOOL_NOT_ALLOWED, source_digest=source_digest,
                    duration_ms=int((time.monotonic() - t0) * 1000), stderr=str(exc),
                )
        extra_allowlist = extra_allowlist + ("eclipse_tools",)
    else:
        tool_names = ()
    offenders = check_imports(
        request.source, extra_allowlist, tool_names=tool_names,
        allow_url_literals=bool(allow_url_literals and allow_tools),
    )
    if offenders:
        tool_offenders = [
            item for item in offenders
            if item == "eclipse_tools" or item.startswith("eclipse_tools")
        ]
        code = (
            st.TOOL_NOT_ALLOWED
            if tool_offenders and len(tool_offenders) == len(offenders)
            else IMPORT_NOT_ALLOWED
        )
        return AnalysisResult(
            status="refused", code=code, source_digest=source_digest,
            duration_ms=int((time.monotonic() - t0) * 1000),
            stderr=(
                f"disallowed source element(s): {', '.join(offenders)}. "
                "Only that element(s) are refused — the rest of the program is "
                "allowed; remove or rewrite the named one and it runs. "
                f"The importable modules are: "
                f"{', '.join(sorted(tuple(IMPORT_ALLOWLIST) + tuple(extra_allowlist)))}."
            ),
        )

    try:
        inputs, digests = _prepare_inputs(request.inputs)
    except AnalysisError as exc:
        return AnalysisResult(
            status="refused", code=exc.code, source_digest=source_digest,
            duration_ms=int((time.monotonic() - t0) * 1000), stderr=exc.reason,
        )

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

    return PreparedAnalysis(
        source_digest=source_digest,
        allow_tools=allow_tools,
        tool_names=tuple(tool_names),
        inputs=inputs,
        input_digests=digests,
        interpreter=interpreter,
        managed_path=managed_path,
        extra_allowlist=extra_allowlist,
        package_lock_digest=package_lock_digest(),
        # The RUNTIME guard enforces exactly this list, so the AST filter and
        # the enforcement point can never disagree.
        import_allowlist=tuple(IMPORT_ALLOWLIST) + tuple(extra_allowlist),
    )


def guard_payload(
    prepared: PreparedAnalysis, stage: Path, extra_paths: list[str],
) -> dict[str, Any]:
    """The runtime-guard parameters for one execution.

    * `import_allowlist` — the modules the guarded `__import__` will import.
    * `read_roots` — where a program may READ: its own folder, the
      interpreter's own tree (its libraries) and the managed site-packages.
    * `write_roots` — where it may WRITE: its own folder (the staging
      directory, which is its own temporary workspace) and nothing else. The
      host's control files are written AFTER the program returns, so a program
      cannot pre-write a result.
    """
    roots = [str(stage)]
    interpreter = Path(prepared.interpreter) if prepared.interpreter else None
    if interpreter is not None:
        roots.append(str(interpreter.parent))
    roots.extend(extra_paths)
    return {
        "import_allowlist": list(prepared.import_allowlist),
        "read_roots": roots,
        "write_roots": [str(stage)],
    }


def resolve_tool_request(
    pending: Any,
    *,
    memo: dict[str, Any],
    tool_calls: list[st.ToolCallRef],
    tool_resolver: st.ToolResolver,
    source_digest: str,
    input_digests: dict[str, str],
    interpreter: str,
    package_lock: str,
    started: float,
    tool_call_limit: int = st.MAX_TOOL_CALLS,
) -> Optional[AnalysisResult]:
    """Validate and resolve one pending read; returns a terminal result on error.

    On success it mutates ``memo`` and ``tool_calls`` and returns ``None`` so the
    caller replays the program. Shared by the one-shot and kernel runners.
    """
    duration_ms = int((time.monotonic() - started) * 1000)

    def failed(status: str, code: Optional[str], stderr: str, *, refused: bool = False) -> AnalysisResult:
        return AnalysisResult(
            status=status, code=code, source_digest=source_digest,
            input_digests=input_digests, interpreter=interpreter,
            package_lock_digest=package_lock, duration_ms=duration_ms,
            tool_calls=tool_calls, stderr=stderr[:2_000],
        )

    request_name = pending.get("name") if isinstance(pending, dict) else None
    request_args = pending.get("args") if isinstance(pending, dict) else None
    try:
        capability, params = st.validate_tool_request(request_name, request_args)
    except st.ToolRequestError as exc:
        return failed("refused", exc.code, exc.reason)
    if len(tool_calls) >= tool_call_limit:
        return failed(
            "refused", st.TOOL_LIMIT,
            f"the analysis asked for more than {tool_call_limit} data reads",
        )

    key = st.cache_key(str(request_name), request_args)
    if key in memo:
        return failed(
            "failed", st.TOOL_PROTOCOL_INVALID,
            "the analysis asked again for a value it already holds",
        )

    try:
        value = tool_resolver(capability, params)
    except TimeoutError as exc:
        return failed("timed_out", TIMED_OUT, str(exc))
    except Exception as exc:  # noqa: BLE001 - a host failure is reported
        return failed("failed", st.TOOL_RESOLVE_FAILED, f"{request_name}: {exc}")

    try:
        bounded = st.bound_tool_result(value)
    except st.ToolResultError as exc:
        return failed("refused", st.TOOL_RESULT_TOO_LARGE, str(exc))

    memo[key] = bounded
    if st.memo_size(memo) > st.MAX_TOOL_MEMO_BYTES:
        return failed(
            "refused", st.TOOL_RESULT_TOO_LARGE,
            "the data read exceeded the analysis memory budget",
        )
    tool_calls.append(st.ToolCallRef(
        name=str(request_name),
        args_digest=st.digest_args(params),
        result_digest=st.digest_result(bounded),
        status=str(bounded.get("status") or "OK")[:32],
        round=len(tool_calls) + 1,
    ))
    return None


def run_analysis(
    request: AnalysisRequest,
    *,
    output_dir: Optional[Path] = None,
    tool_resolver: Optional[st.ToolResolver] = None,
    kernel: Optional[Any] = None,
    cancel_event: Optional[Any] = None,
    tool_allowlist: Optional[tuple[str, ...]] = None,
    allow_url_literals: bool = False,
    tool_call_limit: int = st.MAX_TOOL_CALLS,
) -> AnalysisResult:
    """Run one analysis in the Phase 3 sandbox. Records enough to re-derive it.

    The program runs in an ISOLATED staging directory (never the repo): its inputs
    arrive as DATA on file, its relative writes land in staging, and only files it
    declares as artefacts are collected. The RUNTIME GUARD (`sandbox_guard.py`)
    confines it: a guarded `__import__` (only the allowlist), a safe
    `os`/`sys`/`importlib`/`builtins`, the privilege modules denied, an audit
    hook that refuses a network, a process, native code or a file outside the
    program's own folder. The OS process bounds (memory, processes, wall clock)
    sit on top of that. `cancel_event` kills the tree when the run is
    cancelled, so no child outlives its run (W14).

    When a `tool_resolver` is attached, a program may also call the read-only
    `eclipse_tools` bindings. That channel is DETERMINISTIC REPLAY, not a live
    pipe: the runner writes one pending request and exits; the host validates,
    resolves through the existing DataBridge, memoizes the reply and re-runs the
    same program. Only final outputs cross to the model context.
    """
    if kernel is not None:
        return kernel.execute(
            request, output_dir=output_dir, tool_resolver=tool_resolver,
        )

    t0 = time.monotonic()
    prepared = prepare_analysis(
        request, tool_resolver=tool_resolver, tool_allowlist=tool_allowlist,
        allow_url_literals=allow_url_literals,
    )
    if isinstance(prepared, AnalysisResult):
        return prepared

    source_digest = prepared.source_digest
    allow_tools = prepared.allow_tools
    tool_names = prepared.tool_names
    inputs = prepared.inputs
    digests = prepared.input_digests
    interpreter = prepared.interpreter
    managed_path = prepared.managed_path
    package_lock = prepared.package_lock_digest

    # 4. Write the payload + runner to a temp dir OUTSIDE the workspace, then run.
    with tempfile.TemporaryDirectory(prefix="be-analysis-") as tmp:
        stage = Path(tmp)
        payload_path = stage / "payload.json"
        out_path = stage / "out.json"
        pending_path = stage / "pending.json"
        runner_path = stage / "runner.py"
        extra_paths = [str(managed_path)] if managed_path is not None and managed_path.is_dir() else []
        payload: dict[str, Any] = {
            "source": request.source, "inputs": inputs, "extra_paths": extra_paths,
        }
        payload.update(guard_payload(prepared, stage, extra_paths))
        if allow_tools:
            payload.update({
                "tool_bindings": list(tool_names),
                "tool_pending_path": str(pending_path),
                "tool_memo": {},
            })
        runner_path.write_text(_RUNNER_SOURCE, encoding="utf-8")
        # Relative writes land in the staging dir only (cwd), never the repo. The
        # program writes a deliverable into `output/`; only those files are
        # collected.
        (stage / "output").mkdir(exist_ok=True)

        deadline = time.monotonic() + max(1, int(request.timeout_s))
        memo: dict[str, Any] = {}
        tool_calls: list[st.ToolCallRef] = []

        while True:
            # A previous round's files must never masquerade as this round's.
            for stale in (out_path, pending_path):
                try:
                    stale.unlink()
                except FileNotFoundError:
                    pass

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return AnalysisResult(
                    status="timed_out", code=TIMED_OUT, source_digest=source_digest,
                    input_digests=digests, interpreter=interpreter,
                    package_lock_digest=package_lock_digest(),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    tool_calls=tool_calls, stderr="the analysis ran out of time",
                )

            payload["tool_memo"] = memo
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            spec = sandbox_mod.RunSpec(
                argv=[interpreter, str(runner_path), str(payload_path), str(out_path)],
                cwd=stage, env=sandbox_mod.build_env(),
                timeout_s=max(1, int(remaining)), output_cap_bytes=MAX_OUTPUT_BYTES,
                network=False,
                # R3-02: the declared limits are now ENFORCED, not just declared.
                # CPU is a TOTAL-burn guard across the process tree, deliberately
                # above the wall-clock timeout so the wall clock stays the primary
                # bound for a single process.
                cpu_seconds=MAX_CPU_SECONDS,
                memory_mb=DEFAULT_MEMORY_MB,
                process_limit=MAX_PROCESSES,
            )
            raw = sandbox_mod.run(spec, cancel_event=cancel_event)
            duration_ms = int((time.monotonic() - t0) * 1000)

            if raw.timed_out:
                return AnalysisResult(
                    status="timed_out", code=TIMED_OUT, source_digest=source_digest,
                    input_digests=digests, interpreter=interpreter,
                    package_lock_digest=package_lock_digest(), duration_ms=duration_ms,
                    tool_calls=tool_calls, stderr=raw.output[:4_000],
                    cpu_ms=raw.cpu_ms, memory_peak_mb=raw.memory_peak_mb,
                    process_count=raw.process_count, resource_limit=raw.resource_limit,
                    exit_code=raw.exit_code,
                )
            if raw.cancelled:
                # The run was cancelled: the tree is killed, so nothing outlives
                # it (W14). The verdict says so honestly.
                return AnalysisResult(
                    status="refused", code="CANCELLED", source_digest=source_digest,
                    input_digests=digests, interpreter=interpreter,
                    package_lock_digest=package_lock_digest(), duration_ms=duration_ms,
                    tool_calls=tool_calls, stderr="the analysis was cancelled",
                    cpu_ms=raw.cpu_ms, memory_peak_mb=raw.memory_peak_mb,
                    process_count=raw.process_count, resource_limit=raw.resource_limit,
                    exit_code=raw.exit_code,
                )

            if raw.exit_code == st.TOOL_SENTINEL:
                if not pending_path.is_file():
                    return AnalysisResult(
                        status="failed", code=st.TOOL_PROTOCOL_INVALID,
                        source_digest=source_digest, input_digests=digests,
                        interpreter=interpreter, package_lock_digest=package_lock_digest(),
                        duration_ms=duration_ms, tool_calls=tool_calls,
                        stderr="the analysis stopped without a valid data request",
                    )
                try:
                    if pending_path.stat().st_size > st.MAX_TOOL_REQUEST_BYTES:
                        return AnalysisResult(
                            status="refused", code=st.TOOL_ARGS_INVALID,
                            source_digest=source_digest, input_digests=digests,
                            interpreter=interpreter, package_lock_digest=package_lock_digest(),
                            duration_ms=duration_ms, tool_calls=tool_calls,
                            stderr="the analysis sent an oversized data request",
                        )
                    pending = json.loads(pending_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    return AnalysisResult(
                        status="failed", code=st.TOOL_PROTOCOL_INVALID,
                        source_digest=source_digest, input_digests=digests,
                        interpreter=interpreter, package_lock_digest=package_lock_digest(),
                        duration_ms=duration_ms, tool_calls=tool_calls,
                        stderr="the analysis sent an unreadable data request",
                    )

                failure = resolve_tool_request(
                    pending, memo=memo, tool_calls=tool_calls,
                    tool_resolver=tool_resolver, source_digest=source_digest,
                    input_digests=digests, interpreter=interpreter,
                    package_lock=package_lock_digest(), started=t0,
                    tool_call_limit=tool_call_limit,
                )
                if failure is not None:
                    return failure
                continue

            outputs: dict[str, Any] = {}
            ok = False
            if out_path.is_file():
                try:
                    # The result is BOUNDED before it is read: a program that
                    # writes a huge result must not make the HOST allocate it.
                    if out_path.stat().st_size > MAX_RESULT_BYTES:
                        raise ValueError("the analysis result exceeded the result budget")
                    parsed = json.loads(out_path.read_text(encoding="utf-8"))
                    ok = bool(parsed.get("ok"))
                    outputs = _bounded_outputs(parsed.get("outputs") or {})
                except (OSError, ValueError):
                    ok = False
            if raw.exit_code != 0 or not ok:
                code = st.TOOL_PROTOCOL_INVALID if raw.exit_code == st.TOOL_SENTINEL else None
                return AnalysisResult(
                    status="failed", code=code, source_digest=source_digest,
                    input_digests=digests, interpreter=interpreter,
                    package_lock_digest=package_lock_digest(), duration_ms=duration_ms,
                    tool_calls=tool_calls, stderr=raw.output[:4_000],
                    cpu_ms=raw.cpu_ms, memory_peak_mb=raw.memory_peak_mb,
                    process_count=raw.process_count, resource_limit=raw.resource_limit,
                    exit_code=raw.exit_code,
                )

            artifacts = _collect_artifacts(output_dir, stage) if output_dir else []
            break

    return AnalysisResult(
        status="ok", outputs=outputs, artifacts=artifacts, source_digest=source_digest,
        input_digests=digests, interpreter=interpreter,
        package_lock_digest=package_lock_digest(), duration_ms=duration_ms,
        tool_calls=tool_calls,
        cpu_ms=raw.cpu_ms, memory_peak_mb=raw.memory_peak_mb,
        process_count=raw.process_count, resource_limit=raw.resource_limit,
        exit_code=raw.exit_code,
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
        # A file the program wrote is copied only when it is this big: an
        # unbounded copy would let a program fill the host's disk (W14).
        try:
            if path.stat().st_size > MAX_ARTIFACT_BYTES:
                continue
        except OSError:
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
