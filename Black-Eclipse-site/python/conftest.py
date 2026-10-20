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
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# The tests directory is not a package; make the sibling helper importable.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests"))

# Tests must never race a background search warm-index against their temp
# databases. The real runtime leaves this unset (warm-up on); tests turn it off.
os.environ.setdefault("HARNESS_SEARCH_WARM_INDEX", "0")

# The repository source adapter walks the real source tree; a test that indexes
# (e.g. the boot warm-index case) must not pay for that, and its document counts
# must stay about the fixture rows. Production leaves this on (default "1").
os.environ.setdefault("HARNESS_SEARCH_INDEX_REPO", "0")

# Some test modules import `harness.main` at collection time, which constructs the
# process-wide `AgenticService` before most modules have redirected their own temp
# paths. Anchor the MCP server config to a temp file HERE (conftest imports before
# any test module) so a developer's REAL `<repo>/mcp-servers.json` — a legitimate
# app state (Settings → MCP / `mcp_install`) — can never leak into the suite and
# make an unrelated test order-dependent.
os.environ.setdefault(
    "HARNESS_MCP_CONFIG",
    os.path.join(tempfile.mkdtemp(prefix="be-suite-cfg-"), "mcp-servers.json"),
)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_process_globals():
    """Reset process-global subsystem singletons around every test.

    The Artifact Center registers a PROCESS-GLOBAL service at boot
    (`artifacts.bootstrap.install_artifact_layer`, called from
    `AgenticService.__init__` and the `/artifacts/*` self-heal). Without this, a
    test that constructs a service leaks that global into every later test, so a
    test that clears it (`set_artifact_service(None)`) becomes order- and
    timing-dependent. Each test now starts from a clean global and the original
    value is restored afterwards. Purely additive; introduces no new behavior.
    """
    try:
        from harness.artifacts import bootstrap as _artifacts_bootstrap
    except Exception:  # noqa: BLE001 - the artifacts layer is optional
        yield
        return
    saved = _artifacts_bootstrap._SINGLETON  # noqa: SLF001 - the one global we isolate
    _artifacts_bootstrap._SINGLETON = None  # noqa: SLF001
    # The preview engine's video-poster extractor is a module global the video
    # layer registers at boot. Isolate it too, so a test that installs one
    # cannot leak a poster generator into every later test.
    _preview_engine = None
    _poster_saved = None
    try:
        from harness.artifacts import preview as _preview_engine  # noqa: PLC0415

        _poster_saved = _preview_engine._video_poster  # noqa: SLF001
        _preview_engine._video_poster = None  # noqa: SLF001
    except Exception:  # noqa: BLE001 - the preview engine is optional
        _preview_engine = None
    # The UI Engineering runtime registers a process-global service the same way
    # (`ui.bootstrap.install_ui_layer` / the `/ui/*` self-heal). Isolate it too so
    # a test that builds a service cannot leak that global into a later test.
    _ui_bootstrap = None
    _ui_saved = None
    try:
        from harness.ui import bootstrap as _ui_bootstrap  # noqa: PLC0415

        _ui_saved = _ui_bootstrap._SINGLETON  # noqa: SLF001
        _ui_bootstrap._SINGLETON = None  # noqa: SLF001
    except Exception:  # noqa: BLE001 - the ui layer is optional
        _ui_bootstrap = None
    # The recovery tools also hold a process-global service (`set_recovery_service`).
    _recovery_tools = None
    _recovery_saved = None
    try:
        from harness.recovery import tools as _recovery_tools  # noqa: PLC0415

        _recovery_saved = _recovery_tools._SERVICE  # noqa: SLF001
        _recovery_tools._SERVICE = None  # noqa: SLF001
    except Exception:  # noqa: BLE001 - the recovery layer is optional
        _recovery_tools = None
    try:
        yield
    finally:
        _artifacts_bootstrap._SINGLETON = saved  # noqa: SLF001
        if _preview_engine is not None:
            _preview_engine._video_poster = _poster_saved  # noqa: SLF001
        if _ui_bootstrap is not None:
            _ui_bootstrap._SINGLETON = _ui_saved  # noqa: SLF001
        if _recovery_tools is not None:
            _recovery_tools._SERVICE = _recovery_saved  # noqa: SLF001
        # A test may start a warm analysis kernel; never let its process tree
        # survive into the next test (or the pytest process exit).
        try:
            from harness.code import kernel as _kernel  # noqa: PLC0415

            _kernel.reset_kernel_pool()
        except Exception:  # noqa: BLE001 - the analysis kernel is optional
            pass


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
