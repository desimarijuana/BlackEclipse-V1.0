"""The LSP package: a provider-agnostic Language Server Protocol client.

CIUE never depends on one language server. `LanguageServerProvider` describes how
to detect, launch and handshake ONE server; `LSPManager` routes a request to the
right running server and degrades honestly when none is available.
"""
