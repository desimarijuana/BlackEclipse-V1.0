# Formula Language

> `last-verified: 2026-10-10`
> Implementation: `python/harness/stats/formula.py` (parser + whitelist evaluator)
> Used by: `build_features` (`{"name": "...", "expression": "..."}`)

A restricted expression language for user-defined features. **No** `eval`/`exec`,
**no** imports, **no** attribute access, **no** I/O. Only the functions in
`FUNCTIONS` are callable, and only variables supplied in the evaluation context
are readable.

## Grammar

```
expr    := term (('+' | '-' | '<' | '>' | '<=' | '>=' | '==' | '!=') term)*
term    := unary (('*' | '/') unary)*
unary   := ('-' | '+') unary | power
power   := primary ('^' unary)?          # right-associative; binds tighter than unary
primary := NUMBER | IDENT | IDENT '(' args? ')' | '(' expr ')'
args    := expr (',' expr)*
```

Exponentiation binds tighter than unary minus: `-close ^ 2 == -(close^2)`.

## Resource limits

`MAX_EXPRESSION_LEN=2000`, `MAX_TOKENS=512`, `MAX_NODES=256`,
`MAX_SERIES_LEN=2_000_000`. Breaching any raises `FormulaError`
(`TOO_LONG`, `TOO_COMPLEX`, `TOO_LARGE`).

## Variables

Context keys: `price`, `close` (default = price), `returns`, and `high`, `low`,
`volume`, `benchmark` when supplied. Unknown variables are rejected at evaluation
(`MISSING_INPUT`).

## Function catalogue (allowlist)

- **Arithmetic**: `add subtract multiply divide abs log sqrt`
- **Time series**: `lag diff pct_change log_return`
- **Rolling**: `rolling_mean rolling_std rolling_min rolling_max rolling_quantile`
- **Normalization**: `zscore rank minmax_scale winsorize`
- **Statistics**: `correlation covariance beta skew kurtosis`
- **Technical**: `sma ema rsi macd atr bollinger_bands`
- **Cross-sectional**: `cross_sectional_rank sector_rank demean neutralize`
- **Conditions**: `where greater_than less_than clip`

`bollinger_bands(x, w, k=2)` returns the band *width* relative to the middle
band, `(upper-lower)/mid`, so it composes as a scalar series.

## Errors

`EMPTY`, `TOO_LONG`, `TOO_COMPLEX`, `BAD_CHAR`, `SYNTAX`, `TRAILING`, `PAREN`,
`UNKNOWN_FUNCTION`, `UNKNOWN_VARIABLE`, `MISSING_INPUT`, `SHAPE`, `DOMAIN`,
`EVAL`, `NODE`, `TOO_LARGE`.

## Security invariants (tested in `test_stats_formula.py`)

- `__import__(x)`, `open(x)`, `eval(x)`, `exec(x)`, `getattr(x, ...)` and any
  non-allowlisted identifier produce `UNKNOWN_FUNCTION`.
- Attribute access (`close.__class__`) and unexpected characters are rejected at
  tokenize/parse time.
- Empty and over-long expressions are rejected before evaluation.

## Example

```
sma(close, 20) / lag(close, 1) - 1
where(greater_than(rsi(close, 14), 70), 1, 0)
zscore(returns, 20)
```
