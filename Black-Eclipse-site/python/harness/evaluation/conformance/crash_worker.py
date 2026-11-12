"""Crash worker for the C8 kill matrix.

Run in a separate process, killed at a chosen durable window. The parent then
resumes and asserts at-most-once effect semantics:

    before_begin  -> no ledger row          -> resume may execute once
    after_begin   -> row state=started      -> resume must not execute (unknown)
    after_effect  -> effect happened, row started -> resume must not execute
    after_finish  -> row state=done         -> resume must not execute

Usage: python -c "<launcher>" -- <db> <effects-log> <mode>
"""

from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3:
        return 2
    db_path, effect_log, mode = args[0], args[1], args[2]

    from harness.persistence import AgentMemoryStore  # noqa: PLC0415
    from harness.run_effects import RunEffects  # noqa: PLC0415

    if mode == "before_begin":
        os._exit(9)
    store = AgentMemoryStore(db_path)
    effects = RunEffects(store)
    effects.begin("crash_run", 1, "c1", "order_submit", "external_action")
    if mode == "after_begin":
        os._exit(9)
    with open(effect_log, "a", encoding="utf-8") as handle:
        handle.write("effect\n")
    if mode == "after_effect":
        os._exit(9)
    effects.finish("crash_run", 1, "c1", ok=True)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
