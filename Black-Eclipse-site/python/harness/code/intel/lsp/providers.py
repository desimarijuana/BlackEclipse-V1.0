"""The shipped language server providers.

Each entry is one mature, real language server. CIUE does not implement language
semantics from scratch, and it does not hard-code a single implementation: the
table below is the registry, and a missing executable is a graceful
`LANGUAGE_SERVER_MISSING`, never a crash.

The launch argv lists are the conventional invocations:

  TypeScript/JavaScript → typescript-language-server --stdio
  Python                → pyright-langserver --stdio (Pyright / basedpyright)
  Java                  → Eclipse JDT LS (jdtls) — project-specific data dir
  C#                    → csharp-ls / OmniSharp-compatible LSP
  C/C++                 → clangd
  Go                    → gopls
  Rust                  → rust-analyzer
  PHP                   → intelephense (node) / phpactor
  SQL                   → sql-language-server

Every argv is a fixed template; `%ROOT%` is the only substitution and it is
resolved from the workspace root, never model text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .provider import LanguageServerProvider, LanguageServerSpec, SpecProvider

# Each spec tries its primary form, then the fallbacks, until one resolves.
_SPECS: tuple[LanguageServerSpec, ...] = (
    LanguageServerSpec(
        provider_id="typescript",
        languages=("typescript", "javascript"),
        argv=("typescript-language-server", "--stdio"),
        fallbacks=(
            ("npx", "--yes", "typescript-language-server@latest", "--stdio"),
        ),
        initialization_options={
            "hostInfo": "eclipse",
            "preferences": {"includeInlayParameterNameHints": "none"},
        },
    ),
    LanguageServerSpec(
        provider_id="python",
        languages=("python",),
        argv=("pyright-langserver", "--stdio"),
        fallbacks=(
            ("npx", "--yes", "pyright-langserver", "--stdio"),
            ("basedpyright-langserver", "--stdio"),
        ),
        initialization_options={"settings": {"python": {"analysis": {"typeCheckingMode": "basic"}}}},
    ),
    LanguageServerSpec(
        provider_id="java",
        languages=("java",),
        argv=("jdtls", "-data", "%ROOT%"),
        fallbacks=(("eclipse-jdtls", "-data", "%ROOT%"),),
    ),
    LanguageServerSpec(
        provider_id="csharp",
        languages=("csharp",),
        argv=("csharp-ls",),
        fallbacks=(("omnisharp", "--languageserver"),),
    ),
    LanguageServerSpec(
        provider_id="cpp",
        languages=("c", "cpp"),
        argv=("clangd", "--background-index"),
        fallbacks=(("clangd",),),
    ),
    LanguageServerSpec(
        provider_id="go",
        languages=("go",),
        argv=("gopls",),
        fallbacks=(("gopls", "serve"),),
    ),
    LanguageServerSpec(
        provider_id="rust",
        languages=("rust",),
        argv=("rust-analyzer",),
    ),
    LanguageServerSpec(
        provider_id="php",
        languages=("php",),
        argv=("intelephense", "--stdio"),
        fallbacks=(("phpactor", "language-server"),),
    ),
    LanguageServerSpec(
        provider_id="sql",
        languages=("sql",),
        argv=("sql-language-server", "up", "--method", "stdio"),
        fallbacks=(("sql-language-server", "up", "--stdio"),),
    ),
)


def build_providers() -> list[LanguageServerProvider]:
    return [
        SpecProvider(provider_id=spec.provider_id, languages=spec.languages, server_spec=spec)
        for spec in _SPECS
    ]


# The languages CIUE can serve when a server is installed. A language with no
# provider is structurally understood (AST/index) but has no semantic layer.
SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(
    dict.fromkeys(lang for spec in _SPECS for lang in spec.languages)
)


def provider_for_language(language: str) -> Optional[LanguageServerSpec]:
    """The spec that serves a language, or None. The first match wins."""
    for spec in _SPECS:
        if language in spec.languages:
            return spec
    return None


__all__ = [
    "SUPPORTED_LANGUAGES",
    "build_providers",
    "provider_for_language",
]
