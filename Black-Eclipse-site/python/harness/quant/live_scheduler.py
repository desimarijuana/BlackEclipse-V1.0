"""Bar-close scheduler for live trials.

The scheduler is intentionally thin: it lists active trials and calls the SAME
`run_once` path, which claims the bar, runs risk and refuses duplicates. It never
sends its own order.

A cron or job can call `run_due` once per minute or on a bar boundary.
"""

from __future__ import annotations

from typing import Any


async def run_due(service: Any, gateway: Any) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for trial in service.list(limit=200):
        if trial.get("status") not in ("ready", "running", "paused"):
            continue
        try:
            result = await service.run_once(trial["id"], gateway=gateway)
            results.append({"trialId": trial["id"], "status": trial["status"],
                            "result": result})
        except Exception as exc:  # noqa: BLE001 - one trial must not stop the batch
            errors.append({"trialId": trial["id"], "error": str(exc)})
    return {
        "ran": len(results),
        "errors": errors,
        "results": results,
        "note": "Each run is idempotent per closed bar; a duplicate bar is skipped.",
    }


__all__ = ["run_due"]
