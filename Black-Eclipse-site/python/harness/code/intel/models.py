"""The Unified Code Model — one normalized representation for every backend.

LSP, Tree-sitter, the AST engine and the local index each produce different
shapes. CIUE normalizes them HERE so the agent never sees a backend's private
structure. Every dataclass has a `to_dict()` that emits the compact, deterministic
camelCase JSON the agent tools return.

The model is deliberately plain data (no behavior beyond serialization): it is the
contract the manager, index and tools all speak.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ── Symbol kinds (the normalized vocabulary) ─────────────────────────────────

SYMBOL_KINDS: tuple[str, ...] = (
    "function", "method", "class", "interface", "type", "variable", "constant",
    "enum", "module", "namespace", "component", "route", "model", "field",
    "property", "constructor", "parameter", "export", "import", "unknown",
)

# ── Diagnostic severities ────────────────────────────────────────────────────

SEVERITIES: tuple[str, ...] = ("error", "warning", "information", "hint")

_SEVERITY_BY_LSP = {1: "error", 2: "warning", 3: "information", 4: "hint"}


def severity_from_lsp(value: Any) -> str:
    try:
        return _SEVERITY_BY_LSP.get(int(value), "information")
    except (TypeError, ValueError):
        return "information"


# ── Core dataclasses ─────────────────────────────────────────────────────────


@dataclass
class CodeLocation:
    file: str
    line: int
    column: int = 1
    endLine: Optional[int] = None
    endColumn: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"file": self.file, "line": self.line, "column": self.column}
        if self.endLine is not None:
            payload["endLine"] = self.endLine
        if self.endColumn is not None:
            payload["endColumn"] = self.endColumn
        return payload


@dataclass
class CodeSymbol:
    id: str
    name: str
    kind: str
    file: str
    line: int
    column: int = 1
    language: str = ""
    project_id: str = ""
    end_line: int = 0
    end_column: int = 0
    container_id: Optional[str] = None
    container_name: Optional[str] = None
    signature: str = ""
    type: str = ""
    documentation: str = ""
    exported: bool = False
    detail: str = ""
    engine: str = "ast"
    # A dotted, container-qualified name (UserService.createUser) when known.
    qualified_name: str = ""

    def location(self) -> CodeLocation:
        return CodeLocation(
            file=self.file, line=self.line, column=self.column,
            endLine=self.end_line or None, endColumn=self.end_column or None,
        )

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "language": self.language,
            "engine": self.engine,
        }
        if self.qualified_name and self.qualified_name != self.name:
            payload["qualifiedName"] = self.qualified_name
        if self.signature:
            payload["signature"] = self.signature
        if self.type:
            payload["type"] = self.type
        if self.container_name:
            payload["container"] = self.container_name
        if self.exported:
            payload["exported"] = True
        if not compact and self.documentation:
            payload["documentation"] = self.documentation[:1_000]
        if not compact and self.detail:
            payload["detail"] = self.detail
        if not compact and self.end_line:
            payload["endLine"] = self.end_line
            payload["endColumn"] = self.end_column
        return payload


@dataclass
class CodeReference:
    file: str
    line: int
    column: int = 1
    end_line: int = 0
    end_column: int = 0
    text: str = ""
    is_definition: bool = False
    is_write: bool = False
    engine: str = "index"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "file": self.file, "line": self.line, "column": self.column,
            "definition": self.is_definition, "engine": self.engine,
        }
        if self.end_line:
            payload["endLine"] = self.end_line
            payload["endColumn"] = self.end_column
        if self.text:
            payload["text"] = self.text[:300]
        if self.is_write:
            payload["write"] = True
        return payload


@dataclass
class CodeDiagnostic:
    message: str
    severity: str
    file: str
    line: int
    column: int = 1
    end_line: int = 0
    end_column: int = 0
    source: str = ""
    code: str = ""
    related: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "message": self.message[:1_000], "severity": self.severity,
            "file": self.file, "line": self.line, "column": self.column,
        }
        if self.source:
            payload["source"] = self.source
        if self.code:
            payload["code"] = self.code
        if self.end_line:
            payload["endLine"] = self.end_line
            payload["endColumn"] = self.end_column
        if self.related:
            payload["related"] = self.related[:20]
        return payload


@dataclass
class CodeImport:
    module: str
    names: list[str] = field(default_factory=list)
    file: str = ""
    line: int = 0
    is_relative: bool = False
    resolved: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"module": self.module, "names": list(self.names)}
        if self.line:
            payload["line"] = self.line
        if self.is_relative:
            payload["relative"] = True
        if self.resolved:
            payload["resolved"] = self.resolved
        return payload


@dataclass
class CodeDependency:
    source: str      # workspace-relative file
    target: str      # workspace-relative file or an external module id
    kind: str = "import"   # import | call | reference | inherit
    external: bool = False
    line: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source, "target": self.target, "kind": self.kind,
            "external": self.external,
        }
        if self.line:
            payload["line"] = self.line
        return payload


@dataclass
class CallEdge:
    caller: str          # symbol id
    callee: str          # symbol id or a bare name when unresolved
    caller_name: str = ""
    callee_name: str = ""
    file: str = ""
    line: int = 0
    resolved: bool = True
    engine: str = "ast"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "caller": self.caller, "callee": self.callee,
            "from": self.caller_name, "to": self.callee_name,
            "resolved": self.resolved, "engine": self.engine,
        }
        if self.file:
            payload["file"] = self.file
            payload["line"] = self.line
        return payload


@dataclass
class CodeFile:
    path: str            # workspace-relative posix path
    language: str = ""
    sha256: str = ""
    size: int = 0
    symbols: int = 0
    imports: int = 0
    exports: int = 0
    indexed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path, "language": self.language, "size": self.size,
            "symbols": self.symbols, "imports": self.imports, "exports": self.exports,
            "sha256": self.sha256, "indexedAt": self.indexed_at,
        }


@dataclass
class ProjectInfo:
    root: str
    project_id: str
    workspace_id: str = ""
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    build_systems: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    monorepo: bool = False
    project_roots: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root, "projectId": self.project_id,
            "workspaceId": self.workspace_id, "languages": self.languages,
            "frameworks": self.frameworks, "packageManagers": self.package_managers,
            "buildSystems": self.build_systems, "entryPoints": self.entry_points,
            "databases": self.databases, "monorepo": self.monorepo,
            "projectRoots": self.project_roots, "tests": self.tests,
            "configFiles": self.config_files,
        }


def make_symbol_id(project_id: str, file: str, line: int, column: int, name: str) -> str:
    """A stable, collision-free symbol id within a project."""
    return f"{project_id}:{file}:{line}:{column}:{name}"


__all__ = [
    "CallEdge",
    "CodeDependency",
    "CodeDiagnostic",
    "CodeFile",
    "CodeImport",
    "CodeLocation",
    "CodeReference",
    "CodeSymbol",
    "ProjectInfo",
    "SEVERITIES",
    "SYMBOL_KINDS",
    "make_symbol_id",
    "severity_from_lsp",
]
