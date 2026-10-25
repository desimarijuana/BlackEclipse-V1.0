"""Boot wiring for the graph runtime.

Best-effort and idempotent: a failure leaves ``service.graphs`` None (the
routes then report the runtime as unavailable) rather than breaking boot. The
service reuses the ONE `agent-memory.db` connection — it introduces no second
store and no second scheduler.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .service import GraphService
from .store import GraphRunStore

log = logging.getLogger("harness.graph_runtime")

_SINGLETON: Optional[GraphService] = None


def get_graph_service() -> Optional[GraphService]:
    """The process-wide graph service, or None before boot wired it."""
    return _SINGLETON


def set_graph_service(service: Optional[GraphService]) -> None:
    global _SINGLETON
    _SINGLETON = service


def install_graph_layer(service: Any) -> bool:
    try:
        store = GraphRunStore(service.store)
        graph_service = GraphService(store)
        if getattr(service, "fabric", None) is not None:
            graph_service.set_fabric(service.fabric)
        # Finance nodes read the runtime's persistent bar series (the SAME vault
        # the research-data tools fill) — no second ingestion path.
        from ..market.series_store import SeriesStore  # noqa: PLC0415

        from .datasets import GraphDatasetStore, set_dataset_store  # noqa: PLC0415
        from .finance_nodes import set_market_gateway, set_series_store  # noqa: PLC0415
        from .research_nodes import set_evidence_store  # noqa: PLC0415
        from .agent_nodes import set_agent_runner, set_plan_runner  # noqa: PLC0415
        from ..research.web_store import EvidenceStore  # noqa: PLC0415

        def _agent_runner(context, config, objective):
            """Run ONE bounded turn on the existing agent run plane."""
            import asyncio  # noqa: PLC0415
            import os  # noqa: PLC0415

            from ..agents import get_agent  # noqa: PLC0415
            from ..schemas import ModelSettings, RunInput, RunRequest  # noqa: PLC0415

            if not context.model_settings:
                raise ValueError(
                    "model settings are unavailable for this run; start it as an "
                    "operator run with a configured model provider"
                )
            try:
                base = get_agent(config["agent"])
            except KeyError as exc:
                raise ValueError(f"unknown agent {config['agent']!r}") from exc
            agent = base.model_copy(update={
                "maxSteps": max(1, min(int(config["maxSteps"]), base.maxSteps or 8)),
            })
            callback = context.callback_base_url or (
                os.environ.get("HARNESS_CALLBACK_URL")
                or f"http://127.0.0.1:{os.environ.get('PORT', '3000')}"
            )
            request = RunRequest(
                runId=f"graph:{context.run_id}:{context.node_id}",
                input=RunInput(query=objective),
                agent=agent,
                modelSettings=ModelSettings(**context.model_settings),
                userId=context.user_id,
                callbackBaseUrl=callback,
                callbackToken=context.callback_token or os.environ.get("CRON_SECRET"),
                analysisEnabled=False,
            )
            result = asyncio.run(service.run(request))
            status = getattr(result.status, "value", str(result.status))
            if status not in ("succeeded",):
                error = getattr(result, "error", None)
                message = getattr(error, "message", None) or getattr(result, "output", None) or status
                raise ValueError(f"agent run {status}: {message}")
            finding = {
                "text": result.output or "",
                "runId": result.runId,
                "status": status,
                "research": result.research,
                "tokens": result.totalTokens,
                "toolCalls": result.toolCalls,
            }
            return {"finding": finding, "evidence": result.research or {}}

        def _plan_runner(context, objective):
            """One bounded structured-plan model call; credentials stay in memory."""
            import asyncio  # noqa: PLC0415

            from .agent_plan import generate_step_plan  # noqa: PLC0415

            return asyncio.run(generate_step_plan(
                objective, model_settings=context.model_settings,
            ))

        set_agent_runner(_agent_runner)
        set_plan_runner(_plan_runner)
        set_series_store(SeriesStore(service.store))
        set_evidence_store(
            getattr(service, "evidence_store", None) or EvidenceStore(service.store)
        )
        gateway_factory = getattr(service, "server_market_gateway", None)
        if callable(gateway_factory):
            try:
                set_market_gateway(gateway_factory())
            except Exception:  # noqa: BLE001 - the gateway is optional
                set_market_gateway(None)
        dataset_store = GraphDatasetStore(service.store)
        dataset_store.purge_expired()
        set_dataset_store(dataset_store)
        service.graphs_datasets = dataset_store
        service.graphs_store = store
        service.graphs = graph_service
        set_graph_service(graph_service)
        # A run left `running` by the previous process can never finish.
        orphans = store.reconcile_orphans()
        if orphans:
            log.info("marked %d interrupted graph run(s) as failed", orphans)
        return True
    except Exception:  # noqa: BLE001 - never block boot
        log.warning("graph runtime unavailable", exc_info=True)
        service.graphs_store = None
        service.graphs = None
        set_graph_service(None)
        return False


__all__ = ["install_graph_layer", "get_graph_service", "set_graph_service"]
