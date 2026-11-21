"""HTTP surface for the OpenBB Workspace bridge.

Two routes, both operator-gated (loopback or the runtime secret), because a
Workspace agent runs models and tools on this machine:

  GET  /openbb/agents.json   the agent card OpenBB reads to discover the server
  POST /openbb/v1/query      one stateless query, streamed as OpenBB SSE

Why `POST /openbb/v1/query` and not a bare `/v1/query`: the harness already owns
the root namespace for its own API, and OpenBB's endpoint path is configured on
the agent card. The card below is the single place that says where it lives, so
the two can never disagree.

The route does not invent credentials. `modelSettings` must arrive with the
request (see `adapter.build_run_request`); a Workspace request that carries none
is refused with a named code rather than silently answered by some default
provider.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..deps import require_operator, service
from ..openbb_bridge import BridgeError, build_run_request, openbb_frames, prepare
from ..schemas import RunRequest
# The front door origin for the read-only JDdS bridge. Imported rather than
# re-derived: it is the one policy for this value (`service.py` is line-ratcheted,
# so a public alias there would cost the budget for no behaviour).
from ..service import _default_callback_base_url

QUERY_PATH = "/openbb/v1/query"

router = APIRouter(tags=["openbb"], dependencies=[Depends(require_operator)])

_STATUS = {
    "BAD_PAYLOAD": 400,
    "NO_MESSAGES": 400,
    "NO_USER_TURN": 400,
    "NO_MODEL_SETTINGS": 400,
}


def _refuse(exc: BridgeError) -> HTTPException:
    return HTTPException(
        status_code=_STATUS.get(exc.code, 400),
        detail={"code": exc.code, "message": exc.message},
    )


def agent_card() -> dict[str, Any]:
    """The OpenBB agent description. Only what is true is advertised."""
    return {
        "name": "Eclipse",
        "description": (
            "BlackEclipse finance harness: market data, research, quant backtests, "
            "portfolio and risk analysis with cited evidence."
        ),
        "endpoints": {"query": QUERY_PATH},
        "features": {
            # The answer arrives as one message_chunk after the run's progress
            # steps: the runtime's answer is the run output, not token deltas.
            "streaming": True,
            "widget-dashboard-select": True,
            "widget-dashboard-search": False,
        },
    }


@router.get("/openbb/agents.json")
def openbb_agents_json() -> dict[str, Any]:
    return agent_card()


@router.post(QUERY_PATH)
async def openbb_query(request: Request) -> StreamingResponse:
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - a non-JSON body is a client error
        raise HTTPException(status_code=400, detail={"code": "BAD_JSON", "message": "body is not JSON"})
    try:
        prepared = prepare(payload)
        run_id = f"run_{uuid.uuid4().hex[:16]}"
        body = build_run_request(payload, prepared, run_id)
        # A Workspace request cannot know where the front door lives; the runtime
        # does. An explicit value from the caller wins.
        body.setdefault("callbackBaseUrl", _default_callback_base_url())
        run_request = RunRequest.model_validate(body)
    except BridgeError as exc:
        raise _refuse(exc) from exc
    except ValueError as exc:  # pydantic validation of the composed run
        raise HTTPException(
            status_code=400,
            detail={"code": "BAD_RUN_REQUEST", "message": str(exc)[:500]},
        ) from exc

    await service.run_background(run_request)
    queue = service.bus.open_stream(run_id)
    return StreamingResponse(
        openbb_frames(service, run_id, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Run-Id": run_id,
        },
    )


__all__ = ["QUERY_PATH", "agent_card", "router"]
