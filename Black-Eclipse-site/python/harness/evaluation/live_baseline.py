"""Pinned live-tier baselines and the published report.

The scripted corpus proves the harness path. Only the live tier measures a real
model, so only the live tier may be pinned as a model baseline. A baseline is
keyed by provider + model + base URL + temperature + prompt hash + corpus
checksum: a changed prompt or corpus is a different experiment, never a silent
update of the old number.

The baseline file carries no secrets (never an API key), and a report says which
tier produced it.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ..persistence import now_iso
from .ablation import ArmEvidence, arm_evidence
from .regression import detect_regressions
from .significance import paired_bootstrap

LIVE_BASELINE_VERSION = "1.0.0"
DEFAULT_LIVE_BASELINE = os.path.join(
    os.path.dirname(__file__), "baselines", "live_v1.json",
)


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def live_key(
    *,
    provider: str,
    model: str,
    base_url: str = "",
    temperature: Optional[float] = None,
    prompt_hash: str = "",
    dataset_checksum: str = "",
) -> str:
    """Stable identity for one live experiment."""
    raw = _canonical({
        "provider": str(provider or ""),
        "model": str(model or ""),
        "baseUrl": str(base_url or ""),
        "temperature": temperature,
        "promptHash": str(prompt_hash or ""),
        "datasetChecksum": str(dataset_checksum or ""),
    }).encode("utf-8")
    return "live:" + hashlib.sha256(raw).hexdigest()[:32]


def build_live_baseline(
    suite: Any,
    *,
    provider: str,
    model: str,
    tier: str,
    base_url: str = "",
    temperature: Optional[float] = None,
    prompt_hash: str = "",
    recorded_at: Optional[str] = None,
) -> dict[str, Any]:
    """Project a LIVE suite into a pinnable baseline entry."""
    if str(tier or "").strip().lower() != "live":
        raise ValueError(
            "a live baseline can only be built from the live tier; "
            "the scripted tier is not model evidence"
        )
    if not str(provider or "").strip() or not str(model or "").strip():
        raise ValueError("a live baseline requires an explicit provider and model")
    evidence: ArmEvidence = arm_evidence(suite, "live")
    key = live_key(
        provider=provider,
        model=model,
        base_url=base_url,
        temperature=temperature,
        prompt_hash=prompt_hash,
        dataset_checksum=getattr(suite, "dataset_checksum", ""),
    )
    return {
        "baselineVersion": LIVE_BASELINE_VERSION,
        "key": key,
        "recordedAt": recorded_at or now_iso(),
        "tier": "live",
        "provider": str(provider),
        "model": str(model),
        "baseUrl": str(base_url or "") or None,
        "temperature": temperature,
        "promptHash": str(prompt_hash or "") or None,
        "dataset": getattr(suite, "dataset_name", ""),
        "datasetVersion": getattr(suite, "dataset_version", ""),
        "datasetChecksum": getattr(suite, "dataset_checksum", ""),
        "taskCount": len(getattr(suite, "tasks", []) or []),
        "taskSuccess": evidence.task_success,
        "ci": [evidence.ci_low, evidence.ci_high],
        "successes": evidence.successes,
        "measuredTrials": evidence.measured_trials,
        "totalTrials": evidence.total_trials,
        "dimensions": evidence.dimensions,
        "categories": evidence.categories,
        "taskRates": evidence.task_rates,
        "costUsd": evidence.cost_usd,
        "latencyMs": evidence.latency_ms,
        "agentVersion": getattr(suite, "agent_version", None),
        "gitCommit": getattr(suite, "git_commit", None),
    }


def read_live_baselines(path: Optional[str] = None) -> dict[str, Any]:
    target = os.path.abspath(path or DEFAULT_LIVE_BASELINE)
    if not os.path.isfile(target):
        return {
            "baselineVersion": LIVE_BASELINE_VERSION,
            "updatedAt": None,
            "baselines": {},
        }
    with open(target, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or "baselines" not in payload:
        raise ValueError("a live baseline registry must contain a 'baselines' object")
    payload.setdefault("baselineVersion", LIVE_BASELINE_VERSION)
    payload.setdefault("updatedAt", None)
    return payload


def write_live_baseline(
    entry: Mapping[str, Any],
    *,
    path: Optional[str] = None,
) -> dict[str, Any]:
    """Merge one entry into the registry (identity is the entry key)."""
    target = os.path.abspath(path or DEFAULT_LIVE_BASELINE)
    registry = read_live_baselines(target)
    key = str(entry.get("key") or "")
    if not key:
        raise ValueError("a live baseline entry requires a key")
    registry["baselines"][key] = dict(entry)
    registry["updatedAt"] = now_iso()
    registry["baselineVersion"] = LIVE_BASELINE_VERSION
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return registry


def find_live_baseline(
    registry: Mapping[str, Any],
    *,
    provider: str,
    model: str,
    base_url: str = "",
    temperature: Optional[float] = None,
    prompt_hash: str = "",
    dataset_checksum: str = "",
) -> Optional[dict[str, Any]]:
    key = live_key(
        provider=provider,
        model=model,
        base_url=base_url,
        temperature=temperature,
        prompt_hash=prompt_hash,
        dataset_checksum=dataset_checksum,
    )
    baseline = (registry.get("baselines") or {}).get(key)
    return dict(baseline) if isinstance(baseline, Mapping) else None


def _current_metrics(evidence: ArmEvidence) -> dict[str, Any]:
    return {
        "aggregates": {
            **dict(evidence.dimensions),
            "task_success": evidence.task_success,
        },
        "categories": dict(evidence.categories),
        "passRate": evidence.task_success,
    }


def compare_live_baseline(
    baseline: Mapping[str, Any],
    suite: Any,
) -> dict[str, Any]:
    """Compare a live suite with its pinned baseline, per dimension."""
    current = arm_evidence(suite, "live")
    baseline_metrics = {
        "aggregates": {
            **dict(baseline.get("dimensions") or {}),
            "task_success": baseline.get("taskSuccess"),
        },
        "categories": dict(baseline.get("categories") or {}),
    }
    current_metrics = _current_metrics(current)
    comparison = detect_regressions(baseline_metrics, current_metrics)
    critical = [
        row for row in comparison.get("regressions") or []
        if row.get("severity") == "regression"
    ]
    paired = paired_bootstrap(
        dict(baseline.get("taskRates") or {}), current.task_rates,
    )
    delta = (
        None if current.task_success is None or baseline.get("taskSuccess") is None
        else round(current.task_success - float(baseline["taskSuccess"]), 6)
    )
    return {
        "ok": not critical,
        "delta": delta,
        "deltaCi": [paired["ciLow"], paired["ciHigh"]],
        "pValue": paired["pValue"],
        "pairedTasks": paired["pairedTasks"],
        "regressions": comparison.get("regressions") or [],
        "warnings": comparison.get("warnings") or [],
        "baseline": {
            "key": baseline.get("key"),
            "provider": baseline.get("provider"),
            "model": baseline.get("model"),
            "recordedAt": baseline.get("recordedAt"),
            "taskSuccess": baseline.get("taskSuccess"),
        },
        "current": {
            "taskSuccess": current.task_success,
            "ci": [current.ci_low, current.ci_high],
            "measuredTrials": current.measured_trials,
        },
    }


def publish_report(
    entry: Mapping[str, Any],
    *,
    comparison: Optional[Mapping[str, Any]] = None,
    path: Optional[str] = None,
) -> str:
    """Write the live-tier report as Markdown and return the path.

    The report always names the tier, provider, model, prompt hash and corpus
    checksum. A missing comparison is labelled NOT COMPARED, never PASS.
    """
    target = os.path.abspath(path or os.path.join("reports", "rsl-live-report.md"))
    if os.path.isdir(target) or target.endswith(os.sep):
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        target = os.path.join(target, f"rsl-report-{stamp}.md")
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)

    verdict = (
        "NOT COMPARED" if comparison is None
        else ("PASS" if comparison.get("ok") else "FAIL")
    )
    lines = [
        "# RSL live-tier report",
        "",
        f"- tier: **{entry.get('tier', 'live')}**",
        f"- provider/model: `{entry.get('provider')}` / `{entry.get('model')}`",
        f"- base URL: `{entry.get('baseUrl') or 'default'}` · "
        f"temperature: `{entry.get('temperature')}`",
        f"- dataset: `{entry.get('dataset')}` @ `{entry.get('datasetVersion')}` "
        f"({entry.get('taskCount')} tasks)",
        f"- dataset checksum: `{entry.get('datasetChecksum')}`",
        f"- prompt hash: `{entry.get('promptHash') or 'UNKNOWN'}`",
        f"- recorded: {entry.get('recordedAt')}",
        f"- verdict: **{verdict}**",
        "",
        "## Measures",
        "",
        "| measure | value |",
        "|---|---|",
    ]
    for key, value in sorted((entry.get("dimensions") or {}).items()):
        lines.append(f"| {key} | {'UNKNOWN' if value is None else value} |")
    lines.append(
        f"| task_success | {'UNKNOWN' if entry.get('taskSuccess') is None else entry.get('taskSuccess')} |"
    )
    ci = entry.get("ci") or [None, None]
    lines.append(
        f"| task_success 95% CI | "
        f"{'UNKNOWN' if ci[0] is None else f'{ci[0]}..{ci[1]}'} |"
    )
    lines += ["", "## Comparison", ""]
    if comparison is None:
        lines.append("- no pinned baseline for this identity; nothing to compare")
    else:
        delta = comparison.get("delta")
        delta_ci = comparison.get("deltaCi") or [None, None]
        lines.append(
            f"- delta: {'UNKNOWN' if delta is None else f'{delta:+.4f}'} "
            f"(paired CI {delta_ci[0]}..{delta_ci[1]}, "
            f"p={comparison.get('pValue')}, "
            f"tasks={comparison.get('pairedTasks')})"
        )
        regressions = comparison.get("regressions") or []
        lines.append(f"- regressions: {len(regressions)}")
        for row in regressions:
            lines.append(
                f"  - **{row.get('dimension')}**: {row.get('baseline')} → "
                f"{row.get('current')}"
            )
        warnings = comparison.get("warnings") or []
        lines.append(f"- warnings: {len(warnings)}")
        for row in warnings:
            lines.append(
                f"  - {row.get('dimension')}: {row.get('baseline')} → "
                f"{row.get('current')}"
            )
    lines += [
        "",
        "> The scripted tier is not represented here: it cannot measure a prompt "
        "change. This report is live-model evidence only.",
        "",
    ]
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return target


__all__ = [
    "DEFAULT_LIVE_BASELINE",
    "LIVE_BASELINE_VERSION",
    "build_live_baseline",
    "compare_live_baseline",
    "find_live_baseline",
    "live_key",
    "publish_report",
    "read_live_baselines",
    "write_live_baseline",
]
