"""Read-only `eclipse_tools` bindings for the analysis sandbox.

The sandbox stays network-free and write-free. A program that needs market data
asks the HOST for one named read; the host validates the request against this
allowlist, resolves it through the existing read-only ``DataBridge``, memoizes
the answer, and replays the same program from the start. The runner stops at the
first uncached call with ``TOOL_SENTINEL``.

No fetched payload crosses into the model context: only the final program
outputs cross. Call metadata (name, argument/result digests, status) is recorded
on ``AnalysisResult`` for audit.

This module deliberately has no import on the execution module (execution
imports it), so the wire helpers can be unit-tested on their own.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_CAMEL = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

# The runner exits with this code when it has written a pending request. The
# parent only treats it as a request when a valid `pending.json` is present, so a
# program that raises `SystemExit(75)` on its own is still a failure.
TOOL_SENTINEL = 75

# Bounds: a program may make at most this many DISTINCT host calls. Replaying is
# cheap; a call that is already memoized costs nothing.
MAX_TOOL_CALLS = 8
# The ceiling a caller MAY raise the call budget to. A scraper legitimately needs
# more than one page (pagination, several sources); the bound is still finite and
# is set by the HOST, never by the program.
MAX_TOOL_CALLS_CEILING = 64
MAX_TOOL_ARGS_BYTES = 4_096
# The whole pending request on disk, including the tool name and JSON envelope.
# Checked BEFORE reading so a hostile argument value cannot balloon host memory.
MAX_TOOL_REQUEST_BYTES = 16_384
MAX_TOOL_RESULT_BYTES = 1_000_000
MAX_TOOL_MEMO_BYTES = 4_000_000

# Stable refusal/failure codes (the analysis result carries one of these).
TOOL_NOT_ALLOWED = "TOOL_NOT_ALLOWED"
TOOL_ARGS_INVALID = "TOOL_ARGS_INVALID"
TOOL_LIMIT = "TOOL_LIMIT"
TOOL_PROTOCOL_INVALID = "TOOL_PROTOCOL_INVALID"
TOOL_RESOLVE_FAILED = "TOOL_RESOLVE_FAILED"
TOOL_RESULT_TOO_LARGE = "TOOL_RESULT_TOO_LARGE"

ToolResolver = Callable[[str, dict[str, Any]], dict[str, Any]]

_SYMBOL_RE = re.compile(r"^[A-Z0-9.^=\-]{1,32}$")
_MARKET_RE = re.compile(r"^[A-Z0-9 /&+_.\-]{1,24}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_URL_CHARS = 2_000
_MAX_SELECTOR_CHARS = 500
_MAX_FIELD_NAME_CHARS = 64
_MAX_FIELDS = 40

_INTERVALS = (
    "1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo",
)
_RANGES = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max")


@dataclass(frozen=True)
class ParamSpec:
    """One accepted argument. Unknown arguments are refused, never forwarded."""

    kind: str  # symbol | market | choice | date | url | selector | fields | bool | int
    required: bool = False
    choices: tuple[str, ...] = ()
    minimum: int = 0
    maximum: int = 0


@dataclass(frozen=True)
class ToolBinding:
    name: str
    capability: str
    description: str
    params: Mapping[str, ParamSpec]


# The ONE binding set. Every entry is a read: no writes, no web, no MCP, no
# arbitrary registry tool. The bridge's own capability allowlist is the second
# gate; this table is the sandbox-facing first gate.
TOOL_BINDINGS: dict[str, ToolBinding] = {
    "market_snapshot": ToolBinding(
        name="market_snapshot",
        capability="market_snapshot",
        description="A stored market snapshot for one instrument (price and reference data).",
        params={
            "symbol": ParamSpec("symbol", required=True),
            "market": ParamSpec("market"),
        },
    ),
    "live_quote": ToolBinding(
        name="live_quote",
        capability="live_quote",
        description="A live quote for one instrument.",
        params={
            "symbol": ParamSpec("symbol", required=True),
            "market": ParamSpec("market"),
        },
    ),
    "price_history": ToolBinding(
        name="price_history",
        capability="price_history",
        description="An OHLCV series for one instrument over a bounded window.",
        params={
            "symbol": ParamSpec("symbol", required=True),
            "market": ParamSpec("market"),
            "interval": ParamSpec("choice", choices=_INTERVALS),
            "range": ParamSpec("choice", choices=_RANGES),
            "start": ParamSpec("date"),
            "end": ParamSpec("date"),
        },
    ),
    # The WEB binding. It is deliberately NOT part of `DATA_TOOL_NAMES`: the
    # analysis sandbox stays network-free, and only the scraper lane (which
    # fetches pages through the same hardened host transport) may use it.
    "web_page": ToolBinding(
        name="web_page",
        capability="web_collect",
        description=(
            "Fetch ONE page and read it: repeated records by CSS selector, the "
            "page's tables, or its links. The host does the fetching (safe "
            "transport, size and time caps) and the extraction is deterministic."
        ),
        params={
            "url": ParamSpec("url", required=True),
            "selector": ParamSpec("selector"),
            "fields": ParamSpec("fields"),
            "attribute": ParamSpec("attribute"),
            "tables": ParamSpec("bool"),
            "links": ParamSpec("bool"),
            "max_rows": ParamSpec("int", minimum=1, maximum=500),
        },
    ),
}

#: The data bindings the analysis sandbox may use (no network).
DATA_TOOL_NAMES: tuple[str, ...] = (
    "market_snapshot", "live_quote", "price_history",
)
#: The web binding — the scraper lane's only way out of the sandbox.
WEB_TOOL_NAMES: tuple[str, ...] = ("web_page",)


class ToolRequestError(ValueError):
    """A refused sandbox tool request. ``code`` is stable and testable."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class ToolResultError(ValueError):
    """A host tool result that cannot safely be memoized."""


class ToolCallRef(BaseModel):
    """Audit metadata for one host call. It carries NO fetched payload."""

    model_config = _CAMEL

    name: str
    args_digest: str
    result_digest: str
    status: str = "OK"
    round: int = Field(0, ge=0, le=MAX_TOOL_CALLS_CEILING)


def tool_names() -> tuple[str, ...]:
    """The bindings the ANALYSIS sandbox may use: the data reads, no network."""
    return DATA_TOOL_NAMES


def select_tool_names(names: tuple[str, ...]) -> tuple[str, ...]:
    """The named bindings, validated against the table.

    The HOST picks the set (the analysis lane gets the data reads; the scraper
    lane gets the web binding), so a program can never widen its own reach.
    """
    out: list[str] = []
    for name in names:
        if name not in TOOL_BINDINGS:
            raise ValueError(f"no such data tool: {name!r}")
        if name not in out:
            out.append(name)
    return tuple(out)


def canonical_args(args: Mapping[str, Any]) -> str:
    """The exact canonical form the runner uses for its memo key."""
    return json.dumps(
        dict(args), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def cache_key(name: str, args: Mapping[str, Any]) -> str:
    """The runner and the host must compute the same key from the RAW arguments."""
    return f"{name}:{canonical_args(args)}"


def digest_args(args: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_args(args).encode("utf-8")).hexdigest()


def digest_result(value: Any) -> str:
    text = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_param(name: str, spec: ParamSpec, value: Any) -> Any:
    if spec.kind == "symbol":
        if not isinstance(value, str):
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} must be text")
        text = value.strip().upper()
        if not _SYMBOL_RE.match(text):
            raise ToolRequestError(
                TOOL_ARGS_INVALID,
                f"{name} must look like a ticker (letters, digits, . ^ = -)",
            )
        return text
    if spec.kind == "market":
        if not isinstance(value, str):
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} must be text")
        text = value.strip().upper()
        if not text or not _MARKET_RE.match(text):
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} is not a valid market label")
        return text
    if spec.kind == "choice":
        if not isinstance(value, str):
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} must be text")
        text = value.strip().lower()
        if text not in spec.choices:
            raise ToolRequestError(
                TOOL_ARGS_INVALID, f"{name} must be one of: {', '.join(spec.choices)}",
            )
        return text
    if spec.kind == "date":
        if not isinstance(value, str) or not _DATE_RE.match(value.strip()):
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} must be a YYYY-MM-DD date")
        text = value.strip()
        try:
            _dt.date.fromisoformat(text)
        except ValueError as exc:
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} is not a real date") from exc
        return text
    if spec.kind == "url":
        if not isinstance(value, str):
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} must be text")
        text = value.strip()
        if len(text) > _MAX_URL_CHARS:
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} is too long")
        parsed = urlsplit(text)
        if parsed.scheme.lower() not in ("http", "https"):
            raise ToolRequestError(
                TOOL_ARGS_INVALID, f"{name} must be an http or https address",
            )
        if not parsed.hostname:
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} has no host")
        if parsed.username or parsed.password:
            raise ToolRequestError(
                TOOL_ARGS_INVALID, f"{name} must not carry credentials",
            )
        return text
    if spec.kind == "selector":
        if not isinstance(value, str):
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} must be text")
        text = value.strip()
        if not text or len(text) > _MAX_SELECTOR_CHARS:
            raise ToolRequestError(
                TOOL_ARGS_INVALID,
                f"{name} must be a CSS selector of 1..{_MAX_SELECTOR_CHARS} characters",
            )
        return text
    if spec.kind == "attribute":
        if not isinstance(value, str):
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} must be text")
        text = value.strip()
        if not text or len(text) > _MAX_SELECTOR_CHARS:
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} is not a usable attribute name")
        return text
    if spec.kind == "fields":
        if not isinstance(value, dict):
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} must be an object")
        if len(value) > _MAX_FIELDS:
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} has too many fields")
        out: dict[str, str] = {}
        for key, child in value.items():
            name_text = str(key).strip()
            child_text = str(child).strip()
            if not name_text or len(name_text) > _MAX_FIELD_NAME_CHARS:
                raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} has an unusable field name")
            if not child_text or len(child_text) > _MAX_SELECTOR_CHARS:
                raise ToolRequestError(
                    TOOL_ARGS_INVALID, f"{name}.{name_text} is not a usable selector",
                )
            out[name_text] = child_text
        return out
    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} must be true or false")
        return value
    if spec.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} must be a whole number")
        if spec.minimum and value < spec.minimum:
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} must be at least {spec.minimum}")
        if spec.maximum and value > spec.maximum:
            raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} must be at most {spec.maximum}")
        return value
    raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} has an unsupported kind")


def validate_tool_request(name: Any, args: Any) -> tuple[str, dict[str, Any]]:
    """Validate a pending request; return the normalized bridge parameters.

    The memo key is computed from the RAW arguments elsewhere, so normalization
    here never changes which cached value the runner finds on replay.
    """
    if not isinstance(name, str) or name not in TOOL_BINDINGS:
        raise ToolRequestError(TOOL_NOT_ALLOWED, f"no read-only data tool named {name!r}")
    if not isinstance(args, dict):
        raise ToolRequestError(TOOL_ARGS_INVALID, "tool arguments must be an object")

    binding = TOOL_BINDINGS[name]
    unknown = sorted(set(args) - set(binding.params))
    if unknown:
        raise ToolRequestError(
            TOOL_ARGS_INVALID, f"{name} does not accept: {', '.join(unknown)}",
        )

    try:
        raw_size = len(canonical_args(args).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ToolRequestError(TOOL_ARGS_INVALID, "tool arguments must be JSON values") from exc
    if raw_size > MAX_TOOL_ARGS_BYTES:
        raise ToolRequestError(TOOL_ARGS_INVALID, "tool arguments are too large")

    params: dict[str, Any] = {}
    for key, spec in binding.params.items():
        value = args.get(key)
        if value is None:
            if spec.required:
                raise ToolRequestError(TOOL_ARGS_INVALID, f"{name} needs {key}")
            continue
        params[key] = _validate_param(key, spec, value)

    start, end = params.get("start"), params.get("end")
    if start and end and start > end:
        raise ToolRequestError(TOOL_ARGS_INVALID, "start must not be after end")
    return binding.capability, params


def bound_tool_result(value: Any) -> dict[str, Any]:
    """Return a plain-JSON, size-bounded copy of a bridge result.

    A non-object, non-JSON or oversized result fails honestly instead of being
    silently stringified: the sandbox would otherwise compute on a fake shape.
    """
    if not isinstance(value, dict):
        raise ToolResultError("a data tool must return an object")
    try:
        text = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ToolResultError("a data tool returned a value that is not JSON") from exc
    if len(text.encode("utf-8")) > MAX_TOOL_RESULT_BYTES:
        raise ToolResultError("the data tool result is too large to memoize")
    return json.loads(text)


def memo_size(memo: Mapping[str, Any]) -> int:
    try:
        return len(json.dumps(memo, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        return MAX_TOOL_MEMO_BYTES + 1


__all__ = [
    "DATA_TOOL_NAMES",
    "MAX_TOOL_ARGS_BYTES",
    "MAX_TOOL_CALLS",
    "MAX_TOOL_CALLS_CEILING",
    "MAX_TOOL_MEMO_BYTES",
    "MAX_TOOL_REQUEST_BYTES",
    "MAX_TOOL_RESULT_BYTES",
    "TOOL_ARGS_INVALID",
    "TOOL_BINDINGS",
    "TOOL_LIMIT",
    "TOOL_NOT_ALLOWED",
    "TOOL_PROTOCOL_INVALID",
    "TOOL_RESOLVE_FAILED",
    "TOOL_RESULT_TOO_LARGE",
    "TOOL_SENTINEL",
    "WEB_TOOL_NAMES",
    "ToolBinding",
    "ToolCallRef",
    "ToolRequestError",
    "ToolResolver",
    "ToolResultError",
    "bound_tool_result",
    "cache_key",
    "digest_args",
    "digest_result",
    "memo_size",
    "select_tool_names",
    "tool_names",
    "validate_tool_request",
]
