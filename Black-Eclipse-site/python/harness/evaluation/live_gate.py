"""The LIVE evaluation lane - a real model, measured (Round 3 / W8, ADR-H296).

**Why this module exists.** Until now the evaluation suite had two tiers that
were easy to confuse: the OFFLINE tier, which replaces the model with a
recorded script and therefore measures the RUNTIME (the tool surface, the
policy, the graders, the wiring), and a LIVE tier that existed in
`runner.ServiceAgentInvoker` but was reachable only by hand. A harness that
cannot be measured by anyone else is a harness that has to be taken on trust.

This module is the lane: it runs the live tier over a task set with a REAL
model, records the result with the provenance the store requires, and returns
the suite so the caller can publish it.

**It never fabricates.** With no provider configured it returns `None` and an
honest reason. A benchmark table with a guessed number in it is worse than an
empty one.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .runner import EvaluationRunner, ServiceAgentInvoker
from .scoring import check_thresholds
from .tasks import load_all_builtin, select_tasks

#: The env var that says "a live provider is configured".
PROVIDER_ENV = "BLACK_ECLIPSE_PROVIDER"
API_KEY_ENV = "BLACK_ECLIPSE_API_KEY"

#: Providers that are local and keyless by design.
LOCAL_PROVIDERS = frozenset({"ollama", "lmstudio", "local"})


def provider_configured() -> bool:
    """Whether a live provider can be used.

    A local provider needs only a name; a hosted one also needs a key. A hosted
    provider with no key is NOT configured - the lane reports NOT MEASURED
    instead of running trials that can only fail with 401.
    """
    provider = (os.environ.get(PROVIDER_ENV) or "").strip().lower()
    if not provider:
        return False
    if provider in LOCAL_PROVIDERS:
        return True
    return bool((os.environ.get(API_KEY_ENV) or "").strip())


#: The cheapest capability that proves the front door answers.
PREFLIGHT_CAPABILITY = "market_snapshot"


async def preflight_bridge() -> str:
    """One sentence when the front door cannot answer, else "".

    A dead front door used to produce 12 failed trials and ~179 ConnectError
    lines that read as the agent's fault. `HttpDataBridge.fetch` never raises, so
    no handler is needed here.
    """
    from ..bridge import HttpDataBridge  # noqa: PLC0415

    base = os.environ.get("HARNESS_CALLBACK_URL") or (
        f"http://127.0.0.1:{os.environ.get('PORT', '3000')}"
    )
    result = await HttpDataBridge(base, os.environ.get("CRON_SECRET")).fetch(
        PREFLIGHT_CAPABILITY, {"symbol": "AAPL"},
    )
    status = str((result or {}).get("status", "")).upper()
    if status == "OK":
        return ""
    detail = (result or {}).get("error") or "no detail"
    return (
        f"the data bridge at {base} answered {status or 'nothing'} ({detail}). "
        "The live lane needs a working front door - start the app with `npm run up`."
    )


async def run_live_gate(
    *,
    model: str = "",
    base_url: str = "",
    suite: str = "",
    task_limit: int = 12,
    trials: int = 1,
    persist: bool = True,
) -> tuple[Optional[Any], str]:
    """Run the live tier. Returns `(suite, reason)`.

    `suite` is None when the lane could not run, and `reason` says why - in
    plain words, so the published file can quote it.
    """
    if not provider_configured() and not model:
        return None, (
            "no live provider is configured. Set "
            f"{PROVIDER_ENV} (and {API_KEY_ENV}), or pass --model "
            "<provider>/<model>."
        )
    provider, _, model_name = (model or "openai/gpt-4o-mini").partition("/")

    # Cheap, decisive: is the environment able to answer at all? A lane that runs
    # against a dead front door measures the outage, not the agent.
    unhealthy = await preflight_bridge()
    if unhealthy:
        return None, unhealthy
    try:
        from ..deps import service  # noqa: PLC0415
        from ..schemas import ModelSettings  # noqa: PLC0415

        settings = ModelSettings(
            provider=provider, model=model_name or provider, base_url=base_url or None,
        )
        invoker = ServiceAgentInvoker(
            service, settings, allow_external_side_effects=False,
        )
    except Exception as exc:  # noqa: BLE001 - an unavailable provider is a reason
        return None, f"the live tier is unavailable: {type(exc).__name__}: {exc}"

    from ..persistence import AgentMemoryStore  # noqa: PLC0415

    from .store import EvaluationStore  # noqa: PLC0415

    store = AgentMemoryStore()
    try:
        dataset = load_all_builtin()
        tasks = select_tasks(dataset, suite=suite or None)
        # The live lane runs the PRODUCTION service; it cannot supply the
        # eval-only tools or synthetic environments the offline tier uses. A
        # tier-0 adversarial task would therefore measure a missing tool and
        # report 0.0 - which is exactly what the first live smoke did.
        tasks = [task for task in tasks if task.live_eligible]
        if task_limit:
            tasks = tasks[:task_limit]
        if not tasks:
            return None, "the live lane selected no tasks."
        runner = EvaluationRunner(
            store, invoker=invoker, eval_store=EvaluationStore(store),
        )
        result = await runner.run_suite(
            tasks, dataset_name=dataset.name, dataset_version=dataset.version,
            dataset_checksum=dataset.checksum, suite=suite, trials=trials,
            tier=1, persist=persist, metadata={"kind": "evaluation", "tier": "live"},
        )
        result.thresholds = check_thresholds(
            result.aggregates, sample_size=result.measured_trials,
        )
        return result, ""
    except Exception as exc:  # noqa: BLE001 - a failed lane is a reason, not a number
        return None, f"the live lane failed: {type(exc).__name__}: {exc}"
    finally:
        try:
            store.close()
        except Exception:  # noqa: BLE001
            pass


__all__ = [
    "API_KEY_ENV",
    "LOCAL_PROVIDERS",
    "PROVIDER_ENV",
    "provider_configured",
    "run_live_gate",
]
