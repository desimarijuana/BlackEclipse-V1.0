"""The machine message editor for reword/edit during `git rebase -i`.

The sequence editor (which knows the FINAL order of the rebase) writes the
planned replacement messages, in order, to `BLACK_ECLIPSE_REBASE_QUEUE_DIR`.
Git invokes this editor once per `reword`/`edit` step, in that same order, with
the commit-message file as `argv[1]`. This script writes the next queued message
and advances a counter, so no interactive editor is ever opened.

When no message is queued for the current step, the existing message is kept
(the file is left untouched).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 0
    target = Path(argv[1])
    queue_dir = os.environ.get("BLACK_ECLIPSE_REBASE_QUEUE_DIR")
    if not queue_dir:
        return 0
    base = Path(queue_dir)
    counter_file = base / "counter"
    try:
        index = int(counter_file.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        index = 0
    message_file = base / f"msg_{index}.txt"
    try:
        message = message_file.read_text(encoding="utf-8")
    except OSError:
        return 0  # nothing queued for this step: keep the existing message
    try:
        target.write_text(message, encoding="utf-8", newline="\n")
    except OSError:
        return 0
    try:
        counter_file.write_text(str(index + 1), encoding="utf-8")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
