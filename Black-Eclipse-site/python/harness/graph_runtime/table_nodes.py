"""Tabular transform nodes.

Financial data arrives as arrays of JSON objects (bars, fundamentals, filings,
screener rows). These nodes cover the common deterministic operations without a
second dataframe engine: select/rename, sort/limit, aggregate/group, dedupe and
join. Every node is bounded and fails honestly on a shape it cannot handle.

Contract notes that are easy to get wrong:

* A dotted path (`fundamentals.pe`) is resolved the same way everywhere; the
  output column keeps the name that was typed unless an `alias=path` was given.
* `sort_limit` coerces numeric strings, so a provider that sends `"100"` sorts
  as a number, not lexicographically. Nulls always sort last, in both directions.
* `join` normalises keys (`1`, `1.0` and `"1"` match) and never silently drops
  duplicate right-side rows: `onDuplicate` decides first/last/all.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Optional

from .model import ExecutionMode, PortDef, PortKind, PortType
from .registry import ConfigField, NodeDef, NodeExecContext
from .values import MISSING, coerce_number, key_part, resolve_path

_ALL = tuple(ExecutionMode)
MAX_ROWS = 100_000
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z_0-9]{0,63}$")


def rows_of(value: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(value, dict) and isinstance(value.get("rows"), list):
        value = value["rows"]
    if not isinstance(value, list):
        raise ValueError(f"{label} expects an array of objects")
    if len(value) > MAX_ROWS:
        raise ValueError(f"{label} is bounded to {MAX_ROWS} rows (got {len(value)})")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise ValueError(f"{label} row {index} is {type(row).__name__}, expected an object")
        rows.append(row)
    return rows


def field_of(row: dict[str, Any], path: str) -> Any:
    """Backwards-compatible wrapper: a missing path reads as null."""
    if not path:
        return row
    value = resolve_path(row, path)
    return None if value is MISSING else value


def _parse_list(text: Any) -> list[str]:
    return [part.strip() for part in str(text or "").split(",") if part.strip()]


def _parse_json_object(text: Any, label: str) -> dict[str, Any]:
    if isinstance(text, dict):
        return text
    if not text:
        return {}
    try:
        parsed = json.loads(str(text))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a JSON object")
    return parsed


def _parse_projection(text: Any) -> list[tuple[str, str]]:
    """Parse `fields` into (output name, dotted path) pairs.

    Accepts `symbol`, `fundamentals.pe` and `pe=fundamentals.pe`. The output
    column keeps the typed text unless an explicit alias is supplied, so a
    reader of the downstream data can see where it came from.
    """
    projection: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in _parse_list(text):
        if "=" in entry:
            alias, _, path = entry.partition("=")
            alias, path = alias.strip(), path.strip()
            if not _IDENTIFIER.match(alias):
                raise ValueError(f"field alias {alias!r} must be a plain name (letters, digits, _)")
            if not path:
                raise ValueError(f"field {entry!r} has an alias but no path")
        else:
            alias = path = entry
        if alias in seen:
            raise ValueError(f"field {alias!r} is selected more than once")
        seen.add(alias)
        projection.append((alias, path))
    return projection


def exec_select(context: NodeExecContext) -> dict[str, Any]:
    rows = rows_of(context.inputs.get("rows"), "transform.select")
    projection = _parse_projection(context.config.get("fields"))
    rename = _parse_json_object(context.config.get("rename"), "rename")
    on_missing = str(context.config.get("onMissing") or "null").strip().lower()
    if on_missing not in ("null", "drop", "error"):
        raise ValueError(f"unsupported onMissing policy {on_missing!r}")

    out: list[dict[str, Any]] = []
    dropped = 0
    for index, row in enumerate(rows):
        if projection:
            source: dict[str, Any] = {}
            keep_row = True
            for alias, path in projection:
                value = resolve_path(row, path)
                if value is MISSING:
                    if on_missing == "error":
                        raise ValueError(f"row {index} has no field {path!r}")
                    if on_missing == "drop":
                        keep_row = False
                        break
                    value = None
                source[alias] = value
            if not keep_row:
                dropped += 1
                continue
        else:
            source = dict(row)

        if rename:
            renamed: dict[str, Any] = {}
            for key, value in source.items():
                target = rename.get(key, key)
                if not isinstance(target, str) or not target.strip():
                    raise ValueError(f"rename target for {key!r} must be a non-empty name")
                if target in renamed:
                    raise ValueError(
                        f"rename maps more than one field to {target!r}; "
                        "a column would be silently lost"
                    )
                renamed[target] = value
            source = renamed
        out.append(source)

    return {"rows": out, "dropped": dropped, "_control": ["done"]}


class _Descending:
    """Invert one component of a sort key without reversing null placement."""

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value

    def __lt__(self, other: "_Descending") -> bool:
        return other.value < self.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Descending) and self.value == other.value


def _sort_key(value: Any, descending: bool, case_insensitive: bool = False) -> tuple[int, int, Any]:
    if value is None or value is MISSING:
        # Nulls last in BOTH directions: a missing price is not the smallest one.
        return (1, 0, 0.0)
    if isinstance(value, bool):
        return (0, 0, _Descending(1.0 if value else 0.0) if descending else (1.0 if value else 0.0))
    number = coerce_number(value)
    if number is not None:
        return (0, 0, _Descending(number) if descending else number)
    if isinstance(value, (dict, list)):
        text = json.dumps(value, sort_keys=True, default=str)
    else:
        text = str(value)
        if case_insensitive:
            text = text.casefold()
    return (0, 1, _Descending(text) if descending else text)


def _parse_sort_keys(text: Any, default_order: str) -> list[tuple[str, bool]]:
    keys: list[tuple[str, bool]] = []
    for entry in _parse_list(text):
        parts = entry.split()
        if len(parts) == 1:
            keys.append((parts[0], default_order == "desc"))
        elif len(parts) == 2 and parts[1].lower() in ("asc", "desc"):
            keys.append((parts[0], parts[1].lower() == "desc"))
        else:
            raise ValueError(
                f"sort key {entry!r} must be a field, optionally followed by asc or desc"
            )
    if not keys:
        # Legacy behaviour: an empty key sorts by the whole row.
        keys.append(("", default_order == "desc"))
    return keys


def exec_sort_limit(context: NodeExecContext) -> dict[str, Any]:
    rows = rows_of(context.inputs.get("rows"), "transform.sort_limit")
    order = str(context.config.get("order") or "asc").strip().lower()
    if order not in ("asc", "desc"):
        raise ValueError(f"order must be 'asc' or 'desc', got {order!r}")
    keys = _parse_sort_keys(context.config.get("field"), order)
    case_insensitive = bool(context.config.get("caseInsensitive"))
    try:
        limit = int(context.config.get("limit", 0))
        offset = int(context.config.get("offset", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit and offset must be whole numbers") from exc
    if limit < 0:
        raise ValueError("limit cannot be negative")
    if offset < 0:
        raise ValueError("offset cannot be negative")

    ordered = list(rows)
    # Stable passes, least significant key first: each key keeps its own
    # direction while nulls stay last in every pass.
    for path, descending in reversed(keys):
        ordered.sort(key=lambda row, p=path, d=descending: _sort_key(
            row if not p else resolve_path(row, p), d, case_insensitive
        ))

    end = offset + limit if limit else None
    ordered = ordered[offset:end]
    return {"rows": ordered, "_control": ["done"]}


def _aggregate_numbers(values: list[Any], field: str) -> list[float]:
    """Numeric values, coercing numeric strings and refusing the rest.

    A provider that sends ``"100.5"`` is still a number; a provider that sends
    ``"n/a"`` is a data-quality problem the node must report, not skip.
    """
    numbers: list[float] = []
    for value in values:
        if value is None:
            continue
        number = coerce_number(value)
        if number is None:
            raise ValueError(f"{field} is not numeric: {value!r}")
        numbers.append(number)
    return numbers


def _percentile(numbers: list[float], pct: float) -> float:
    """Linear-interpolation percentile (the numpy default), 0-100."""
    if not numbers:
        return 0.0
    ordered = sorted(numbers)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct / 100.0
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def _sample_stddev(numbers: list[float]) -> float:
    """Sample standard deviation (n-1). One point has no spread: 0.0."""
    if len(numbers) < 2:
        return 0.0
    mean = math.fsum(numbers) / len(numbers)
    variance = math.fsum((number - mean) ** 2 for number in numbers) / (len(numbers) - 1)
    return math.sqrt(variance)


AGGREGATE_OPS = ("sum", "avg", "min", "max", "count", "median", "stddev", "percentile")


def exec_aggregate(context: NodeExecContext) -> dict[str, Any]:
    rows = rows_of(context.inputs.get("items"), "logic.aggregate")
    field = str(context.config.get("field") or "").strip()
    op = str(context.config.get("op") or "sum").strip().lower()
    if op not in AGGREGATE_OPS:
        raise ValueError(f"unsupported aggregate op {op!r}")
    if op not in ("count",) and not field:
        raise ValueError("an aggregate other than count needs a field")
    percentile = 50.0
    if op == "percentile":
        try:
            percentile = float(context.config.get("percentile", 50))
        except (TypeError, ValueError) as exc:
            raise ValueError("percentile must be a number between 0 and 100") from exc
        if not 0 <= percentile <= 100:
            raise ValueError("percentile must be between 0 and 100")
    group_by = _parse_list(context.config.get("groupBy"))

    def reducer(values: list[Any]) -> Optional[float]:
        if op == "count":
            return float(len(values))
        numbers = _aggregate_numbers(values, field or "value")
        if not numbers:
            # No rows (or no numeric value for any row) is NOT zero. A fabricated
            # zero is indistinguishable from a real one; report "nothing to
            # aggregate" so a downstream node cannot treat it as data.
            return None
        if op == "sum":
            return float(math.fsum(numbers))
        if op == "avg":
            return float(math.fsum(numbers) / len(numbers))
        if op == "min":
            return float(min(numbers))
        if op == "max":
            return float(max(numbers))
        if op == "median":
            return _percentile(numbers, 50.0)
        if op == "stddev":
            return _sample_stddev(numbers)
        return _percentile(numbers, percentile)

    groups: dict[tuple[Any, ...], list[Any]] = {}
    for row in rows:
        key = tuple(field_of(row, path) for path in group_by) if group_by else ()
        groups.setdefault(key, []).append(field_of(row, field) if field else row)

    out: list[dict[str, Any]] = []
    for key, values in groups.items():
        item: dict[str, Any] = {}
        for index, name in enumerate(group_by):
            item[name] = key[index]
        item["value"] = reducer(values)
        item["count"] = len(values)
        out.append(item)

    # A real key, not str(tuple(...)): numeric groups must not sort as text
    # ("10" before "9"), and nulls belong last.
    out.sort(key=lambda item: tuple(_sort_key(item.get(name), False) for name in group_by))
    overall = reducer([field_of(row, field) if field else row for row in rows])
    context.emit(
        f"{len(rows)} row(s) → {len(out)} group(s); value "
        + ("none" if overall is None else f"{overall:g}")
    )
    return {"value": overall, "groups": out, "_control": ["done"]}


def exec_deduplicate(context: NodeExecContext) -> dict[str, Any]:
    rows = rows_of(context.inputs.get("items"), "logic.deduplicate")
    keys = _parse_list(context.config.get("keys"))
    keep = str(context.config.get("keep") or "first").strip().lower()
    if keep not in ("first", "last"):
        raise ValueError(f"unsupported deduplicate keep policy {keep!r}")
    case_insensitive = bool(context.config.get("caseInsensitive"))
    positions: dict[Any, int] = {}
    out: list[dict[str, Any]] = []
    for row in rows:
        if keys:
            # Same identity rule as transform.join: 1, 1.0 and "1" are one row,
            # so a provider that switches numeric types cannot defeat dedupe.
            identity: Any = tuple(
                key_part(resolve_path(row, key), case_insensitive=case_insensitive)
                for key in keys
            )
        else:
            identity = tuple(sorted(
                (name, key_part(value, case_insensitive=case_insensitive))
                for name, value in row.items()
            ))
        existing = positions.get(identity)
        if existing is None:
            positions[identity] = len(out)
            out.append(row)
        elif keep == "last":
            out[existing] = row
    context.emit(f"kept {len(out)} of {len(rows)} row(s) ({len(rows) - len(out)} duplicate(s))")
    return {"items": out, "dropped": len(rows) - len(out), "_control": ["done"]}


def _row_key(row: dict[str, Any], fields: list[str], case_insensitive: bool) -> tuple[Any, ...]:
    return tuple(key_part(resolve_path(row, field), case_insensitive=case_insensitive) for field in fields)


def _merge_rows(left: dict[str, Any], right: dict[str, Any], suffix: str) -> dict[str, Any]:
    merged = dict(left)
    for name, value in right.items():
        if name not in merged:
            merged[name] = value
        elif merged[name] is None and value is not None:
            merged[name] = value
        elif merged[name] == value:
            continue  # same column, same value: nothing to disambiguate
        elif suffix:
            target = f"{name}{suffix}"
            if target in merged and merged[target] != value:
                raise ValueError(
                    f"join suffix {suffix!r} produces a duplicate column {target!r}; "
                    "pick a more specific suffix"
                )
            merged[target] = value
    return merged


def _with_nulls(row: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    filled = dict(row)
    for name in columns:
        filled.setdefault(name, None)
    return filled


def exec_join(context: NodeExecContext) -> dict[str, Any]:
    left = rows_of(context.inputs.get("left"), "transform.join left")
    right = rows_of(context.inputs.get("right"), "transform.join right")
    left_keys = _parse_list(context.config.get("leftKey"))
    right_keys = _parse_list(context.config.get("rightKey")) or list(left_keys)
    how = str(context.config.get("how") or "inner").strip().lower()
    on_duplicate = str(context.config.get("onDuplicate") or "first").strip().lower()
    case_insensitive = bool(context.config.get("caseInsensitive"))
    suffix = str(context.config.get("suffix") or "").strip()

    if how not in ("inner", "left", "right", "full", "anti"):
        raise ValueError(f"unsupported join type {how!r}")
    if on_duplicate not in ("first", "last", "all"):
        raise ValueError(f"unsupported onDuplicate policy {on_duplicate!r}")
    if not left_keys or not right_keys:
        raise ValueError("join needs leftKey and rightKey")
    if len(left_keys) != len(right_keys):
        raise ValueError(
            "composite join keys must match on both sides "
            f"(left has {len(left_keys)}, right has {len(right_keys)})"
        )

    right_columns = sorted({name for row in right for name in row})
    left_columns = sorted({name for row in left for name in row})

    index: dict[tuple[Any, ...], list[int]] = {}
    for position, row in enumerate(right):
        index.setdefault(_row_key(row, right_keys, case_insensitive), []).append(position)

    out: list[dict[str, Any]] = []
    matched = 0
    used_right: set[int] = set()

    for row in left:
        positions = index.get(_row_key(row, left_keys, case_insensitive)) or []
        if positions:
            matched += 1
            used_right.update(positions)
            if how == "anti":
                continue
            if on_duplicate == "first":
                candidates = positions[:1]
            elif on_duplicate == "last":
                candidates = positions[-1:]
            else:
                candidates = positions
            for position in candidates:
                out.append(_merge_rows(row, right[position], suffix))
        elif how == "anti":
            out.append(dict(row))
        elif how in ("left", "full"):
            out.append(_with_nulls(row, right_columns))

    if how in ("right", "full"):
        for position, row in enumerate(right):
            if position not in used_right:
                out.append(_with_nulls(row, left_columns))

    if len(out) > MAX_ROWS:
        raise ValueError(
            f"transform.join produced more than {MAX_ROWS} rows; "
            "narrow the join or set onDuplicate to first/last"
        )
    return {"rows": out, "matched": matched, "_control": ["done"]}


def build_table_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="transform.select", version="1.0.0", label="Select fields",
            category="transform",
            inputs=(
                PortDef(id="in", name="Run", type=PortType.ANY, kind=PortKind.CONTROL, optional=True),
                PortDef(id="rows", name="Rows", type=PortType.ARRAY),
            ),
            outputs=(
                PortDef(id="rows", name="Rows", type=PortType.ARRAY),
                PortDef(id="dropped", name="Dropped", type=PortType.NUMBER),
                PortDef(id="done", name="Done", type=PortType.ANY, kind=PortKind.CONTROL),
            ),
            config_fields=(
                ConfigField("fields", "string", "", max_length=4_000),
                ConfigField("rename", "string", "", max_length=4_000),
                ConfigField("onMissing", "enum", "null", enum=("null", "drop", "error")),
            ),
            allowed_modes=_ALL, executor=exec_select,
            metadata={
                "docs": (
                    "Select/rename columns. Dotted paths are resolved; "
                    "`pe=fundamentals.pe` aliases a column."
                ),
            },
        ),
        NodeDef(
            type="transform.sort_limit", version="1.0.0", label="Sort / limit",
            category="transform",
            inputs=(
                PortDef(id="in", name="Run", type=PortType.ANY, kind=PortKind.CONTROL, optional=True),
                PortDef(id="rows", name="Rows", type=PortType.ARRAY),
            ),
            outputs=(
                PortDef(id="rows", name="Rows", type=PortType.ARRAY),
                PortDef(id="done", name="Done", type=PortType.ANY, kind=PortKind.CONTROL),
            ),
            config_fields=(
                ConfigField("field", "string", "", max_length=1_000),
                ConfigField("order", "enum", "asc", enum=("asc", "desc")),
                ConfigField("limit", "integer", 0, minimum=0, maximum=MAX_ROWS),
                ConfigField("offset", "integer", 0, minimum=0, maximum=MAX_ROWS),
                ConfigField("caseInsensitive", "boolean", False),
            ),
            allowed_modes=_ALL, executor=exec_sort_limit,
            metadata={
                "docs": (
                    "Sort by one or more dotted keys (`date desc, symbol`), "
                    "coercing numeric strings; nulls always last."
                ),
            },
        ),
        NodeDef(
            type="logic.aggregate", version="1.0.0", label="Aggregate / group",
            category="logic",
            inputs=(
                PortDef(id="in", name="Run", type=PortType.ANY, kind=PortKind.CONTROL, optional=True),
                PortDef(id="items", name="Items", type=PortType.ARRAY),
            ),
            outputs=(
                PortDef(id="value", name="Value", type=PortType.NUMBER, nullable=True),
                PortDef(id="groups", name="Groups", type=PortType.ARRAY),
                PortDef(id="done", name="Done", type=PortType.ANY, kind=PortKind.CONTROL),
            ),
            config_fields=(
                ConfigField("field", "string", "", max_length=200),
                ConfigField(
                    "op", "enum", "sum",
                    enum=("sum", "avg", "min", "max", "count", "median", "stddev", "percentile"),
                ),
                ConfigField("groupBy", "string", "", max_length=1_000),
                ConfigField("percentile", "number", 50.0, minimum=0, maximum=100),
            ),
            allowed_modes=_ALL, executor=exec_aggregate,
            metadata={
                "docs": (
                    "Bounded numeric aggregate (sum/avg/min/max/count/median/stddev/"
                    "percentile), optionally grouped; stddev is the sample form."
                ),
            },
        ),
        NodeDef(
            type="logic.deduplicate", version="1.0.0", label="Deduplicate",
            category="logic",
            inputs=(
                PortDef(id="in", name="Run", type=PortType.ANY, kind=PortKind.CONTROL, optional=True),
                PortDef(id="items", name="Items", type=PortType.ARRAY),
            ),
            outputs=(
                PortDef(id="items", name="Items", type=PortType.ARRAY),
                PortDef(id="dropped", name="Dropped", type=PortType.NUMBER),
                PortDef(id="done", name="Done", type=PortType.ANY, kind=PortKind.CONTROL),
            ),
            config_fields=(
                ConfigField("keys", "string", "", max_length=1_000),
                ConfigField("keep", "enum", "first", enum=("first", "last")),
                ConfigField("caseInsensitive", "boolean", False),
            ),
            allowed_modes=_ALL, executor=exec_deduplicate,
            metadata={
                "docs": (
                    "Keep the first (or last) row per key; keys compare with the join "
                    "identity rule (1 == 1.0 == \"1\"). Empty keys compares whole rows."
                ),
            },
        ),
        NodeDef(
            type="transform.join", version="1.0.0", label="Join rows",
            category="transform",
            inputs=(
                PortDef(id="in", name="Run", type=PortType.ANY, kind=PortKind.CONTROL, optional=True),
                PortDef(id="left", name="Left", type=PortType.ARRAY),
                PortDef(id="right", name="Right", type=PortType.ARRAY),
            ),
            outputs=(
                PortDef(id="rows", name="Rows", type=PortType.ARRAY),
                PortDef(id="matched", name="Matched", type=PortType.NUMBER),
                PortDef(id="done", name="Done", type=PortType.ANY, kind=PortKind.CONTROL),
            ),
            config_fields=(
                ConfigField("leftKey", "string", "", max_length=1_000),
                ConfigField("rightKey", "string", "", max_length=1_000),
                ConfigField("how", "enum", "inner", enum=("inner", "left", "right", "full", "anti")),
                ConfigField("caseInsensitive", "boolean", False),
                ConfigField("suffix", "string", "", max_length=100),
                ConfigField("onDuplicate", "enum", "first", enum=("first", "last", "all")),
            ),
            allowed_modes=_ALL, executor=exec_join,
            metadata={
                "docs": (
                    "Inner/left/right/full/anti join on one or more dotted keys. "
                    "Duplicate right keys are explicit via onDuplicate, never dropped."
                ),
            },
        ),
    ]


__all__ = [
    "build_table_nodes",
    "rows_of",
    "field_of",
    "exec_select",
    "exec_sort_limit",
    "exec_aggregate",
    "exec_deduplicate",
    "exec_join",
]
