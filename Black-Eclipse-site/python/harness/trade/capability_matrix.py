"""Generated broker capability matrix for `docs/trading.md`.

The declarations live in `trade/model.BrokerKind` (registered through
`trade/registry.register_kind`). This module renders them into the doc so the
page cannot quietly disagree with the code, and `--check` fails when it does.

What a row means, stated once:

  * It is a **declaration**, not a runtime verification. `available` reports
    only whether the adapter's dependency imports on this host.
  * A `demo` mode never grants live trading. Live execution still requires an
    armed connection and a mandate (`trade/authority.py`, `trade/mandates.py`).
  * A kind with no `execution` is read-only; it can report account, positions
    and quotes but cannot place an order.

Run `python -m harness.trade.capability_matrix --write` after changing a kind,
or `--check` to verify the committed page (CI does the latter).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

BEGIN = "<!-- BEGIN GENERATED broker-capability-matrix -->"
END = "<!-- END GENERATED broker-capability-matrix -->"

#: `python/harness/trade/capability_matrix.py` -> repo `Black-Eclipse-site/`.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = _REPO_ROOT / "docs" / "trading.md"

INTRO = (
    "Declared broker kinds, generated from `python/harness/trade/registry.py`.\n"
    "Every row is a **declaration, not a runtime verification**: `available`\n"
    "only reports whether the adapter's dependency imports on this host, and a\n"
    "paper mode never grants live trading. Live execution still requires an\n"
    "armed connection plus a mandate. In the Capabilities column `orders` means\n"
    "**reading** working orders; only the Execution column permits placement, so\n"
    "a kind without execution is read-only."
)

_HEADER = (
    "| Kind | Label | Auth | Modes | Asset classes | Capabilities | Execution | Available |\n"
    "|---|---|---|---|---|---|---|---|"
)


def _cell(values: Iterable[Any]) -> str:
    """A table cell: sorted, backticked, or an explicit `none`."""
    items = sorted({str(v) for v in values if v not in (None, "")})
    return ", ".join(f"`{v}`" for v in items) if items else "none"


def _availability(row: dict[str, Any]) -> str:
    if row.get("available"):
        return "yes"
    return f"no — {row.get('unavailableReason') or 'unavailable'}"


def kind_rows() -> list[dict[str, Any]]:
    """Every registered broker kind, sorted by id. Imports the registry lazily."""
    from .registry import list_kinds  # noqa: PLC0415 - keep module import cheap

    rows = list_kinds()
    return sorted(rows, key=lambda row: str(row.get("id", "")))


def render_table(rows: Sequence[dict[str, Any]]) -> str:
    """The markdown table for already-fetched rows (pure, testable)."""
    lines = [INTRO, "", _HEADER]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{row.get('id', '')}`",
                    str(row.get("label") or row.get("id") or ""),
                    f"`{row.get('auth', '')}`",
                    _cell(row.get("modes") or ()),
                    _cell(row.get("assetClasses") or ()),
                    _cell(row.get("capabilities") or ()),
                    "yes" if row.get("execution") else "no (read-only)",
                    _availability(row),
                )
            )
            + " |"
        )
    if not rows:
        lines.append("| none registered | — | — | — | — | — | — | — |")
    return "\n".join(lines)


def render_block() -> str:
    """The full marker-delimited block (for `--print` and review diffs)."""
    return _wrap(render_table(kind_rows()))


def _wrap(body: str) -> str:
    """Put an inner body between the generated markers."""
    return "\n".join((BEGIN, "", body.strip(), "", END))


def splice(document: str, body: str) -> str:
    """Replace the generated block with `body`, or append one when absent.

    `body` is the INNER table text; the markers are added here so a caller can
    never forget them.
    """
    block = _wrap(body)
    start = document.find(BEGIN)
    end = document.find(END)
    if start != -1 and end != -1 and end > start:
        return document[:start] + block + document[end + len(END):]
    separator = "" if document.endswith("\n") else "\n"
    return f"{document}{separator}\n## Declared broker kinds (generated)\n\n{block}\n"


def check(path: Path = DOC_PATH) -> list[str]:
    """Problems that make the committed page disagree with the code."""
    if not path.exists():
        return [f"{path} does not exist"]
    document = path.read_text(encoding="utf-8")
    if BEGIN not in document or END not in document:
        return [f"{path} has no generated block ({BEGIN} … {END})"]
    start = document.find(BEGIN)
    end = document.find(END)
    current = document[start + len(BEGIN):end]
    expected = render_table(kind_rows())
    if current.strip() != expected.strip():
        return [
            f"{path} broker capability matrix is stale; "
            "run `python -m harness.trade.capability_matrix --write`"
        ]
    return []


def write(path: Path = DOC_PATH) -> None:
    path.write_text(splice(path.read_text(encoding="utf-8"), render_table(kind_rows())), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the broker capability matrix.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="update docs/trading.md")
    group.add_argument("--check", action="store_true", help="fail if the page is stale")
    group.add_argument("--print", action="store_true", help="print the block to stdout")
    args = parser.parse_args(argv)

    if args.print:
        print(render_block())
        return 0
    if args.write:
        write()
        print(f"wrote {DOC_PATH}")
        return 0
    problems = check()
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
