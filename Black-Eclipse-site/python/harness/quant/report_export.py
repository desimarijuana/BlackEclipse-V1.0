"""Export a research result as a self-contained HTML report or a notebook.

The export is a *record*, not a new computation. It reads the stored experiment,
its artifact and its run manifest and writes exactly those numbers, with the
assumptions, warnings, data fingerprint and the not-advice note attached.

No template engine, no JS dependency: one HTML file that opens anywhere, and a
notebook that a user can replay against the local runtime.
"""

from __future__ import annotations

import html
import json
import os
from typing import Any, Optional

from .errors import ExperimentNotFound, QuantError


def _export_root() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    return os.path.join(root, ".black-eclipse", "quant", "exports")


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _metric_rows(metrics: dict[str, Any]) -> str:
    rows = []
    for key in sorted(metrics):
        value = metrics[key]
        rows.append(
            f"<tr><th>{html.escape(key)}</th><td>{html.escape(_fmt(value))}</td></tr>"
        )
    return "\n".join(rows)


def render_experiment_html(experiment: dict[str, Any], artifact: dict[str, Any],
                           manifest: Optional[dict[str, Any]] = None) -> str:
    exp_id = experiment.get("id", "experiment")
    metrics = experiment.get("metrics") or artifact.get("metrics") or {}
    warnings = experiment.get("warnings") or artifact.get("warnings") or []
    cfg = artifact.get("configuration") or experiment.get("configuration") or {}
    data = (manifest or {}).get("data") or {}
    digest = (manifest or {}).get("digest") or "unavailable"
    symbols = ", ".join(data.get("symbols") or experiment.get("symbols") or [])
    strategies = ", ".join(
        f"{s.get('id')}@{s.get('version')}" for s in (manifest or {}).get("strategies") or []
    ) or f"{experiment.get('strategyId')}@{experiment.get('strategyVersion')}"
    warning_html = "".join(
        f"<li><code>{html.escape(str(w.get('code')))}</code> — {html.escape(str(w.get('message')))}</li>"
        for w in warnings
    ) or "<li>None reported.</li>"
    carry = (cfg.get("carry") or {})
    execution = cfg.get("execution") or {}
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Eclipse research report — {html.escape(exp_id)}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; background:#0a0a0b; color:#e8e8ea;
         font:14px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }}
  .wrap {{ max-width:900px; margin:0 auto; padding:40px 24px 80px; }}
  h1 {{ font-size:26px; margin:0 0 4px; }} h2 {{ font-size:16px; margin:28px 0 10px;
       color:#c9c9cf; letter-spacing:.01em; }}
  .sub {{ color:#8b8b93; font-size:12px; }}
  .card {{ border:1px solid rgba(255,255,255,.08); border-radius:14px;
           background:rgba(255,255,255,.025); padding:16px 18px; margin:14px 0; }}
  table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }}
  th,td {{ text-align:left; padding:6px 8px; border-bottom:1px solid rgba(255,255,255,.06); }}
  th {{ color:#9a9aa3; font-weight:500; }}
  code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }}
  ul {{ margin:6px 0 0 18px; padding:0; }}
  .note {{ color:#9a9aa3; font-size:12px; }}
</style></head><body><div class="wrap">
  <h1>Eclipse research report</h1>
  <p class="sub">Experiment <code>{html.escape(exp_id)}</code> · {html.escape(str(experiment.get('kind')))} ·
     {html.escape(str(experiment.get('createdAt') or ''))}</p>

  <div class="card">
    <h2>Identity</h2>
    <p>Strategy: <strong>{html.escape(strategies)}</strong><br>
       Symbols: {html.escape(symbols or '—')} · Interval:
       {html.escape(str(experiment.get('interval') or cfg.get('interval') or '—'))}<br>
       Window: {html.escape(str(experiment.get('start') or cfg.get('start') or '—'))} →
       {html.escape(str(experiment.get('end') or cfg.get('end') or '—'))}</p>
  </div>

  <div class="card">
    <h2>Metrics</h2>
    <table>{_metric_rows(metrics)}</table>
    <p class="note">Every value was computed by the deterministic Eclipse engine and
       read from the stored artifact.</p>
  </div>

  <div class="card">
    <h2>Assumptions</h2>
    <p>Execution: <code>{html.escape(json.dumps(execution, sort_keys=True))}</code></p>
    <p>Carry: financing {html.escape(_fmt(carry.get('financing')))}, borrow
       {html.escape(_fmt(carry.get('borrow')))}, locate fees
       {html.escape(_fmt(carry.get('locateFees')))}, dividends
       {html.escape(_fmt(carry.get('dividends')))}.</p>
  </div>

  <div class="card">
    <h2>Warnings ({len(warnings)})</h2>
    <ul>{warning_html}</ul>
  </div>

  <div class="card">
    <h2>Reproducibility</h2>
    <p>Manifest digest: <code>{html.escape(str(digest))}</code><br>
       Engine: {html.escape(str((manifest or {}).get('engineVersion') or '—'))}<br>
       Data fingerprint: <code>{html.escape(json.dumps(data.get('series') or {}, sort_keys=True))}</code></p>
  </div>

  <p class="note">Research output, not investment advice. A backtest is evidence about
     the past under stated assumptions; it is not a forecast or a guarantee. Paper
     deployments place no orders. Verify any data or method against its source.</p>
</div></body></html>
"""


def render_notebook(experiment: dict[str, Any], artifact: dict[str, Any],
                    manifest: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    exp_id = experiment.get("id", "experiment")
    metrics = experiment.get("metrics") or artifact.get("metrics") or {}
    cells = [
        _md(f"# Eclipse research notebook — `{exp_id}`\n\n"
            f"Strategy `{experiment.get('strategyId')}@{experiment.get('strategyVersion')}`, "
            f"kind `{experiment.get('kind')}`.\n\n"
            "This notebook is a record of a stored experiment. It does not re-run "
            "or invent values by itself."),
        _code("import json\n"
              f"experiment_id = {exp_id!r}\n"
              "# Load the artifact from the local runtime (adjust the path if needed)\n"
              "artifact = json.load(open('artifact.json', encoding='utf-8'))\n"
              "metrics = artifact.get('metrics', {})\n"
              "metrics"),
        _md("## Metrics\n" + "\n".join(
            f"- **{k}**: {_fmt(v)}" for k, v in sorted(metrics.items())
        )),
        _md("## Warnings\n" + ("\n".join(
            f"- `{w.get('code')}` — {w.get('message')}" for w in
            (experiment.get('warnings') or [])) or "None reported.")),
        _md("## Reproducibility\n"
            f"- Manifest digest: `{(manifest or {}).get('digest')}`\n"
            f"- Engine: `{(manifest or {}).get('engineVersion')}`\n"
            "- Re-run with `reproduce_experiment` and compare metrics."),
        _md("## Disclaimer\nResearch output, not investment advice. Backtests are "
            "evidence about the past under stated assumptions."),
    ]
    return {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"},
                     "language_info": {"name": "python"}},
        "cells": cells,
    }


def _md(source: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": source.splitlines(True)}


def _code(source: str) -> dict[str, Any]:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": source.splitlines(True)}


def export_experiment(store: Any, experiment_id: str, *,
                      fmt: str = "html") -> dict[str, Any]:
    """Write an export and return its path, content type and body."""
    if fmt not in ("html", "notebook", "ipynb"):
        raise QuantError(f"unsupported export format {fmt!r}",
                         detail={"formats": ["html", "notebook"]})
    try:
        experiment = store.get_experiment(experiment_id)
        artifact = store.read_artifact(experiment_id)
    except ExperimentNotFound:
        raise
    try:
        manifest = store.get_run_manifest(experiment_id)
    except Exception:  # noqa: BLE001 - an old experiment may predate manifests
        manifest = None
    os.makedirs(_export_root(), exist_ok=True)
    if fmt == "html":
        body = render_experiment_html(experiment, artifact, manifest)
        path = os.path.join(_export_root(), f"{experiment_id}.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        return {"format": "html", "path": path, "mimeType": "text/html", "content": body}
    notebook = render_notebook(experiment, artifact, manifest)
    body = json.dumps(notebook, indent=2)
    path = os.path.join(_export_root(), f"{experiment_id}.ipynb")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return {"format": "notebook", "path": path,
            "mimeType": "application/x-ipynb+json", "content": body}


__all__ = ["export_experiment", "render_experiment_html", "render_notebook"]
