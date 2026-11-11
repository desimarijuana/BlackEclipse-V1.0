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
            merge_bot_model_override,
            set_agent_runner,
            set_agent_task_runner,
            set_bot_resolver,
            set_plan_runner,
        )
        from .skill_nodes import set_skill_runner  # noqa: PLC0415
        from .agent_structured_nodes import set_structured_runner  # noqa: PLC0415
        from .memory_nodes import (  # noqa: PLC0415
            set_memory_forget_runner,
            set_memory_list_runner,
            set_memory_recall_runner,
            set_memory_remember_runner,
            set_memory_update_runner,
        )
        from .image_nodes import set_vision_asset_store, set_vision_runner  # noqa: PLC0415
        from .team_nodes import set_team_runner  # noqa: PLC0415
        from .output_nodes import set_notify_runner  # noqa: PLC0415
        from .approval_nodes import set_approval_runner  # noqa: PLC0415
        from ..agent_presets import (  # noqa: PLC0415
            AgentPresetStore,
            get_preset_store,
            set_preset_store,
        )
        from .video_nodes import set_video_runner  # noqa: PLC0415
        from .trade_learning_nodes import (  # noqa: PLC0415
            set_journal_loader,
            set_trade_learning_service,
        )
        from ..trade_learning.service import TradeLearningService  # noqa: PLC0415
        from ..trade_learning.store import TradeLearningStore  # noqa: PLC0415
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
                # The SAME projection a normal (non-graph) run uses, so a preset
                # cannot behave differently on the two surfaces.
                from ..agent_presets import agent_config_from_preset  # noqa: PLC0415

                base = agent_config_from_preset(preset)
            # Optional graph-level refinements. Instructions are appended to the
            # preset's system prompt; a tool allowlist can only NARROW the
            # preset's tools. Neither can grant a new capability.
            instructions = str(config.get("instructions") or "").strip()
            if instructions:
                base = base.model_copy(update={
                    "systemPrompt": (base.systemPrompt + "\n\n" + instructions)[:24_000],
                })
            requested_tools = config.get("tools")
            if isinstance(requested_tools, str):
                requested_tools = [part.strip() for part in requested_tools.split(",") if part.strip()]
            if isinstance(requested_tools, list) and requested_tools:
                if base.tools is not None:
                    unknown = [tool for tool in requested_tools if tool not in base.tools]
                    if unknown:
                        raise ValueError(
                            "tools not available to this agent: " + ", ".join(sorted(set(unknown)))
                        )
                base = base.model_copy(update={"tools": list(dict.fromkeys(requested_tools))})
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
                modelSettings=ModelSettings(**merge_bot_model_override(
                    context.model_settings, config.get("modelSettings"),
                )),
                userId=context.user_id,
                callbackBaseUrl=callback,
                callbackToken=context.callback_token or os.environ.get("CRON_SECRET"),
                analysisEnabled=False,
                resumeFrom=resume_from,
            )
            result = asyncio.run(service.run(request))
            return agent_result_payload(result)

        def _agent_task_runner(context, config, objective):
            """The n8n-style Agent node: memory read/write around one turn."""
            from .memory_nodes import resolve_scope  # noqa: PLC0415

            mode = str(config.get("memoryMode") or "read").strip().lower()
            scope = resolve_scope(config.get("memoryScope"), context)
            memory = getattr(service, "memory", None)
            memory_block = ""
            if mode in ("read", "read_write") and memory is not None:
                try:
                    recalled = memory.retrieve(
                        query=objective[:4_000],
                        scope=scope,
                        limit=int(config.get("memoryLimit", 8)),
                        run_id=context.run_id,
                    )
                    memory_block = str(getattr(recalled, "context", "") or "")
                except Exception:  # noqa: BLE001 - a memory read must not fail the turn
                    memory_block = ""
            composed = objective
            if memory_block:
                composed = (
                    f"{objective}\n\nMemory context (bounded; may be stale — verify "
                    f"before relying on it):\n{memory_block[:4_000]}"
                )
            payload = _agent_runner(context, config, composed)
            if mode in ("write", "read_write") and memory is not None:
                output = ""
                if isinstance(payload, dict):
                    finding = payload.get("finding")
                    if isinstance(finding, dict):
                        output = str(finding.get("text") or "")
                if output:
                    try:
                        memory.write_memory(
                            memory_type="summary",
                            content=output[:2_000],
                            source="manual",
                            scope=scope,
                            source_run_id=context.run_id,
                            importance=float(config.get("memoryImportance", 0.5)),
                            created_by=context.user_id,
                        )
                    except Exception as exc:  # noqa: BLE001 - the turn succeeded
                        context.emit(f"memory write skipped: {exc}")
            return payload

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
        set_agent_task_runner(_agent_task_runner)
        set_plan_runner(_plan_runner)

        def _skill_runner(context, config):
            """Run ONE skill through the EXISTING skill runtime (`execute_skill`).

            No second tool allowlist, permission check or version resolver: the
            node only decides WHICH skill@version and the inputs, and maps the
            result honestly.
            """
            import asyncio  # noqa: PLC0415
            import os  # noqa: PLC0415

            from ..schemas import ModelSettings  # noqa: PLC0415
            from ..skills.runtime import SkillExecutionRequest  # noqa: PLC0415

            if not context.model_settings:
                raise ValueError(
                    "model settings are unavailable for this run; start it as an "
                    "operator run with a configured model provider"
                )
            skill_id = str(config.get("skillId") or "")
            if context.test_run:
                # A skill's declared tools are the surface `execute_skill` will
                # bind. A test run may keep only read-only ones; refuse by name
                # rather than run a procedure with its tools silently removed.
                from ..agents import dry_run_tools  # noqa: PLC0415

                registry = getattr(service, "skill_registry", None)
                manifest = registry.manifest(skill_id) if registry is not None else None
                if manifest is not None:
                    required = list(getattr(manifest, "requiredTools", None) or [])
                    allowed = set(dry_run_tools(required))
                    missing = sorted(tool for tool in required if tool not in allowed)
                    if missing:
                        raise ValueError(
                            "a test run cannot execute this skill: it requires "
                            + ", ".join(missing)
                            + " (only read-only tools run without an operator grant)"
                        )
            callback = context.callback_base_url or (
                os.environ.get("HARNESS_CALLBACK_URL")
                or f"http://127.0.0.1:{os.environ.get('PORT', '3000')}"
            )
            request = SkillExecutionRequest(
                skillId=skill_id,
                version=config.get("version"),
                input=dict(config.get("input") or {}),
                # One stable id per graph node, so a re-executed node links to the
                # same parent trace instead of inventing a second lineage.
                runId=f"graph:{context.run_id}:{context.node_id}",
                parentRunId=f"graph:{context.run_id}",
                executionMode="workflow",
                userId=context.user_id,
                operator=context.operator,
                timeoutMs=config.get("timeoutMs"),
                modelSettings=ModelSettings(**context.model_settings),
                callbackBaseUrl=callback,
                callbackToken=context.callback_token or os.environ.get("CRON_SECRET"),
            )
            result = asyncio.run(service.run_skill(request))
            return result.model_dump() if hasattr(result, "model_dump") else dict(result)

        set_skill_runner(_skill_runner)

        def _structured_runner(context, op, args):
            """ONE bounded structured model call — no tools, no agent loop."""
            import asyncio  # noqa: PLC0415

            from . import agent_structured  # noqa: PLC0415

            if not context.model_settings:
                raise ValueError(
                    "model settings are unavailable for this run; start it as an "
                    "operator run with a configured model provider"
                )
            operations = {
                "classify": agent_structured.classify_json,
                "extract": agent_structured.extract_json,
                "summarize": agent_structured.summarize_json,
                "critique": agent_structured.critique_json,
            }
            function = operations.get(op)
            if function is None:
                raise ValueError(f"unknown structured operation {op!r}")
            return asyncio.run(
                function(**args, model_settings=context.model_settings)
            )

        set_structured_runner(_structured_runner)

        def _memory_recall_runner(context, args):
            """Read the ONE memory service (policy + dedupe + recall-deny)."""
            memory = getattr(service, "memory", None)
            if memory is None:
                raise ValueError("the memory service is unavailable in this runtime")
            result = memory.retrieve(
                query=args["query"],
                memory_types=args["types"] or None,
                scope=args["scope"],
                limit=args["limit"],
                run_id=context.run_id,
            )
            return {
                "memories": list(getattr(result, "memories", None) or []),
                "context": str(getattr(result, "context", "") or ""),
            }

        def _memory_remember_runner(context, args):
            """Write one durable memory through the service (never re-implemented)."""
            memory = getattr(service, "memory", None)
            if memory is None:
                raise ValueError("the memory service is unavailable in this runtime")
            record = memory.write_memory(
                memory_type=args["memoryType"],
                content=args["content"],
                source="manual",
                scope=args["scope"],
                subject=args["subject"],
                source_run_id=context.run_id,
                importance=args["importance"],
                created_by=context.user_id,
            )
            keep = (
                "id", "memoryType", "memory_type", "scope", "scopeId",
                "status", "verification", "createdAt",
            )
            return {"memory": {key: record.get(key) for key in keep if key in record}}

        def _memory_list_runner(context, args):
            memory = getattr(service, "memory", None)
            if memory is None:
                raise ValueError("the memory service is unavailable in this runtime")
            rows = memory.list_memories(
                memory_type=args.get("memoryType") or None,
                scope=args.get("scope") or None,
                status=args.get("status") or None,
                subject=args.get("subject") or None,
                limit=int(args.get("limit", 50)),
                include_inactive=bool(args.get("includeInactive", True)),
            )
            return {"memories": rows}

        def _memory_update_runner(context, args):
            memory = getattr(service, "memory", None)
            if memory is None:
                raise ValueError("the memory service is unavailable in this runtime")
            record = memory.update_memory(
                args["memoryId"], content=args.get("content"),
                subject=args.get("subject"), importance=args.get("importance"),
            )
            return {"memory": record}

        def _memory_forget_runner(context, args):
            memory = getattr(service, "memory", None)
            if memory is None:
                raise ValueError("the memory service is unavailable in this runtime")
            record = memory.archive_memory(args["memoryId"], reason=args.get("reason"))
            return {"memory": record}

        set_memory_recall_runner(_memory_recall_runner)
        set_memory_remember_runner(_memory_remember_runner)
        set_memory_list_runner(_memory_list_runner)
        set_memory_update_runner(_memory_update_runner)
        set_memory_forget_runner(_memory_forget_runner)

        def _vision_runner(context, request):
            """Read one stored image through the ONE vision engine."""
            import asyncio  # noqa: PLC0415

            from ..schemas import ModelSettings  # noqa: PLC0415
            from ..vision.contracts import Region, VisionInput  # noqa: PLC0415
            from ..vision.orchestrator import VisionContext, orchestrate  # noqa: PLC0415

            store = getattr(service, "vision_assets", None)
            if store is None:
                raise ValueError("the vision asset store is unavailable in this runtime")
            asset_id = str(request.get("assetId") or "")
            owner = str(context.user_id or "local")[:120]
            asset = store.get(asset_id, owner=owner)
            if asset is None:
                raise ValueError(f"image {asset_id!r} does not exist")
            data = store.open_bytes(asset_id, owner=owner)
            if not data:
                raise ValueError(f"image {asset_id!r} has no bytes")
            settings = context.model_settings
            if isinstance(settings, dict):
                settings = ModelSettings(**settings)
            if settings is None:
                raise ValueError(
                    "model settings are unavailable for this run; start it as an "
                    "operator run with a configured model provider"
                )
            region = None
            raw_region = request.get("region")
            if isinstance(raw_region, (list, tuple)) and len(raw_region) == 4:
                try:
                    region = Region(*(int(value) for value in raw_region))
                except (TypeError, ValueError):
                    region = None
            options = dict(request.get("options") or {})
            options.setdefault("sourceAssetId", asset_id)
            vision_input = VisionInput(
                source=data,
                source_kind="bytes",
                question=str(request.get("question") or ""),
                mode=str(request.get("mode") or "analyze"),
                region=region,
                options=options,
                model_settings=settings,
                provenance={"source": "graph-asset", "assetId": asset_id},
            )
            vision_ctx = VisionContext(
                run_settings=settings,
                asset_store=store,
                run_id=context.run_id,
                user_id=context.user_id,
            )
            result = asyncio.run(orchestrate(vision_input, vision_ctx))
            if not result.ok:
                error = result.error or {}
                raise ValueError(str(error.get("message") or "vision request failed"))
            return result.to_dict()

        set_vision_runner(_vision_runner)
        set_vision_asset_store(getattr(service, "vision_assets", None))

        def _team_runner(context, args):
            """Run the committee through the EXISTING team runtime."""
            import asyncio  # noqa: PLC0415

            from ..institution.preset import build_team  # noqa: PLC0415

            if not context.model_settings:
                raise ValueError(
                    "model settings are unavailable for this run; start it as an "
                    "operator run with a configured model provider"
                )
            team_service = getattr(service, "team", None)
            if team_service is None:
                from ..team.bootstrap import install_team_layer  # noqa: PLC0415

                try:
                    install_team_layer(service)
                except Exception as exc:  # noqa: BLE001 - reported honestly below
                    raise ValueError(f"the team runtime is unavailable: {exc}") from exc
                team_service = getattr(service, "team", None)
            if team_service is None:
                raise ValueError("the team runtime is unavailable")

            team = build_team(
                args["objective"],
                universe=args["universe"],
                horizon=args["horizon"],
                constraints=[],
            )

            async def _go():
                run = await team_service.run(
                    team, model_settings=context.model_settings,
                )
                try:
                    await team_service.wait(run.id, timeout_s=float(args["timeoutS"]))
                except Exception:  # noqa: BLE001 - finalize reports the real state
                    pass
                final = await team_service.finalize(run.id)
                synthesis = team_service.synthesize(run.id)
                return run, final, synthesis

            run, final, synthesis = asyncio.run(_go())
            return {
                "status": str(final.get("status") or ""),
                "teamRunId": run.id,
                "decision": final,
                "synthesis": synthesis,
                "error": None
                if str(final.get("status") or "") in ("COMPLETED", "PARTIAL")
                else f"team finished with status {final.get('status') or 'unknown'}",
            }

        set_team_runner(_team_runner)

        def _notify_runner(context, args):
            """Send through the ONE channel service (`send_outbound`)."""
            import asyncio  # noqa: PLC0415

            channels = getattr(service, "channels", None)
            if channels is None:
                from ..channels.bootstrap import install_channel_layer  # noqa: PLC0415

                try:
                    channels = install_channel_layer(service)
                except Exception as exc:  # noqa: BLE001
                    raise ValueError(f"the channel service is unavailable: {exc}") from exc
            if channels is None:
                raise ValueError("the channel service is unavailable")
            return asyncio.run(
                channels.send_outbound(
                    args["channel"], args["destination"], args["message"],
                )
            )

        set_notify_runner(_notify_runner)

        def _approval_runner(context, args):
            """Read/create ONE `graph_approval` in the single-use approval store.

            The decision is not consumed: it gates this run+node, so a resumed
            run reads the same answer instead of asking again.
            """
            store = getattr(service, "approvals", None)
            if store is None:
                raise ValueError("the approval store is unavailable in this runtime")

            def view(record):
                keep = (
                    "id", "status", "decidedBy", "decidedAt", "reason",
                    "expiresAt", "risk", "actionSummary",
                )
                return {key: record.get(key) for key in keep if key in record}

            existing = store.find_active_kind(
                kind="graph_approval",
                request_key=args["requestKey"],
                digest=args["digest"],
            )
            if existing is not None:
                return {"status": "approved", "approval": view(existing)}
            record = store.request_kind(
                kind="graph_approval",
                request_key=args["requestKey"],
                digest=args["digest"],
                effect="external_action",
                run_id=context.run_id,
                action_summary=args["title"],
                affected_data=args["message"] or None,
                risk=args["risk"],
                ttl_seconds=args["ttlHours"] * 3600,
                grant_scope="graph",
            )
            status = str((record or {}).get("status") or "").strip().lower()
            mapped = status if status in ("approved", "denied") else "pending"
            return {"status": mapped, "approval": view(record or {})}

        set_approval_runner(_approval_runner)

        def _bot_resolver(bot_id):
            """Read one saved bot from the EXISTING automation store.

            A bot is an `Automation` tagged `bot`/`monitor` (or an `mon_` id) —
            the same rule the Bots workspace uses. Reading is all this does: it
            never dispatches the automation or touches its schedule.
            """
            store = service.automation_store()
            definition = store.get_automation(bot_id)
            if definition is None:
                return None
            tags = list(getattr(definition, "tags", None) or [])
            action = definition.action
            return {
                "id": definition.id,
                "name": definition.name,
                "isBot": (
                    "bot" in tags
                    or "monitor" in tags
                    or str(definition.id).startswith("mon_")
                ),
                "kind": "workflow" if action.type == "execute_workflow" else "agent",
                "agentId": action.agent_id or "eclipse-agent",
                "objective": action.objective or definition.description or "",
                # The bot's own model pin (same shape the dispatcher reads).
                "modelSettings": (
                    action.config.get("modelSettings")
                    if isinstance(action.config.get("modelSettings"), dict)
                    else None
                ),
            }

        set_bot_resolver(_bot_resolver)
        set_paper_store(PaperAccountStore(service.store))

        # Typed decisions: the graph nodes reuse the ONE decision service built
        # at boot (provider registry + confidence policy + audit store on the
        # SAME agent-memory connection). Absent, the nodes report an honest
        # "unavailable"-style error rather than guessing.
        from .decision_nodes import set_decision_service  # noqa: PLC0415

        set_decision_service(getattr(service, "decision", None))

        # Trade learning: findings + playbook versions on the SAME agent-memory
        # connection. The journal itself stays in JDDS and is read through the
        # authenticated, read-only bridge — never written from here.
        # Isolated: a learning-store failure must not take the graph runtime down.
        try:
            learning_store = TradeLearningStore(service.store)
            learning_service = TradeLearningService(learning_store, service.store)
            set_trade_learning_service(learning_service)
            service.trade_learning = learning_service

            def _journal_loader(context, params):
                import asyncio  # noqa: PLC0415

                bridge_getter = getattr(service, "server_bridge", None)
                if not callable(bridge_getter):
                    raise ValueError("the journal data bridge is unavailable")
                return asyncio.run(bridge_getter().fetch("journal_trades", params))

            set_journal_loader(_journal_loader)
        except Exception:  # noqa: BLE001 - optional capability, never a boot blocker
            log.warning("trade learning unavailable", exc_info=True)
            service.trade_learning = None
            set_trade_learning_service(None)
            set_journal_loader(None)

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
        # Uploaded files are local scratch on the SAME connection; the store is
        # bounded and never a market-data source.
        from .assets import GraphAssetStore, set_asset_store  # noqa: PLC0415

        asset_store = GraphAssetStore(service.store)
        asset_store.purge_expired()
        set_asset_store(asset_store)
        service.graphs_assets = asset_store
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
