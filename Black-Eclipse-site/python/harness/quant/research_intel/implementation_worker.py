"""Isolated worker for one registered research implementation.

Invoked as `python -I implementation_worker.py <input.json> <output.json>`.

Input: {"sourcePath": "...", "rows": [...], "params": {...}}
Output: {"status":"ok","result":{...}} or {"status":"error","error":{...}}

The source must define `run(rows, params) -> dict`. This worker is a separate
process with a scrubbed environment; the parent enforces the timeout and the
output cap. It is process isolation, not a container.
"""

from __future__ import annotations

import json
import sys
import traceback


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: implementation_worker.py <input> <output>", file=sys.stderr)
        return 2
    in_path, out_path = argv[1], argv[2]
    with open(in_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    try:
        with open(payload["sourcePath"], "r", encoding="utf-8") as fh:
            source = fh.read()
        namespace = {"__name__": "research_implementation"}
        exec(compile(source, payload["sourcePath"], "exec"), namespace)
        run = namespace.get("run")
        if not callable(run):
            raise ValueError("the implementation must define run(rows, params)")
        result = run(payload.get("rows") or [], payload.get("params") or {})
        if not isinstance(result, dict):
            raise ValueError("run(rows, params) must return a dict")
        output = {"status": "ok", "result": result}
    except Exception as exc:  # noqa: BLE001
        output = {
            "status": "error",
            "error": {"type": type(exc).__name__, "message": str(exc),
                      "trace": traceback.format_exc(limit=4)},
        }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
