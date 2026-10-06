"""Eclipse Code Intelligence & Understanding Engine (CIUE).

A first-class, modular code-understanding subsystem layered under the existing
code capability. The agent asks `code_get_definition`, `code_find_references`,
`code_find_symbol`, … and CIUE decides whether the answer comes from an LSP, the
Tree-sitter/AST layer, the local index or the project analyzer — and always names
which engine answered.

Design rules (see `docs/harness/code-intelligence.md`):

  * deterministic code navigation is NEVER delegated to the model;
  * the repository is never treated as plain text;
  * the whole repository is never dumped into context;
  * rename is semantic (LSP WorkspaceEdit) or a preview-first structural edit —
    never a regex;
  * no coupling to one language or one language server;
  * a language-server failure never crashes the runtime;
  * the code index is a DEDICATED store, never agent memory.

Reuse, not rebuild: path security delegates to `code/policy.py` and
`code/workspace.py`; file reading/encoding/watching delegates to `code/fs/`; the
symbol extractor table is the existing `code/fs/symbols.py`.
"""

from .errors import IntelError, IntelUnavailable
from .models import (
    CallEdge,
    CodeDependency,
    CodeDiagnostic,
    CodeFile,
    CodeImport,
    CodeLocation,
    CodeReference,
    CodeSymbol,
    ProjectInfo,
)

__all__ = [
    "CallEdge",
    "CodeDependency",
    "CodeDiagnostic",
    "CodeFile",
    "CodeImport",
    "CodeLocation",
    "CodeIntelligenceManager",
    "CodeReference",
    "CodeSymbol",
    "IntelError",
    "IntelUnavailable",
    "ProjectInfo",
]


def __getattr__(name: str):  # pragma: no cover - lazy import to avoid cycles
    if name == "CodeIntelligenceManager":
        from .manager import CodeIntelligenceManager

        return CodeIntelligenceManager
    raise AttributeError(name)
