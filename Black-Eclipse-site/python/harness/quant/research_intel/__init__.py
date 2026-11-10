"""Quant Research Intelligence.

A research layer on top of the deterministic quant engine: scholarly discovery,
literature extraction with provenance, a method knowledge base, explained
suitability, reproduction separated from trading adaptation, validation and the
Quant Research Dossier.

It creates no second engine, database, search stack or agent. See
`docs/quant-research-intelligence-plan.md`.
"""

from .catalog import CATALOG, catalog_by_id, get_catalog_method, list_catalog
from .schema import (
    IMPLEMENTATION_STATUS,
    LIFECYCLE,
    METHOD_SCHEMA_VERSION,
    REPRODUCTION_STATUS,
    normalize_spec,
    validate_method_spec,
)
from .store import ResearchStore

__all__ = [
    "CATALOG",
    "IMPLEMENTATION_STATUS",
    "LIFECYCLE",
    "METHOD_SCHEMA_VERSION",
    "REPRODUCTION_STATUS",
    "ResearchStore",
    "catalog_by_id",
    "get_catalog_method",
    "list_catalog",
    "normalize_spec",
    "validate_method_spec",
]
