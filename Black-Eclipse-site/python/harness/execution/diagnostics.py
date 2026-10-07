"""The diagnostic engine — normalize compiler/runtime/test output.

The single most important transformation for autonomous debugging: turning an
opaque blob of stdout/stderr into a list of structured `Diagnostic`s with
file/line/column where the tool actually provides them. The rules here are
deterministic parsers, not heuristics over model text, and every parser is
independent of the process layer so it can be tested on fixed strings.

Sources understood: TypeScript (`tsc`), Python tracebacks, Node/V8 stack
frames, ESLint/prettier, pytest, generic `file:line:col: message`, and the C/C++/
Java `file:line: error` shape. Unknown output yields a single message-only
diagnostic rather than a fabricated location.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from .models import Diagnostic

MAX_DIAGNOSTICS = 200
MAX_MESSAGE_CHARS = 600

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _strip_ansi(text: str) -> str:
    """Strip terminal color/control codes. Reuses the terminal subsystem's helper."""
    try:
        from ...terminal.session import strip_ansi  # noqa: PLC0415

        return strip_ansi(text)
    except Exception:  # noqa: BLE001
        return _ANSI.sub("", text)

# src/app.ts(42,17): error TS2339: Property 'foo' does not exist on type 'X'.
_TS = re.compile(
    r"^(?P<file>[^\s(][^()]*?)\((?P<line>\d+),(?P<col>\d+)\):\s*"
    r"(?P<sev>error|warning|info)\s+(?P<code>TS\d+):\s*(?P<msg>.*)$"
)
# src/a.ts:3:1 - error TS1234: msg   (some formatters)
_TS_COLON = re.compile(
    r"^(?P<file>[^\s:][^:]*?):(?P<line>\d+):(?P<col>\d+)\s*[-:]?\s*"
    r"(?P<sev>error|warning|info)\s+(?P<code>TS\d+):\s*(?P<msg>.*)$"
)
# File "src/user.py", line 91, in handle
_PY_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>.*))?$')
# The final `TypeError: Cannot read properties of undefined`
_PY_EXC = re.compile(r"^(?P<code>[A-Za-z_][\w.]*(?:Error|Exception|Warning)):\s*(?P<msg>.*)$")
# at foo (src/user.ts:91:14)   |   at src/user.ts:91:14
_JS_FRAME = re.compile(r"^\s*at\s+(?:(?P<func>[^(]+?)\s+\()?(?P<file>[^()\s]+):(?P<line>\d+):(?P<col>\d+)\)?$")
# eslint-style:  3:1  error  message  rule-name
_ESLINT = re.compile(
    r"^\s*(?P<line>\d+):(?P<col>\d+)\s+(?P<sev>error|warning)\s{2,}(?P<msg>.+?)(?:\s{2,}(?P<code>[\w@/-]+))?$"
)
# pytest: FAILED tests/test_x.py::test_y - AssertionError: ...
_PYTEST = re.compile(
    r"^(?P<status>FAILED|ERROR|PASSED|SKIPPED)\s+(?P<file>[^\s:]+)::(?P<test>[^\s]+)(?:\s+-\s+(?P<msg>.*))?$"
)
# generic: path/file.ext:12:3: error: message  (C/C++/Rust/Java/go/gcc style)
_GENERIC = re.compile(
    r"^(?P<file>[^\s:][^:]*?):(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<sev>error|warning|note|fatal error):\s*(?P<msg>.*)$"
)
# rust: error[E0382]: ... followed by  --> src/main.rs:3:5
_RUST = re.compile(r"^\s*-->\s+(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+)")
# go: file.go:12:3: message  (no severity keyword)
_GO = re.compile(r"^(?P<file>[\w./\\-]+\.go):(?P<line>\d+):(?P<col>\d+):\s*(?P<msg>.*)$")

_SEV = {"error": "error", "warning": "warning", "info": "info", "note": "info", "fatal error": "error"}


def _clip(text: str) -> str:
    text = (text or "").strip()
    return text if len(text) <= MAX_MESSAGE_CHARS else text[:MAX_MESSAGE_CHARS] + "…"


def _emit(out: list[Diagnostic], diag: Diagnostic) -> None:
    if len(out) < MAX_DIAGNOSTICS:
        out.append(diag)


def parse_typescript(output: str) -> list[Diagnostic]:
    """Parse `tsc` output (both the `(l,c)` and `:l:c` forms)."""
    out: list[Diagnostic] = []
    for raw in output.splitlines():
        line = raw.rstrip()
        match = _TS.match(line) or _TS_COLON.match(line)
        if not match:
            continue
        _emit(out, Diagnostic(
            file=match.group("file").strip(), line=int(match.group("line")),
            column=int(match.group("col")), severity=_SEV.get(match.group("sev"), "error"),
            category="compile", message=_clip(match.group("msg")),
            code=match.group("code"), source="typescript",
        ))
    return out


def parse_python_traceback(output: str) -> list[Diagnostic]:
    """Parse a Python traceback into the deepest frame + the exception message."""
    frames: list[tuple[str, int, str]] = []
    exc: Optional[tuple[str, str]] = None
    for raw in output.splitlines():
        frame = _PY_FRAME.match(raw)
        if frame:
            frames.append((frame.group("file"), int(frame.group("line")), frame.group("func") or ""))
            continue
        exc_match = _PY_EXC.match(raw.strip())
        if exc_match:
            exc = (exc_match.group("code"), exc_match.group("msg"))
    if not frames and not exc:
        return []
    stack = [f"{f}:{ln}" for f, ln, _ in frames]
    deepest = frames[-1] if frames else ("", 0, "")
    return [Diagnostic(
        file=deepest[0], line=deepest[1], column=0,
        severity="error", category="runtime",
        message=_clip((exc[0] + ": " + exc[1]) if exc else "python error"),
        stack=stack, source="python",
    )]


def parse_js_stack(output: str) -> list[Diagnostic]:
    """Parse Node/V8 stack frames; report the first frame inside the workspace."""
    out: list[Diagnostic] = []
    frames: list[tuple[str, int, int, str]] = []
    message = ""
    for raw in output.splitlines():
        frame = _JS_FRAME.match(raw)
        if frame:
            frames.append((frame.group("file"), int(frame.group("line")), int(frame.group("col")), frame.group("func") or ""))
        elif not message:
            exc = _PY_EXC.match(raw.strip())
            if exc:
                message = f"{exc.group('code')}: {exc.group('msg')}"
    # Prefer the first non-node_modules frame; fall back to the first frame.
    chosen = next((f for f in frames if "node_modules" not in f[0] and not f[0].startswith("node:")), frames[0] if frames else None)
    if chosen is None and not message:
        return []
    stack = [f"{f}:{ln}:{c}" for f, ln, c, _ in frames]
    if chosen is not None:
        _emit(out, Diagnostic(
            file=chosen[0], line=chosen[1], column=chosen[2], severity="error",
            category="runtime", message=_clip(message or "runtime error"), stack=stack, source="javascript",
        ))
    elif message:
        _emit(out, Diagnostic(category="runtime", message=_clip(message), stack=stack, source="javascript"))
    return out


def parse_eslint(output: str) -> list[Diagnostic]:
    """Parse ESLint's stylish reporter: a file header followed by `l:c sev msg`."""
    out: list[Diagnostic] = []
    current = ""
    for raw in output.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if "/" in stripped and not stripped[0].isdigit() and "error" not in stripped.split(" ")[0]:
            current = stripped.split(" ")[0]
            continue
        match = _ESLINT.match(raw)
        if match and current:
            _emit(out, Diagnostic(
                file=current, line=int(match.group("line")), column=int(match.group("col")),
                severity=_SEV.get(match.group("sev"), "error"), category="lint",
                message=_clip(match.group("msg")), code=match.group("code") or "", source="lint",
            ))
    return out


def parse_pytest(output: str) -> list[Diagnostic]:
    """Parse pytest's short test summary lines into diagnostics."""
    out: list[Diagnostic] = []
    for raw in output.splitlines():
        match = _PYTEST.match(raw.strip())
        if not match or match.group("status") in ("PASSED",):
            continue
        _emit(out, Diagnostic(
            file=match.group("file").replace("::", "/"), line=0, column=0,
            severity="error", category="test",
            message=_clip(f"{match.group('test')}: {match.group('msg') or match.group('status')}"),
            source="pytest",
        ))
    return out


def parse_generic(output: str) -> list[Diagnostic]:
    """Parse `file:line:col: error: message` and go-style `file.go:l:c: msg`."""
    out: list[Diagnostic] = []
    pending_message = ""
    for raw in output.splitlines():
        generic = _GENERIC.match(raw.strip())
        if generic:
            _emit(out, Diagnostic(
                file=generic.group("file"), line=int(generic.group("line")),
                column=int(generic.group("col")),
                severity=_SEV.get(generic.group("sev"), "error"), category="compile",
                message=_clip(generic.group("msg")), source="compiler",
            ))
            continue
        rust = _RUST.match(raw)
        if rust:
            _emit(out, Diagnostic(
                file=rust.group("file"), line=int(rust.group("line")),
                column=int(rust.group("col")), severity="error", category="compile",
                message=_clip(pending_message or "compiler error"), source="compiler",
            ))
            continue
        go_match = _GO.match(raw.strip())
        if go_match:
            _emit(out, Diagnostic(
                file=go_match.group("file"), line=int(go_match.group("line")),
                column=int(go_match.group("col")), severity="error", category="compile",
                message=_clip(go_match.group("msg")), source="compiler",
            ))
            continue
        stripped = raw.strip()
        if stripped.startswith(("error", "error[")) or "error[" in stripped:
            pending_message = stripped
    return out


# Order: try language-specific, then the generic compiler shape, then stacks.
_PARSERS = (
    ("typescript", parse_typescript),
    ("javascript", parse_js_stack),
    ("python", parse_python_traceback),
    ("pytest", parse_pytest),
    ("lint", parse_eslint),
    ("generic", parse_generic),
)

# Map a runtime language to the parser order that fits it best.
_LANGUAGE_ORDER: dict[str, tuple[str, ...]] = {
    "typescript": ("typescript", "lint", "generic", "javascript"),
    "javascript": ("javascript", "lint", "generic"),
    "python": ("python", "pytest", "generic"),
    "sql": ("generic",),
    "shell": ("generic",),
    "rust": ("generic",),
    "go": ("generic",),
    "java": ("generic",),
    "c": ("generic",),
    "cpp": ("generic",),
    "csharp": ("generic",),
    "ruby": ("python", "generic"),
    "php": ("generic",),
}
_PARSER_BY_NAME = dict(_PARSERS)


def normalize(output: str, *, language: str = "", source: str = "") -> list[Diagnostic]:
    """Normalize `output` into diagnostics, trying the language's parsers in order.

    The FIRST parser that yields diagnostics wins, so a TypeScript build uses the
    `tsc` parser and never mis-reads a stack frame as a compiler error. When no
    parser matches but the output is non-empty and looks like an error, a single
    message-only diagnostic is returned (no fabricated location). Terminal color
    codes are stripped first so a colored `file:line:col` or stack frame matches.
    """
    if not output or not output.strip():
        return []
    output = _strip_ansi(output)
    order = _LANGUAGE_ORDER.get(language.casefold(), ("generic", "javascript", "python", "typescript", "lint"))
    for name in order:
        parser = _PARSER_BY_NAME.get(name)
        if parser is None:
            continue
        found = parser(output)
        if found:
            if source:
                for diag in found:
                    if not diag.source:
                        diag.source = source
            return _dedupe(found)
    lowered = output.casefold()
    if any(token in lowered for token in ("error", "exception", "failed", "traceback")):
        return [Diagnostic(category="runtime", message=_clip(output), source=source or "output")]
    return []


def _dedupe(diags: Iterable[Diagnostic]) -> list[Diagnostic]:
    seen: set[tuple[str, int, int, str]] = set()
    out: list[Diagnostic] = []
    for diag in diags:
        key = (diag.file, diag.line, diag.column, diag.message)
        if key in seen:
            continue
        seen.add(key)
        out.append(diag)
        if len(out) >= MAX_DIAGNOSTICS:
            break
    return out


class DiagnosticEngine:
    """The object seam the orchestrator/engines call."""

    def normalize(self, output: str, *, language: str = "", source: str = "") -> list[Diagnostic]:
        return normalize(output, language=language, source=source)

    def merge(self, *groups: Iterable[Diagnostic]) -> list[Diagnostic]:
        merged: list[Diagnostic] = []
        for group in groups:
            merged.extend(group)
        return _dedupe(merged)


__all__ = [
    "DiagnosticEngine",
    "MAX_DIAGNOSTICS",
    "normalize",
    "parse_eslint",
    "parse_generic",
    "parse_js_stack",
    "parse_pytest",
    "parse_python_traceback",
    "parse_typescript",
]
