"""Server-rendered SLO dashboard (C7).

One card per objective with its budget and burn rate, plus the run/latency/cost
and failure summaries the release gate reads. Self-contained HTML (no build step,
no third-party JS) so it works on an operator-gated box with nothing installed.

Every interpolated value is escaped. The page is read-only.
"""

from __future__ import annotations

import html
from typing import Any

_CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;padding:32px;background:#0b0d10;color:#e8eaed;
 font:14px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
h1{font-size:22px;font-weight:600;margin:0 0 4px}
.sub{color:#9aa0a6;margin:0 0 28px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.card{background:#14181d;border:1px solid #232a31;border-radius:14px;padding:18px}
.card h2{font-size:14px;margin:0 0 12px;color:#cfd4da;font-weight:600}
.ok{color:#6ee7a8}.bad{color:#ff8f8f}.muted{color:#8b929a}
.big{font-size:28px;font-weight:650;letter-spacing:-.02em}
.row{display:flex;justify-content:space-between;gap:12px;padding:4px 0;
 border-bottom:1px solid #1d2329;font-variant-numeric:tabular-nums}
.row:last-child{border-bottom:0}
.bar{height:6px;background:#1d2329;border-radius:99px;overflow:hidden;margin-top:10px}
.bar>span{display:block;height:100%;background:#6ee7a8}
.bar.warn>span{background:#f6c177}.bar.crit>span{background:#ff8f8f}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #1d2329;font-variant-numeric:tabular-nums}
th{color:#9aa0a6;font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
code{color:#c7d2fe}
.foot{margin-top:28px;color:#6b7280;font-size:12px}
"""


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _num(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return _e(value)


def _status(healthy: bool) -> str:
    return '<span class="ok">healthy</span>' if healthy else '<span class="bad">breaching</span>'


def _slo_card(slo: dict[str, Any]) -> str:
    remaining = slo.get("errorBudgetRemaining")
    health = bool(slo.get("healthy"))
    remaining_pct = 100.0 if remaining is None else max(0.0, min(1.0, float(remaining))) * 100.0
    bar_class = "" if remaining_pct > 50 else ("warn" if remaining_pct > 10 else "crit")
    kind = str(slo.get("kind") or "ratio")
    detail = ""
    if kind == "percentile":
        detail = (
            f'<div class="row"><span>p95</span><span>{_num(slo.get("p95"), 1, " " + str(slo.get("unit") or ""))}</span></div>'
            f'<div class="row"><span>threshold</span><span>{_num(slo.get("threshold"), 1, " " + str(slo.get("unit") or ""))}</span></div>'
        )
    elif kind == "rate":
        compliance_value = slo.get("compliance")
        failure_pct = None if compliance_value is None else (1.0 - float(compliance_value)) * 100.0
        detail = (
            f'<div class="row"><span>failure rate</span><span>{_num(failure_pct, 2, "%")}</span></div>'
            f'<div class="row"><span>max</span><span>{_num((slo.get("threshold") or 0) * 100, 2, "%")}</span></div>'
        )
    compliance = slo.get("compliance")
    return (
        '<div class="card">'
        f'<h2>{_e(slo.get("name"))}</h2>'
        f'<div class="big {("ok" if health else "bad")}">'
        f'{_status(health)}</div>'
        f'<div class="row"><span>compliance</span><span>{_num(None if compliance is None else float(compliance) * 100, 2, "%")}</span></div>'
        f'<div class="row"><span>samples</span><span>{_e(slo.get("total"))}</span></div>'
        f'{detail}'
        f'<div class="row"><span>error budget</span><span>{_num(remaining_pct, 1, "%")}</span></div>'
        f'<div class="row"><span>burn rate</span><span>{_num(slo.get("burnRate"), 2, "×")}</span></div>'
        f'<div class="bar {bar_class}"><span style="width:{remaining_pct:.1f}%"></span></div>'
        f'<div class="foot">{_e(slo.get("description") or "")}</div>'
        "</div>"
    )


def render_dashboard(report: dict[str, Any], *, refresh_s: int = 15) -> str:
    runs = report.get("runs") or {}
    latency = report.get("latency") or {}
    resume = report.get("resume") or {}
    cost = report.get("cost") or {}
    tools = report.get("tools") or {}
    failures = report.get("failures") or {}
    slos = (report.get("slos") or {})
    objectives = slos.get("objectives") or []

    cards = "".join(_slo_card(slo) for slo in objectives) or '<div class="card">No SLOs recorded yet.</div>'
    failure_rows = "".join(
        f"<tr><td>{_e(name)}</td><td>{_e(count)}</td></tr>" for name, count in failures.items()
    ) or '<tr><td colspan="2" class="muted">No failures recorded.</td></tr>'

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="{int(refresh_s)}">
<title>Eclipse observability — SLOs</title><style>{_CSS}</style></head>
<body>
<h1>Observability — SLOs that bite</h1>
<p class="sub">Live error budgets, latency, cost and failure classes. Operator-gated; refreshes every {int(refresh_s)}s.</p>
<div class="grid">
{cards}
<div class="card"><h2>Runs</h2>
<div class="row"><span>created</span><span>{_e(runs.get("created"))}</span></div>
<div class="row"><span>terminal</span><span>{_e(runs.get("terminal"))}</span></div>
<div class="row"><span>completed / failed / cancelled</span><span>{_e(runs.get("completed"))} / {_e(runs.get("failed"))} / {_e(runs.get("cancelled"))}</span></div>
<div class="row"><span>orphaned</span><span>{_e(runs.get("orphaned"))}</span></div>
<div class="row"><span>active now</span><span>{_e(runs.get("active"))}</span></div>
</div>
<div class="card"><h2>Latency</h2>
<div class="row"><span>samples</span><span>{_e(latency.get("samples"))}</span></div>
<div class="row"><span>p50</span><span>{_num(latency.get("p50"), 1, " ms")}</span></div>
<div class="row"><span>p95</span><span>{_num(latency.get("p95"), 1, " ms")}</span></div>
<div class="row"><span>p99</span><span>{_num(latency.get("p99"), 1, " ms")}</span></div>
<div class="row"><span>resume p95</span><span>{_num(resume.get("p95"), 1, " ms")}</span></div>
</div>
<div class="card"><h2>Cost</h2>
<div class="row"><span>tasks priced</span><span>{_e(cost.get("samples"))}</span></div>
<div class="row"><span>total</span><span>${_num(cost.get("totalUsd"), 4)}</span></div>
<div class="row"><span>p50 / p95 per task</span><span>${_num(cost.get("perTaskP50"), 4)} / ${_num(cost.get("perTaskP95"), 4)}</span></div>
<div class="row"><span>unpriced runs</span><span>{_e(cost.get("unpricedRuns"))}</span></div>
</div>
<div class="card"><h2>Tools</h2>
<div class="row"><span>calls</span><span>{_e(tools.get("calls"))}</span></div>
<div class="row"><span>errors</span><span>{_e(tools.get("errors"))}</span></div>
</div>
<div class="card"><h2>Failures by class</h2>
<table><thead><tr><th>class</th><th>count</th></tr></thead>
<tbody>{failure_rows}</tbody></table></div>
</div>
<p class="foot">Generated {_e(report.get("generatedAt"))} · report schema v1 · gate: <code>npm run gate:slo</code></p>
</body></html>"""


__all__ = ["render_dashboard"]
