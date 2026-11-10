"""Large-corpus source layer.

Open any file without copying it, search it without indexing the world, and
answer with bounded tool calls. Roots are catalogued in place; bytes are read
through windows; queries route to metadata, FTS, DuckDB or a bounded scan.

Public surface: ``SourceService`` (build once at boot), ``register_source_tools``
(the agent tools) and the ``sources`` HTTP router.
"""

from __future__ import annotations

from .bootstrap import install_source_layer
from .service import SourceService, build_service, get_sources_service, set_sources_service
from .tools import register_source_tools

__all__ = [
    "install_source_layer", "SourceService", "build_service",
    "get_sources_service", "set_sources_service", "register_source_tools",
]
