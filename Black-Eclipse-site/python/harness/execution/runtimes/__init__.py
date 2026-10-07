"""The runtime registry build + re-exports for the execution layer."""

from __future__ import annotations

from .base import BaseRuntime, PreparedCommand, RuntimeAdapter, RuntimeRegistry, RuntimeUnavailable
from .extra import (
    CRuntime,
    CSharpRuntime,
    CppRuntime,
    GoRuntime,
    JavaRuntime,
    PhpRuntime,
    RubyRuntime,
    RustRuntime,
)
from .javascript import JavaScriptRuntime
from .python_rt import PythonRuntime
from .shell import ShellRuntime
from .sql import SqlRuntime
from .typescript import TypeScriptRuntime

# Languages the layer knows how to detect and reason about. Every one below has a
# registered adapter; an adapter with a missing toolchain reports UNAVAILABLE.
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
    registry.register(GoRuntime())
    registry.register(RustRuntime())
    registry.register(JavaRuntime())
    registry.register(CSharpRuntime())
    registry.register(CRuntime())
    registry.register(CppRuntime())
    registry.register(PhpRuntime())
    registry.register(RubyRuntime())
    return registry


__all__ = [
    "BaseRuntime",
    "CRuntime",
    "CSharpRuntime",
    "CppRuntime",
    "GoRuntime",
    "JavaScriptRuntime",
    "JavaRuntime",
    "PhpRuntime",
    "PreparedCommand",
    "PythonRuntime",
    "RubyRuntime",
    "RuntimeAdapter",
    "RuntimeRegistry",
    "RuntimeUnavailable",
    "RustRuntime",
    "ShellRuntime",
    "SqlRuntime",
    "TypeScriptRuntime",
    "_DECLARED_LANGUAGES",
    "build_runtime_registry",
]
