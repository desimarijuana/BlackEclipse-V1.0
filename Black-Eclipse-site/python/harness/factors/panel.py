"""Panel (cross-sectional) factor evaluation — universe-wide rank and scale.

The per-series evaluator in `stats.formula` cannot express a formula whose
`rank`/`scale` are taken ACROSS the universe on each date. Many published alphas
(most of Alpha101) are exactly that, and approximating them with a time-series
rank produces a different signal whose IC looks real. This module is the missing
axis: a T x N panel evaluator with cross-sectional `rank`/`scale` and
column-wise rolling operators.

Rules, stated so a caller can trust the numbers:

  * **No lookahead.** Rolling operators read only `[t-w+1 … t]`; cross-sectional
    operators read only row `t`. A test mutates future rows and asserts the past
    is unchanged.
  * **Explicit support.** Only the functions in `PANEL_FUNCTIONS` are evaluated.
    Anything else raises `PanelError("UNSUPPORTED_FUNCTION")` rather than
    silently applying a per-series implementation to a 2-D array.
  * **No silent filling.** A window containing a non-finite value yields NaN at
    that column/date, exactly like `stats.formula`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

import numpy as np

from ..stats import formula


class PanelError(ValueError):
    """A panel evaluation problem with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Panel:
    """A T x N field set: rows are dates, columns are symbols."""

    symbols: tuple[str, ...]
    timestamps: tuple[str, ...]
    fields: Mapping[str, np.ndarray]

    def __post_init__(self) -> None:
        rows = len(self.timestamps)
        for name, values in self.fields.items():
            array = np.asarray(values, dtype=float)
            if array.shape != (rows, len(self.symbols)):
                raise PanelError(
                    "BAD_SHAPE",
                    f"field {name!r} has shape {array.shape}, expected "
                    f"({rows}, {len(self.symbols)})",
                )


def build_panel(
    rows_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    fields: Iterable[str],
    *,
    timestamp_key: str = "timestamp",
) -> Panel:
    """Align per-symbol row lists into one panel on their COMMON timestamps.

    Symbols with no shared date are an error rather than an empty panel: an
    intersection of nothing would silently produce a factor over zero assets.
    """
    wanted = list(dict.fromkeys(str(f) for f in fields))
    symbols = tuple(sorted(rows_by_symbol))
    if not symbols:
        raise PanelError("EMPTY", "no symbols supplied")
    indexed: dict[str, dict[str, Mapping[str, Any]]] = {}
    for symbol in symbols:
        table: dict[str, Mapping[str, Any]] = {}
        for row in rows_by_symbol[symbol]:
            stamp = str(row.get(timestamp_key) or "")
            if stamp:
                table[stamp] = row
        if not table:
            raise PanelError("NO_ROWS", f"{symbol} has no timestamped rows")
        indexed[symbol] = table
    common = set(indexed[symbols[0]])
    for symbol in symbols[1:]:
        common &= set(indexed[symbol])
    if not common:
        raise PanelError("NO_COMMON_DATES", "the symbols share no timestamps")
    timestamps = tuple(sorted(common))
    arrays: dict[str, np.ndarray] = {}
    for field in wanted:
        matrix = np.full((len(timestamps), len(symbols)), np.nan, dtype=float)
        for column, symbol in enumerate(symbols):
            table = indexed[symbol]
            for row_index, stamp in enumerate(timestamps):
                value = table[stamp].get(field)
                try:
                    matrix[row_index, column] = float(value)
                except (TypeError, ValueError):
                    matrix[row_index, column] = np.nan
        arrays[field] = matrix
    return Panel(symbols=symbols, timestamps=timestamps, fields=arrays)


# -- elementwise / cross-sectional -------------------------------------------


def _as2d(value: Any) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.ndim == 0:
        return array.reshape(1, 1)
    if array.ndim == 1:
        return array.reshape(-1, 1)
    return array


def cross_sectional_rank(panel: Any) -> np.ndarray:
    """Per-date percentile rank across symbols, in [0, 1]; NaN stays NaN."""
    values = _as2d(panel)
    out = np.full(values.shape, np.nan)
    for row in range(values.shape[0]):
        line = values[row]
        finite = np.isfinite(line)
        count = int(finite.sum())
        if count == 0:
            continue
        if count == 1:
            out[row, finite] = 0.5
            continue
        order = np.argsort(line[finite], kind="mergesort")
        ranks = np.empty(count, dtype=float)
        ranks[order] = np.arange(count, dtype=float)
        # average ties so equal values share a rank
        sorted_values = line[finite][order]
        start = 0
        for index in range(1, count + 1):
            if index == count or sorted_values[index] != sorted_values[start]:
                average = (start + index - 1) / 2.0
                ranks[order[start:index]] = average
                start = index
        out[row, finite] = ranks / (count - 1)
    return out


def cross_sectional_scale(panel: Any, k: float = 1.0) -> np.ndarray:
    """Per-date scaling: x * k / sum(|x| across the row)."""
    values = _as2d(panel)
    out = np.full(values.shape, np.nan)
    totals = np.nansum(np.abs(values), axis=1)
    for row in range(values.shape[0]):
        total = totals[row]
        if not np.isfinite(total) or total == 0:
            continue
        out[row] = values[row] * (float(k) / total)
    return out


def _roll(panel: np.ndarray, window: int, fn) -> np.ndarray:
    w = int(window)
    values = _as2d(panel)
    out = np.full(values.shape, np.nan)
    for row in range(w - 1, values.shape[0]):
        chunk = values[row - w + 1: row + 1]
        for column in range(values.shape[1]):
            column_values = chunk[:, column]
            if not np.isfinite(column_values).all():
                continue
            out[row, column] = fn(column_values)
    return out


def _rank_kernel(chunk: np.ndarray) -> float:
    last = chunk[-1]
    less = float(np.sum(chunk < last))
    equal = float(np.sum(chunk == last))
    n = chunk.size
    return 1.0 if n == 1 else (less + 0.5 * (equal - 1)) / (n - 1)


def _argmax_kernel(chunk: np.ndarray) -> float:
    return float(np.argmax(chunk))


def _argmin_kernel(chunk: np.ndarray) -> float:
    return float(np.argmin(chunk))


def _reg_kernel(chunk: np.ndarray) -> tuple[float, float, float]:
    """OLS of the window against t = 0..w-1: (slope, r2, last residual)."""
    n = chunk.size
    t = np.arange(n, dtype=float)
    t_mean, y_mean = float(t.mean()), float(chunk.mean())
    sxx = float(((t - t_mean) ** 2).sum())
    if sxx == 0:
        return float("nan"), float("nan"), float("nan")
    slope = float(((t - t_mean) * (chunk - y_mean)).sum()) / sxx
    intercept = y_mean - slope * t_mean
    fitted = intercept + slope * t
    ss_res = float(((chunk - fitted) ** 2).sum())
    ss_tot = float(((chunk - y_mean) ** 2).sum())
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return slope, r2, float(chunk[-1] - fitted[-1])


def _corr_kernel(x: np.ndarray, y: np.ndarray) -> float:
    sx, sy = float(np.std(x)), float(np.std(y))
    if sx == 0 or sy == 0:
        return float("nan")
    return float(np.mean((x - x.mean()) * (y - y.mean())) / (sx * sy))


def _elementwise(name: str):
    simple = {
        "abs": np.abs, "log": np.log, "sqrt": np.sqrt, "sign": np.sign,
    }
    return simple.get(name)


PANEL_FUNCTIONS: frozenset[str] = frozenset({
    "add", "subtract", "multiply", "divide", "abs", "log", "sqrt", "sign",
    "lag", "delta", "diff", "pct_change", "log_return",
    "rolling_mean", "rolling_std", "rolling_min", "rolling_max", "rolling_sum",
    "ts_sum", "sumac", "prod", "ts_prod", "sma",
    "regbeta", "regresi", "regbeta_where", "cumprod",
    "neutralize", "signed_power", "wilder", "sma_cn", "maximum", "minimum", "wma",
    "ts_rank", "ts_argmax", "ts_argmin", "decay_linear", "correlation", "covariance",
    "slope", "r2", "resi",
    "rank", "cross_sectional_rank", "scale",
    "where", "greater_than", "less_than", "clip",
})


def _call(name: str, args: list[Any]) -> Any:
    if name not in PANEL_FUNCTIONS:
        raise PanelError(
            "UNSUPPORTED_FUNCTION",
            f"{name}() is not implemented for a panel; supported: "
            f"{', '.join(sorted(PANEL_FUNCTIONS))}",
        )
    if name in ("rank", "cross_sectional_rank"):
        return cross_sectional_rank(args[0])
    if name == "scale":
        return cross_sectional_scale(args[0], args[1] if len(args) > 1 else 1.0)
    if name == "lag":
        n = int(args[1])
        values = _as2d(args[0])
        out = np.full(values.shape, np.nan)
        if n < values.shape[0]:
            out[n:] = values[: values.shape[0] - n] if n else values
        return out
    if name in ("delta", "diff"):
        n = int(args[1]) if len(args) > 1 else 1
        values = _as2d(args[0])
        out = np.full(values.shape, np.nan)
        out[n:] = values[n:] - values[:-n]
        return out
    if name == "pct_change":
        n = int(args[1]) if len(args) > 1 else 1
        values = _as2d(args[0])
        out = np.full(values.shape, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[n:] = values[n:] / values[:-n] - 1.0
        return out
    if name == "log_return":
        n = int(args[1]) if len(args) > 1 else 1
        values = _as2d(args[0])
        out = np.full(values.shape, np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[n:] = np.log(values[n:] / values[:-n])
        return out
    if name in ("rolling_mean", "sma"):
        return _roll(args[0], args[1], lambda c: float(np.mean(c)))
    if name == "rolling_std":
        return _roll(args[0], args[1], lambda c: float(np.std(c, ddof=1)))
    if name == "rolling_min":
        return _roll(args[0], args[1], lambda c: float(np.min(c)))
    if name == "rolling_max":
        return _roll(args[0], args[1], lambda c: float(np.max(c)))
    if name in ("rolling_sum", "ts_sum", "sumac"):
        return _roll(args[0], args[1], lambda c: float(np.sum(c)))
    if name in ("prod", "ts_prod"):
        return _roll(args[0], args[1], lambda c: float(np.prod(c)))
    if name == "ts_rank":
        return _roll(args[0], args[1], _rank_kernel)
    if name == "ts_argmax":
        return _roll(args[0], args[1], _argmax_kernel)
    if name == "ts_argmin":
        return _roll(args[0], args[1], _argmin_kernel)
    if name in ("slope", "r2", "resi"):
        index = {"slope": 0, "r2": 1, "resi": 2}[name]
        return _roll(args[0], args[1], lambda c: _reg_kernel(c)[index])
    if name == "decay_linear":
        w = int(args[1])
        weights = np.arange(1, w + 1, dtype=float)
        weights = weights / weights.sum()
        return _roll(args[0], w, lambda c: float(np.dot(c, weights)))
    if name == "correlation":
        x, y = _as2d(args[0]), _as2d(args[1])
        w = int(args[2]) if len(args) > 2 else x.shape[0]
        out = np.full(x.shape, np.nan)
        for row in range(w - 1, x.shape[0]):
            for column in range(x.shape[1]):
                cx = x[row - w + 1: row + 1, column]
                cy = y[row - w + 1: row + 1, column]
                if not (np.isfinite(cx).all() and np.isfinite(cy).all()):
                    continue
                out[row, column] = _corr_kernel(cx, cy)
        return out
    if name == "covariance":
        x, y = _as2d(args[0]), _as2d(args[1])
        w = int(args[2]) if len(args) > 2 else x.shape[0]
        out = np.full(x.shape, np.nan)
        for row in range(w - 1, x.shape[0]):
            for column in range(x.shape[1]):
                cx = x[row - w + 1: row + 1, column]
                cy = y[row - w + 1: row + 1, column]
                if not (np.isfinite(cx).all() and np.isfinite(cy).all()):
                    continue
                out[row, column] = float(np.cov(cx, cy, ddof=1)[0, 1])
        return out
    if name in ("wilder", "sma_cn"):
        values = _as2d(args[0])
        n = int(args[1])
        m = float(args[2]) if len(args) > 2 else 1.0
        if n <= 0 or m <= 0 or m > n:
            raise PanelError("BAD_ARGUMENT", "wilder(x, n, m) needs 0 < m <= n")
        out = np.full(values.shape, np.nan)
        previous = np.full(values.shape[1], np.nan)
        for row in range(values.shape[0]):
            current = values[row]
            for column in range(values.shape[1]):
                value = current[column]
                if not np.isfinite(value):
                    previous[column] = np.nan   # a gap resets; the next value reseeds
                    continue
                if not np.isfinite(previous[column]):
                    previous[column] = float(value)
                else:
                    previous[column] = (m * float(value) + (n - m) * previous[column]) / n
                out[row, column] = previous[column]
        return out
    if name == "wma":
        w = int(args[1])
        if w <= 0:
            raise PanelError("BAD_ARGUMENT", "wma(x, n) needs n > 0")
        weights = np.arange(w, 0, -1, dtype=float)
        weights = weights / weights.sum()
        return _roll(args[0], w, lambda c: float(np.dot(c, weights)))
    if name in ("maximum", "minimum"):
        a, b = _as2d(args[0]), _as2d(args[1])
        return np.fmax(a, b) if name == "maximum" else np.fmin(a, b)
    if name in ("regbeta", "regresi", "regbeta_where"):
        y = _as2d(args[0])
        x = _as2d(args[1])
        if name == "regbeta_where":
            mask = _as2d(args[2])
            w = int(args[3])
        else:
            mask = None
            w = int(args[2])
        if w < 2:
            raise PanelError("BAD_ARGUMENT", "a paired regression needs a window >= 2")
        out = np.full(y.shape, np.nan)
        for row in range(w - 1, y.shape[0]):
            for column in range(y.shape[1]):
                cy = y[row - w + 1: row + 1, column]
                cx = x[row - w + 1: row + 1, column]
                if not (np.isfinite(cy).all() and np.isfinite(cx).all()):
                    continue
                if mask is not None:
                    cm = mask[row - w + 1: row + 1, column]
                    selected = np.isfinite(cm) & (cm != 0)
                    if int(selected.sum()) < 2:
                        continue
                    cy, cx = cy[selected], cx[selected]
                x_mean, y_mean = float(cx.mean()), float(cy.mean())
                sxx = float(((cx - x_mean) ** 2).sum())
                if sxx == 0:
                    continue
                beta = float(((cx - x_mean) * (cy - y_mean)).sum()) / sxx
                out[row, column] = (
                    beta if name == "regbeta"
                    else float(cy[-1] - (y_mean + beta * (cx[-1] - x_mean)))
                )
        return out
    if name == "cumprod":
        values = _as2d(args[0])
        out = np.full(values.shape, np.nan)
        running = np.full(values.shape[1], np.nan)
        for row in range(values.shape[0]):
            for column in range(values.shape[1]):
                value = values[row, column]
                if not np.isfinite(value):
                    out[row, column] = running[column]
                    continue
                running[column] = (float(value) if not np.isfinite(running[column])
                                   else running[column] * float(value))
                out[row, column] = running[column]
        return out
    if name == "signed_power":
        values = _as2d(args[0])
        # The exponent may be a SERIES (Alpha#84 uses delta(close,5)), so it is
        # broadcast elementwise rather than coerced to a float.
        exponent = _as2d(args[1])
        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            return np.sign(values) * np.abs(values) ** exponent
    if name == "neutralize":
        values = _as2d(args[0])
        groups = _as2d(args[1])
        if groups.shape[1] != values.shape[1]:
            raise PanelError(
                "BAD_GROUP", "neutralize(x, group) needs one group label per name")
        if groups.shape[0] == 1 and values.shape[0] > 1:
            groups = np.broadcast_to(groups, values.shape)
        out = np.full(values.shape, np.nan)
        for row in range(values.shape[0]):
            labels = groups[row]
            values_row = values[row]
            finite = np.isfinite(values_row) & np.isfinite(labels)
            for label in np.unique(labels[finite]):
                cohort = finite & (labels == label)
                if cohort.sum() < 2:
                    # A one-name cohort has no cross-section to neutralise; the
                    # value is kept as-is rather than centred on itself (which
                    # would silently make it 0).
                    out[row, cohort] = values_row[cohort]
                    continue
                out[row, cohort] = values_row[cohort] - float(values_row[cohort].mean())
        return out
    if name in ("where", "greater_than", "less_than", "clip"):
        a = _as2d(args[0])
        if name == "where":
            return np.where(a.astype(bool), _as2d(args[1]), _as2d(args[2]))
        if name == "greater_than":
            return (a > args[1]).astype(float)
        if name == "less_than":
            return (a < args[1]).astype(float)
        low, high = args[1], args[2]
        return np.clip(a, low, high)
    simple = _elementwise(name)
    if simple is not None:
        with np.errstate(divide="ignore", invalid="ignore"):
            return simple(_as2d(args[0]))
    raise PanelError("UNSUPPORTED_FUNCTION", f"{name}() has no panel implementation")


def _eval(node: tuple, context: Mapping[str, Any]) -> Any:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "var":
        name = node[1]
        if name not in context:
            raise PanelError("UNKNOWN_VARIABLE", f"unknown variable: {name}")
        return _as2d(context[name])
    if kind == "unary":
        value = _eval(node[2], context)
        return -value if node[1] == "-" else value
    if kind == "bin":
        op = node[1]
        a = _eval(node[2], context)
        b = _eval(node[3], context)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                return np.asarray(a, dtype=float) / b
            if op == "^":
                return np.asarray(a, dtype=float) ** b
            if op == "<":
                return (np.asarray(a) < b).astype(float)
            if op == ">":
                return (np.asarray(a) > b).astype(float)
            if op == "<=":
                return (np.asarray(a) <= b).astype(float)
            if op == ">=":
                return (np.asarray(a) >= b).astype(float)
            if op == "==":
                return (np.asarray(a) == b).astype(float)
            if op == "!=":
                return (np.asarray(a) != b).astype(float)
        raise PanelError("OP", f"unknown operator {op}")
    if kind == "call":
        return _call(node[1], [_eval(arg, context) for arg in node[2]])
    raise PanelError("NODE", f"unknown AST node: {kind}")


def evaluate(expression: str, panel: Panel) -> np.ndarray:
    """Evaluate `expression` over `panel`, returning a T x N result."""
    parsed = formula.parse(expression, allow=PANEL_FUNCTIONS - set(formula.FUNCTIONS))
    result = _eval(parsed.ast, panel.fields)
    array = np.asarray(result, dtype=float)
    if array.ndim == 1:
        array = array.reshape(-1, 1)
    return array


def to_series(result: np.ndarray, panel: Panel) -> dict[str, list[float]]:
    """Split a T x N result back into per-symbol series."""
    values = _as2d(result)
    return {
        symbol: [
            None if not np.isfinite(values[row, column]) else round(float(values[row, column]), 10)
            for row in range(values.shape[0])
        ]
        for column, symbol in enumerate(panel.symbols)
    }


__all__ = [
    "PANEL_FUNCTIONS",
    "Panel",
    "PanelError",
    "build_panel",
    "cross_sectional_rank",
    "cross_sectional_scale",
    "evaluate",
    "to_series",
]
