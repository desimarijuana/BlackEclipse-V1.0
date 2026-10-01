"""The runtime-produced plain-language gate (roadmap §9 G7).

Every refusal a command can produce carries ONE plain sentence plus a recovery
step, and neither contains a mechanism word from `policy.PLAIN_LANGUAGE_DENYLIST`.
This is the runtime half of the front-door gate in
`src/lib/i18n/plain-language.test.ts` — commands produce text, so the check
belongs in pytest too.
"""

from __future__ import annotations

import re

import pytest

from harness.code import policy
from harness.code.commands import COMMAND_REFUSAL_COPY, refusal_copy

_DENY = {t.casefold() for t in policy.PLAIN_LANGUAGE_DENYLIST}


def _leaks(text: str) -> set[str]:
    lowered = text.casefold()
    found: set[str] = set()
    for term in _DENY:
        if " " in term:
            if term in lowered:
                found.add(term)
            continue
        if re.search(rf"(^|[^a-z0-9]){re.escape(term)}([^a-z0-9]|$)", lowered):
            found.add(term)
    return found


def test_every_refusal_has_a_plain_reason_and_recovery():
    for code, copy in COMMAND_REFUSAL_COPY.items():
        assert copy.get("reason"), code
        assert copy.get("recovery"), code
        assert not _leaks(copy["reason"]), f"{code} reason leaks"
        assert not _leaks(copy["recovery"]), f"{code} recovery leaks"


def test_unknown_code_falls_back_to_plain_copy():
    copy = refusal_copy("SOMETHING_UNKNOWN")
    assert copy["reason"] and copy["recovery"]
    assert not _leaks(copy["reason"])
    assert not _leaks(copy["recovery"])


@pytest.mark.parametrize("code", list(COMMAND_REFUSAL_COPY))
def test_refusal_sentences_end_in_a_full_stop(code):
    copy = refusal_copy(code)
    assert copy["reason"].rstrip().endswith((".", "!", "?”", "?")), copy["reason"]
