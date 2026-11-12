"""C8 conformance suite — fault matrix, golden traces, contract checks."""

from .cases import CASES, CaseResult
from .runner import MANIFEST, SuiteResult, load_manifest, run_conformance

__all__ = [
    "CASES",
    "CaseResult",
    "MANIFEST",
    "SuiteResult",
    "load_manifest",
    "run_conformance",
]
