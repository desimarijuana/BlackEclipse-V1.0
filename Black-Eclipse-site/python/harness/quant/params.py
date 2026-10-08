"""Parameter spaces for optimization and sensitivity analysis.

A parameter space maps a **dotted path** into the strategy dict (e.g.
`indicators.0.params.period`, `rules.exit.stop_loss.value`,
`position_sizing.value`) to a list of candidate values. Paths address both dict
keys and list indices, so any declared indicator, rule value, risk limit or
sizing field can be tuned without special-casing.

An axis may be given as an explicit list, or as a range descriptor
`{"start":…, "stop":…, "step"|"count":…}`. Everything is deterministic: applying
the same parameters yields the same spec, and sampling uses a seeded RNG.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Optional

_MISSING = object()


class ParamError(ValueError):
    pass


# ── Path access ──────────────────────────────────────────────────────────────

def _seg(container: Any, token: str) -> Any:
    if isinstance(container, list):
        try:
            return container[int(token)]
        except (ValueError, IndexError) as exc:
            raise ParamError(f"invalid list index {token!r}") from exc
    if isinstance(container, dict):
        if token not in container:
            raise ParamError(f"path segment {token!r} not found")
        return container[token]
    raise ParamError(f"cannot descend into {type(container).__name__} with {token!r}")


def get_path(obj: Any, path: str, default: Any = _MISSING) -> Any:
    cur = obj
    try:
        for token in path.split("."):
            cur = _seg(cur, token)
        return cur
    except ParamError:
        if default is _MISSING:
            raise
        return default


def _parent(obj: Any, path: str) -> tuple[Any, str]:
    tokens = path.split(".")
    if not tokens or not tokens[-1]:
        raise ParamError(f"invalid parameter path {path!r}")
    parent = obj
    for token in tokens[:-1]:
        parent = _seg(parent, token)
    return parent, tokens[-1]


def set_path(obj: Any, path: str, value: Any) -> None:
    """Set a dotted path in-place. Dict keys are created; list indices must exist."""
    parent, last = _parent(obj, path)
    if isinstance(parent, list):
        try:
            parent[int(last)] = value
        except (ValueError, IndexError) as exc:
            raise ParamError(f"invalid list index {last!r} in {path!r}") from exc
    elif isinstance(parent, dict):
        parent[last] = value
    else:
        raise ParamError(f"cannot set {path!r} on {type(parent).__name__}")


def parent_exists(obj: Any, path: str) -> bool:
    try:
        _parent(obj, path)
        return True
    except ParamError:
        return False


# ── Axis normalization ───────────────────────────────────────────────────────

def _normalize_axis(values: Any) -> list[Any]:
    if isinstance(values, dict):
        if "values" in values:
            return list(values["values"])
        if "start" in values and "stop" in values:
            start = float(values["start"])
            stop = float(values["stop"])
            if start > stop:
                start, stop = stop, start
            if "step" in values:
                step = float(values["step"])
                if step <= 0:
                    raise ParamError("range step must be > 0")
                count = int(round((stop - start) / step)) + 1
                out = [round(start + i * step, 10) for i in range(count)]
            else:
                count = int(values.get("count", 5))
                if count < 1:
                    raise ParamError("range count must be >= 1")
                if count == 1:
                    out = [start]
                else:
                    stepv = (stop - start) / (count - 1)
                    out = [round(start + i * stepv, 10) for i in range(count)]
            if values.get("integer"):
                out = sorted({int(round(v)) for v in out})
            return out
        raise ParamError("range axis needs {start, stop} and step or count")
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ParamError(f"axis values must be a list or range descriptor, got {values!r}")
    return list(values)


# ── Space ────────────────────────────────────────────────────────────────────

@dataclass
class ParamSpace:
    axes: dict[str, list[Any]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Optional[dict[str, Any]]) -> "ParamSpace":
        axes = {path: _normalize_axis(values) for path, values in (raw or {}).items()}
        for path, values in axes.items():
            if not values:
                raise ParamError(f"parameter {path!r} has an empty value list")
        return cls(axes=axes)

    def size(self) -> int:
        n = 1
        for values in self.axes.values():
            n *= len(values)
        return n

    def is_empty(self) -> bool:
        return not self.axes

    def paths(self) -> list[str]:
        return list(self.axes.keys())

    def grid(self) -> Iterator[dict[str, Any]]:
        paths = self.paths()
        if not paths:
            yield {}
            return
        indices = [0] * len(paths)
        while True:
            yield {path: self.axes[path][indices[i]] for i, path in enumerate(paths)}
            # odometer increment
            pos = len(paths) - 1
            while pos >= 0:
                indices[pos] += 1
                if indices[pos] < len(self.axes[paths[pos]]):
                    break
                indices[pos] = 0
                pos -= 1
            if pos < 0:
                return

    def sample(self, n: int, rng: random.Random) -> list[dict[str, Any]]:
        if self.is_empty():
            return [{}]
        out: list[dict[str, Any]] = []
        seen: set[tuple] = set()
        attempts = 0
        target = min(n, self.size())
        while len(out) < target and attempts < target * 50 + 100:
            attempts += 1
            combo = {path: rng.choice(values) for path, values in self.axes.items()}
            key = tuple((p, repr(combo[p])) for p in sorted(combo))
            if key in seen:
                continue
            seen.add(key)
            out.append(combo)
        return out

    def clamp_value(self, path: str, value: Any) -> Any:
        """Snap a value to the nearest allowed axis value (categorical axes only)."""
        values = self.axes.get(path)
        if not values:
            return value
        if value in values:
            return value
        try:
            return min(values, key=lambda v: abs(float(v) - float(value)))
        except (TypeError, ValueError):
            return values[0]


def apply_params(base_spec: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Deep-copy `base_spec` and set every dotted path to its value."""
    spec = copy.deepcopy(base_spec)
    for path, value in params.items():
        set_path(spec, path, value)
    return spec


def summarize_space(space: ParamSpace) -> dict[str, Any]:
    return {
        "axes": {path: {"values": values, "count": len(values)}
                 for path, values in space.axes.items()},
        "dimensions": len(space.axes),
        "gridSize": space.size(),
    }


__all__ = [
    "ParamError",
    "ParamSpace",
    "apply_params",
    "get_path",
    "parent_exists",
    "set_path",
    "summarize_space",
]
