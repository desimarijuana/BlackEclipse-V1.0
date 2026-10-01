"""Harness-owned jobs and event triggers (Phase 6).

A job is durable, reviewable DATA: an intent to run a skill or an objective
later, on a cadence or on an event. It holds no executable code and can never
widen authority — the run it produces is subject to exactly the same permission,
allowlist and policy checks as a user-initiated run.

This package is deliberately additive. The three existing TypeScript schedulers
(`src/lib/{scraper,connectors,investor-eye}/*scheduler*`) still drive data
refresh and are untouched; this is the harness job model beside them (ADR-H108).
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
