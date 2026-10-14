"""The ceiling-enforcing CSV writer.

Pure and testable without network: given rows and a budget, it writes the file
under the run's artifact directory, stops at the row OR byte ceiling, and reports
`(rows_written, complete, stopped_reason)`. The row count it returns is the
count of rows ACTUALLY in the file (the caller verifies against a re-read), and
a partial file is always accompanied by a plain reason.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Iterable

from .budget import AcquisitionBudget


def write_csv(
    path: Path,
    columns: tuple[str, ...],
    rows: Iterable[dict[str, Any]],
    budget: AcquisitionBudget,
) -> tuple[int, bool, str]:
    """Write rows as CSV under the budget. Returns (rows_written, complete, why).

    `complete` is False when the row or byte ceiling stopped the write; `why` is
    a plain sentence naming the limit. Values are stringified; a missing column
    value is written as an empty field (never fabricated).
    """
    buffer = io.StringIO()
    csv.DictWriter(
        buffer, fieldnames=list(columns), extrasaction="ignore", lineterminator="\n",
    ).writeheader()
    written = 0
    stopped = ""
    for row in rows:
        line = io.StringIO()
        csv.DictWriter(
            line, fieldnames=list(columns), extrasaction="ignore", lineterminator="\n",
        ).writerow({key: _clean(row.get(key)) for key in columns})
        encoded = line.getvalue()
        if budget.rows + 1 > budget.max_rows:
            stopped = f"reached the collection limit ({budget.max_rows:,} rows)"
            break
        if budget.bytes_written + len(buffer.getvalue()) + len(encoded) > budget.max_bytes_written:
            stopped = (
                f"reached the collection limit "
                f"({budget.max_bytes_written // (1024 * 1024)} MB)"
            )
            break
        buffer.write(encoded)
        budget.record_rows(1)
        written += 1
    data = buffer.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    # `newline=""` disables the platform newline translation: the file carries
    # the LF terminators exactly as written (Windows would otherwise turn every
    # "\n" into "\r\n" inside already-CRLF-free content and double the breaks).
    path.write_text(data, encoding="utf-8", newline="")
    budget.record_bytes(len(data.encode("utf-8")))
    return written, not stopped, stopped


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


__all__ = ["write_csv"]
