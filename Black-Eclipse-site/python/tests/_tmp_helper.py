"""A resilient temp-directory helper for tests (Windows permission issues).

Some Windows setups have a locked-down or misconfigured `%TEMP%`, which makes a
healthy test look broken when it cannot create its scratch directory. This helper
tries, in order:

  1. `BLACK_ECLIPSE_TMP` (explicit override),
  2. the standard `tempfile.gettempdir()`,
  3. a `.tmp-tests` folder under the repository root.

It never raises for the *first* two failures — it falls through — and only fails
if NO location is writable, with a message that names the fix.
"""

from __future__ import annotations

import os
import shutil
import tempfile

from harness.eclipse_memory.config import repo_root

PROBE_NAME = ".be_write_probe"


def _writable(base: str) -> bool:
    try:
        os.makedirs(base, exist_ok=True)
        probe = os.path.join(base, PROBE_NAME)
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def candidates() -> list[str]:
    return [
        os.environ.get("BLACK_ECLIPSE_TMP", ""),
        tempfile.gettempdir(),
        os.path.join(repo_root(), ".tmp-tests"),
    ]


def resolve_tmp_base() -> str:
    """Return a writable base temp directory, or raise with recovery guidance."""
    for base in candidates():
        if base and _writable(base):
            return base
    raise RuntimeError(
        "No writable temporary directory found. Set BLACK_ECLIPSE_TMP to a writable "
        "folder (e.g. your user Temp directory) and restart."
    )


def make_temp_dir(prefix: str = "be-test-") -> str:
    """Create a fresh temp directory under the resolved base."""
    base = resolve_tmp_base()
    return tempfile.mkdtemp(prefix=prefix, dir=base)


def cleanup(path: str) -> None:
    """Best-effort removal of a directory created for a test."""
    shutil.rmtree(path, ignore_errors=True)


__all__ = ["resolve_tmp_base", "make_temp_dir", "cleanup", "candidates"]
