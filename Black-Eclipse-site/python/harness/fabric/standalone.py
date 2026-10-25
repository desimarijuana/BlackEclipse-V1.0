"""Run Execution-Fabric workers in a DEDICATED process.

The normal app process is producer + consumer. For a worker split on ONE host,
run this module beside the app with the same `agent-memory.db`:

    python -m harness.fabric.standalone --workers graph,agent

The app can then be made producer-only with
`HARNESS_FABRIC_WORKERS=none`. Jobs are claimed atomically, so any number of
processes on this host can share the queue without double execution.

Scope: this is same-host process concurrency over the shared SQLite store, not a
multi-machine fleet. A remote worker would need a shared database/queue, which
this local-first app does not provide.

Set `HARNESS_CALLBACK_URL` in the worker process to the app's base URL so agent
and graph nodes can reach the data bridge / model vault.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from typing import Any, Optional


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m harness.fabric.standalone",
        description="Run Execution-Fabric workers in a dedicated process.",
    )
    parser.add_argument(
        "--workers",
        default=None,
        help="Comma-separated worker kinds or queues (default: $HARNESS_FABRIC_WORKERS or all).",
    )
    return parser.parse_args(argv)


async def run(workers: Optional[str] = None) -> int:
    if workers:
        os.environ["HARNESS_FABRIC_WORKERS"] = workers
    # A worker process must never claim to be a second scheduler/boot owner; it
    # only constructs the service and starts the Fabric consumer loops.
    from ..service import AgenticService  # noqa: PLC0415
    from .bootstrap import install_fabric_layer, start_fabric, stop_fabric  # noqa: PLC0415

    service = AgenticService()
    manager = install_fabric_layer(service)
    if manager is None:
        print(json.dumps({"error": "the execution fabric is disabled or unavailable"}))
        service.close()
        return 2

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _stop(*_args: Any) -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except (NotImplementedError, RuntimeError):  # Windows: fall back to KeyboardInterrupt
            pass

    await start_fabric(service)
    workers_list = [
        {"kind": worker.kind, "queues": list(worker.queues), "concurrency": worker.concurrency}
        for worker in manager.workers()
    ]
    print(json.dumps({
        "pid": os.getpid(),
        "db": getattr(service.store, "path", None),
        "workers": workers_list,
        "callbackUrl": os.environ.get("HARNESS_CALLBACK_URL") or None,
    }), flush=True)
    if not workers_list:
        print(json.dumps({
            "error": "no workers selected; set --workers or HARNESS_FABRIC_WORKERS",
        }), flush=True)
        await stop_fabric(service)
        service.close()
        return 2

    try:
        await stop.wait()
    except KeyboardInterrupt:  # pragma: no cover - Windows Ctrl+C
        pass
    finally:
        await stop_fabric(service)
        service.close()
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(run(args.workers))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
