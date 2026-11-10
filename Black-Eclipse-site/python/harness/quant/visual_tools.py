"""The agent surface of the deterministic Quant Figure Kit.

The builders live in `visuals.py`; this module exposes ONE tool that returns
compact chart blocks naming their source experiment. It lives outside
`tools.py` so the already-large tool registry does not grow another function.

The numbers never travel in a block: the browser resolves
`GET /quant/experiments/{id}/figures/{figure}` and draws the computed spec.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .errors import QuantError, StoreUnavailable
from .visuals import FIGURE_CATALOG, RESEARCH_FIGURES, build_figure, resolve_figures

ToolDefiner = Callable[..., None]


def _store(ctx: Any) -> Any:
    store = getattr(ctx, "quant_store", None)
    if store is None:
        raise StoreUnavailable(
            "the quant store is not configured; strategy/experiment persistence "
            "is unavailable in this runtime"
        )
    return store


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, QuantError):
        return (f"ERROR — {exc.code}: {exc.message}",
                {"status": "ERROR", "error": exc.to_dict()})
    return (f"ERROR — {type(exc).__name__}: {exc}",
            {"status": "ERROR", "error": {"message": str(exc)}})


async def render_quant_figures(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    """Return compact chart blocks for the deterministic Quant Figure Kit.

    A block NAMES its source experiment and figure; the numbers stay in the
    stored artifact. Nothing here carries a series, so a five-figure answer is
    still a short message.
    """
    try:
        experiment_id = str(args.get("experimentId") or "").strip()
        if not experiment_id:
            return ("ERROR - provide `experimentId` (a stored backtest experiment).",
                    {"status": "ERROR",
                     "error": {"code": "EXPERIMENT_ID_REQUIRED"}})
        store = _store(ctx)
        requested = resolve_figures(
            args.get("figures") or args.get("figureSet") or ("core",)
        )
        if not requested:
            return ("ERROR - no known figures were requested.",
                    {"status": "ERROR",
                     "error": {"code": "NO_FIGURES", "available": sorted(FIGURE_CATALOG)}})

        source_ids = {
            "monteCarloExperimentId": args.get("monteCarloExperimentId"),
            "optimizationExperimentId": args.get("optimizationExperimentId"),
            "walkForwardExperimentId": args.get("walkForwardExperimentId"),
        }
        theme = str(args.get("theme") or "eclipse-dark")
        blocks: list[dict[str, Any]] = []
        figures: list[dict[str, Any]] = []
        unavailable: list[dict[str, Any]] = []

        for name in requested:
            source_id = str(
                source_ids.get(RESEARCH_FIGURES.get(name, "")) or experiment_id
            )
            try:
                artifact = store.read_artifact(source_id)
            except Exception as exc:  # noqa: BLE001 - an absent source is a named absence
                entry = {"name": name, "available": False,
                         "reason": f"the source experiment {source_id!r} could not be read: {exc}"}
                figures.append(entry)
                unavailable.append(entry)
                continue

            figure = build_figure(name, artifact, theme=theme)
            entry = {"name": figure.name, "title": figure.title,
                     "available": figure.available, "reason": figure.reason,
                     "sourceExperimentId": source_id}
            figures.append(entry)
            if not figure.available:
                unavailable.append(entry)
                continue
            blocks.append({
                "type": "chart",
                "id": f"quant_{source_id}_{figure.name}"[:120],
                "chartType": "auto",
                "title": figure.title,
                "quant": {"experimentId": source_id, "figure": figure.name},
            })

        available = [f for f in figures if f["available"]]
        if not blocks:
            reasons = "; ".join(f"{item['name']}: {item['reason']}" for item in unavailable)
            return (f"No quant figure could be drawn from {experiment_id}: {reasons}",
                    {"status": "OK", "experimentId": experiment_id,
                     "figures": figures, "blocks": [], "unavailable": unavailable})
        # The model reads the TEXT, not `data`, so the compact blocks are part of
        # the text. They name their source and carry no series, so copying them
        # is cheap and cannot truncate a long curve.
        text = (f"{len(blocks)} figure(s) ready: "
                + ", ".join(f"{f['name']} ({f['sourceExperimentId']})" for f in available)
                + ". Put these objects in the answer's `eclipse-response` "
                + "`blocks` array verbatim; do not retype their data:\n"
                + json.dumps(blocks, separators=(",", ":")))
        return (text, {"status": "OK", "experimentId": experiment_id,
                       "figures": figures, "blocks": blocks,
                       "unavailable": unavailable})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def register_visual_tools(registry: Any, define: ToolDefiner) -> None:
    """Register the Quant Figure Kit tool through the caller's `define` seam."""
    define(
        "render_quant_figures",
        "Build deterministic quant figures (equity, drawdown, monthly returns, "
        "exposure, trade distribution, rolling risk, costs, Monte-Carlo, regime "
        "attribution, 3D parameter surface, walk-forward) as compact chart blocks "
        "that name their source experiment. Embed the returned `blocks` verbatim; "
        "never retype the series.",
        render_quant_figures, {"type": "object", "properties": {
            "experimentId": {"type": "string",
                             "description": "The stored backtest experiment."},
            "figures": {"type": "array", "items": {"type": "string"},
                        "description": "Figure names or presets: core, risk, robustness, "
                                       "validation, everything. Defaults to core."},
            "figureSet": {"type": "string",
                          "description": "Alias for a single preset (core/risk/robustness/"
                                         "validation/everything)."},
            "monteCarloExperimentId": {"type": "string",
                                       "description": "Monte-Carlo or regime-MC experiment."},
            "optimizationExperimentId": {"type": "string",
                                         "description": "Optimization experiment for the 3D surface."},
            "walkForwardExperimentId": {"type": "string",
                                        "description": "Walk-forward experiment."},
            "theme": {"type": "string", "enum": ["eclipse-dark", "eclipse-light"]}},
            "required": ["experimentId"]})


__all__ = ["register_visual_tools", "render_quant_figures"]
