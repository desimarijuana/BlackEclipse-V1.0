"""Eclipse Document Intelligence subsystem.

A production-grade document-understanding capability integrated with the existing
agent runtime, model/provider layer, vision subsystem, Evidence & Research Engine,
OCR engines, query engine, storage, security, telemetry and evaluation.

The public surface:

    DocumentIR / Page / Sheet / ...            — the intermediate representation
    DocumentContext / process_document        — the ONE processing pipeline
    get_adapter / known_kinds                 — the format adapters
    DocumentStore                             — durable tables on agent-memory.db
    search / search_document                  — hybrid retrieval
    compare_documents                         — structured comparison
    query_rows                                — deterministic tabular query
    register_document_tools                   — the agent tools

Nothing here builds a second provider stack, a second OCR engine, a second
evidence store or a second database: every one of those is reused.
"""

from __future__ import annotations

from .chunking import Chunk, chunk_ir
from .compare import ComparisonChange, ComparisonResult, compare_documents
from .config import DocumentConfig, document_config, document_enabled
from .contracts import *  # noqa: F401,F403  (re-export the IR vocabulary)
from .errors import DocumentError, DocumentErrorClass
from .ir import (
    BBox,
    Block,
    DateFacts,
    DocumentIR,
    DocumentImage,
    Page,
    Provenance,
    Section,
    Sheet,
    Table,
    TableCell,
)
from .orchestrator import (
    DocumentContext,
    ProcessedDocument,
    compare_documents_by_ir,
    document_available_kinds,
    process_document,
    query_document,
    search_document,
)
from .processing import ProcessingState, StageResult
from .query import QueryResult, engine_available, query_rows, validate_sql
from .retrieval import RetrievalHit, RetrievalResult, search
from .store import DocumentStore

__all__ = [
    "DocumentConfig", "document_config", "document_enabled",
    "DocumentIR", "Page", "Sheet", "Block", "Table", "TableCell", "DocumentImage",
    "Section", "BBox", "Provenance", "DateFacts",
    "DocumentError", "DocumentErrorClass",
    "DocumentContext", "ProcessedDocument", "process_document",
    "DocumentStore", "Chunk", "chunk_ir",
    "RetrievalHit", "RetrievalResult", "search", "search_document",
    "ComparisonChange", "ComparisonResult", "compare_documents", "compare_documents_by_ir",
    "QueryResult", "query_rows", "query_document", "engine_available", "validate_sql",
    "ProcessingState", "StageResult", "document_available_kinds",
]
