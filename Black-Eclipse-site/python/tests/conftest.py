"""Shared pytest isolation for the process-wide model runtime.

The model runtime's circuit breaker and rate limiter are intentionally shared
across runs in production. The test suite exercises many failure paths against
the same provider keys, so without resetting that process-wide state a later
test can be refused by a circuit opened by an earlier test. Reset only the
transport-health state; usage/cost history stays intact.

Code indexes are scratch caches. Tests that build a real workspace index would
otherwise write one DB per temp project root into the checkout's
`.black-eclipse/code-index/` (thousands of `ws_tools_*.db` files over a few
weeks). Point both index stores at one temp dir for the whole session; the env
vars are inherited by child processes too, and the dir is removed at exit.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest

_INDEX_SCRATCH = Path(tempfile.mkdtemp(prefix="eclipse-test-index-"))
os.environ.setdefault("HARNESS_CODE_INTEL_INDEX_DIR", str(_INDEX_SCRATCH / "code-index"))
os.environ.setdefault("HARNESS_WORKSPACE_INDEX_DIR", str(_INDEX_SCRATCH / "workspace-index"))
atexit.register(shutil.rmtree, _INDEX_SCRATCH, True)


@pytest.fixture(autouse=True)
def _isolate_model_circuits():
    try:
        from harness.model_runtime import get_runtime
        from harness.model_runtime.health import CircuitBreaker, HealthManager, RateLimitManager

        runtime = get_runtime()
        runtime.circuit = CircuitBreaker()
        runtime.rate_limits = RateLimitManager()
        runtime.health = HealthManager()
        router = getattr(runtime, "_router", None)
        if router is not None:
            router._circuit = runtime.circuit
            router._rate_limits = runtime.rate_limits
            router._health = runtime.health
    except Exception:  # noqa: BLE001 - runtime may not be importable in a tiny test
        pass
    yield
