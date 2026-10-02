---
title: "Phase 18 — Visual Output"
status: Not started
phase: 18
depends_on: [15, 16]
unlocks: [19, 20]
last-verified: 2026-10-02
---

# Phase 18 — Visual Output

| | |
|---|---|
| **Depends on** | Phase 15 (an artifact needs a serving route and a renderer before a chart can be one) and Phase 16 (most charts are over collected data). |
| **Unlocks** | Phase 19 (an image the runtime produced is what a vision check would consume) and Phase 20 (the gate grades the honesty of the label). |
| **Estimated work** | 12–16 h of agent time. Changes the analysis sandbox's import surface and the artifact renderer. |
| **Deliverable type** | one renderer module + two recipes + a chart artifact contract + a panel extension. |
| **Decision records** | ADR-H123 (the runtime may render, and every rendered figure is `computed`, never evidence) |
| **Prompt to copy** | [§11 below](#11-implementation-prompt) |

---

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists](#2-why-this-phase-exists)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The figure payload (what crosses the sandbox boundary)](#61-the-figure-payload-what-crosses-the-sandbox-boundary)
  - [6.2 The artifact contract (additive)](#62-the-artifact-contract-additive)
  - [6.3 The two new recipes](#63-the-two-new-recipes)
  - [6.4 The surface](#64-the-surface)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt](#11-implementation-prompt)

---

## 1. Goal

Ask for a drawdown, a distribution, a correlation matrix or a Monte Carlo and get a
**figure** — labelled as worked out by Eclipse, carrying the inputs and the code
digest that produced it, never presented as a retrieved fact. Charts are produced by
the runtime (reproducibly, with provenance) and rendered inline in the conversation.

## 2. Why this phase exists

**(a) The runtime cannot plot, by construction.** `code/execution.py`:

```python
IMPORT_ALLOWLIST: tuple[str, ...] = (
    "math", "statistics", "decimal", "fractions", "datetime", "json", "csv",
    "itertools", "functools", "collections", "typing", "re", "random",
    "numpy", "pandas",
)
```

`check_imports` is an AST walk that rejects anything else, and rejects
`__import__`/`importlib`/`eval`/`exec`/`compile`/`open`/`os`/`sys` by name. Verified:
`grep -rniE "matplotlib|plotly|seaborn|savefig" python/harness --include=*.py`
returns **nothing** in the runtime. So "create a visualisation" is impossible today —
not poorly supported, impossible — and the seven shipped recipes
(`returns_series`, `drawdown_profile`, `correlation_matrix`, `contribution_to_return`,
`reconciliation`, `period_comparison`, `scenario_shock`) return numbers only.

**(b) The artifact type already anticipates an image, and nothing produces one.**
`code/execution.py` sniffs MIME (`image/png` is in the map) and `ArtifactRef` has a
`kind` (`series`/`table`/`scalar`/`text`). The plumbing exists; there is no producer.

**(c) Even if a PNG existed, the chat surface cannot show it.**
`src/components/chat/computed-result-panel.tsx` renders a name and a 12-character
hash — verified in full in Phase 15 §2(c). The serving route does not exist either
(Phase 15 adds it). So this phase is the *producer*, and it depends on 15 for the
*delivery*.

**(d) The honesty rule must be extended, not assumed.** README §3.4 and the system
prompt both say a computed number never masquerades as retrieved data. A **picture**
is the easiest way to break that rule — a chart is persuasive and its provenance is
invisible. So the contract is part of the deliverable: the figure carries its inputs,
its code digest and the `computed` label on the image itself, not only beside it.

## 3. In scope

1. A **renderer module** in the runtime (`code/render.py`), reachable from the
   analysis sandbox through a narrow, explicitly declared path: the sandbox stages a
   JSON payload, the renderer draws it, and the resulting file is collected as an
   `ArtifactRef(kind="figure")`. The model never gets a general plotting library in
   its generated program — that would be a far bigger surface than a renderer.
2. The **import allowlist gains exactly one entry** (`numpy` already there; the
   renderer needs a plotting backend) with the same AST guard, or — preferred — the
   plot is drawn by the renderer process itself, so the model's program still imports
   nothing new. **Decision: the second.** The model returns series; the renderer
   draws. This keeps `IMPORT_ALLOWLIST` untouched, which is the whole point of the
   sandbox.
3. Two new recipes that produce a figure: `distribution_profile` (histogram +
   summary statistics) and `monte_carlo_paths` (bounded paths, seeded, with the
   seed recorded). Both fail honestly on a missing input, like the existing seven.
4. A `figure` artifact contract: `ArtifactRef.kind` gains `"figure"`, carrying
   `code_digest`, `inputs_digest`, `seed` (when the computation was stochastic) and
   the `computed` label.
5. A chart-artifact renderer in chat: the existing Phase-15 `ArtifactView` (image →
   inline) is extended so a figure renders with its provenance line, its inputs and —
   where the run produced the numbers — a link to the computed-result panel.
6. **Bounded** rendering: a cap on series length and path count, deterministic output
   for the same inputs (a recorded seed), and no rendering of a figure over data the
   runtime did not record as an input.

## 4. Who can use it (the non-expert obligation)

The user is a trader, an analyst or a student: someone who reads a chart faster than a
table. They never see "matplotlib", "backend", "agg" or "artifact". What they see:

- "Here's the drawdown profile — worked out by Eclipse from the price history you
  collected (2024-01-01 to 2026-06-30)."
- On the figure itself: the computed label. Beside it: the inputs and the seed, so the
  same figure can be reproduced.
- If the data was too thin to plot, one plain sentence: "There isn't enough history
  for this chart (12 points; 30 needed)." — not a chart with three points on it.

Strings are i18n keys under `figure.*`; the mechanism denylist applies.

## 5. Non-goals (do not do these)

- **No general code execution with a plotting library.** The model never imports a
  drawing library; the renderer draws from a recorded payload. `IMPORT_ALLOWLIST`
  stays as it is.
- **No interactive chart engine.** The existing chart stack (`src/lib/chart/`,
  ECharts) belongs to the app's own screens; a runtime figure is a static image with
  provenance. Do not wire the runtime into the app's chart components.
- **No styling of the app.** The figure uses a fixed, self-contained style so it
  renders identically wherever it is opened.
- **No new data acquisition** — a figure is drawn only from data already recorded as
  an input (retrieved evidence or a collected dataset).
- **No claim that a figure is evidence.** `is_evidence` stays false for anything
  computed; the `computed` label is asserted, not assumed.
- Never commit, push or open a PR; do not commit `jdds.db`.

## 6. Exact contracts to create

### 6.1 The figure payload (what crosses the sandbox boundary)

```python
# python/harness/code/render.py
FigureKind = Literal["line", "histogram", "heatmap", "paths", "scatter"]

class FigureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: FigureKind
    title: str = Field("", max_length=120)
    x_label: str = Field("", max_length=60)   # noqa: N815
    y_label: str = Field("", max_length=60)   # noqa: N815
    series: list[Series]                       # bounded: MAX_SERIES
    annotations: list[str] = Field(default_factory=list, max_length=8)

class Series(BaseModel):
    name: str = Field(..., max_length=60)
    x: list[float] = Field(default_factory=list, max_length=MAX_POINTS)
    y: list[float] = Field(default_factory=list, max_length=MAX_POINTS)
    band: Optional[tuple[list[float], list[float]]] = None   # for `paths`

MAX_SERIES = 8
MAX_POINTS = 5_000

def render_figure(spec: FigureSpec, output_dir: Path, *, label: str) -> ArtifactRef:
    """Draw one figure deterministically and return its artifact reference.

    Deterministic: the same `FigureSpec` bytes produce a byte-identical PNG (fixed
    DPI, fixed colour cycle, no timestamp in the image). The `label` ("Worked out by
    Eclipse, <date>") is drawn ON the figure so a screenshot cannot lose it.
    """
```

### 6.2 The artifact contract (additive)

```python
# python/harness/code/execution.py — ArtifactRef, additive
kind: Literal["series", "table", "scalar", "text", "figure"] = "series"
# For kind="figure":
#   code_digest:    sha256 of the program/spec that produced the numbers
#   inputs_digest:  sha256 of the recorded inputs used
#   seed:           the recorded seed, when the computation was stochastic
```

`is_evidence(artifact)` returns `False` for a figure, and
`render_value`/`provenanceStatusKey` keep their fail-closed behaviour: a figure with
no recorded provenance renders `UNAVAILABLE`, never a bare image.

### 6.3 The two new recipes

```python
# python/harness/code/recipes.py — additive; each fails honestly on a missing input
Recipe(
    name="distribution_profile",
    inputs=(RecipeInput(name="values", kind="series", required=True),),
    outputs=("count", "mean", "median", "stdev", "p05", "p95"),
    figure=FigureKind.HISTOGRAM,
    description="How a set of values is spread: the shape, the middle and the tails.",
),
Recipe(
    name="monte_carlo_paths",
    inputs=(
        RecipeInput(name="returns", kind="series", required=True),
        RecipeInput(name="start_value", kind="scalar", required=True),
        RecipeInput(name="paths", kind="scalar", required=False),
        RecipeInput(name="horizon", kind="scalar", required=False),
        RecipeInput(name="seed", kind="scalar", required=False),
    ),
    outputs=("p05", "p50", "p95", "expected", "max_drawdown_median"),
    figure=FigureKind.PATHS,
    # Bounded and reproducible: default 200 paths, horizon 252, a recorded seed.
    # Sampling FROM the supplied returns — never an assumed distribution invented
    # by the runtime.
    description="A spread of what could happen, drawn from the returns you supplied.",
),
```

**The Monte Carlo rule, stated as a gate:** the recipe samples from the supplied
return series (a bootstrap), records the seed, reports the path count and the horizon,
and labels the output a what-if. It never assumes a normal distribution, never
fabricates a mean or a volatility, and never presents a percentile as a forecast.

### 6.4 The surface

```tsx
// src/components/chat/artifact-view.tsx — the Phase-15 component, extended
// kind="figure" → inline <img> sourced from the Phase-15 serving route, with:
//   - the computed label rendered as text BESIDE the image too (not image-only),
//   - the inputs line (what the figure was drawn from, with its as-of),
//   - the reproducibility line (seed, when present),
//   - a link to the run's computed-result panel when the run produced the numbers.
```

## 7. Work items (ordered)

1. `python/harness/code/render.py` — `FigureSpec`, `Series`, bounds, `render_figure`.
   Pure given a spec; write the determinism test first (render twice, compare bytes).
2. `python/tests/test_render.py` — determinism, bounds, the label present in the
   image, a figure over a too-short series refusing.
3. `python/harness/code/execution.py` — the additive `figure` kind, the three
   provenance fields, `is_evidence` false for figures, and the collection path that
   calls `render_figure` when a recipe declares one.
4. `python/harness/code/recipes.py` — the two recipes + their failing-input cases.
5. `python/harness/analysis_tools.py` — include the figure in the tool result and the
   human-readable text ("Saved: drawdown.png").
6. `src/components/chat/artifact-view.tsx` — the figure branch (depends on Phase 15's
   serving route landing first).
7. `en.ts` — `figure.*`.
8. `python/tests/test_analysis_recipes.py` — extend for the two new recipes (a
   missing input refuses; the seed is recorded; the figure is not evidence).
9. `docs/harness/roadmap/progress/phase-18-progress.md` — created, gates unchecked.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/code/render.py` | new — the figure renderer |
| `python/harness/code/execution.py` | changed — `figure` kind + provenance fields |
| `python/harness/code/recipes.py` | changed — two figure recipes |
| `python/harness/analysis_tools.py` | changed — figures in the result text |
| `src/components/chat/artifact-view.tsx` | changed — the figure branch |
| `src/lib/i18n/dictionaries/en.ts` | changed — `figure.*` |
| `python/tests/test_render.py`, `test_analysis_recipes.py` | new / changed |
| `docs/harness/decisions.md` | changed — ADR-H123 |

## 9. Acceptance gates

```bash
# G1 — determinism and bounds.
./scripts/vendor/python/python.exe -m pytest python/tests/test_render.py -v

# G2 — a figure is never evidence, and it carries its provenance.
./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_provenance.py -v

# G3 — the sandbox's import surface is unchanged (the model still cannot plot).
git diff --stat python/harness/code/execution.py  # must NOT touch IMPORT_ALLOWLIST
./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_execution.py -q

# G4 — the Monte Carlo is bounded, seeded and honest.
./scripts/vendor/python/python.exe -m pytest python/tests/test_recipe_monte_carlo.py -v

# G5 — the figure renders in the surface, and the app builds.
npx vitest run src/components/chat/artifact-view.test.ts
npm run build

# G6 — the full release gate.
npm run check:all
```

| Gate | Assertion |
|---|---|
| G1 | The same `FigureSpec` renders byte-identical twice; MAX_SERIES/MAX_POINTS are enforced (an over-long series is refused, not silently truncated); the computed label is found in the rendered image's text layer / by an OCR-free assertion on the drawing call; a 12-point series requesting a 30-point minimum refuses. |
| G2 | `is_evidence(figure)` is `False`; a figure with no `code_digest` renders `UNAVAILABLE`; the artifact carries `inputs_digest` and the `computed` label. |
| G3 | `IMPORT_ALLOWLIST` is unchanged and `check_imports` still rejects `matplotlib`, `os`, `open`, `exec`; the analysis execution suite passes unchanged. |
| G4 | Paths are bootstrap samples of the supplied returns (a test asserts the sampled values are members of the input set, i.e. no invented distribution); the seed is recorded and re-running with it reproduces the same percentiles; the path count and horizon are reported; a missing `returns` input refuses. |
| G5 | The figure branch renders an `<img>` with the provenance line as text; the artifact test asserts the label is not image-only; `npm run build` exits 0. |
| G6 | `ALL GATES PASSED`; counts reported as observed. |

**A gate not run is a gate not passed.** Paste the raw output of each into
`docs/harness/roadmap/progress/phase-18-progress.md`.

## 10. Definition of done

- A chart request produces a real PNG, reproducibly, with its provenance and the
  computed label on the image and beside it.
- The Monte Carlo samples the user's own returns, records its seed, and is labelled a
  what-if — never a forecast, never an assumed distribution.
- The sandbox's import surface is unchanged; the model still cannot import a drawing
  library or `os`.
- Nothing computed is ever presented as evidence, and the existing fail-closed
  provenance behaviour is intact.
- ADR-H123 written; changelog appended; NAVIGATION row 70 updated; `status:` and the
  index row flipped.

## 11. Implementation prompt

```text
Task: Phase 18 — visual output from the analysis sandbox.

Read first, in full:
- docs/harness/roadmap/phase-18-visual-output.md (this file, verbatim)
- docs/harness/roadmap/README.md (§3.4 never fabricate, §3.5 zero-config, §6 non-goals)
- python/harness/code/{execution.py,recipes.py}, python/harness/analysis_tools.py
- src/components/chat/computed-result-panel.tsx (what exists today)
- the Phase-15 artifact serving route and src/components/chat/artifact-view.tsx

Goal: a chart request produces a real, reproducible, labelled figure from data the
runtime already recorded as an input — with the model never gaining a plotting
library and the figure never becoming evidence.

In scope: §3 items 1–6 and the ordered work items in §7.

Non-goals (do NOT do these):
- Do NOT add a plotting library to IMPORT_ALLOWLIST, and do NOT let the model's
  generated program import one. The renderer draws from a recorded payload.
- No interactive chart engine; do not wire the runtime into src/lib/chart/ or ECharts.
- No runtime-produced figure over data that is not a recorded input.
- No assumed distribution in the Monte Carlo: bootstrap the supplied returns, record
  the seed, and label the result a what-if.
- A figure is never evidence: is_evidence stays False for anything computed.
- Never commit, push or open a PR. Do not commit jdds.db.

Constraints:
- Determinism is a contract: same spec bytes ⇒ byte-identical PNG.
- Bounds are enforced (MAX_SERIES, MAX_POINTS), and an over-long series is refused
  rather than truncated.
- The computed label is drawn ON the figure, so a screenshot cannot lose it.
- Every user-facing string is an i18n key; the mechanism denylist applies.
- Measure before implementing; a corrected audit is a valid outcome. Do not weaken any
  existing test — name every changed expectation with its old and new value.

Acceptance gates — run each from Black-Eclipse-site/ and paste the RAW output into
docs/harness/roadmap/progress/phase-18-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_render.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_provenance.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_execution.py -q
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_recipe_monte_carlo.py -v
  git diff python/harness/code/execution.py | grep -n "IMPORT_ALLOWLIST"    # expect empty
  npx vitest run src/components/chat/artifact-view.test.ts
  npm run build
  npm run check:all

Finish by stating: "docs updated: <files>" or "no doc change — <reason>", plus one
honest non-property: what you did NOT verify.
```

---

**Next:** [Phase 19 — Looking at What It Produced](./phase-19-self-verification.md)
