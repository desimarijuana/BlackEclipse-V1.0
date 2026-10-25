"""Tabular transform nodes.

Financial data arrives as arrays of JSON objects (bars, fundamentals, filings,
screener rows). These nodes cover the common deterministic operations without a
second dataframe engine: select/rename, sort/limit, aggregate/group, dedupe and
join. Every node is bounded and fails honestly on a shape it cannot handle.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_ROWS = 100_000


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
    if not path:
        return row
    current: Any = row
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


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


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} is not numeric: {value!r}")
    return float(value)


def exec_select(context: NodeExecContext) -> dict[str, Any]:
    rows = rows_of(context.inputs.get("rows"), "transform.select")
    fields = _parse_list(context.config.get("fields"))
    rename = _parse_json_object(context.config.get("rename"), "rename")
    out: list[dict[str, Any]] = []
    for row in rows:
        source = row if not fields else {key: row.get(key) for key in fields}
        if rename:
            source = {rename.get(key, key): value for key, value in source.items()}
        out.append(source)
    return {"rows": out}


def exec_sort_limit(context: NodeExecContext) -> dict[str, Any]:
    rows = rows_of(context.inputs.get("rows"), "transform.sort_limit")
    field = str(context.config.get("field") or "").strip()
    order = str(context.config.get("order") or "asc")
    try:
        limit = int(context.config.get("limit", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be a whole number") from exc
    if limit < 0:
        raise ValueError("limit cannot be negative")

    def key(row: dict[str, Any]):
        value = field_of(row, field) if field else row
        if isinstance(value, bool):
            return (1, str(value))
        if isinstance(value, (int, float)):
            return (0, float(value))
        if value is None:
            return (2, 0.0)
        return (1, str(value))

    ordered = sorted(rows, key=key, reverse=(order == "desc"))
    if limit:
        ordered = ordered[:limit]
    return {"rows": ordered}


def exec_aggregate(context: NodeExecContext) -> dict[str, Any]:
    rows = rows_of(context.inputs.get("items"), "logic.aggregate")
    field = str(context.config.get("field") or "").strip()
    op = str(context.config.get("op") or "sum")
    if op not in ("sum", "avg", "min", "max", "count"):
        raise ValueError(f"unsupported aggregate op {op!r}")
    if op != "count" and not field:
        raise ValueError("an aggregate other than count needs a field")
    group_by = _parse_list(context.config.get("groupBy"))

    def reducer(values: list[Any]) -> float:
        if op == "count":
            return float(len(values))
        nums = [_number(value, f"{field}") for value in values if value is not None]
        if not nums:
            return 0.0
        if op == "sum":
            return float(sum(nums))
        if op == "avg":
            return float(sum(nums) / len(nums))
        if op == "min":
            return float(min(nums))
        return float(max(nums))

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

    out.sort(key=lambda item: str(tuple(item.get(name) for name in group_by)))
    overall = reducer([field_of(row, field) if field else row for row in rows])
    return {"value": overall, "groups": out}


def exec_deduplicate(context: NodeExecContext) -> dict[str, Any]:
    rows = rows_of(context.inputs.get("items"), "logic.deduplicate")
    keys = _parse_list(context.config.get("keys"))
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        identity = (
            tuple(field_of(row, key) for key in keys)
            if keys else tuple(sorted(row.items(), key=lambda pair: pair[0]))
        )
        marker = json.dumps(identity, sort_keys=True, default=str)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(row)
    return {"items": out, "dropped": len(rows) - len(out)}


def exec_join(context: NodeExecContext) -> dict[str, Any]:
    left = rows_of(context.inputs.get("left"), "transform.join left")
    right = rows_of(context.inputs.get("right"), "transform.join right")
    left_key = str(context.config.get("leftKey") or "").strip()
    right_key = str(context.config.get("rightKey") or left_key).strip()
    how = str(context.config.get("how") or "inner")
    if how not in ("inner", "left"):
        raise ValueError(f"unsupported join type {how!r}")
    if not left_key or not right_key:
        raise ValueError("join needs leftKey and rightKey")
    index: dict[str, dict[str, Any]] = {}
    for row in right:
        key = json.dumps(field_of(row, right_key), sort_keys=True, default=str)
        index.setdefault(key, row)
    out: list[dict[str, Any]] = []
    matched = 0
    for row in left:
        key = json.dumps(field_of(row, left_key), sort_keys=True, default=str)
        other = index.get(key)
        if other is None:
            if how == "left":
                out.append(dict(row))
            continue
        matched += 1
        merged = dict(row)
        for name, value in other.items():
            if name not in merged or merged[name] is None:
                merged[name] = value
        out.append(merged)
    return {"rows": out, "matched": matched}


def build_table_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="transform.select", version="1.0.0", label="Select fields",
            category="transform",
            inputs=(PortDef(id="rows", name="Rows", type=PortType.ARRAY),),
            outputs=(PortDef(id="rows", name="Rows", type=PortType.ARRAY),),
            config_fields=(
                ConfigField("fields", "string", "", max_length=4_000),
                ConfigField("rename", "string", "", max_length=4_000),
            ),
            allowed_modes=_ALL, executor=exec_select,
            metadata={"docs": "Select/rename columns in an array of objects."},
        ),
        NodeDef(
            type="transform.sort_limit", version="1.0.0", label="Sort / limit",
            category="transform",
            inputs=(PortDef(id="rows", name="Rows", type=PortType.ARRAY),),
            outputs=(PortDef(id="rows", name="Rows", type=PortType.ARRAY),),
            config_fields=(
                ConfigField("field", "string", "", max_length=200),
                ConfigField("order", "enum", "asc", enum=("asc", "desc")),
                ConfigField("limit", "integer", 0, minimum=0, maximum=MAX_ROWS),
            ),
            allowed_modes=_ALL, executor=exec_sort_limit,
            metadata={"docs": "Sort by a dotted field (or the whole row) and optionally limit."},
        ),
        NodeDef(
            type="logic.aggregate", version="1.0.0", label="Aggregate / group",
            category="logic",
            inputs=(PortDef(id="items", name="Items", type=PortType.ARRAY),),
            outputs=(
                PortDef(id="value", name="Value", type=PortType.NUMBER),
                PortDef(id="groups", name="Groups", type=PortType.ARRAY),
            ),
            config_fields=(
                ConfigField("field", "string", "", max_length=200),
                ConfigField("op", "enum", "sum", enum=("sum", "avg", "min", "max", "count")),
                ConfigField("groupBy", "string", "", max_length=1_000),
            ),
            allowed_modes=_ALL, executor=exec_aggregate,
            metadata={"docs": "Bounded numeric aggregate, optionally grouped by dotted fields."},
        ),
        NodeDef(
            type="logic.deduplicate", version="1.0.0", label="Deduplicate",
            category="logic",
            inputs=(PortDef(id="items", name="Items", type=PortType.ARRAY),),
            outputs=(
                PortDef(id="items", name="Items", type=PortType.ARRAY),
                PortDef(id="dropped", name="Dropped", type=PortType.NUMBER),
            ),
            config_fields=(ConfigField("keys", "string", "", max_length=1_000),),
            allowed_modes=_ALL, executor=exec_deduplicate,
            metadata={"docs": "Keep the first row per key (or per whole row when keys is empty)."},
        ),
        NodeDef(
            type="transform.join", version="1.0.0", label="Join rows",
            category="transform",
            inputs=(
                PortDef(id="left", name="Left", type=PortType.ARRAY),
                PortDef(id="right", name="Right", type=PortType.ARRAY),
            ),
            outputs=(
                PortDef(id="rows", name="Rows", type=PortType.ARRAY),
                PortDef(id="matched", name="Matched", type=PortType.NUMBER),
            ),
            config_fields=(
                ConfigField("leftKey", "string", "", max_length=200),
                ConfigField("rightKey", "string", "", max_length=200),
                ConfigField("how", "enum", "inner", enum=("inner", "left")),
            ),
            allowed_modes=_ALL, executor=exec_join,
            metadata={"docs": "Inner/left join of two arrays of objects on a dotted key."},
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
