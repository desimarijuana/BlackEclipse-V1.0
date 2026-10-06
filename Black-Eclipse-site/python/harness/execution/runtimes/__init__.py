"""The runtime registry build + re-exports for the execution layer."""

from __future__ import annotations

from .base import BaseRuntime, PreparedCommand, RuntimeAdapter, RuntimeRegistry, RuntimeUnavailable
from .javascript import JavaScriptRuntime
from .python_rt import PythonRuntime
from .shell import ShellRuntime
from .sql import SqlRuntime
from .typescript import TypeScriptRuntime

# Languages the layer knows how to detect and reason about, even where an
# execution adapter is not yet wired (these report UNAVAILABLE honestly).
_DECLARED_LANGUAGES = (
    "python", "javascript", "typescript", "sql", "shell",
    "rust", "go", "java", "csharp", "c", "cpp", "php", "ruby",
)


def build_runtime_registry() -> RuntimeRegistry:
    """Register the shipped adapters. Adding a language = register one adapter."""
    registry = RuntimeRegistry()
    registry.register(PythonRuntime())
    registry.register(JavaScriptRuntime())
    registry.register(TypeScriptRuntime())
    registry.register(SqlRuntime())
    registry.register(ShellRuntime())
    return registry


__all__ = [
    "BaseRuntime",
    "JavaScriptRuntime",
    "PreparedCommand",
    "PythonRuntime",
    "RuntimeAdapter",
    "RuntimeRegistry",
    "RuntimeUnavailable",
    "ShellRuntime",
    "SqlRuntime",
    "TypeScriptRuntime",
    "_DECLARED_LANGUAGES",
    "build_runtime_registry",
]
