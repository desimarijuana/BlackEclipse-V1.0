"""Shared text decoding + numeric/date parsing for Brazilian official CSVs.

Brazilian open-data exports agree on almost nothing except the two things that
break naive parsers:

  * **decimal comma** (`5,4321`), often with a thousands dot (`1.234.567,89`);
  * **two date orders** — `dd/mm/yyyy` in BCB/Tesouro, `yyyy-mm-dd` in CVM.

Encoding is also inconsistent (CVM ships Latin-1, Tesouro ships UTF-8 with a
BOM), and Portuguese headers carry accents. `decode` tries UTF-8 first and falls
back to Latin-1, which is lossless for the byte range those files use.

A blank cell becomes `None`, never `0.0`: a missing net asset value and a zero
one are different facts, and a caller that wants zero can say so.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any, Optional

#: Cell values that mean "the publisher did not report a number".
_BLANKS = frozenset({"", "-", "--", "null", "nan", "n/a", "na"})


class DatasetError(ValueError):
    """A dataset could not be parsed, with a stable `code`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def decode(raw: bytes | str) -> str:
    """Decode publisher bytes: UTF-8 (with BOM) first, Latin-1 as the fallback."""
    if isinstance(raw, str):
        return raw.lstrip("\ufeff")
    try:
        return bytes(raw).decode("utf-8-sig")
    except UnicodeDecodeError:
        return bytes(raw).decode("latin-1")


def rows(text: str, *, delimiter: str = ";") -> list[dict[str, str]]:
    """Parse a delimited text into stripped-key dicts, skipping blank lines."""
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise DatasetError("NO_HEADER", "the file has no header row")
    fields = [(name or "").strip() for name in reader.fieldnames]
    out: list[dict[str, str]] = []
    for record in reader:
        row = {
            fields[index]: (record.get(reader.fieldnames[index]) or "").strip()
            for index in range(len(fields))
            if fields[index]
        }
        if any(row.values()):
            out.append(row)
    return out


def number(raw: Any) -> Optional[float]:
    """`1.234,56` / `5,4321` / `1234.56` / `-3` -> float; blank or junk -> None.

    Both decimal conventions appear in this corpus, sometimes in one file, so the
    separator is decided by which one comes LAST, not by the publisher.
    """
    text = str(raw or "").strip()
    if text.lower() in _BLANKS:
        return None
    negative = text.startswith("-") or text.startswith("(")
    text = text.strip("()").lstrip("-+").strip()
    last_comma, last_dot = text.rfind(","), text.rfind(".")
    if last_comma > last_dot:                 # decimal comma: 1.234,56
        text = text.replace(".", "").replace(",", ".")
    elif last_dot > last_comma:               # decimal dot: 1,234.56
        text = text.replace(",", "")
    # Neither separator: already a plain integer, nothing to normalize.
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def iso_date(raw: Any) -> str:
    """`dd/mm/yyyy` or `yyyy-mm-dd` -> ISO date. A blank cell is `""`.

    An unparseable date raises: a row silently dated today would corrupt a time
    series in a way no later check could detect.
    """
    text = str(raw or "").strip()
    if text.lower() in _BLANKS:
        return ""
    if "/" in text:
        parts = text.split("/")
        if len(parts) == 3 and len(parts[2]) == 4:
            day, month, year = parts
        else:
            raise DatasetError("BAD_DATE", f"not a dd/mm/yyyy date: {raw!r}")
    elif "-" in text:
        parts = text.split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            year, month, day = parts
        else:
            raise DatasetError("BAD_DATE", f"not a yyyy-mm-dd date: {raw!r}")
    else:
        raise DatasetError("BAD_DATE", f"not a date: {raw!r}")
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError as exc:
        raise DatasetError("BAD_DATE", f"not a real date: {raw!r}") from exc


def pick(row: dict[str, str], *names: str) -> str:
    """The first present column among `names` (publishers rename columns)."""
    for name in names:
        if name in row:
            return row[name]
    return ""


__all__ = ["DatasetError", "decode", "iso_date", "number", "pick", "rows"]
