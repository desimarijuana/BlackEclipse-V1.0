"""Bounded bulk acquisition (Phase 16, first slice).

A request for VOLUME — "two years of daily bars for these 40 names", "the whole
CPI series", "the last four annual statements for each of these" — is served by
ONE bounded, declared collection: a source registry (data, one row per source),
a per-call budget enforced in Python, files written under the run's artifact
directory, and a manifest that says exactly what was collected and what stopped
it. A partial pull is NEVER presented as complete.

The transport is the existing read-only TS bridge (`ctx.data_bridge.fetch`) —
the ONE egress point (R3-04). There is no new HTTP client, no sandbox network,
and no change to the claim-verified research path (`research/`).
"""

from __future__ import annotations

__all__: list[str] = []
