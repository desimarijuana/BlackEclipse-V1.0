"""Safe formula language for user-defined features.

A restricted expression language — no Python ``eval``/``exec``, no imports, no
attribute access, no I/O. The grammar is tiny:

    expr    := term (('+' | '-') term)*
    term    := factor (('*' | '/') factor)*
    factor  := unary ('^' factor)?
    unary   := ('-' | '+')? primary
    primary := NUMBER | IDENT | IDENT '(' args? ')' | '(' expr ')'
    args    := expr (',' expr)*

Identifiers are either a registered function (whitelist) or a variable supplied
in the evaluation context. Unknown names, arity mismatches, resource-limit
breaches and non-finite results are rejected with a structured `FormulaError`.

Only the functions in `FUNCTIONS` are callable; each works on NumPy arrays with
scalar broadcasting, so `close / sma(close, 20) - 1` is valid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

MAX_EXPRESSION_LEN = 2000
MAX_TOKENS = 512
MAX_NODES = 256
MAX_SERIES_LEN = 2_000_000


class FormulaError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Token:
    kind: str
    value: Any
    pos: int


def _tokenize(text: str) -> list[Token]:
    if len(text) > MAX_EXPRESSION_LEN:
        raise FormulaError("TOO_LONG", "formula exceeds the maximum length")
    tokens: list[Token] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            j = i
            while j < n and (text[j].isdigit() or text[j] == "."):
                j += 1
            tokens.append(Token("NUMBER", float(text[i:j]), i))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(Token("IDENT", text[i:j], i))
            i = j
            continue
        two = text[i: i + 2]
        if two in ("<=", ">=", "==", "!="):
            tokens.append(Token("OP", two, i))
            i += 2
            continue
        if c in "+-*/^<>(),":
            kind = "OP" if c not in "()," else c
            tokens.append(Token(kind, c, i))
            i += 1
            continue
        raise FormulaError("BAD_CHAR", f"unexpected character {c!r} at {i}")
        if len(tokens) > MAX_TOKENS:
            raise FormulaError("TOO_COMPLEX", "formula has too many tokens")
    tokens.append(Token("EOF", None, n))
    return tokens


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.i = 0
        self.nodes = 0

    def peek(self) -> Token:
        return self.tokens[self.i]

    def next(self) -> Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def _count(self) -> None:
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise FormulaError("TOO_COMPLEX", "formula is too deeply nested")

    def parse(self) -> tuple:
        node = self.expr()
        if self.peek().kind != "EOF":
            raise FormulaError("TRAILING", f"unexpected token {self.peek().value!r}")
        return node

    def expr(self) -> tuple:
        node = self.term()
        while self.peek().kind == "OP" and self.peek().value in ("+", "-", "<", ">", "<=", ">=", "==", "!="):
            op = self.next().value
            self._count()
            node = ("bin", op, node, self.term())
        return node

    def term(self) -> tuple:
        node = self.unary()
        while self.peek().kind == "OP" and self.peek().value in ("*", "/"):
            op = self.next().value
            self._count()
            node = ("bin", op, node, self.unary())
        return node

    def unary(self) -> tuple:
        if self.peek().kind == "OP" and self.peek().value in ("-", "+"):
            op = self.next().value
            self._count()
            return ("unary", op, self.unary())
        return self.power()

    def power(self) -> tuple:
        node = self.primary()
        if self.peek().kind == "OP" and self.peek().value == "^":
            self.next()
            self._count()
            node = ("bin", "^", node, self.unary())
        return node

    def primary(self) -> tuple:
        tok = self.peek()
        if tok.kind == "NUMBER":
            self.next()
            self._count()
            return ("num", tok.value)
        if tok.kind == "IDENT":
            self.next()
            name = tok.value
            if self.peek().kind == "(":
                self.next()
                args = []
                if self.peek().kind != ")":
                    args.append(self.expr())
                    while self.peek().kind == ",":
                        self.next()
                        args.append(self.expr())
                if self.peek().kind != ")":
                    raise FormulaError("PAREN", f"missing ')' after {name}()")
                self.next()
                self._count()
                return ("call", name, args)
            self._count()
            return ("var", name)
        if tok.kind == "(":
            self.next()
            node = self.expr()
            if self.peek().kind != ")":
                raise FormulaError("PAREN", "missing closing ')'")
            self.next()
            return node
        raise FormulaError("SYNTAX", f"unexpected token {tok.value!r} at {tok.pos}")


# ── function registry ────────────────────────────────────────────────────────


def _as_arr(x: Any) -> np.ndarray:
    return np.asarray(x, dtype=float)


def _lag(x, n):
    n = int(n)
    out = np.full_like(_as_arr(x), np.nan, dtype=float)
    if n < 0 or n >= out.size:
        return out
    if n == 0:
        return _as_arr(x).copy()
    out[n:] = _as_arr(x)[:-n]
    return out


def _diff(x, n=1):
    n = int(n)
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    if n < a.size:
        out[n:] = a[n:] - a[:-n]
    return out


def _pct_change(x, n=1):
    n = int(n)
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[n:] = a[n:] / a[:-n] - 1.0
    return out


def _log_return(x, n=1):
    n = int(n)
    a = _as_arr(x)
    if np.any(a[np.isfinite(a)] <= 0):
        raise FormulaError("DOMAIN", "log_return requires positive prices")
    out = np.full(a.size, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out[n:] = np.log(a[n:] / a[:-n])
    return out


def _rolling(x, w, fn):
    w = int(w)
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    for i in range(w - 1, a.size):
        chunk = a[i - w + 1: i + 1]
        if np.isfinite(chunk).all():
            out[i] = fn(chunk)
    return out


def _rolling_quantile(x, w, q):
    return _rolling(x, w, lambda c: float(np.quantile(c, float(q))))


def _ts_rank(x, w):
    """Rank (0..1) of the LATEST value inside its rolling window.

    Ties get half credit, so a constant window ranks 0.5 rather than 0 or 1.
    This is Alpha101's `ts_rank` (a time-series rank) — not a cross-sectional
    rank over a universe.
    """
    w = int(w)
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    for i in range(w - 1, a.size):
        chunk = a[i - w + 1: i + 1]
        if not np.isfinite(chunk).all():
            continue
        last = chunk[-1]
        less = float(np.sum(chunk < last))
        equal = float(np.sum(chunk == last))
        if w > 1:
            out[i] = (less + 0.5 * (equal - 1)) / (w - 1)
        else:
            out[i] = 1.0
    return out


def _wilder(x, n, m):
    """GTJA/Wilder recursive mean: `Y_t = (m*X_t + (n-m)*Y_{t-1}) / n`.

    This is **not** a rolling mean: it is an exponentially weighted recursion with
    memory of every prior observation, seeded with the first valid value. GTJA191
    is full of `SMA(X,N,M)` and means this operator, so calling it `sma` (a rolling
    mean here) would silently change the alpha.

    A NaN input **resets** the recursion for that series and the next finite value
    reseeds it — the convention the published GTJA implementation documents
    ("missing input resets this stock; the next valid input reseeds it"). Resuming
    from a stale value across a gap would smooth across an unknown.
    """
    n = int(n)
    m = float(m)
    if n <= 0 or m <= 0 or m > n:
        raise FormulaError("BAD_ARGUMENT", "wilder(x, n, m) needs 0 < m <= n")
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    previous = float("nan")
    for index, value in enumerate(a):
        if not np.isfinite(value):
            previous = float("nan")   # a gap resets; the next value reseeds
            continue
        previous = float(value) if not np.isfinite(previous) else (
            (m * float(value) + (n - m) * previous) / n
        )
        out[index] = previous
    return out


def _wma(x, n):
    """GTJA/TDX `WMA(X,N)`: weights `N, N-1, ..., 1`, i.e. **oldest heaviest**.

    This is the mirror image of `decay_linear`, whose newest observation carries
    the largest weight. The published GTJA implementation documents exactly this
    convention ("oldest-to-newest weights n, ..., 1"), so implementing it as
    `decay_linear` would silently invert the smoothing.
    """
    n = int(n)
    if n <= 0:
        raise FormulaError("BAD_ARGUMENT", "wma(x, n) needs n > 0")
    weights = np.arange(n, 0, -1, dtype=float)
    weights = weights / weights.sum()
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    for i in range(n - 1, a.size):
        chunk = a[i - n + 1: i + 1]
        if not np.isfinite(chunk).all():
            continue
        out[i] = float(np.dot(chunk, weights))
    return out


def _pair_window(x, y, w):
    """Align two series into a rolling (y, x) window, refusing bad arguments."""
    w = int(w)
    if w < 2:
        raise FormulaError("BAD_ARGUMENT", "a paired regression needs a window >= 2")
    return _as_arr(x), _as_arr(y), w


def _regbeta(y, x, w):
    """Rolling OLS slope of `y` on `x` (GTJA's `REGBETA(y, x, n)`).

    This is **not** `slope`, which regresses against time. GTJA's downside-beta
    (`#149`) and factor-neutralisation formulas regress one series on another, and
    substituting a time slope there would measure a different quantity.
    """
    yv, xv, w = _pair_window(y, x, w)
    out = np.full(yv.size, np.nan)
    for i in range(w - 1, yv.size):
        cy = yv[i - w + 1: i + 1]
        cx = xv[i - w + 1: i + 1]
        if not (np.isfinite(cy).all() and np.isfinite(cx).all()):
            continue
        x_mean = float(cx.mean())
        sxx = float(((cx - x_mean) ** 2).sum())
        if sxx == 0:
            continue
        out[i] = float(((cx - x_mean) * (cy - float(cy.mean()))).sum()) / sxx
    return out


def _regresi(y, x, w):
    """Rolling OLS residual of the LAST `y` from its regression on `x`."""
    yv, xv, w = _pair_window(y, x, w)
    out = np.full(yv.size, np.nan)
    for i in range(w - 1, yv.size):
        cy = yv[i - w + 1: i + 1]
        cx = xv[i - w + 1: i + 1]
        if not (np.isfinite(cy).all() and np.isfinite(cx).all()):
            continue
        x_mean, y_mean = float(cx.mean()), float(cy.mean())
        sxx = float(((cx - x_mean) ** 2).sum())
        if sxx == 0:
            continue
        beta = float(((cx - x_mean) * (cy - y_mean)).sum()) / sxx
        out[i] = float(cy[-1] - (y_mean + beta * (cx[-1] - x_mean)))
    return out


def _regbeta_where(y, x, cond, w):
    """`REGBETA` restricted to the observations where `cond` is truthy.

    GTJA #149 is a **downside** beta: it regresses stock returns on benchmark
    returns using only the days the benchmark fell. A mask cannot be expressed by
    dropping rows (that would change the window's meaning), so the mask is carried
    into the regression explicitly and a window with fewer than two selected
    observations is NaN rather than a slope from one point.
    """
    yv, xv, w = _pair_window(y, x, w)
    mask = _as_arr(cond)
    out = np.full(yv.size, np.nan)
    for i in range(w - 1, yv.size):
        cy = yv[i - w + 1: i + 1]
        cx = xv[i - w + 1: i + 1]
        cm = mask[i - w + 1: i + 1]
        selected = np.isfinite(cy) & np.isfinite(cx) & np.isfinite(cm) & (cm != 0)
        if int(selected.sum()) < 2:
            continue
        sy, sx = cy[selected], cx[selected]
        x_mean = float(sx.mean())
        sxx = float(((sx - x_mean) ** 2).sum())
        if sxx == 0:
            continue
        out[i] = float(((sx - x_mean) * (sy - float(sy.mean()))).sum()) / sxx
    return out


def _cumprod(x):
    """Expanding product from the first finite value (GTJA #143's `SELF` state).

    A missing value carries the running product forward; it does not reset it,
    because the published formula multiplies only on the days its condition holds.
    """
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    running = float("nan")
    for i, value in enumerate(a):
        if not np.isfinite(value):
            out[i] = running
            continue
        running = float(value) if not np.isfinite(running) else running * float(value)
        out[i] = running
    return out


def _regresi_multi(y, x1, x2, x3, w):
    """Rolling residual of `y` on a THREE-factor model (GTJA's `REGRESI` with
    MKT/SMB/HML).

    The factors are declared inputs, never invented: GTJA #30 regresses a stock's
    returns on the market, size and value factors it does not itself supply, so the
    caller must provide them. An ill-conditioned window (singular normal equations)
    is NaN rather than a pseudo-solution — a fitted residual from a rank-deficient
    system would look like signal.
    """
    w = int(w)
    if w < 4:
        raise FormulaError("BAD_ARGUMENT", "a three-factor regression needs a window >= 4")
    yv = _as_arr(y)
    xs = [_as_arr(x) for x in (x1, x2, x3)]
    out = np.full(yv.size, np.nan)
    for i in range(w - 1, yv.size):
        cy = yv[i - w + 1: i + 1]
        columns = [cx[i - w + 1: i + 1] for cx in xs]
        if not np.isfinite(cy).all() or not all(np.isfinite(c).all() for c in columns):
            continue
        design = np.column_stack([np.ones(w)] + columns)
        # `lstsq` happily returns a minimum-norm solution for a rank-deficient
        # design, which is NOT an identifiable fit. A collinear factor set would
        # then produce a residual that looks like signal, so the rank is checked
        # explicitly and a deficient window stays NaN.
        if np.linalg.matrix_rank(design) < design.shape[1]:
            continue
        try:
            coefficients, *_ = np.linalg.lstsq(design, cy, rcond=None)
        except np.linalg.LinAlgError:
            continue
        if not np.isfinite(coefficients).all():
            continue
        out[i] = float(cy[-1] - float(design[-1] @ coefficients))
    return out


def _signed_power(x, p):
    """`sign(x) * |x| ** p` — the published `SignedPower`.

    Unlike `x ^ p`, this is defined for a negative base: `(-2)^0.5` is NaN in IEEE
    arithmetic but `signed_power(-2, 0.5)` is `-1.414`, which is what the paper
    means (it is a signed magnitude, not a complex number).
    """
    a = _as_arr(x)
    with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        return np.sign(a) * np.abs(a) ** np.asarray(p, dtype=float)


def _maximum(a, b):
    """Elementwise maximum of two series (GTJA's `MAX(x, y)`)."""
    return np.fmax(_as_arr(a), _as_arr(b))


def _minimum(a, b):
    """Elementwise minimum of two series (GTJA's `MIN(x, y)`)."""
    return np.fmin(_as_arr(a), _as_arr(b))


def _ts_argmax(x, w):
    """0-based position of the window maximum; earliest wins on ties."""
    w = int(w)
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    for i in range(w - 1, a.size):
        chunk = a[i - w + 1: i + 1]
        if not np.isfinite(chunk).all():
            continue
        out[i] = float(np.argmax(chunk))
    return out


def _ts_argmin(x, w):
    """0-based position of the window minimum; earliest wins on ties."""
    w = int(w)
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    for i in range(w - 1, a.size):
        chunk = a[i - w + 1: i + 1]
        if not np.isfinite(chunk).all():
            continue
        out[i] = float(np.argmin(chunk))
    return out


def _decay_linear(x, w):
    """Linearly weighted mean, most recent observation weighted highest."""
    w = int(w)
    weights = np.arange(1, w + 1, dtype=float)
    weights = weights / weights.sum()
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    for i in range(w - 1, a.size):
        chunk = a[i - w + 1: i + 1]
        if not np.isfinite(chunk).all():
            continue
        out[i] = float(np.dot(chunk, weights))
    return out


def _regression(chunk: np.ndarray) -> tuple[float, float, float] | None:
    """OLS of the window against t = 0..w-1: (slope, r2, last residual)."""
    n = chunk.size
    t = np.arange(n, dtype=float)
    t_mean, y_mean = float(t.mean()), float(chunk.mean())
    sxx = float(((t - t_mean) ** 2).sum())
    if sxx == 0:
        return None
    sxy = float(((t - t_mean) * (chunk - y_mean)).sum())
    slope = sxy / sxx
    intercept = y_mean - slope * t_mean
    fitted = intercept + slope * t
    ss_res = float(((chunk - fitted) ** 2).sum())
    ss_tot = float(((chunk - y_mean) ** 2).sum())
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return slope, r2, float(chunk[-1] - fitted[-1])


def _slope(x, w):
    """OLS slope of the window against time (Alpha158 `Slope`)."""
    w = int(w)
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    for i in range(w - 1, a.size):
        chunk = a[i - w + 1: i + 1]
        if not np.isfinite(chunk).all():
            continue
        fit = _regression(chunk)
        if fit is not None:
            out[i] = fit[0]
    return out


def _r2(x, w):
    """Coefficient of determination of the window against time (`Rsquare`)."""
    w = int(w)
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    for i in range(w - 1, a.size):
        chunk = a[i - w + 1: i + 1]
        if not np.isfinite(chunk).all():
            continue
        fit = _regression(chunk)
        if fit is not None:
            out[i] = fit[1]
    return out


def _resi(x, w):
    """Residual of the LAST point from its window regression (`Resi`)."""
    w = int(w)
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    for i in range(w - 1, a.size):
        chunk = a[i - w + 1: i + 1]
        if not np.isfinite(chunk).all():
            continue
        fit = _regression(chunk)
        if fit is not None:
            out[i] = fit[2]
    return out


def _scale_series(x, k=1.0):
    """Scale a SERIES by the sum of its absolute values.

    Deliberately named `scale_series`: Alpha101's `scale(x, k)` divides by the
    cross-sectional sum over the universe at each date, which this per-series
    evaluator cannot reproduce. The name says which one this is.
    """
    a = _as_arr(x)
    total = float(np.nansum(np.abs(a)))
    if total == 0:
        return np.full(a.size, np.nan)
    return a * (float(k) / total)


def _sma(x, w):
    return _rolling(x, w, lambda c: float(np.mean(c)))


def _ema(x, span):
    span = int(span)
    a = _as_arr(x)
    if a.size == 0:
        return a
    k = 2.0 / (span + 1)
    out = np.full(a.size, np.nan)
    prev = a[0]
    out[0] = prev
    for i in range(1, a.size):
        prev = a[i] * k + prev * (1 - k) if np.isfinite(a[i]) else prev
        out[i] = prev
    return out


def _rsi(x, w):
    w = int(w)
    a = _as_arr(x)
    out = np.full(a.size, np.nan)
    gains = np.zeros(a.size)
    losses = np.zeros(a.size)
    for i in range(1, a.size):
        d = a[i] - a[i - 1]
        gains[i] = max(d, 0.0)
        losses[i] = max(-d, 0.0)
    ag = np.mean(gains[1: w + 1]) if a.size > w else np.nan
    al = np.mean(losses[1: w + 1]) if a.size > w else np.nan
    for i in range(w + 1, a.size):
        ag = (ag * (w - 1) + gains[i]) / w
        al = (al * (w - 1) + losses[i]) / w
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


def _macd(x, fast=12, slow=26, signal=9):
    line = _ema(x, fast) - _ema(x, slow)
    return line - _ema(line, signal)


def _atr(high, low, close, w=14):
    h, l, c = _as_arr(high), _as_arr(low), _as_arr(close)
    n = min(h.size, l.size, c.size)
    tr = np.full(n, np.nan)
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return _rolling(tr, int(w), lambda x: float(np.mean(x)))


def _bollinger_bands(x, w, k=2):
    mid = _sma(x, w)
    sd = _rolling(x, w, lambda c: float(np.std(c, ddof=0)))
    width = 2 * float(k) * sd
    with np.errstate(divide="ignore", invalid="ignore"):
        return width / mid


def _zscore(x, w=None):
    a = _as_arr(x)
    if w is None:
        m, s = np.nanmean(a), np.nanstd(a, ddof=0)
        return (a - m) / s if s else np.zeros_like(a)
    w = int(w)
    mean = _rolling(x, w, lambda c: float(np.mean(c)))
    sd = _rolling(x, w, lambda c: float(np.std(c, ddof=0)))
    with np.errstate(divide="ignore", invalid="ignore"):
        return (a - mean) / np.where(sd == 0, np.nan, sd)


def _rank(x):
    a = _as_arr(x)
    order = np.argsort(a)
    ranks = np.empty(a.size)
    ranks[order] = np.arange(a.size)
    return ranks


def _minmax_scale(x):
    a = _as_arr(x)
    lo, hi = np.nanmin(a), np.nanmax(a)
    return (a - lo) / (hi - lo) if hi > lo else np.zeros_like(a)


def _winsorize(x, lower=0.05, upper=0.95):
    a = _as_arr(x)
    lo = np.nanquantile(a, float(lower))
    hi = np.nanquantile(a, float(upper))
    return np.clip(a, lo, hi)


def _correlation(x, y, w=None):
    a, b = _as_arr(x), _as_arr(y)
    if w is None:
        if a.size != b.size:
            raise FormulaError("SHAPE", "correlation inputs must be equal length")
        m = np.isfinite(a) & np.isfinite(b)
        if m.sum() < 2:
            return np.array([np.nan])
        return np.array([float(np.corrcoef(a[m], b[m])[0, 1])])
    return _rolling_pairs(a, b, int(w), lambda ca, cb: float(np.corrcoef(ca, cb)[0, 1]))


def _rolling_pairs(a, b, w, fn):
    out = np.full(a.size, np.nan)
    for i in range(w - 1, a.size):
        ca, cb = a[i - w + 1: i + 1], b[i - w + 1: i + 1]
        m = np.isfinite(ca) & np.isfinite(cb)
        if m.sum() >= 2:
            out[i] = fn(ca[m], cb[m])
    return out


def _covariance(x, y):
    a, b = _as_arr(x), _as_arr(y)
    m = np.isfinite(a) & np.isfinite(b)
    return np.array([float(np.cov(a[m], b[m], ddof=1)[0, 1])]) if m.sum() > 1 else np.array([np.nan])


def _beta(x, y):
    a, b = _as_arr(x), _as_arr(y)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 2 or np.var(b[m]) == 0:
        return np.array([np.nan])
    return np.array([float(np.cov(a[m], b[m])[0, 1] / np.var(b[m]))])


def _skew(x):
    a = _as_arr(x)
    a = a[np.isfinite(a)]
    if a.size < 3 or a.std() == 0:
        return np.array([np.nan])
    z = (a - a.mean()) / a.std()
    return np.array([float(np.mean(z ** 3))])


def _kurtosis(x):
    a = _as_arr(x)
    a = a[np.isfinite(a)]
    if a.size < 4 or a.std() == 0:
        return np.array([np.nan])
    z = (a - a.mean()) / a.std()
    return np.array([float(np.mean(z ** 4) - 3.0)])


def _where(cond, a, b):
    return np.where(_as_arr(cond).astype(bool), a, b)


def _greater_than(a, b):
    return (_as_arr(a) > b).astype(float)


def _less_than(a, b):
    return (_as_arr(a) < b).astype(float)


def _clip(x, lo, hi):
    return np.clip(_as_arr(x), float(lo), float(hi))


def _demean(x):
    a = _as_arr(x)
    return a - np.nanmean(a)


def _neutralize(x, y):
    a, b = _as_arr(x), _as_arr(y)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 2 or np.var(b[m]) == 0:
        return a - np.nanmean(a)
    beta = np.cov(a[m], b[m])[0, 1] / np.var(b[m])
    return a - beta * b


def _cross_sectional_rank(x):
    return _rank(x)


FUNCTIONS: dict[str, Callable[..., Any]] = {
    "add": lambda a, b: _as_arr(a) + b,
    "subtract": lambda a, b: _as_arr(a) - b,
    "multiply": lambda a, b: _as_arr(a) * b,
    "divide": lambda a, b: _as_arr(a) / b,
    "abs": lambda x: np.abs(_as_arr(x)),
    "log": lambda x: np.log(_as_arr(x)),
    "sqrt": lambda x: np.sqrt(_as_arr(x)),
    "lag": _lag,
    "diff": _diff,
    "pct_change": _pct_change,
    "log_return": _log_return,
    "rolling_mean": lambda x, w: _rolling(x, w, lambda c: float(np.mean(c))),
    "rolling_std": lambda x, w: _rolling(x, w, lambda c: float(np.std(c, ddof=1))),
    "rolling_min": lambda x, w: _rolling(x, w, lambda c: float(np.min(c))),
    "rolling_max": lambda x, w: _rolling(x, w, lambda c: float(np.max(c))),
    # `ts_sum` is Alpha101's `sum(x, d)`: a plain rolling sum, not a
    # weighted one. `rolling_sum` is the same function under the house name.
    "rolling_sum": lambda x, w: _rolling(x, w, lambda c: float(np.sum(c))),
    "ts_sum": lambda x, w: _rolling(x, w, lambda c: float(np.sum(c))),
    # GTJA names the plain rolling sum SUMAC; it is not a cumulative total.
    "sumac": lambda x, w: _rolling(x, w, lambda c: float(np.sum(c))),
    "prod": lambda x, w: _rolling(x, w, lambda c: float(np.prod(c))),
    "ts_prod": lambda x, w: _rolling(x, w, lambda c: float(np.prod(c))),
    # GTJA/Wilder recursion and elementwise pair ops (see `_wilder`).
    "wilder": _wilder,
    "sma_cn": _wilder,
    "wma": _wma,
    "maximum": _maximum,
    "regbeta": _regbeta,
    "regresi": _regresi,
    "regbeta_where": _regbeta_where,
    "regresi_multi": _regresi_multi,
    "cumprod": _cumprod,
    "signed_power": _signed_power,
    "minimum": _minimum,
    "rolling_quantile": _rolling_quantile,
    "zscore": _zscore,
    "rank": _rank,
    "minmax_scale": _minmax_scale,
    "winsorize": _winsorize,
    "correlation": _correlation,
    "covariance": _covariance,
    "beta": _beta,
    "skew": _skew,
    "kurtosis": _kurtosis,
    "sma": _sma,
    "ema": _ema,
    "rsi": _rsi,
    "macd": _macd,
    "atr": _atr,
    "bollinger_bands": _bollinger_bands,
    "cross_sectional_rank": _cross_sectional_rank,
    "sector_rank": _cross_sectional_rank,
    "demean": _demean,
    "neutralize": _neutralize,
    "where": _where,
    "greater_than": _greater_than,
    "less_than": _less_than,
    "clip": _clip,
}

# `delta` is the name published factor libraries use for a first difference;
# `sign` is required by formulas such as Alpha101 #12. Both are aliases over the
# same array helpers, so there is one implementation, not two.
FUNCTIONS["delta"] = _diff
FUNCTIONS["sign"] = lambda x: np.sign(_as_arr(x))
# Time-series operators published factor libraries rely on. Their names say
# "ts_" because they rank/weight WITHIN one instrument's window; they are not
# cross-sectional operators.
FUNCTIONS["ts_rank"] = _ts_rank
FUNCTIONS["ts_argmax"] = _ts_argmax
FUNCTIONS["ts_argmin"] = _ts_argmin
FUNCTIONS["slope"] = _slope
FUNCTIONS["r2"] = _r2
FUNCTIONS["resi"] = _resi
FUNCTIONS["decay_linear"] = _decay_linear
FUNCTIONS["scale_series"] = _scale_series


@dataclass
class ParsedFormula:
    ast: tuple
    variables: list[str]
    functions: list[str]


def _collect(node: tuple, variables: set, functions: set) -> None:
    kind = node[0]
    if kind == "var":
        variables.add(node[1])
    elif kind == "call":
        functions.add(node[1])
        for arg in node[2]:
            _collect(arg, variables, functions)
    elif kind == "bin":
        _collect(node[2], variables, functions)
        _collect(node[3], variables, functions)
    elif kind == "unary":
        _collect(node[2], variables, functions)


def parse(text: str, *, allow: Iterable[str] = ()) -> ParsedFormula:
    """Parse `text`. `allow` names extra functions a specialised evaluator
    supports (e.g. a panel-only `scale`) without registering them for the
    per-series evaluator, which would silently give them the wrong semantics."""
    if not isinstance(text, str) or not text.strip():
        raise FormulaError("EMPTY", "formula is empty")
    ast = _Parser(_tokenize(text)).parse()
    variables: set[str] = set()
    functions: set[str] = set()
    _collect(ast, variables, functions)
    unknown = functions - set(FUNCTIONS) - set(allow)
    if unknown:
        raise FormulaError("UNKNOWN_FUNCTION", f"unknown function(s): {sorted(unknown)}")
    return ParsedFormula(ast=ast, variables=sorted(variables), functions=sorted(functions))


def _eval(node: tuple, context: dict[str, Any]) -> Any:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "var":
        name = node[1]
        if name not in context:
            raise FormulaError("UNKNOWN_VARIABLE", f"unknown variable: {name}")
        value = context[name]
        arr = _as_arr(value)
        if arr.size > MAX_SERIES_LEN:
            raise FormulaError("TOO_LARGE", f"variable {name} exceeds the size limit")
        return arr
    if kind == "unary":
        val = _eval(node[2], context)
        return -val if node[1] == "-" else val
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
                return _as_arr(a) / b
            if op == "^":
                return _as_arr(a) ** b
            if op == "<":
                return (_as_arr(a) < b).astype(float)
            if op == ">":
                return (_as_arr(a) > b).astype(float)
            if op == "<=":
                return (_as_arr(a) <= b).astype(float)
            if op == ">=":
                return (_as_arr(a) >= b).astype(float)
            if op == "==":
                return (_as_arr(a) == b).astype(float)
            if op == "!=":
                return (_as_arr(a) != b).astype(float)
        raise FormulaError("OP", f"unknown operator {op}")
    if kind == "call":
        name = node[1]
        fn = FUNCTIONS.get(name)
        if fn is None:
            raise FormulaError("UNKNOWN_FUNCTION", f"unknown function: {name}")
        call_args = [_eval(a, context) for a in node[2]]
        try:
            return fn(*call_args)
        except FormulaError:
            raise
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            raise FormulaError("EVAL", f"{name}() failed: {exc}") from exc
    raise FormulaError("NODE", f"unknown AST node: {kind}")


def evaluate(text: str, context: dict[str, Any]) -> tuple[np.ndarray, ParsedFormula]:
    parsed = parse(text)
    missing = [v for v in parsed.variables if v not in context]
    if missing:
        raise FormulaError("MISSING_INPUT", f"missing input variable(s): {missing}")
    result = _eval(parsed.ast, context)
    arr = _as_arr(result)
    if arr.ndim == 0:
        arr = np.full(len(next(iter(context.values()))), float(arr)) if context else np.array([float(arr)])
    arr = np.where(np.isfinite(arr), arr, np.nan)
    return arr, parsed


__all__ = ["FormulaError", "FUNCTIONS", "ParsedFormula", "parse", "evaluate"]
