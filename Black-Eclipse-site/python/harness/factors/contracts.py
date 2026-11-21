"""The input contract for zoo factors that need data OHLCV does not carry.

Some published alphas use **vwap**, which cannot be derived from open/high/low/
close without fabricating it: the usual `(high + low + close) / 3` is a typical
price, not a volume-weighted average, and substituting it would make the factor's
IC look real while measuring something else.

So the contract is explicit:

  * a factor that needs it declares `requiresInputs: ["vwap"]`;
  * `require_inputs(factor, fields)` raises `MISSING_INPUT` naming what is
    missing — a refusal, not a silent NaN column;
  * `missing_inputs(factor, fields)` is the non-raising form a UI can use to grey
    a factor out and say *why*.

This keeps "available" honest: an alpha is runnable when its declared inputs are
present, and the caller learns which input it must supply.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping


class FactorInputError(ValueError):
    """A factor cannot run on the supplied inputs, with a stable `code`."""

    def __init__(self, code: str, message: str, *, missing: Iterable[str] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.missing = tuple(missing)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "missing": list(self.missing)}


def required_inputs(factor: Mapping[str, Any]) -> tuple[str, ...]:
    """The inputs a factor declares beyond the OHLCV surface."""
    declared = factor.get("requiresInputs") or ()
    if isinstance(declared, str):
        declared = (declared,)
    return tuple(str(name) for name in declared)


def missing_inputs(factor: Mapping[str, Any], available: Iterable[str]) -> list[str]:
    """Declared inputs that `available` does not provide, in declaration order."""
    have = {str(name) for name in available}
    # A factor's own `inputs` list is what its expression reads; a declared
    # requirement that the expression does not use would be a metadata bug, so
    # both sets are honoured rather than trusting one.
    return [name for name in required_inputs(factor) if name not in have]


def require_inputs(factor: Mapping[str, Any], available: Iterable[str]) -> None:
    """Raise `MISSING_INPUT` when a declared input is absent."""
    missing = missing_inputs(factor, available)
    if missing:
        raise FactorInputError(
            "MISSING_INPUT",
            f"{factor.get('name') or 'factor'} needs {', '.join(missing)}, which the "
            "caller must supply (it is not derivable from OHLCV)",
            missing=missing,
        )


def describe(factor: Mapping[str, Any], available: Iterable[str]) -> dict[str, Any]:
    """A small, serialisable statement of what this factor needs and has."""
    missing = missing_inputs(factor, available)
    return {
        "name": factor.get("name"),
        "requiresInputs": list(required_inputs(factor)),
        "runnable": not missing,
        "missing": missing,
        "reason": (
            f"needs {', '.join(missing)}" if missing else "inputs satisfied"
        ),
    }


__all__ = [
    "FactorInputError",
    "describe",
    "missing_inputs",
    "require_inputs",
    "required_inputs",
]
