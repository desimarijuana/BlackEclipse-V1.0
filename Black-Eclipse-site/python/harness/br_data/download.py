"""B3 download step — an HTTP fetch with an injectable opener.

The sync never touches the network; this module is the only place that does, and
it is deliberately thin: fetch bytes, prove they are a zip, write them to a
`.part` file, rename atomically, then hand the path to `sync_archive`.

Why an injected `opener` instead of a global client:

  * the tests run against a **recorded fixture** and never reach B3;
  * a caller can supply a retrying/backpressured transport without this module
    growing a second HTTP stack;
  * the default is stdlib `urllib`, so installing Eclipse never pulls an SDK for
    a dataset most users will not sync.

Failure is named and re-raised: a download that writes a truncated file which a
later sync silently accepts is worse than a download that fails.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .cotahist import CotahistError
from .store import BrStore
from .sync import SyncReport, sync_archive

#: A B3 archive is tens of MB; 256 MB is a generous ceiling that still refuses a
#: runaway response before it fills the disk.
MAX_BYTES = 256 * 1024 * 1024

#: `opener(url, timeout) -> bytes`. Injectable so tests never hit the network.
Opener = Callable[[str, float], bytes]


class DownloadError(CotahistError):
    """A fetch problem, with a stable `code` (HTTP_<status>, NOT_ZIP, TOO_LARGE...)."""


def _urllib_opener(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "BlackEclipse/br-data"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"HTTP_{exc.code}", f"B3 returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise DownloadError("UNREACHABLE", f"could not reach {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise DownloadError("TIMEOUT", f"{url} timed out") from exc


#: The stdlib transport under a public name, for callers (the scheduler) that need
#: an opener but must not import a private helper.
open_url: Opener = _urllib_opener


def download_archive(
    url: str,
    dest_dir: str | Path,
    *,
    opener: Optional[Opener] = None,
    timeout: float = 60.0,
    filename: Optional[str] = None,
) -> Path:
    """Fetch `url` into `dest_dir` and return the written path.

    The write is atomic: bytes land in `<name>.part` and are renamed only after
    the payload is proven to be a zip, so a partial file never becomes `latest`.
    """
    payload = (opener or _urllib_opener)(str(url), float(timeout))
    if not isinstance(payload, (bytes, bytearray)):
        raise DownloadError("BAD_PAYLOAD", "the opener returned something that is not bytes")
    data = bytes(payload)
    if len(data) > MAX_BYTES:
        raise DownloadError("TOO_LARGE", f"payload exceeds {MAX_BYTES} bytes")
    if data[:2] != b"PK":
        raise DownloadError("NOT_ZIP", "the response is not a zip archive")
    folder = Path(dest_dir)
    folder.mkdir(parents=True, exist_ok=True)
    name = filename or Path(str(url).split("?")[0]).name or "cotahist.zip"
    target = folder / name
    partial = target.with_suffix(target.suffix + ".part")
    partial.write_bytes(data)
    partial.replace(target)
    return target


def sync_from_url(
    url: str,
    store: BrStore,
    dest_dir: str | Path,
    *,
    opener: Optional[Opener] = None,
    timeout: float = 60.0,
    filename: Optional[str] = None,
) -> SyncReport:
    """download → sync. The store records the run exactly as for a local archive."""
    path = download_archive(url, dest_dir, opener=opener, timeout=timeout, filename=filename)
    return sync_archive(path, store, source=Path(str(url).split("?")[0]).name or path.name)


__all__ = [
    "MAX_BYTES",
    "DownloadError",
    "Opener",
    "download_archive",
    "open_url",
    "sync_from_url",
]
