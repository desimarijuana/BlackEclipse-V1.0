"""The bounded template renderer used by `transform.template`.

Placeholders, dotted paths, format specs, `{{?}}` for legitimately-null values and
nested `{{#each}}` row blocks â€” all bounded (rows, depth, output size) and rendered
by spending a shared budget as it appends, so a pathological template fails fast
instead of allocating gigabytes. Re-exported by ``nodes.py``.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

from .values import MISSING, coerce_number, resolve_path

_TAG_RE = re.compile(
    r"\{\{\s*(?:"
    r"(?P<open>#each\s+[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_0-9]+)*)"
    r"|(?P<close>/each)"
    r"|(?P<name>[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_0-9]+)*|this)\s*"
    r"(?P<optional>\?)?\s*(?::(?P<spec>[^{}]+?))?"
    r")\s*\}\}"
)
MAX_TEMPLATE_OUTPUT = 50_000
MAX_TEMPLATE_ROWS = 10_000
MAX_TEMPLATE_DEPTH = 5
_ESCAPE_SENTINEL = "\ue000"
_NO_ITEM = object()


def _format_template_date(value: Any, pattern: str, name: str) -> str:
    moment: Any = value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        moment = datetime.fromtimestamp(float(value), tz=timezone.utc)
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"template value {name!r} is not an ISO date: {value!r}"
            ) from exc
    if not isinstance(moment, (datetime, date)):
        raise ValueError(f"template value {name!r} is not a date: {type(value).__name__}")
    try:
        return moment.strftime(pattern)
    except ValueError as exc:
        raise ValueError(f"template date format {pattern!r} is not valid: {exc}") from exc


def _format_template_value(value: Any, spec: str, name: str) -> str:
    if not spec:
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
    spec = spec.strip()
    if spec == "json":
        return json.dumps(value, sort_keys=True)
    if spec == "date" or spec.startswith("date:"):
        return _format_template_date(value, spec.partition(":")[2] or "%Y-%m-%d", name)
    numeric = coerce_number(value)
    if numeric is None:
        raise ValueError(
            f"template format {spec!r} in {{{{{name}:{spec}}}}} needs a number, "
            f"got {type(value).__name__}"
        )
    try:
        return format(numeric, spec)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"template format {spec!r} is not valid for a number: {exc}") from exc


def _template_tokens(template: str) -> list[tuple[Any, ...]]:
    tokens: list[tuple[Any, ...]] = []
    position = 0
    for match in _TAG_RE.finditer(template):
        if match.start() > position:
            tokens.append(("text", template[position:match.start()]))
        if match.group("open"):
            tokens.append(("open", match.group("open")[len("#each"):].strip()))
        elif match.group("close"):
            tokens.append(("close",))
        else:
            tokens.append((
                "var",
                match.group("name"),
                bool(match.group("optional")),
                (match.group("spec") or "").strip(),
            ))
        position = match.end()
    if position < len(template):
        tokens.append(("text", template[position:]))
    return tokens


def _template_lookup(name: str, item: Any, index: Optional[int], values: dict[str, Any]) -> Any:
    """Resolve a name against the current row first, then the root inputs."""
    root, _, rest = name.partition(".")
    base: Any
    if item is not _NO_ITEM and isinstance(item, dict) and root in item:
        base = item[root]
    elif root in values:
        base = values[root]
    elif name == "this":
        return item
    elif name == "index":
        return index
    else:
        return MISSING
    return resolve_path(base, rest) if rest else base


def _render_var(
    token: tuple[Any, ...],
    item: Any,
    index: Optional[int],
    values: dict[str, Any],
) -> str:
    name, optional, spec = token[1], token[2], token[3]
    root = name.split(".")[0]
    has_root = root in values or (isinstance(item, dict) and root in item)
    if not has_root and name not in ("this", "index"):
        raise ValueError(
            f"template references unknown input {name!r}"
            f" (available: {', '.join(sorted(values))})"
        )
    value = _template_lookup(name, item, index, values)
    if value is _NO_ITEM:
        raise ValueError("{{this}} is only available inside a {{#each}} block")
    if value is MISSING or value is None:
        if optional:
            return ""
        raise ValueError(
            f"template input {name!r} has no value; "
            f"write {{{{{name}?}}}} to render it blank, or wire the input"
        )
    return _format_template_value(value, spec, name)


def _block_items(path: str, item: Any, index: Optional[int], values: dict[str, Any]) -> list[Any]:
    value = _template_lookup(path, item, index, values)
    if value is MISSING or value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(
            f"{{{{#each {path}}}}} needs an array, got {type(value).__name__}"
        )
    if len(value) > MAX_TEMPLATE_ROWS:
        raise ValueError(f"{{{{#each {path}}}}} is bounded to {MAX_TEMPLATE_ROWS} rows")
    return value


def _block_close(tokens: list[tuple[Any, ...]], start: int) -> int:
    depth = 0
    position = start
    while position < len(tokens):
        kind = tokens[position][0]
        if kind == "open":
            depth += 1
        elif kind == "close":
            if depth == 0:
                return position
            depth -= 1
        position += 1
    return -1


def _render_tokens(
    tokens: list[tuple[Any, ...]],
    values: dict[str, Any],
    item: Any = _NO_ITEM,
    index: Optional[int] = None,
    depth: int = 0,
    budget: Optional[list[int]] = None,
) -> str:
    out: list[str] = []
    spent = budget if budget is not None else [0]

    def push(rendered: str) -> None:
        # Bound DURING rendering, not after it. Nested blocks multiply rows
        # (10k × 10k), so checking only the final string would let a small
        # template allocate gigabytes before failing.
        spent[0] += len(rendered)
        if spent[0] > MAX_TEMPLATE_OUTPUT:
            raise ValueError(f"rendered template exceeds {MAX_TEMPLATE_OUTPUT} characters")
        out.append(rendered)

    position = 0
    while position < len(tokens):
        token = tokens[position]
        if token[0] == "text":
            push(token[1])
            position += 1
        elif token[0] == "var":
            push(_render_var(token, item, index, values))
            position += 1
        elif token[0] == "close":
            raise ValueError("template has a {{/each}} without a matching {{#each}}")
        else:
            if depth >= MAX_TEMPLATE_DEPTH:
                raise ValueError(f"template blocks nest deeper than {MAX_TEMPLATE_DEPTH}")
            close = _block_close(tokens, position + 1)
            if close < 0:
                raise ValueError(
                    f"{{{{#each {token[1]}}}}} is not closed with {{{{/each}}}}"
                )
            body = tokens[position + 1:close]
            for row_index, row in enumerate(_block_items(token[1], item, index, values)):
                push(_render_tokens(body, values, row, row_index, depth + 1, spent))
            position = close + 1
    return "".join(out)


def render_template(template: str, values: dict[str, Any]) -> str:
    """Render placeholders and one-or-more-level `{{#each path}}` blocks.

    Grammar: ``{{path}}``, ``{{path?}}`` (blank when null/absent),
    ``{{path:spec}}`` where spec is ``json``, ``date``/``date:<strftime>`` or a
    Python number format spec, ``{{#each path}}…{{/each}}`` (the row is the
    lookup scope; ``{{this}}``/``{{index}}`` are available), and ``\\{{`` for a
    literal ``{{``. Unknown names and null required values are an error, never a
    silent blank.
    """
    if not isinstance(template, str):
        raise ValueError("template must be text")
    escaped = template.replace(r"\{{", _ESCAPE_SENTINEL)
    rendered = _render_tokens(_template_tokens(escaped), values)
    rendered = rendered.replace(_ESCAPE_SENTINEL, "{{")
    if len(rendered) > MAX_TEMPLATE_OUTPUT:
        raise ValueError(f"rendered template exceeds {MAX_TEMPLATE_OUTPUT} characters")
    return rendered


__all__ = ["render_template", "MAX_TEMPLATE_OUTPUT", "MAX_TEMPLATE_ROWS", "MAX_TEMPLATE_DEPTH"]
