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
    INPUT_INVALID,
    run_analysis,
)


@dataclass(frozen=True)
class RecipeInput:
    name: str
    kind: str            # series | table | scalar | text
    description: str


@dataclass(frozen=True)
class Recipe:
    name: str
    answers: str
    inputs: tuple[RecipeInput, ...]
    source: str
    missing_prompt: str = "I need {missing} to do that."
    artifact_name: Optional[str] = None
    writes_artifact: bool = False


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
    """Run a named recipe, or REFUSE honestly when an input is missing.

    A missing input is a QUESTION, not a guess: the refusal names what is missing
    and carries the plain prompt to ask the user. No default is substituted and no
    silently shorter period is used.
    """
    recipe = get_recipe(name)
    if recipe is None:
        return AnalysisResult(
            status="refused", code="RECIPE_NOT_FOUND",
            stderr=f"no recipe named {name!r}",
        )
    provided = inputs or {}
    missing = [i for i in recipe.inputs if i.name not in provided or provided[i.name] is None]
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
            inputs=[AnalysisInput(name=i.name, kind=i.kind, value=provided[i.name]) for i in recipe.inputs],
            purpose=recipe.answers,
            timeout_s=timeout_s,
        )
    except Exception as exc:  # noqa: BLE001 - a malformed recipe call is a refusal
        raise AnalysisError(INPUT_INVALID, str(exc)) from exc
    return run_analysis(request, output_dir=output_dir)


__all__ = ["RECIPES", "Recipe", "RecipeInput", "get_recipe", "list_recipes", "run_recipe"]
