"""Deterministic instruction parsing for `edit_file`.

`edit_file`'s job is to turn a plain-language instruction ("rename beta to BETA",
"add a null check after the parse call", "delete the unused import") into a
CONCRETE minimal edit, without a model call and without guessing. This module is
that parser.

It is deliberately conservative. It only returns an edit when BOTH a target and a
replacement (for a replace/insert) or a target (for a delete) are named
explicitly, and it refuses vague pronouns ("it", "this", "the file"). When it
cannot derive an edit it returns None, and `edit_file` falls back to returning the
inspection packet so the model can choose an exact anchor. It never invents text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# A replacement/insert target or value that names nothing specific. Such an
# instruction is not actionable on its own.
_VAGUE = frozenset({
    "it", "this", "that", "them", "the file", "the code", "the function",
    "the value", "the line", "the text", "everything", "something", "anything",
})

# Ordered so the most specific connective wins. Each yields the operation plus
# which captured group is the "old" (target/anchor) and which is the "new" (value).
_REPLACE = re.compile(
    r"^\s*(?:please\s+)?(?:rename|change|replace|swap|update|set|turn|convert)\s+"
    r"(?P<old>.+?)\s+(?:to|with|into|by|->|=>|:)\s+(?P<new>.+?)\s*[.!]?\s*$",
    re.I,
)
_INSERT_AFTER = re.compile(
    r"^\s*(?:please\s+)?(?:add|insert|append|put)\s+(?P<new>.+?)\s+"
    r"(?:after|below|following)\s+(?P<old>.+?)\s*[.!]?\s*$",
    re.I,
)
_INSERT_BEFORE = re.compile(
    r"^\s*(?:please\s+)?(?:add|insert|put)\s+(?P<new>.+?)\s+"
    r"(?:before|above|preceding)\s+(?P<old>.+?)\s*[.!]?\s*$",
    re.I,
)
_APPEND = re.compile(
    r"^\s*(?:please\s+)?(?:append|add|insert)\s+(?P<new>.+?)\s+"
    r"(?:at\s+the\s+end|to\s+the\s+end|to\s+the\s+file|at\s+end)\s*[.!]?\s*$",
    re.I,
)
_PREPEND = re.compile(
    r"^\s*(?:please\s+)?(?:prepend|add|insert)\s+(?P<new>.+?)\s+"
    r"(?:at\s+the\s+(?:start|beginning)|to\s+the\s+(?:start|beginning))\s*[.!]?\s*$",
    re.I,
)
_DELETE = re.compile(
    r"^\s*(?:please\s+)?(?:delete|remove)\s+(?:the\s+)?(?P<old>.+?)\s*[.!]?\s*$",
    re.I,
)

# Inline-code formatting is stripped so `foo` and "foo" both become foo.
_WRAPPER = re.compile(r"^[`'\"“”]+(.*?)[`'\"“”]+$", re.S)
_LEADING_ARTICLE = re.compile(r"^(?:the|a|an)\s+", re.I)


@dataclass(frozen=True)
class ParsedEdit:
    operation: str          # replace | insert | delete | append | prepend
    old_text: Optional[str]
    new_text: Optional[str]
    source: str             # the instruction text it was derived from

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "oldText": self.old_text,
            "newText": self.new_text,
            "source": self.source,
        }


def _clean(value: str) -> str:
    text = value.strip()
    wrapped = _WRAPPER.match(text)
    if wrapped:
        text = wrapped.group(1).strip()
    return text


def _clean_target(value: str) -> str:
    """Clean an anchor/target and drop a leading article, so "the timeout" matches
    the code token `timeout` rather than its prose description."""
    text = _clean(value)
    text = _LEADING_ARTICLE.sub("", text).strip()
    return text


def _usable(value: Optional[str]) -> bool:
    if value is None:
        return False
    text = value.strip()
    if not text:
        return False
    return text.casefold() not in _VAGUE


def parse_edit_instruction(instruction: str) -> Optional[ParsedEdit]:
    """Derive a concrete edit from a plain instruction, or None when not possible.

    Deterministic and side-effect-free. The order matters: append/prepend/insert
    phrases are more specific than the generic replace connective, so they are
    tried first.
    """
    text = str(instruction or "").strip()
    if not text:
        return None

    for pattern in (_INSERT_AFTER, _INSERT_BEFORE, _APPEND, _PREPEND):
        match = pattern.match(text)
        if match:
            value = _clean(match.group("new"))
            if not _usable(value):
                continue
            if pattern is _APPEND:
                return ParsedEdit("append", None, value, text)
            if pattern is _PREPEND:
                return ParsedEdit("prepend", None, value, text)
            anchor = _clean_target(match.group("old"))
            if not _usable(anchor):
                continue
            return ParsedEdit("insert", anchor, value, text)

    replace = _REPLACE.match(text)
    if replace:
        old = _clean_target(replace.group("old"))
        new = _clean(replace.group("new"))
        if _usable(old) and new != "":
            return ParsedEdit("replace", old, new, text)

    delete = _DELETE.match(text)
    if delete:
        old = _clean_target(delete.group("old"))
        if _usable(old):
            return ParsedEdit("delete", old, None, text)

    return None


def is_insert_before(instruction: str) -> bool:
    """Whether the insert phrasing was a 'before' form (used by the caller)."""
    match = _INSERT_BEFORE.match(str(instruction or "").strip())
    return match is not None


__all__ = ["ParsedEdit", "is_insert_before", "parse_edit_instruction"]
