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
        from .paper_store import PaperAccountStore  # noqa: PLC0415
        from .research_nodes import set_evidence_store  # noqa: PLC0415
        from .trading_nodes import set_paper_store  # noqa: PLC0415
        from .agent_nodes import (  # noqa: PLC0415
            agent_result_payload,
            agent_run_identity,
            set_agent_runner,
            set_plan_runner,
        )
        from ..agent_presets import (  # noqa: PLC0415
            AgentPresetStore,
            get_preset_store,
            set_preset_store,
        )
        from .video_nodes import set_video_runner  # noqa: PLC0415
        from ..research.web_store import EvidenceStore  # noqa: PLC0415

        def _agent_runner(context, config, objective):
            """Run ONE bounded turn on the existing agent run plane."""
            import asyncio  # noqa: PLC0415
            import os  # noqa: PLC0415

            from ..agents import get_agent  # noqa: PLC0415
            from ..schemas import AgentConfig, ModelSettings, RunInput, RunRequest  # noqa: PLC0415

            if not context.model_settings:
                raise ValueError(
                    "model settings are unavailable for this run; start it as an "
                    "operator run with a configured model provider"
                )
            agent_id = str(config.get("agent") or "eclipse-agent")
            try:
                base = get_agent(agent_id)
            except (KeyError, ValueError):
                # A user-authored preset. The node may pin a version; absent one
                # resolves the preset's current version (backward compatible).
                presets = get_preset_store()
                pinned = config.get("agentVersion")
                try:
                    version = int(pinned) if pinned else None
                except (TypeError, ValueError):
                    version = None
                preset = presets.get(agent_id, version) if presets is not None else None
                if preset is None:
                    raise ValueError(f"unknown agent {agent_id!r}") from None
                base = AgentConfig(
                    id=preset["id"],
                    name=preset["name"],
                    systemPrompt=preset["systemPrompt"],
                    tools=list(preset.get("tools") or []),
                    maxSteps=int(preset.get("maxSteps") or 8),
                    allowMcpTools=bool(preset.get("allowMcpTools")),
                    allowPluginTools=bool(preset.get("allowPluginTools")),
                )
            if context.test_run or not context.allow_network:
                # A test/dry run may call the model but must not reach the
                # world. Narrow the declared allowlist DOWN to the read-only
                # finance surface; this can only remove tools.
                from ..agents import dry_run_tools  # noqa: PLC0415

                tools = dry_run_tools(base.tools)
                base = base.model_copy(update={"tools": tools})
                context.emit(f"dry run: {len(tools)} read-only tool(s) bound")

            agent = base.model_copy(update={
                "maxSteps": max(1, min(int(config["maxSteps"]), base.maxSteps or 8)),
            })
            callback = context.callback_base_url or (
                os.environ.get("HARNESS_CALLBACK_URL")
                or f"http://127.0.0.1:{os.environ.get('PORT', '3000')}"
            )
            # Re-enter the same agent run when a durable checkpoint exists, so a
            # graph resumed after a restart continues the turn instead of
            # replaying it. Without a checkpoint the turn restarts under a fresh
            # id (a model call has no world effect, so replay is safe here).
            agent_run_id, resume_from = agent_run_identity(
                service.store, f"graph:{context.run_id}:{context.node_id}",
            )
            request = RunRequest(
                runId=agent_run_id,
                input=RunInput(query=objective),
                agent=agent,
                modelSettings=ModelSettings(**context.model_settings),
                userId=context.user_id,
                callbackBaseUrl=callback,
                callbackToken=context.callback_token or os.environ.get("CRON_SECRET"),
                analysisEnabled=False,
                resumeFrom=resume_from,
            )
            result = asyncio.run(service.run(request))
            return agent_result_payload(result)

        def _plan_runner(context, objective):
            """One bounded structured-plan model call; credentials stay in memory."""
            import asyncio  # noqa: PLC0415

            from .agent_plan import generate_step_plan  # noqa: PLC0415

            return asyncio.run(generate_step_plan(
                objective, model_settings=context.model_settings,
            ))

        preset_store = AgentPresetStore(service.store, service.registry)
        service.agent_presets = preset_store
        set_preset_store(preset_store)

        set_agent_runner(_agent_runner)
        set_plan_runner(_plan_runner)
        set_paper_store(PaperAccountStore(service.store))

        def _video_runner(context, symbols, title, mode):
            """Build a recap storyboard and run the EXISTING video pipeline."""
            import asyncio  # noqa: PLC0415
            import uuid  # noqa: PLC0415

            from ..video.recaps import create_recap_project  # noqa: PLC0415

            video = getattr(service, "video", None)
            if video is None:
                raise ValueError(
                    "the video pipeline is unavailable; enable it and install the "
                    "fframes worker"
                )
            project = create_recap_project(video, symbols=symbols, title=title)
            job = asyncio.run(video.run_render_job({
                "projectId": project["id"],
                "jobId": f"graph_{uuid.uuid4().hex[:12]}",
                "mode": mode,
            }))
            return {"project": project, "job": job}

        set_video_runner(_video_runner)
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
