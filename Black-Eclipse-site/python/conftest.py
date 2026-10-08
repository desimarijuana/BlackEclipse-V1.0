"""Shared pytest configuration for the harness test suite.

Two jobs:

  1. Make the `harness` package importable when pytest runs from any cwd.
  2. Provide a `tmp_workspace` fixture backed by the resilient temp-base resolver
     in `python/tests/_tmp_helper.py`. Some Windows setups have a locked-down or
     misconfigured `%TEMP%`; a test that only uses the stdlib default then looks
     broken rather than the environment being wrong. The resolver honours
     `BLACK_ECLIPSE_TMP` (the same override `harness.mcp.diagnostics` and
     `doctor.js` respect), falls back to the stdlib temp dir, then to a
     repo-local `.tmp-tests`.

Any test that needs a writable scratch directory can request `tmp_workspace`
instead of `tmp_path`; it receives the same kind of path.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# The tests directory is not a package; make the sibling helper importable.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests"))

# Tests must never race a background search warm-index against their temp
# databases. The real runtime leaves this unset (warm-up on); tests turn it off.
os.environ.setdefault("HARNESS_SEARCH_WARM_INDEX", "0")

import pytest  # noqa: E402


@pytest.fixture
def tmp_workspace():
    """A fresh writable temp directory, resolved the resilient way.

    Prefers `BLACK_ECLIPSE_TMP`, then the stdlib temp dir, then `<repo>/.tmp-tests`.
    Removed on teardown.
    """
    from _tmp_helper import cleanup, make_temp_dir

    path = make_temp_dir("be-test-")
    try:
        yield path
    finally:
        cleanup(path)
