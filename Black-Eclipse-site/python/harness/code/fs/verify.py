"""Verification — the safety net after every mutation.

Three pieces, matching the required lifecycle:

  * `SyntaxValidator` — a per-language syntax check. Python uses the stdlib
    `ast`; JSON/JSONC use `json`; TOML uses `tomllib`; JS/TS, Go, Rust, Java, C/C++
    use a bounded bracket/brace/paren balance check. It never runs a build tool
    (that would be expensive per edit); it is a cheap, deterministic sanity gate.
  * `ChangeValidator` — validates a set of proposed edits (path allowed, target
    present/missing as declared, expected hash intact) WITHOUT writing anything.
  * `EditVerifier` — after a write: the file exists, is readable, its hash is what
    was reported, the new content is present, and (when a language is known) it
    parses. Returns a structured verdict; never raises on a failed check — a
    failed verification is DATA the agent reads.

Verification is part of the editing lifecycle, not a separate build step.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import encoding as enc
from . import errors as err
from . import metadata as meta
from . import resolver as res
from . import symbols as symbols_mod

MAX_VERIFY_BYTES = 2_000_000
_MAX_BRACKETS = 5_000  # a balance scan bound so a pathological file cannot stall


@dataclass
class SyntaxResult:
    valid: bool
    language: str
    checker: str
    error: Optional[str] = None
    line: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "valid": self.valid, "language": self.language, "checker": self.checker,
        }
        if self.error:
            payload["error"] = self.error
        if self.line is not None:
            payload["line"] = self.line
        return payload


# ── syntax validators ───────────────────────────────────────────────────────


def _check_python(text: str) -> SyntaxResult:
    try:
        ast.parse(text)
        return SyntaxResult(True, "python", "ast")
    except SyntaxError as exc:
        return SyntaxResult(False, "python", "ast", error=str(exc.msg or exc), line=exc.lineno)
    except Exception as exc:  # noqa: BLE001 - a parser crash is a failed check, not a crash
        return SyntaxResult(False, "python", "ast", error=f"{type(exc).__name__}: {exc}")


def _check_json(text: str) -> SyntaxResult:
    try:
        json.loads(text)
        return SyntaxResult(True, "json", "json")
    except ValueError as exc:
        return SyntaxResult(False, "json", "json", error=str(exc))


def _check_toml(text: str) -> SyntaxResult:
    try:
        import tomllib  # noqa: PLC0415 - 3.11+; the vendored interpreter is 3.12

        tomllib.loads(text)
        return SyntaxResult(True, "toml", "tomllib")
    except ModuleNotFoundError:
        return _check_brackets(text, "toml")
    except Exception as exc:  # noqa: BLE001
        return SyntaxResult(False, "toml", "tomllib", error=str(exc))


_BRACKETS = {"(": ")", "[": "]", "{": "}"}
_CLOSERS = {v: k for k, v in _BRACKETS.items()}


def _check_brackets(text: str, language: str) -> SyntaxResult:
    """A bounded bracket/brace/paren balance scan, string- and comment-aware.

    This is deliberately shallow: it catches the common truncation/typo failure
    (an unbalanced brace from a bad patch) without pretending to be a parser.
    """
    stack: list[str] = []
    quote = ""
    escaped = False
    line = 1
    in_line_comment = False
    in_block_comment = False
    scanned = 0
    index = 0
    while index < len(text):
        ch = text[index]
        nxt = text[index + 1] if index + 1 < len(text) else ""
        scanned += 1
        if scanned > len(text) or scanned > MAX_VERIFY_BYTES:
            break
        if ch == "\n":
            line += 1
            in_line_comment = False
        if in_line_comment:
            index += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = ""
            index += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            index += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            index += 2
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            index += 1
            continue
        if ch in _BRACKETS:
            if len(stack) >= _MAX_BRACKETS:
                break
            stack.append(ch)
        elif ch in _CLOSERS:
            if not stack or stack[-1] != _CLOSERS[ch]:
                return SyntaxResult(
                    False, language, "bracket-balance",
                    error=f"unexpected {ch!r}", line=line,
                )
            stack.pop()
        index += 1
    if quote:
        return SyntaxResult(False, language, "bracket-balance", error="unterminated string", line=line)
    if stack:
        return SyntaxResult(False, language, "bracket-balance", error=f"unclosed {stack[-1]!r}", line=line)
    return SyntaxResult(True, language, "bracket-balance")


_BRACKET_LANGUAGES = {
    "typescript", "javascript", "go", "rust", "java", "csharp", "c", "cpp",
    "php", "ruby", "kotlin", "swift", "scala",
}


def validate_syntax(text: str, *, language: Optional[str] = None, path: str = "") -> SyntaxResult:
    """Validate `text` as `language` (or the language implied by `path`)."""
    if len(text) > MAX_VERIFY_BYTES:
        return SyntaxResult(False, language or "text", "size", error="file too large to validate")
    lang = language or symbols_mod.detect_language(path)
    if lang == "python":
        return _check_python(text)
    if lang == "json" or lang in ("jsonc",):
        return _check_json(text)
    if lang == "toml":
        return _check_toml(text)
    if lang in _BRACKET_LANGUAGES:
        return _check_brackets(text, lang)
    return SyntaxResult(True, lang, "none")


def validate_file(path: Path, *, language: Optional[str] = None) -> SyntaxResult:
    try:
        decoded = enc.read_text(path)
    except err.FsError as exc:
        return SyntaxResult(False, language or "text", "read", error=exc.reason)
    return validate_syntax(decoded.text, language=language, path=str(path))


# ── change validation (no writes) ────────────────────────────────────────────


@dataclass
class ChangeCheck:
    path: str
    ok: bool
    code: Optional[str] = None
    message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": self.path, "ok": self.ok}
        if self.code:
            payload["code"] = self.code
        if self.message:
            payload["message"] = self.message
        return payload


def validate_changes(ctx: Any, edits: list[dict[str, Any]]) -> dict[str, Any]:
    """Check a list of proposed edits without applying any of them.

    Each edit is `{path, operation, oldText?, newText?, expectedHash?}`. Returns
    `{valid, checks}`; a single failing check makes `valid` False — the same
    all-or-nothing rule `multi_file_patch` enforces before it writes.
    """
    checks: list[ChangeCheck] = []
    for edit in edits:
        if not isinstance(edit, dict):
            checks.append(ChangeCheck("", False, err.INVALID_PATH, "each change must be an object"))
            continue
        path = str(edit.get("path") or "")
        operation = str(edit.get("operation") or "replace").lower()
        try:
            ctx.require("write", path)
            if operation == "create":
                target = res.resolve(ctx.ws, path, for_write=True)
                if target.exists():
                    checks.append(ChangeCheck(path, False, err.FILE_EXISTS, "already exists"))
                    continue
            else:
                target = res.require_regular_file(ctx.ws, path)
                if res.is_binary_file(target):
                    checks.append(ChangeCheck(path, False, err.UNSUPPORTED_BINARY_OPERATION, "binary file"))
                    continue
                expected = edit.get("expectedHash")
                if expected and meta.hash_file(target) != expected:
                    checks.append(ChangeCheck(path, False, err.STALE_FILE, "changed since read"))
                    continue
                if operation in ("replace", "delete"):
                    old_text = edit.get("oldText") or edit.get("old")
                    if old_text is not None:
                        text = enc.read_text(target).text
                        count = text.count(str(old_text))
                        if count == 0:
                            checks.append(ChangeCheck(path, False, err.PATCH_CONTEXT_MISMATCH, "target not found"))
                            continue
                        if operation == "replace" and count > 1:
                            checks.append(ChangeCheck(path, False, err.AMBIGUOUS_PATCH, "target appears more than once"))
                            continue
            checks.append(ChangeCheck(path, True))
        except err.FsError as exc:
            checks.append(ChangeCheck(path, False, exc.code, exc.reason))
    return {"valid": all(c.ok for c in checks), "checks": [c.to_dict() for c in checks]}


# ── post-write verification ──────────────────────────────────────────────────


def verify_mutation(
    ws: Any,
    rel_path: str,
    *,
    expected_hash: Optional[str] = None,
    expect_text: Optional[str] = None,
    check_syntax: bool = True,
) -> dict[str, Any]:
    """Verify a file after a mutation. Returns `{verified, checks}`.

    Checks: the file exists, is readable, its hash equals what was reported, the
    expected new text is present, and — when the language is known — it parses.
    """
    checks: dict[str, Any] = {}
    try:
        target = res.resolve(ws, rel_path)
    except err.FsError as exc:
        return {"verified": False, "checks": {"exists": False}, "code": exc.code, "message": exc.reason}
    checks["exists"] = target.exists()
    if not checks["exists"]:
        return {"verified": False, "checks": checks, "code": err.PATH_NOT_FOUND, "message": "file missing after change"}
    try:
        decoded = enc.read_text(target)
    except err.FsError as exc:
        checks["readable"] = False
        return {"verified": False, "checks": checks, "code": exc.code, "message": exc.reason}
    checks["readable"] = True
    actual = meta.hash_file(target)
    checks["hash"] = actual
    if expected_hash is not None:
        checks["hashMatches"] = actual == expected_hash
    if expect_text is not None:
        checks["contentMatches"] = expect_text in decoded.text
    result: dict[str, Any] = {"verified": True, "language": symbols_mod.detect_language(rel_path), "checks": checks}
    if check_syntax:
        syntax = validate_syntax(decoded.text, path=rel_path)
        result["syntax"] = syntax.to_dict()
        if not syntax.valid:
            result["verified"] = False
    if expected_hash is not None and not checks.get("hashMatches", True):
        result["verified"] = False
    if expect_text is not None and not checks.get("contentMatches", True):
        result["verified"] = False
    return result


def verify_workspace_file(ws: Any, rel_path: str, *, expected_hash: Optional[str] = None) -> dict[str, Any]:
    """The agent-facing `verify_file`: syntax + integrity for one file."""
    target = res.require_regular_file(ws, rel_path)
    if res.is_binary_file(target):
        return {
            "status": "ok", "path": res.relative(ws, target), "binary": True,
            "verified": True, "syntax": None,
        }
    decoded = enc.read_text(target)
    syntax = validate_syntax(decoded.text, path=rel_path)
    actual = meta.hash_file(target)
    verified = syntax.valid and (expected_hash is None or actual == expected_hash)
    return {
        "status": "ok",
        "path": res.relative(ws, target),
        "binary": False,
        "language": syntax.language,
        "verified": verified,
        "syntax": syntax.to_dict(),
        "sha256": actual,
        "hashMatches": (expected_hash is None or actual == expected_hash),
    }


__all__ = [
    "ChangeCheck",
    "SyntaxResult",
    "validate_changes",
    "validate_file",
    "validate_syntax",
    "verify_mutation",
    "verify_workspace_file",
]
