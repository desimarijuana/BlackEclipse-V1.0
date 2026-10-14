"""One-shot headless chat — `eclipse chat -z "..."` (Phase W10).

The scripting surface the CLI was missing: run ONE question through the ONE
runtime and print the answer. It runs in-process (like `eclipse eval`), so it
needs no front door; model settings come from the `HARNESS_JOB_*` environment —
the SAME source a scheduled job uses — and a real provider/key env wins.

No new agent loop, no second registry: `deps.service.run` is the very path the
web chat uses, so a headless answer carries the same honesty rules (UNAVAILABLE
instead of fabricated data, the same tool surface and approvals).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from typing import Any


def _model_settings() -> Any:
    from .schemas import ModelSettings  # noqa: PLC0415

    return ModelSettings(
        provider=os.environ.get("HARNESS_JOB_PROVIDER", "ollama"),
        model=os.environ.get("HARNESS_JOB_MODEL", "llama3.1"),
        base_url=os.environ.get("HARNESS_JOB_BASE_URL") or None,
        api_key=os.environ.get("HARNESS_JOB_API_KEY") or None,
    )


def _run_once(question: str, *, agent_id: str) -> dict[str, Any]:
    """Run ONE question through the shared runtime; return a plain result dict."""
    from .deps import service  # noqa: PLC0415 - constructing the ONE runtime is intended
    from .schemas import RunInput, RunRequest  # noqa: PLC0415

    request = RunRequest(
        runId=uuid.uuid4().hex,
        input=RunInput(query=question),
        agentId=agent_id or None,
        modelSettings=_model_settings(),
        callbackBaseUrl=os.environ.get("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000"),
        callbackToken=os.environ.get("CRON_SECRET") or None,
    )
    result = asyncio.run(service.run(request))
    payload = result.model_dump()
    return {
        "success": payload.get("status") == "completed",
        "runId": payload.get("runId"),
        "status": payload.get("status"),
        "output": payload.get("output") or "",
        "error": payload.get("error"),
    }


def run_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="eclipse chat",
        description="Ask Eclipse one question and print the answer (headless).",
    )
    parser.add_argument("question", nargs="?", default=None,
                        help="the question (one-shot; same as -z)")
    parser.add_argument("-z", "--message", dest="question_flag", default=None,
                        help="the question (one-shot; same as the positional)")
    parser.add_argument("--agent", default="eclipse-agent", help="agent preset id")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    question = (args.question_flag or args.question or "").strip()
    if not question:
        print("eclipse chat: a question is required (eclipse chat -z \"...\")", file=sys.stderr)
        return 2

    try:
        result = _run_once(question, agent_id=str(args.agent or "eclipse-agent"))
    except Exception as exc:  # noqa: BLE001 - a runtime failure is a clean CLI error
        if args.json:
            print(json.dumps({"success": False, "code": "RUN_FAILED", "error": str(exc)[:500]}))
        else:
            print(f"eclipse chat: the run could not start: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, default=str))
    else:
        output = str(result.get("output") or "").strip()
        if output:
            print(output)
        elif result.get("error"):
            print(f"eclipse chat: {result['error']}", file=sys.stderr)
    return 0 if result.get("success") else 1


__all__ = ["run_cli"]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run_cli(sys.argv[1:]))
