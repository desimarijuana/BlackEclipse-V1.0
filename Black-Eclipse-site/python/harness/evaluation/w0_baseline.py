"""W0 baseline collector.

Reads an existing `agent-memory.db` **read-only** and emits a bounded,
provenance-carrying baseline artifact. It never writes the database, never
fabricates a missing metric, and never reads prompts or tool output bodies.

Usage:
    python -m harness.evaluation.w0_baseline --db path/to/agent-memory.db \\
        --out docs/harness/baselines/w0-<sha>-<date>.json

The Markdown companion is written next to the JSON with the same stem.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

from ..config import flags


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _metric(
    value: Any,
    *,
    unit: str,
    source: str,
    sample: int = 0,
    measured: Optional[bool] = None,
) -> dict[str, Any]:
    ok = (value is not None) if measured is None else bool(measured)
    return {
        "value": value if ok else None,
        "unit": unit,
        "sample": int(sample),
        "measured": bool(ok),
        "source": source,
    }


def percentile(values: Iterable[float], p: float) -> Optional[float]:
    """Nearest-rank percentile (same convention as quant metrics)."""
    ordered = sorted(float(v) for v in values if v is not None)
    if not ordered:
        return None
    p = min(1.0, max(0.0, float(p)))
    index = max(0, math.ceil(p * len(ordered)) - 1)
    return ordered[index]


def _epoch(stamp: Any) -> Optional[float]:
    if not stamp:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.timestamp()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(r["name"]) for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.DatabaseError:
        return set()


def _rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.DatabaseError:
        return []


def _read_only(path: str) -> sqlite3.Connection:
    # `mode=ro` fails closed on a missing file instead of creating an empty DB.
    uri = "file:" + str(Path(path).resolve()).replace("\\", "/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _runs(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "HarnessRun"):
        return {
            "total": _metric(None, unit="runs", source="HarnessRun", measured=False),
            "byStatus": _metric(None, unit="runs", source="HarnessRun", measured=False),
        }
    statuses = {
        str(r["status"]): int(r["c"])
        for r in _rows(conn, "SELECT status, COUNT(*) AS c FROM HarnessRun GROUP BY status")
    }
    total = sum(statuses.values())
    terminal = statuses.get("completed", 0) + statuses.get("failed", 0) + statuses.get("cancelled", 0)
    correctness = (statuses.get("completed", 0) / terminal) if terminal else None
    rows = _rows(
        conn,
        "SELECT status, startedAt, finishedAt, promptTokens, completionTokens, totalTokens "
        "FROM HarnessRun",
    )
    latencies = []
    for row in rows:
        start, end = _epoch(row.get("startedAt")), _epoch(row.get("finishedAt"))
        if start is not None and end is not None and end >= start:
            latencies.append((end - start) * 1000.0)
    prompt_tokens = [int(r.get("promptTokens") or 0) for r in rows]
    prompt_measured = any(value > 0 for value in prompt_tokens)
    return {
        "total": _metric(total, unit="runs", source="HarnessRun", sample=total),
        "byStatus": _metric(statuses, unit="runs", source="HarnessRun", sample=total),
        "terminalCorrectness": _metric(
            correctness, unit="ratio", source="HarnessRun", sample=terminal,
        ),
        "interrupted": _metric(
            statuses.get("interrupted"), unit="runs", source="HarnessRun",
            sample=total, measured="interrupted" in statuses,
        ),
        "latencyMs": _metric(
            {
                "p50": percentile(latencies, 0.50),
                "p95": percentile(latencies, 0.95),
                "p99": percentile(latencies, 0.99),
            },
            unit="ms", source="HarnessRun.startedAt/finishedAt", sample=len(latencies),
            measured=bool(latencies),
        ),
        "promptTokens": _metric(
            {
                "mean": (sum(prompt_tokens) / len(prompt_tokens)) if prompt_tokens else None,
                "p95": percentile(prompt_tokens, 0.95),
            },
            unit="tokens", source="HarnessRun.promptTokens", sample=len(prompt_tokens),
            measured=prompt_measured,
        ),
    }


def _events(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "HarnessEvent"):
        return {"counts": _metric(None, unit="events", source="HarnessEvent", measured=False)}
    counts = {
        str(r["type"]): int(r["c"])
        for r in _rows(conn, "SELECT type, COUNT(*) AS c FROM HarnessEvent GROUP BY type")
    }
    failed_codes: dict[str, int] = {}
    for row in _rows(conn, "SELECT data FROM HarnessEvent WHERE type='run.failed'"):
        try:
            data = json.loads(row.get("data") or "{}")
        except (TypeError, ValueError):
            continue
        code = str(((data or {}).get("error") or {}).get("code") or "")
        if code:
            failed_codes[code] = failed_codes.get(code, 0) + 1
    total = sum(counts.values())
    return {
        "counts": _metric(counts, unit="events", source="HarnessEvent", sample=total),
        "failedCodes": _metric(failed_codes, unit="events", source="HarnessEvent", sample=sum(failed_codes.values())),
        "runResumed": _metric(counts.get("run.resumed", 0), unit="events", source="HarnessEvent", sample=total),
        "contextOverflow": _metric(counts.get("context.overflow", 0), unit="events", source="HarnessEvent", sample=total),
        "contextRetry": _metric(counts.get("context.retry", 0), unit="events", source="HarnessEvent", sample=total),
        "historyBounded": _metric(counts.get("memory.history_bounded", 0), unit="events", source="HarnessEvent", sample=total),
        "runPartial": _metric(counts.get("run.partial", 0), unit="events", source="HarnessEvent", sample=total),
        "runFlags": _metric(counts.get("run.flags", 0), unit="events", source="HarnessEvent", sample=total),
    }


def _models(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "ModelRequest"):
        return {"attempts": _metric(None, unit="attempts", source="ModelRequest", measured=False)}
    rows = _rows(
        conn,
        "SELECT provider, model, fallback, success, retries, errorClass, "
        "inputTokens, outputTokens, totalTokens, latencyMs, ttftMs, costTotal, "
        "costEstimated FROM ModelRequest",
    )
    if not rows:
        return {"attempts": _metric(0, unit="attempts", source="ModelRequest", sample=0)}
    latencies = [float(r["latencyMs"] or 0) for r in rows if r.get("latencyMs") is not None]
    ttfts = [float(r["ttftMs"]) for r in rows if r.get("ttftMs") is not None]
    priced = [r for r in rows if r.get("costTotal") is not None]
    cost_values = [float(r["costTotal"]) for r in priced]
    errors: dict[str, int] = {}
    for row in rows:
        if row.get("errorClass"):
            errors[str(row["errorClass"])] = errors.get(str(row["errorClass"]), 0) + 1
    return {
        "attempts": _metric(len(rows), unit="attempts", source="ModelRequest", sample=len(rows)),
        "fallbacks": _metric(sum(1 for r in rows if int(r.get("fallback") or 0)), unit="attempts", source="ModelRequest", sample=len(rows)),
        "retries": _metric(sum(int(r.get("retries") or 0) for r in rows), unit="retries", source="ModelRequest", sample=len(rows)),
        "errorClasses": _metric(errors, unit="attempts", source="ModelRequest", sample=sum(errors.values())),
        "tokens": _metric(
            {
                "input": sum(int(r.get("inputTokens") or 0) for r in rows),
                "output": sum(int(r.get("outputTokens") or 0) for r in rows),
                "total": sum(int(r.get("totalTokens") or 0) for r in rows),
            },
            unit="tokens", source="ModelRequest", sample=len(rows),
        ),
        "latencyMs": _metric(
            {"p50": percentile(latencies, 0.50), "p95": percentile(latencies, 0.95)},
            unit="ms", source="ModelRequest.latencyMs", sample=len(latencies),
            measured=bool(latencies),
        ),
        "ttftMs": _metric(
            {"p50": percentile(ttfts, 0.50), "p95": percentile(ttfts, 0.95)},
            unit="ms", source="ModelRequest.ttftMs", sample=len(ttfts),
            measured=bool(ttfts),
        ),
        "cost": _metric(
            {
                "total": sum(cost_values) if priced else None,
                "pricedCoverage": (len(priced) / len(rows)) if rows else None,
                "estimated": sum(1 for r in priced if int(r.get("costEstimated") or 0)),
            },
            unit="usd", source="ModelRequest.costTotal", sample=len(rows),
            measured=bool(priced),
        ),
    }


def _tools(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "HarnessToolExecution"):
        return {"calls": _metric(None, unit="calls", source="HarnessToolExecution", measured=False)}
    rows = _rows(
        conn, "SELECT name, ok, durationMs, text FROM HarnessToolExecution"
    )
    if not rows:
        return {"calls": _metric(0, unit="calls", source="HarnessToolExecution", sample=0)}
    durations = [float(r["durationMs"] or 0) for r in rows]
    errors = sum(1 for r in rows if not int(r.get("ok") or 0))
    lengths = [len(str(r.get("text") or "")) for r in rows]
    return {
        "calls": _metric(len(rows), unit="calls", source="HarnessToolExecution", sample=len(rows)),
        "errorRate": _metric(errors / len(rows), unit="ratio", source="HarnessToolExecution", sample=len(rows)),
        "latencyMs": _metric(
            {"p50": percentile(durations, 0.50), "p95": percentile(durations, 0.95)},
            unit="ms", source="HarnessToolExecution.durationMs", sample=len(durations),
        ),
        "resultChars": _metric(
            {"mean": sum(lengths) / len(lengths), "p95": percentile(lengths, 0.95)},
            unit="chars", source="HarnessToolExecution.text", sample=len(lengths),
        ),
    }


def _effects(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "RunEffect"):
        return {"unknown": _metric(None, unit="effects", source="RunEffect", measured=False)}
    counts = {
        str(r["state"]): int(r["c"])
        for r in _rows(conn, "SELECT state, COUNT(*) AS c FROM RunEffect GROUP BY state")
    }
    total = sum(counts.values())
    return {
        "total": _metric(total, unit="effects", source="RunEffect", sample=total),
        "states": _metric(counts, unit="effects", source="RunEffect", sample=total),
        "unknown": _metric(counts.get("unknown", 0), unit="effects", source="RunEffect", sample=total),
        "started": _metric(counts.get("started", 0), unit="effects", source="RunEffect", sample=total),
    }


def _git_commit(cwd: Optional[str] = None) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except Exception:  # noqa: BLE001 - provenance must never fail the collector
        return "unknown"


def build_report(
    db_path: str,
    *,
    label: str = "w0-baseline",
    commit: str = "",
    generated_at: Optional[str] = None,
) -> dict[str, Any]:
    """Read `db_path` read-only and return a baseline report (no writes)."""
    conn = _read_only(db_path)
    try:
        runs = _runs(conn)
        events = _events(conn)
        models = _models(conn)
        tools = _tools(conn)
        effects = _effects(conn)
    finally:
        conn.close()

    report = {
        "version": 1,
        "label": label,
        "generatedAt": generated_at or _utc_now(),
        "provenance": {
            "commit": commit or _git_commit(),
            "dirty": None,
            "platform": os.name,
            "python": sys.version.split()[0],
            "flags": flags.snapshot(),
            "flagsHash": flags.snapshot_hash(),
        },
        "window": {
            "db": str(db_path),
            "source": "read-only-db",
        },
        "metrics": {
            "runs": runs,
            "events": events,
            "model": models,
            "tools": tools,
            "effects": effects,
            # Evaluation/gates are filled by the caller/CI; this collector never
            # infers a gate result from runtime data.
            "eval": {
                "offline": _metric(None, unit="verdict", source="not run by collector", measured=False),
                "live": _metric(None, unit="verdict", source="not run by collector", measured=False),
            },
        },
        "unmeasured": [],
        "notes": [
            "Read-only baseline. Missing tables/columns are measured=false, never zero.",
            "Run `node scripts/test-evals.js`, `npm run gate:slo`, `npm run audit:agent` "
            "and `node scripts/run-live-evals.js` separately to fill gate/eval results.",
        ],
    }
    for section in report["metrics"].values():
        for name, metric in section.items():
            if isinstance(metric, dict) and metric.get("measured") is False:
                report["unmeasured"].append({
                    "metric": name,
                    "reason": metric.get("source") or "not measured",
                })
    return report


def _fmt(metric: dict[str, Any]) -> str:
    if not metric.get("measured"):
        return "UNKNOWN"
    value = metric.get("value")
    if isinstance(value, dict):
        return ", ".join(f"{k}={_fmt({'value': v, 'measured': True})}" for k, v in value.items())
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def attach_gates(report: dict[str, Any], gates: dict[str, Any]) -> dict[str, Any]:
    """Attach externally-produced gate verdicts without inventing any.

    `gates` is the caller's record (offline/live/SLO/audit/conformance/tsc). It
    is copied verbatim so the baseline names the command that produced it.
    The offline/live verdicts also fill the `metrics.eval` placeholders.
    """
    report["gates"] = dict(gates or {})
    eval_metrics = report.setdefault("metrics", {}).setdefault("eval", {})
    for name in ("offline", "live"):
        gate = report["gates"].get(name)
        if not isinstance(gate, dict):
            continue
        eval_metrics[name] = _metric(
            gate.get("status", "UNKNOWN"),
            unit="verdict",
            source=str(gate.get("source") or "external gate"),
            sample=1,
            measured=True,
        )
    return report


def render_markdown(report: dict[str, Any]) -> str:
    prov = report.get("provenance") or {}
    lines = [
        "---",
        f"title: {report.get('label', 'w0-baseline')}",
        "status: Generated",
        f"last-verified: {report.get('generatedAt', '')}",
        "---",
        "",
        f"# {report.get('label', 'w0-baseline')}",
        "",
        f"- commit: `{prov.get('commit', 'unknown')}`",
        f"- generated: `{report.get('generatedAt', '')}`",
        f"- flagsHash: `{prov.get('flagsHash', '')}`",
        f"- source: `{(report.get('window') or {}).get('source', '')}`",
        "",
        "A metric that could not be measured is `UNKNOWN`, never `0`.",
        "",
    ]
    for section, metrics in (report.get("metrics") or {}).items():
        if not isinstance(metrics, dict):
            continue
        lines.extend([f"## {section}", "", "| metric | value | sample | source |", "|---|---|---:|---|"])
        for name, metric in metrics.items():
            if not isinstance(metric, dict):
                continue
            lines.append(
                f"| {name} | {_fmt(metric)} | {metric.get('sample', 0)} | {metric.get('source', '')} |"
            )
        lines.append("")
    unmeasured = report.get("unmeasured") or []
    if unmeasured:
        lines.extend(["## Unmeasured", ""])
        for item in unmeasured:
            lines.append(f"- `{item['metric']}` — {item['reason']}")
        lines.append("")
    gates = report.get("gates") or {}
    if gates:
        lines.extend(["## Gates", "", "| gate | status | detail |", "|---|---|---|"])
        for name, gate in gates.items():
            if isinstance(gate, dict):
                status = gate.get("status", "UNKNOWN")
                detail = gate.get("detail") or gate.get("reason") or gate.get("source") or ""
            else:
                status, detail = str(gate), ""
            lines.append(f"| {name} | {status} | {detail} |")
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Collect a read-only W0 baseline.")
    parser.add_argument("--db", required=True, help="agent-memory.db to read (read-only)")
    parser.add_argument("--out", required=True, help="JSON output path")
    parser.add_argument("--label", default="w0-baseline")
    parser.add_argument("--commit", default="")
    parser.add_argument("--gates", default="", help="JSON file of external gate verdicts")
    args = parser.parse_args(argv)

    if not Path(args.db).exists():
        print(f"[w0-baseline] database not found: {args.db}")
        return 2
    report = build_report(args.db, label=args.label, commit=args.commit)
    if args.gates:
        try:
            gates = json.loads(Path(args.gates).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"[w0-baseline] could not read --gates: {exc}")
            return 2
        attach_gates(report, gates)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    print(f"[w0-baseline] wrote {out} and {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
