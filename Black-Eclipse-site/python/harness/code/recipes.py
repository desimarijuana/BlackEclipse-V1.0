"""The shipped analysis recipes — DATA, not prose.

Each recipe is a tested, named analysis the agent can reach for instead of writing
code from scratch. Every recipe:

  (a) runs in the Phase 3 sandbox (via `code/execution.run_analysis`),
  (b) declares its inputs,
  (c) FAILS HONESTLY when an input is absent — it ASKS rather than substituting a
      default or a shorter period, and
  (d) carries the §6.2 provenance record (computed, never retrieved).

A recipe never decides what is TRUE; it computes and labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .execution import (
    AnalysisError,
    AnalysisInput,
    AnalysisRequest,
    AnalysisResult,
    FigurePayload,
    INPUT_INVALID,
    run_analysis,
)


@dataclass(frozen=True)
class RecipeInput:
    name: str
    kind: str            # series | table | scalar | text
    description: str
    # Phase 18 (additive): a required input is asked for when absent; an OPTIONAL
    # one may be omitted (the recipe's own program applies its documented default).
    required: bool = True


@dataclass(frozen=True)
class Recipe:
    name: str
    answers: str
    inputs: tuple[RecipeInput, ...]
    source: str
    missing_prompt: str = "I need {missing} to do that."
    artifact_name: Optional[str] = None
    writes_artifact: bool = False
    # Phase 18 (additive): the extra NAMED modules this recipe's source imports
    # (the figure recipe needs `io` + `matplotlib`). Comes from THIS table only —
    # a caller/model cannot widen the analysis allowlist.
    extra_imports: tuple[str, ...] = ()
    # Phase 18 (additive): the figure payload a successful run carries — the
    # figure kind, which inputs were drawn, and which input holds the seed.
    figure_kind: Optional[str] = None
    figure_series: tuple[str, ...] = ()
    figure_seed_input: Optional[str] = None


# ── The seven recipes (§6.6) ─────────────────────────────────────────────────

_RETURNS_SERIES = """
prices = inputs.get("prices")
out = []
for prev, curr in zip(prices, prices[1:]):
    if prev == 0:
        out.append(None)
    else:
        out.append(round(curr / prev - 1.0, 6))
result = {"returns": out, "count": len(out)}
"""

_DRAWDOWN_PROFILE = """
prices = inputs.get("prices")
peak = prices[0]
worst = 0.0
peak_i = trough_i = 0
peak_at = trough_at = 0
for i, value in enumerate(prices):
    if value > peak:
        peak = value
        peak_i = i
    dd = value / peak - 1.0 if peak else 0.0
    if dd < worst:
        worst = dd
        trough_i = i
        peak_at, trough_at = peak_i, i
result = {"maxDrawdownPct": round(worst * 100, 4), "peakIndex": peak_at, "troughIndex": trough_at}
"""

_CORRELATION_MATRIX = """
rows = inputs.get("returns")
names = [r["name"] for r in rows]
series = {r["name"]: [float(x) for x in r["values"]] for r in rows}
def corr(a, b):
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    if n < 2:
        return None
    ma, mb = sum(a)/n, sum(b)/n
    cov = sum((a[i]-ma)*(b[i]-mb) for i in range(n)) / (n-1)
    va = sum((x-ma)**2 for x in a)/(n-1)
    vb = sum((x-mb)**2 for x in b)/(n-1)
    if va == 0 or vb == 0:
        return None
    return round(cov / (va**0.5 * vb**0.5), 6)
matrix = [[corr(series[x], series[y]) for y in names] for x in names]
result = {"names": names, "matrix": matrix}
"""

_CONTRIBUTION_TO_RETURN = """
rows = inputs.get("holdings")
holdings = {r["name"]: float(r["value"]) for r in rows}
total = sum(holdings.values())
contributions = {k: round((v/total)*100, 4) for k, v in holdings.items()} if total else {}
result = {"total": total, "contributionsPct": contributions}
"""

_RECONCILIATION = """
left = inputs.get("left")
right = inputs.get("right")
lk = {r["key"]: r.get("value") for r in left}
rk = {r["key"]: r.get("value") for r in right}
only_left = sorted(set(lk) - set(rk))
only_right = sorted(set(rk) - set(lk))
mismatches = sorted(k for k in set(lk) & set(rk) if lk[k] != rk[k])
result = {
    "onlyLeft": only_left, "onlyRight": only_right, "mismatched": mismatches,
    "agree": not (only_left or only_right or mismatches),
}
"""

_PERIOD_COMPARISON = """
current = inputs.get("current")
previous = inputs.get("previous")
change = None
if previous:
    change = round((current - previous) / abs(previous) * 100, 6)
result = {"current": current, "previous": previous, "changePct": change}
"""

_SCENARIO_SHOCK = """
rows = inputs.get("values")
shock = inputs.get("shockPct")
factor = 1.0 + (shock / 100.0)
shocked = {r["name"]: round(float(r["value"]) * factor, 6) for r in rows}
result = {"shockPct": shock, "shockedValues": shocked}
"""

# Phase 18: the FIRST figure recipe. Rendered in the sandbox (Agg backend, no
# display, no network), written as bytes into the run's `output/` folder, and
# collected as an artifact the verification ledger then CHECKS (exists, digest,
# size, opens as an image). The plotted series is the computation's own drawn
# series — computed, never evidence (ADR-H123).
_DRAWDOWN_FIGURE = """
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
prices = [float(p) for p in inputs.get("prices")]
peak = prices[0]
drawdowns = []
for value in prices:
    if value > peak:
        peak = value
    drawdowns.append(round((value / peak - 1.0) * 100, 4) if peak else 0.0)
fig, ax = plt.subplots(figsize=(8, 3.2), dpi=110)
ax.plot(range(len(prices)), drawdowns, color="#e11d48", linewidth=1.4)
ax.set_title("Drawdown")
ax.set_xlabel("Period")
ax.set_ylabel("Drawdown percent")
ax.grid(True, alpha=0.25)
fig.tight_layout()
buf = io.BytesIO()
fig.savefig(buf, format="png")
plt.close(fig)
write_artifact("drawdown.png", buf.getvalue())
worst = min(drawdowns) if drawdowns else 0.0
result = {"maxDrawdownPct": round(worst, 4), "points": len(prices)}
"""

# Phase 18: the spread of a set of values — the shape, the middle and the tails.
# The histogram is drawn from the recorded input; the statistics are computed,
# never retrieved (ADR-H123).
_DISTRIBUTION_PROFILE = """
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
values = [float(v) for v in inputs.get("values")]
ordered = sorted(values)
n = len(ordered)
def _q(q):
    if n == 0:
        return None
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(n - 1, lo + 1)
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac
mean = sum(values) / n if n else None
var = sum((v - mean) ** 2 for v in values) / (n - 1) if n > 1 else 0.0
fig, ax = plt.subplots(figsize=(7, 3.2), dpi=110)
bins = min(40, max(5, n // 5 if n else 5))
ax.hist(values, bins=bins, color="#0ea5e9", edgecolor="#0f172a", linewidth=0.4)
ax.set_title("Distribution")
ax.set_xlabel("Value")
ax.set_ylabel("Count")
ax.grid(True, alpha=0.2)
fig.tight_layout()
buf = io.BytesIO()
fig.savefig(buf, format="png")
plt.close(fig)
write_artifact("distribution.png", buf.getvalue())
result = {
    "count": n,
    "mean": round(mean, 6) if mean is not None else None,
    "median": round(_q(0.5), 6) if n else None,
    "stdev": round(var ** 0.5, 6) if n > 1 else None,
    "p05": round(_q(0.05), 6) if n else None,
    "p95": round(_q(0.95), 6) if n else None,
}
"""

# Phase 18: a bootstrap Monte Carlo — each path resamples FROM the supplied
# returns (never an assumed distribution, never an invented mean or volatility),
# the seed is recorded, and the result is labelled a what-if, not a forecast.
_MONTE_CARLO_PATHS = """
import io
import random
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
returns = [float(r) for r in inputs.get("returns")]
start_value = float(inputs.get("start_value"))
paths = int(inputs.get("paths") or 200)
horizon = int(inputs.get("horizon") or 252)
seed = int(inputs.get("seed") or 0)
paths = max(1, min(paths, 500))
horizon = max(1, min(horizon, 1000))
rng = random.Random(seed)
all_paths = []
for _ in range(paths):
    value = start_value
    line = []
    for _ in range(horizon):
        value = value * (1.0 + returns[rng.randrange(len(returns))])
        line.append(value)
    all_paths.append(line)
def _pct(values, q):
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[idx]
p05 = [_pct([p[i] for p in all_paths], 0.05) for i in range(horizon)]
p50 = [_pct([p[i] for p in all_paths], 0.50) for i in range(horizon)]
p95 = [_pct([p[i] for p in all_paths], 0.95) for i in range(horizon)]
def _max_drawdown(line):
    peak = line[0]
    worst = 0.0
    for value in line:
        if value > peak:
            peak = value
        dd = value / peak - 1.0 if peak else 0.0
        if dd < worst:
            worst = dd
    return worst * 100.0
drawdowns = sorted(_max_drawdown(line) for line in all_paths)
mid = min(len(drawdowns) - 1, max(0, int(round(0.5 * (len(drawdowns) - 1)))))
fig, ax = plt.subplots(figsize=(8, 3.4), dpi=110)
for line in all_paths[:40]:
    ax.plot(range(horizon), line, color="#94a3b8", linewidth=0.4, alpha=0.5)
ax.plot(range(horizon), p50, color="#0ea5e9", linewidth=1.6)
ax.plot(range(horizon), p05, color="#e11d48", linewidth=1.0)
ax.plot(range(horizon), p95, color="#22c55e", linewidth=1.0)
ax.set_title("What-if paths (not a forecast)")
ax.set_xlabel("Step")
ax.set_ylabel("Value")
ax.grid(True, alpha=0.2)
fig.tight_layout()
buf = io.BytesIO()
fig.savefig(buf, format="png")
plt.close(fig)
write_artifact("monte_carlo.png", buf.getvalue())
result = {
    "paths": paths,
    "horizon": horizon,
    "seed": seed,
    "startValue": start_value,
    "expected": round(p50[-1], 4),
    "p05": round(p05[-1], 4),
    "p50": round(p50[-1], 4),
    "p95": round(p95[-1], 4),
    "maxDrawdownMedianPct": round(drawdowns[mid], 4),
    "label": "what-if",
}
"""

RECIPES: tuple[Recipe, ...] = (
    Recipe(
        name="returns_series",
        answers="what did this do over time",
        inputs=(RecipeInput("prices", "series", "a list of prices over time"),),
        source=_RETURNS_SERIES,
        missing_prompt="I need the prices to work out the returns — which series should I use?",
    ),
    Recipe(
        name="drawdown_profile",
        answers="how bad was the worst fall, and how long",
        inputs=(RecipeInput("prices", "series", "a list of prices over time"),),
        source=_DRAWDOWN_PROFILE,
        missing_prompt="I need the prices to work out the worst fall — which series should I use?",
    ),
    Recipe(
        name="correlation_matrix",
        answers="are these moving together",
        inputs=(RecipeInput("returns", "table", "one row per item with `name` and `values`"),),
        source=_CORRELATION_MATRIX,
        missing_prompt="I need the return history for each holding to compare them — which ones should I use?",
    ),
    Recipe(
        name="contribution_to_return",
        answers="what drove the result",
        inputs=(RecipeInput("holdings", "table", "a mapping of name to value/weight"),),
        source=_CONTRIBUTION_TO_RETURN,
        missing_prompt="I need the holdings and their values to work out the contributions — which ones should I use?",
    ),
    Recipe(
        name="reconciliation",
        answers="do these two sets agree, and where not",
        inputs=(
            RecipeInput("left", "table", "rows of `key`/`value`"),
            RecipeInput("right", "table", "rows of `key`/`value`"),
        ),
        source=_RECONCILIATION,
        missing_prompt="I need both sets of records to compare them — which two should I reconcile?",
    ),
    Recipe(
        name="period_comparison",
        answers="this quarter vs last",
        inputs=(
            RecipeInput("current", "scalar", "the current period's value"),
            RecipeInput("previous", "scalar", "the previous period's value"),
        ),
        source=_PERIOD_COMPARISON,
        missing_prompt="I need both periods' values to compare them — which two should I use?",
    ),
    Recipe(
        name="scenario_shock",
        answers="what if this fell 20%",
        inputs=(
            RecipeInput("values", "table", "a mapping of name to value"),
            RecipeInput("shockPct", "scalar", "the percentage move to apply"),
        ),
        source=_SCENARIO_SHOCK,
        missing_prompt="I need the holdings and the percentage move to work that out — what should I assume?",
    ),
    # Phase 18 (slice): the drawdown, as a FIGURE. Produces a PNG artifact the
    # chat can hand over; the numbers still come back in `result`, so a claim
    # about them is checked exactly like any other computed value.
    Recipe(
        name="drawdown_figure",
        answers="show me the worst fall as a chart",
        inputs=(RecipeInput("prices", "series", "a list of prices over time"),),
        source=_DRAWDOWN_FIGURE,
        missing_prompt="I need the prices to draw the worst fall — which series should I use?",
        artifact_name="drawdown.png",
        writes_artifact=True,
        extra_imports=("io", "matplotlib"),
        figure_kind="line",
        figure_series=("prices",),
    ),
    # Phase 18 (slice): the spread of a set of values — a histogram plus the
    # middle and the tails, all computed from the recorded input.
    Recipe(
        name="distribution_profile",
        answers="how is this spread — the shape, the middle and the tails",
        inputs=(RecipeInput("values", "series", "a list of values"),),
        source=_DISTRIBUTION_PROFILE,
        missing_prompt="I need the values to show how they are spread — which series should I use?",
        artifact_name="distribution.png",
        writes_artifact=True,
        extra_imports=("io", "matplotlib"),
        figure_kind="histogram",
        figure_series=("values",),
    ),
    # Phase 18 (slice): a bounded, seeded bootstrap over the user's own returns.
    # It is a what-if: no distribution is assumed and no percentile is a forecast.
    Recipe(
        name="monte_carlo_paths",
        answers="what could happen, drawn from the returns you supplied",
        inputs=(
            RecipeInput("returns", "series", "the period returns to resample"),
            RecipeInput("start_value", "scalar", "the value to start from"),
            RecipeInput("paths", "scalar", "how many paths to draw (default 200, max 500)", required=False),
            RecipeInput("horizon", "scalar", "how many steps per path (default 252, max 1000)", required=False),
            RecipeInput("seed", "scalar", "the random seed to record (default 0)", required=False),
        ),
        source=_MONTE_CARLO_PATHS,
        missing_prompt=(
            "I need the returns and a starting value to run the what-if — "
            "which series and start should I use?"
        ),
        artifact_name="monte_carlo.png",
        writes_artifact=True,
        extra_imports=("io", "matplotlib"),
        figure_kind="paths",
        figure_series=("returns",),
        figure_seed_input="seed",
    ),
)


def get_recipe(name: str) -> Optional[Recipe]:
    return next((r for r in RECIPES if r.name == name), None)


def list_recipes() -> list[dict[str, Any]]:
    return [
        {"name": r.name, "answers": r.answers,
         "inputs": [{"name": i.name, "kind": i.kind, "description": i.description} for i in r.inputs]}
        for r in RECIPES
    ]


def run_recipe(
    name: str, inputs: dict[str, Any], *, output_dir: Optional[Path] = None, timeout_s: int = 120,
) -> AnalysisResult:
    """Run a named recipe, or REFUSE honestly when a required input is missing.

    A missing input is a QUESTION, not a guess: the refusal names what is missing
    and carries the plain prompt to ask the user. No default is substituted and no
    silently shorter period is used. An OPTIONAL input that is absent simply does
    not reach the program, whose documented default applies.
    """
    recipe = get_recipe(name)
    if recipe is None:
        return AnalysisResult(
            status="refused", code="RECIPE_NOT_FOUND",
            stderr=f"no recipe named {name!r}",
        )
    provided = inputs or {}
    missing = [
        i for i in recipe.inputs
        if i.required and (i.name not in provided or provided[i.name] is None)
    ]
    if missing:
        names = ", ".join(i.name for i in missing)
        prompt = recipe.missing_prompt
        if "{missing}" in prompt:
            prompt = prompt.replace("{missing}", names)
        return AnalysisResult(
            status="refused", code=INPUT_INVALID,
            stderr=f"missing input(s): {names}",
            provenance=None,
            outputs={"_prompt": prompt, "_missing": [i.name for i in missing]},
        )
    try:
        request = AnalysisRequest(
            source=recipe.source,
            inputs=[
                AnalysisInput(name=i.name, kind=i.kind, value=provided[i.name])
                for i in recipe.inputs
                if i.name in provided and provided[i.name] is not None
            ],
            purpose=recipe.answers,
            timeout_s=timeout_s,
            extra_imports=recipe.extra_imports,
        )
    except Exception as exc:  # noqa: BLE001 - a malformed recipe call is a refusal
        raise AnalysisError(INPUT_INVALID, str(exc)) from exc
    result = run_analysis(request, output_dir=output_dir)
    if result.status == "ok" and recipe.figure_kind:
        # The figure payload (§6.1): what was drawn, from which recorded inputs,
        # with the seed when the computation was stochastic. A figure is never
        # evidence — the label is part of the payload.
        names = recipe.figure_series or tuple(
            i.name for i in recipe.inputs if i.kind == "series"
        )
        seed: Optional[int] = None
        if recipe.figure_seed_input and provided.get(recipe.figure_seed_input) is not None:
            try:
                seed = int(provided[recipe.figure_seed_input])
            except (TypeError, ValueError):
                seed = None
        result.figure = FigurePayload(
            kind=recipe.figure_kind,
            artifact=recipe.artifact_name,
            series=[{"name": name, "points": len(provided.get(name) or [])} for name in names],
            seed=seed,
        )
    return result


__all__ = ["RECIPES", "Recipe", "RecipeInput", "get_recipe", "list_recipes", "run_recipe"]
