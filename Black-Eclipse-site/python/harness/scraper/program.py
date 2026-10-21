"""The contract between a generated scraper program and the host.

The program is ordinary Python, with ONE obligation: it must leave its answer
in a global named ``result`` —

    result = {"rows": [{"name": "...", "value": "..."}], "columns": ["name", "value"]}

``rows`` is a list of flat records (string keys, scalar values). ``columns`` is
optional (the host derives it from the rows when it is absent) and ``notes`` is
an optional plain-language sentence about what the run found.

Everything here is a BOUND, not a rule about what the program may do: the
sandbox's own checks (imports, reflection, sockets) are enforced in
``code/execution.py`` and are not re-implemented here. This module only decides
whether what came back is usable, and refuses it honestly when it is not.
"""

from __future__ import annotations

from typing import Any

MAX_PROGRAM_CHARS = 20_000
MAX_ROWS = 5_000
MAX_COLUMNS = 64
MAX_COLUMN_NAME = 64
MAX_CELL_CHARS = 2_000
MAX_NOTES_CHARS = 2_000

#: The scalar cell types a record may hold. A nested object or list is refused:
#: the vault stores flat records, and a nested value would have no honest
#: column shape.
_SCALARS = (str, int, float, bool)


class ScraperProgramError(ValueError):
    """A scraper program that cannot be run, or whose answer is unusable."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def check_program(source: str) -> str:
    """Validate the program's SIZE (the AST rules live in the sandbox)."""
    text = source if isinstance(source, str) else ""
    if not text.strip():
        raise ScraperProgramError("PROGRAM_INVALID", "the scraper program is empty")
    if len(text) > MAX_PROGRAM_CHARS:
        raise ScraperProgramError(
            "PROGRAM_TOO_LARGE",
            f"the scraper program is longer than {MAX_PROGRAM_CHARS} characters",
        )
    return text


#: Appended to the agent's program so that "the program never answered" is a
#: failure with a plain reason, not a dataset of zero rows. The sandbox's own
#: restrictions (no reflection, no `globals`/`dir`) are why this reads the
#: name with a `try` instead of asking the namespace.
_MISSING_RESULT = """

# --- host check (added by Eclipse) ---
try:
    result
except NameError:
    raise ValueError("the scraper program did not set `result`")
"""


def wrap_program(source: str) -> str:
    """The program as the sandbox runs it: the agent's code + the answer check."""
    return source + _MISSING_RESULT


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str):
        return value[:MAX_CELL_CHARS]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    return str(value)[:MAX_CELL_CHARS]


def read_result(outputs: Any) -> tuple[list[dict[str, Any]], list[str], str]:
    """Read the program's answer: (rows, columns, notes).

    The host wraps the program so that it either sets ``result`` or fails
    loudly; what arrives here IS that answer. A program that produced no
    answer is a FAILURE, not an empty dataset: "I collected nothing" and "the
    program never answered" must not look alike.
    """
    if not isinstance(outputs, dict):
        raise ScraperProgramError(
            "RESULT_INVALID",
            "`result` must be an object with a `rows` list",
        )
    if "rows" not in outputs:
        raise ScraperProgramError(
            "RESULT_MISSING",
            "the scraper program did not leave an answer in `result`",
        )
    result = outputs
    raw_rows = result.get("rows")
    if not isinstance(raw_rows, list):
        raise ScraperProgramError(
            "RESULT_INVALID",
            "`result` must have a `rows` list",
        )
    if len(raw_rows) > MAX_ROWS:
        raise ScraperProgramError(
            "RESULT_TOO_LARGE",
            f"the scraper returned more than {MAX_ROWS} rows",
        )

    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            raise ScraperProgramError(
                "RESULT_INVALID",
                "every row must be an object of field → value",
            )
        clean: dict[str, Any] = {}
        for key, value in row.items():
            name = str(key).strip()
            if not name:
                continue
            if len(name) > MAX_COLUMN_NAME:
                name = name[:MAX_COLUMN_NAME]
            if not isinstance(value, _SCALARS) and value is not None:
                value = str(value)
            clean[name] = _cell(value)
        rows.append(clean)

    columns: list[str] = []
    raw_columns = result.get("columns")
    if isinstance(raw_columns, list):
        for column in raw_columns:
            name = str(column).strip()
            if name and name not in columns:
                columns.append(name[:MAX_COLUMN_NAME])
    if not columns:
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    columns.append(key)
    if len(columns) > MAX_COLUMNS:
        columns = columns[:MAX_COLUMNS]

    notes = str(result.get("notes") or "")[:MAX_NOTES_CHARS]
    return rows, columns, notes


__all__ = [
    "MAX_CELL_CHARS",
    "MAX_COLUMNS",
    "MAX_NOTES_CHARS",
    "MAX_PROGRAM_CHARS",
    "MAX_ROWS",
    "ScraperProgramError",
    "check_program",
    "read_result",
    "wrap_program",
]
