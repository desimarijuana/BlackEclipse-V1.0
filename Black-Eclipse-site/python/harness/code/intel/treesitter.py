"""Tree-sitter integration — the fast structural parsing layer (optional).

Tree-sitter is the ideal fast structural parser, but it is an OPTIONAL
dependency: CIUE must work with zero extra installs. This module imports
`tree_sitter` (and any installed grammars) lazily and reports honestly whether it
is available. When it is not, every method raises `IntelUnavailable("tree-sitter")`
and the caller (the AST engine) falls back to the stdlib/regex extractors that
already exist in `code/fs/symbols.py`.

Nothing here sends a file to a model to learn its structure — structural
understanding is always deterministic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

# Language → the tree-sitter grammar module/name. Only loaded if importable.
_GRAMMAR_MODULES: dict[str, tuple[str, ...]] = {
    "python": ("tree_sitter_python",),
    "javascript": ("tree_sitter_javascript",),
    "typescript": ("tree_sitter_typescript",),
    "tsx": ("tree_sitter_typescript",),
    "go": ("tree_sitter_go",),
    "rust": ("tree_sitter_rust",),
    "java": ("tree_sitter_java",),
    "c": ("tree_sitter_c",),
    "cpp": ("tree_sitter_cpp",),
    "csharp": ("tree_sitter_c_sharp",),
    "php": ("tree_sitter_php",),
}


def _require_tree_sitter():
    try:  # noqa: PLC0415
        import tree_sitter  # type: ignore

        return tree_sitter
    except Exception as exc:  # noqa: BLE001
        from .errors import IntelUnavailable

        raise IntelUnavailable("tree-sitter", f"tree-sitter is not installed ({exc})") from exc


def tree_sitter_available() -> bool:
    try:
        _require_tree_sitter()
        return True
    except Exception:  # noqa: BLE001
        return False


def available_grammars() -> list[str]:
    """Which language grammars are actually installed. Empty when none are."""
    out: list[str] = []
    for language, modules in _GRAMMAR_MODULES.items():
        for module in modules:
            try:
                __import__(module)
                out.append(language)
                break
            except Exception:  # noqa: BLE001
                continue
    return out


class TreeSitterEngine:
    """A per-language tree-sitter parser, when the grammars are present.

    `parse` returns a (language, tree) pair. `extract_symbols` is intentionally
    minimal: it walks the tree and yields definition nodes, but the authoritative
    symbol model is built by the AST engine, which can consume a tree-sitter tree
    when available and fall back otherwise. This keeps one symbol contract.
    """

    def __init__(self, language: str) -> None:
        self.language = language
        self._parser: Any = None
        self._grammar: Any = None

    @property
    def available(self) -> bool:
        try:
            self._ensure()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _ensure(self) -> None:
        if self._parser is not None:
            return
        ts = _require_tree_sitter()
        grammar = None
        for module in _GRAMMAR_MODULES.get(self.language, ()):
            try:
                mod = __import__(module)
                grammar = mod.language()
                break
            except Exception:  # noqa: BLE001
                continue
        if grammar is None:
            from .errors import IntelUnavailable

            raise IntelUnavailable("tree-sitter", f"no tree-sitter grammar for {self.language!r}")
        try:
            parser = ts.Parser()
            # Newer bindings require set_language(); older accept a constructor arg.
            if hasattr(parser, "set_language"):
                parser.set_language(grammar)
            self._parser = parser
            self._grammar = grammar
        except Exception as exc:  # noqa: BLE001
            from .errors import IntelUnavailable

            raise IntelUnavailable("tree-sitter", f"could not build a parser for {self.language!r}: {exc}") from exc

    def parse(self, text: str) -> Any:
        self._ensure()
        return self._parser.parse(text.encode("utf-8"))

    def get_syntax_tree(self, text: str) -> Any:
        return self.parse(text)

    def extract_functions(self, text: str) -> list[dict[str, Any]]:
        return self._extract(text, _FUNCTION_NODES.get(self.language, ()))

    def extract_classes(self, text: str) -> list[dict[str, Any]]:
        return self._extract(text, _CLASS_NODES.get(self.language, ()))

    def extract_symbols(self, text: str) -> list[dict[str, Any]]:
        kinds = set(_FUNCTION_NODES.get(self.language, ())) | set(_CLASS_NODES.get(self.language, ()))
        return self._extract(text, tuple(kinds))

    def _extract(self, text: str, node_types: tuple[str, ...]) -> list[dict[str, Any]]:
        if not node_types:
            return []
        tree = self.parse(text)
        root = getattr(tree, "root_node", None)
        if root is None:
            return []
        wanted = set(node_types)
        out: list[dict[str, Any]] = []

        def _walk(node: Any) -> None:
            if getattr(node, "type", "") in wanted:
                name_node = node.child_by_field_name("name")
                name = ""
                if name_node is not None:
                    name = text.encode("utf-8")[name_node.start_byte:name_node.end_byte].decode("utf-8", "replace")
                out.append({
                    "name": name, "kind": node.type,
                    "startLine": node.start_point[0] + 1,
                    "endLine": node.end_point[0] + 1,
                    "startColumn": node.start_point[1] + 1,
                })
            for i in range(getattr(node, "child_count", 0)):
                _walk(node.child(i))

        _walk(root)
        return out


# The definition node types per language (a bounded, useful subset).
_FUNCTION_NODES: dict[str, tuple[str, ...]] = {
    "python": ("function_definition",),
    "javascript": ("function_declaration", "method_definition", "arrow_function"),
    "typescript": ("function_declaration", "method_definition", "function_signature"),
    "tsx": ("function_declaration", "method_definition"),
    "go": ("function_declaration", "method_declaration"),
    "rust": ("function_item",),
    "java": ("method_declaration", "constructor_declaration"),
    "c": ("function_definition",),
    "cpp": ("function_definition",),
    "csharp": ("method_declaration", "constructor_declaration"),
    "php": ("function_definition", "method_declaration"),
}
_CLASS_NODES: dict[str, tuple[str, ...]] = {
    "python": ("class_definition",),
    "javascript": ("class_declaration",),
    "typescript": ("class_declaration", "interface_declaration", "type_alias_declaration", "enum_declaration"),
    "tsx": ("class_declaration", "interface_declaration"),
    "go": ("type_declaration",),
    "rust": ("struct_item", "enum_item", "trait_item"),
    "java": ("class_declaration", "interface_declaration", "enum_declaration"),
    "c": ("struct_specifier",),
    "cpp": ("class_specifier", "struct_specifier"),
    "csharp": ("class_declaration", "interface_declaration", "struct_declaration"),
    "php": ("class_declaration", "interface_declaration"),
}


__all__ = [
    "TreeSitterEngine",
    "available_grammars",
    "tree_sitter_available",
]
