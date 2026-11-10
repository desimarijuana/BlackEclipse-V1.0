"""Model card for a strategy version.

A model card is the human-readable evidence record: what the model does, what it
assumes, what was tested, what is unknown, and who owns it.
"""

from __future__ import annotations

from typing import Any

from .errors import QuantError
from .lifecycle import LifecycleService
from .store import QuantStore


def build_model_card(store: QuantStore, strategy_id: str,
                     version: str) -> dict[str, Any]:
    record = store.get_strategy(strategy_id, version)
    spec = record.get("spec") or {}
    lifecycle = LifecycleService(store).get(strategy_id, version)
    approvals = [a for a in store.list_approvals(strategy_id)
                 if str(a.get("version")) == str(version)]
    experiments = [e for e in store.list_experiments(strategy_id=strategy_id, limit=100)
                   if str(e.get("strategyVersion") or e.get("version") or "") == str(version)]
    paper_runs = store.list_paper_runs(strategy_id=strategy_id)
    metrics = {}
    for experiment in experiments:
        if experiment.get("metrics"):
            metrics = experiment["metrics"]
            break

    limitations = list(spec.get("limitations") or [])
    if not experiments:
        limitations.append("No completed backtest is recorded for this version.")
    if not paper_runs:
        limitations.append("No paper run is recorded for this strategy.")
    if not approvals:
        limitations.append("No approval review is recorded for this version.")
    limitations.append("Historical metrics are evidence, not a promise of future return.")

    card = {
        "schemaVersion": "1.0.0",
        "strategyId": strategy_id,
        "version": version,
        "name": record.get("name"),
        "lifecycle": lifecycle.get("state"),
        "universe": spec.get("universe") or {},
        "timeframes": spec.get("timeframes") or {},
        "objective": spec.get("objective") or spec.get("metadata", {}).get("objective"),
        "assumptions": spec.get("assumptions") or [],
        "limitations": limitations,
        "approvals": approvals,
        "experiments": [
            {"id": e.get("id"), "status": e.get("status"),
             "interval": e.get("interval"), "metrics": e.get("metrics")}
            for e in experiments[:10]
        ],
        "paperRuns": [
            {"id": p.get("id"), "status": p.get("status"),
             "createdAt": p.get("createdAt")}
            for p in paper_runs[:10]
        ],
        "latestMetrics": metrics,
        "owner": lifecycle.get("actor") or "operator",
        "review": {
            "state": lifecycle.get("state"),
            "updatedAt": lifecycle.get("updatedAt"),
            "evidence": lifecycle.get("evidence") or {},
        },
    }
    markdown = _render(card)
    card["markdown"] = markdown
    return card


def _render(card: dict[str, Any]) -> str:
    lines = [
        f"# Model card: {card['name']} (`{card['strategyId']}` v{card['version']})",
        "",
        f"**Lifecycle:** {card['lifecycle']}  ",
        f"**Owner:** {card['owner']}",
        "",
        "## Universe",
        "",
        f"```json\n{card['universe']}\n```",
        "",
        "## Objective",
        "",
        str(card.get("objective") or "Not stated."),
        "",
        "## Assumptions",
        "",
    ]
    lines.extend(f"- {a}" for a in card["assumptions"]) if card["assumptions"] else lines.append(
        "No assumptions are recorded."
    )
    lines.extend(["", "## Evidence", ""])
    if card["experiments"]:
        for exp in card["experiments"]:
            lines.append(f"- `{exp['id']}` · {exp['status']} · {exp['interval']}")
    else:
        lines.append("No experiment is recorded.")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in card["limitations"])
    lines.extend([
        "",
        "## Review",
        "",
        f"State: {card['review']['state']} · updated {card['review']['updatedAt']}",
        "",
        "A model card is evidence about the process, not a recommendation to trade.",
        "",
    ])
    return "\n".join(lines)


__all__ = ["build_model_card"]
