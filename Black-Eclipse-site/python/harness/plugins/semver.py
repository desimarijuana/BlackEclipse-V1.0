"""A small, dependency-free semantic-version parser and range matcher.

The plugin manifest is validated with this module (no third-party packaging
dependency, so the runtime stack stays minimal). It implements the subset of
SemVer 2.0.0 the plugin platform needs:

  * parse `MAJOR.MINOR.PATCH[-prerelease][+build]`
  * total ordering (SemVer precedence: numeric > alpha, prerelease < release)
  * range satisfaction: `=`, `>`, `>=`, `<`, `<=`, `^`, `~`, `*`/`x`,
    comma/space-separated conjunctions, and `||` alternatives.

Unparseable input raises `ValueError`, so a malformed version can never silently
compare as equal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering
from typing import Optional

_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)"
    r"\.(?P<minor>0|[1-9]\d*)"
    r"\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


@total_ordering
@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    @classmethod
    def parse(cls, value: str) -> "Version":
        if not isinstance(value, str):
            raise ValueError(f"version must be a string, got {type(value).__name__}")
        match = _SEMVER_RE.match(value.strip())
        if not match:
            raise ValueError(f"invalid semantic version: {value!r}")
        pre = match.group("prerelease")
        build = match.group("build")
        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=tuple(pre.split(".")) if pre else (),
            build=tuple(build.split(".")) if build else (),
        )

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            base += "-" + ".".join(self.prerelease)
        if self.build:
            base += "+" + ".".join(self.build)
        return base

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch, self.prerelease) == (
            other.major, other.minor, other.patch, other.prerelease,
        )

    def __lt__(self, other: "Version") -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        a = (self.major, self.minor, self.patch)
        b = (other.major, other.minor, other.patch)
        if a != b:
            return a < b
        return _pre_lt(self.prerelease, other.prerelease)

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.prerelease))

    def core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)


def _pre_lt(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """SemVer prerelease precedence (a release sorts AFTER any prerelease)."""
    if a == b:
        return False
    if not a:  # release > prerelease
        return False
    if not b:
        return True
    for x, y in zip(a, b):
        if x == y:
            continue
        x_num, y_num = x.isdigit(), y.isdigit()
        if x_num and y_num:
            return int(x) < int(y)
        if x_num != y_num:
            return x_num  # numeric identifiers have lower precedence
        return x < y
    return len(a) < len(b)


def parse(value: str) -> Version:
    return Version.parse(value)


def compare(a: str, b: str) -> int:
    va, vb = Version.parse(a), Version.parse(b)
    return (va > vb) - (va < vb)


def is_valid(value: str) -> bool:
    try:
        Version.parse(value)
        return True
    except ValueError:
        return False


def _next_caret(v: Version) -> Version:
    """Upper bound (exclusive) for `^`. ^0.x.y is special-cased per SemVer."""
    if v.major > 0:
        return Version(v.major + 1, 0, 0)
    if v.minor > 0:
        return Version(0, v.minor + 1, 0)
    return Version(0, 0, v.patch + 1)


@dataclass(frozen=True)
class _Comparator:
    op: str
    version: Version

    def matches(self, v: Version, include_prerelease: bool) -> bool:
        if self.op in ("", "="):
            return v == self.version
        if self.op == ">":
            return v > self.version
        if self.op == ">=":
            return v >= self.version
        if self.op == "<":
            return v < self.version
        if self.op == "<=":
            return v <= self.version
        if self.op == "^":
            return v >= self.version and v < _next_caret(self.version)
        if self.op == "~":
            upper = Version(self.version.major, self.version.minor + 1, 0)
            return v >= self.version and v < upper
        raise ValueError(f"unknown comparator {self.op!r}")


def satisfies(version: str, range_expr: str) -> bool:
    """True when `version` satisfies `range_expr`.

    An empty range or `*`/`x` matches anything. Prerelease versions only satisfy
    a range that itself names a prerelease (standard SemVer range rule), which
    keeps a `^1.0.0` constraint from matching `2.0.0-alpha`.
    """
    v = Version.parse(version)
    expr = (range_expr or "").strip()
    if expr in ("", "*", "x", "X"):
        return True
    for alternative in expr.split("||"):
        if _satisfies_all(v, alternative.strip()):
            return True
    return False


def _satisfies_all(v: Version, expr: str) -> bool:
    if not expr:
        return True
    parts = [p for p in re.split(r"[\s,]+", expr) if p]
    range_has_pre = _range_mentions_prerelease(parts)
    # Standard SemVer range rule: a prerelease version only satisfies a range
    # whose comparators also name a prerelease. Otherwise `2.0.0-alpha` would
    # match `>=1.0.0`, which it must not.
    if v.prerelease and not range_has_pre:
        return False
    for part in parts:
        if part in ("*", "x", "X"):
            continue
        if not _parse_comparator(part).matches(v, range_has_pre):
            return False
    return True


def _range_mentions_prerelease(parts: list[str]) -> bool:
    for part in parts:
        stripped = re.sub(r"^[<>=^~]*", "", part).strip()
        if not stripped or stripped in ("*", "x", "X"):
            continue
        try:
            if Version.parse(_pad_partial(stripped)).prerelease:
                return True
        except ValueError:
            continue
    return False


def _pad_partial(raw: str) -> str:
    core = raw.split("+")[0]
    hv = core.split("-")
    nums = hv[0].split(".")
    while len(nums) < 3:
        nums.append("0")
    out = ".".join(nums[:3])
    if len(hv) > 1:
        out += "-" + "-".join(hv[1:])
    return out


def _parse_comparator(part: str) -> _Comparator:
    match = re.match(r"^(>=|<=|>|<|\^|~|=)?\s*(.+)$", part)
    if not match:
        raise ValueError(f"invalid version range token: {part!r}")
    op = match.group(1) or ""
    raw = match.group(2).strip()
    # `1.2.x` / `1.x` partial ranges → the `~`/`^`-style bounds.
    if re.search(r"[xX*]", raw):
        nums = raw.split(".")
        nums = [n for n in nums if n not in ("x", "X", "*")]
        if len(nums) == 1:
            return _Comparator("^", Version(int(nums[0]), 0, 0))
        if len(nums) == 2:
            return _Comparator("~", Version(int(nums[0]), int(nums[1]), 0))
    # A bare partial `1` or `1.2` means the `^` range.
    if raw.count(".") == 0 and not op:
        return _Comparator("^", Version(int(raw), 0, 0))
    if raw.count(".") == 1 and not op:
        major, minor = raw.split(".")
        return _Comparator("~", Version(int(major), int(minor), 0))
    return _Comparator(op, Version.parse(raw))


__all__ = ["Version", "parse", "compare", "is_valid", "satisfies"]
