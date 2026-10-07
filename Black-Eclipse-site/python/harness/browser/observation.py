"""Accessibility-first observation.

`browser_snapshot` does NOT dump raw HTML. It asks Playwright for the page's
accessibility tree (`aria_snapshot(mode="ai")`), which annotates each node with a
stable Playwright aria ref (`[ref=eN]`). Eclipse RENUMBERS those to its own
stable, per-snapshot references (`@e1`, `@e2`, …) and keeps the mapping, so the
agent can act on `@e4` and the runtime resolves it against the CURRENT page.

Large pages never flood the model: when the rendered snapshot exceeds the
configured character budget the FULL text is persisted under
`artifacts_root/snapshots/<session>/<snapshot>.txt` (the existing gitignored
artifacts area, never the operator's checkout) and the model receives a bounded,
paginated head plus the path — the same filesystem the rest of the harness uses.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Matches a Playwright aria ref annotation: `[ref=e12]`.
_REF_RE = re.compile(r"\[ref=(e\d+)\]")
# Matches a snapshot line `- role "name":` / `- role "name"`. Role is the token
# after `- ` up to the first space; name (if any) is the first quoted string.
_LINE_RE = re.compile(r'^\s*-\s+(?P<role>[A-Za-z][A-Za-z0-9]*)(?:\s+"(?P<name>[^"]*)")?')

INTERACTIVE_ROLES = frozenset({
    "button", "link", "textbox", "checkbox", "radio", "combobox", "listbox",
    "menuitem", "menuitemcheckbox", "menuitemradio", "option", "searchbox",
    "slider", "spinbutton", "switch", "tab", "treeitem", "textbox",
})


@dataclass
class SnapshotElement:
    ref: str            # Eclipse stable ref: `@e3`
    aria_ref: str       # Playwright ref: `e3`
    role: str
    name: str
    line: str
    interactive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref, "role": self.role, "name": self.name,
            "interactive": self.interactive, "line": self.line,
        }


@dataclass
class Snapshot:
    generation: int
    url: str
    title: str
    text: str                 # the bounded, model-facing text
    full_text: str            # the complete text (never sent whole)
    elements: dict[str, SnapshotElement] = field(default_factory=dict)
    full_path: Optional[str] = None
    truncated: bool = False
    chars: int = 0
    created_at: float = 0.0

    @property
    def interactive(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.elements.values() if e.interactive]

    def element(self, ref: str) -> Optional[SnapshotElement]:
        return self.elements.get(ref)

    def summary(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "url": self.url,
            "title": self.title,
            "chars": self.chars,
            "truncated": self.truncated,
            "fullPath": self.full_path,
            "elementCount": len(self.elements),
            "interactiveCount": len(self.interactive),
        }


def parse_snapshot(raw: str, generation: int) -> tuple[str, dict[str, SnapshotElement]]:
    """Renumber Playwright aria refs to Eclipse `@eN` refs.

    Returns `(renumbered_text, elements)`. The renumbering is deterministic and
    ORDERED by first appearance, so the same tree yields the same refs and a
    re-snapshot on an unchanged page is stable.
    """
    mapping: dict[str, str] = {}
    counter = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal counter
        aria_ref = match.group(1)
        eclipse_ref = mapping.get(aria_ref)
        if eclipse_ref is None:
            counter += 1
            eclipse_ref = f"@e{counter}"
            mapping[aria_ref] = eclipse_ref
        return f"[ref={eclipse_ref}]"

    renumbered = _REF_RE.sub(_sub, raw)

    elements: dict[str, SnapshotElement] = {}
    for line in renumbered.splitlines():
        ref_match = re.search(r"\[ref=(@e\d+)\]", line)
        if not ref_match:
            continue
        eclipse_ref = ref_match.group(1)
        line_match = _LINE_RE.match(line)
        role = line_match.group("role") if line_match else "generic"
        name = (line_match.group("name") if line_match else "") or ""
        aria_ref = next((a for a, e in mapping.items() if e == eclipse_ref), "")
        elements[eclipse_ref] = SnapshotElement(
            ref=eclipse_ref, aria_ref=aria_ref, role=role, name=name,
            line=line.strip(), interactive=role in INTERACTIVE_ROLES,
        )
    return renumbered, elements


def _bound(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    marker = (
        f"\n\n[TRUNCATED: this page's snapshot is {len(text)} characters; the "
        f"first {limit} are shown. The complete snapshot is saved at the path "
        "above — read it with the file tools and page through it.]"
    )
    return text[:limit] + marker


class SnapshotEngine:
    """Builds and persists accessibility snapshots for one session."""

    def __init__(self, *, session_id: str, snapshots_dir: Path, max_chars: int) -> None:
        self._session_id = session_id
        self._dir = Path(snapshots_dir) / session_id
        self._max_chars = max(1_000, int(max_chars))
        self.generation = 0
        self._latest: Optional[Snapshot] = None

    @property
    def latest(self) -> Optional[Snapshot]:
        return self._latest

    async def build(self, page: Any, *, persist_on_truncate: bool = True) -> Snapshot:
        """Capture the current page as an accessibility snapshot."""
        self.generation += 1
        generation = self.generation
        url = ""
        title = ""
        try:
            url = page.url
        except Exception:  # noqa: BLE001
            url = ""
        try:
            title = await page.title()
        except Exception:  # noqa: BLE001
            title = ""
        raw = ""
        try:
            # `mode="ai"` yields the ref-annotated tree; it is the closest to the
            # Hermes/Playwright accessibility snapshot with stable refs.
            raw = await page.locator("body").aria_snapshot(mode="ai")
        except Exception:
            try:
                raw = await page.locator("body").aria_snapshot()
            except Exception:  # noqa: BLE001 - an unrendered page has no tree
                raw = ""
        if not raw.strip():
            raw = f"- generic [ref=e1]: (the page has no accessibility content)\n  - text: {title}"
        renumbered, elements = parse_snapshot(raw, generation)
        full_text = renumbered
        full_path: Optional[str] = None
        truncated = len(full_text) > self._max_chars
        if truncated and persist_on_truncate:
            full_path = str(self._persist(generation, url, title, full_text))
        text = _bound(full_text, self._max_chars)
        snapshot = Snapshot(
            generation=generation, url=url, title=title, text=text, full_text=full_text,
            elements=elements, full_path=full_path, truncated=truncated,
            chars=len(full_text), created_at=time.time(),
        )
        self._latest = snapshot
        return snapshot

    def _persist(self, generation: int, url: str, title: str, text: str) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"snapshot-{generation}-{int(time.time())}.txt"
        header = f"# Eclipse browser snapshot\n# url: {url}\n# title: {title}\n\n"
        try:
            path.write_text(header + text, encoding="utf-8")
        except OSError:
            return path
        return path

    def resolve_ref(self, ref: str) -> Optional[SnapshotElement]:
        if self._latest is None:
            return None
        return self._latest.element(ref)


def persist_artifact(
    *, session_id: str, kind: str, text: str, root: Path,
) -> Optional[str]:
    """Persist a large model-facing artifact to disk and return its path.

    Used for console/network/error dumps: when the rendered text exceeds the
    context budget the FULL text is written under `artifactsRoot/<kind>/<session>/`
    (the same gitignored area snapshots use) and the model receives a bounded head
    plus the path. Returns None if the write fails (the caller then bounds only).
    """
    directory = Path(root) / kind / session_id
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{kind}-{int(time.time())}.txt"
        path.write_text(text, encoding="utf-8")
        return str(path)
    except OSError:
        return None


__all__ = [
    "INTERACTIVE_ROLES",
    "Snapshot",
    "SnapshotElement",
    "SnapshotEngine",
    "parse_snapshot",
    "persist_artifact",
]
