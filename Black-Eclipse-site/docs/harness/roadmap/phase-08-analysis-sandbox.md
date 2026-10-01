---
title: "Phase 8 — Analysis Sandbox (Computing, Not Just Retrieving)"
status: Not started
phase: 8
depends_on: [5]
unlocks: [9]
last-verified: 2026-09-30
---

# Phase 8 — Analysis Sandbox (Computing, Not Just Retrieving)

| | |
|---|---|
| **Depends on** | Phase 3 (the sandbox), Phase 5 (autonomy + approvals) |
| **Unlocks** | Phase 9 (kits need a working compute sandbox) |
| **Estimated work** | 5–8 h of agent time |
| **Deliverable type** | new `code/execution.py` + an `analysis_run` tool + artefacts + a provenance rule |
| **New ADRs** | ADR-H110 |
| **Prompt to copy** | [§11 below](#11-implementation-prompt-copy-this-to-opencode) |

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists (the real gap)](#2-why-this-phase-exists-the-real-gap)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The execution contract — `python/harness/code/execution.py`](#61-the-execution-contract--pythonharnesscodeexecutionpy)
  - [6.2 The provenance rule (the important part)](#62-the-provenance-rule-the-important-part)
  - [6.3 The tool — `analysis_run`](#63-the-tool--analysis_run)
  - [6.4 Artefacts](#64-artefacts)
  - [6.5 Reproducibility](#65-reproducibility)
  - [6.6 The shipped analysis recipes](#66-the-shipped-analysis-recipes)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt (copy this to OpenCode)](#11-implementation-prompt-copy-this-to-opencode)

## 1. Goal

Let Eclipse **compute** — a backtest, a correlation matrix, a drawdown, a ratio
that no shipped calculator covers — reproducibly, in the Phase 3 sandbox, with the
result *labelled by where it came from*.

Today Eclipse can retrieve a number and can run a small fixed set of pure
calculators. It cannot *derive a new one*. This phase closes that, without opening
the door to a number that looks retrieved but was not.

## 2. Why this phase exists (the real gap)

The harness has a deliberate, well-built gap here. `research/calculations.py` is
*"pure-Python period change, CAGR, annualized volatility, max drawdown, Sharpe —
with formula/version/input provenance and hard input guards."* That is exactly the
right shape: a small, auditable, provenance-carrying calculator. But the list is
closed. A user asking for a metric outside it gets retrieval (if some source
publishes it) or nothing.

And the repo's law is unambiguous about the danger of the alternative:

> **Never fabricate financial data.** Unavailable data renders an `UNAVAILABLE`
> state; simulated/stale data is always labeled. — `AGENTS.md`

A code sandbox can trivially produce a plausible-looking number from invented
inputs. So this phase's real work is not "run Python" — Phase 3 already does that
— it is **the provenance rule that keeps a computed number from ever being mistaken
for a retrieved one.** Everything else is plumbing.

The second precedent is the MCP provenance contract: every MCP result carries
`verification: external`, `eclipseVerified: false`, its source and `retrievedAt`,
and is labelled external in its text. A computed result gets the same treatment,
with `computed` instead of `external`.

## 3. In scope

1. `python/harness/code/execution.py` — a bounded analysis-run contract on top of
   the Phase 3 sandbox.
2. The `analysis_run` tool, off by default per run.
3. The provenance rule, enforced in the renderer (not in a prompt).
4. Artefact collection with digests.
5. Reproducibility: interpreter, package set and source recorded so a result can be
   re-derived from the trace alone.
6. A small library of shipped, tested analysis recipes.

## 4. Who can use it (the non-expert obligation)

1. **The user asks for an answer, not for code.** *"What would a 60/40 split of
   these have done since 2020?"*, *"How correlated are my five biggest
   holdings?"*, *"Reconcile these two columns."* Eclipse writes the code; the user
   never sees it unless they open "details".
2. **A computed number says so, in words.** It is rendered as *"worked out by
   Eclipse"* with a short plain line (*"Using your portfolio's monthly returns,
   Jan 2020 – Sep 2026"*), never as if a provider published it. Retrieved numbers
   are unchanged and keep their source line. The two must be visually distinct at
   a glance.
3. **Every computed number can be explained.** "Show me how you got that" reveals
   the inputs, the period, and the method — the same affordance the research
   receipt already provides for retrieved evidence.
4. **A missing input is a question, not a guess.** *"I need the monthly returns
   for these five holdings to do that — two aren't in your data. Do you want me to
   use the three I have, or skip it?"* Never an invented series, never a silently
   shorter period.
5. **The words *sandbox*, *interpreter*, *import*, *module*, *stdout*, *stderr*,
   *argv* and *exit code* never reach the surface.** They live in the trace.
6. **All new copy is an i18n key** in `src/lib/i18n/` (`dictionaries/en.ts`,
   `dictionaries/index.ts`, `translate.ts`, `use-t.ts`).
7. **The plain-language gate** (§9 G7) covers the computation labels and the
   missing-input prompt.

## 5. Non-goals (do not do these)

- **No notebook UI.** No cell execution surface, no REPL.
- **No second research engine.** A computed number does not become evidence without
  going through `research/claims.py` (see §6.2 for the one legal path).
- No network in the analysis sandbox (default deny, same as Phase 3).
- No arbitrary imports — the import allowlist is explicit and small.
- No reading of `jdds.db` except through data the run already received as input.
- Do not commit, push, or open a PR.

## 6. Exact contracts to create

### 6.1 The execution contract — `python/harness/code/execution.py`

```python
"""Bounded, reproducible analysis execution — Phase 3's sandbox, aimed at a task.

This module never decides what is TRUE. It decides what was COMPUTED, records
exactly enough to re-derive it, and hands the result to a renderer that is
forbidden to present it as retrieved data.
"""

IMPORT_ALLOWLIST: tuple[str, ...] = (
    "math", "statistics", "decimal", "fractions", "datetime", "json", "csv",
    "statistics", "itertools", "functools", "collections", "typing",
    "numpy", "pandas",                      # present in the vendored interpreter
)
DEFAULT_TIMEOUT_S: int = 120
DEFAULT_MEMORY_MB: int = 2048
MAX_OUTPUT_BYTES: int = 200_000

class AnalysisInput(BaseModel):
    """Data the run already holds, passed as DATA — never interpolated into source."""
    name: str = Field(..., pattern=r"[a-z_][a-z0-9_]{0,40}")
    kind: Literal["series", "table", "scalar", "text"]
    value: Any                       # JSON-serialisable; validated against `kind`
    provenance: Optional[str] = None  # where it came from (a citation id / receipt leg)

class AnalysisRequest(BaseModel):
    source: str = Field(..., max_length=20_000)     # the program (inspected, not eval'd)
    inputs: list[AnalysisInput] = []
    purpose: str = Field(..., max_length=300)       # plain words, shown to the user
    timeout_s: int = DEFAULT_TIMEOUT_S

class AnalysisResult(BaseModel):
    status: Literal["ok", "failed", "refused", "timed_out"]
    outputs: dict[str, Any] = {}          # named results, JSON-safe, size-capped
    artifacts: list[ArtifactRef] = []     # §6.4
    stderr: str = ""                      # bounded; trace-only, never surfaced
    source_digest: str                    # SHA-256 of the source
    input_digests: dict[str, str]
    interpreter: str                      # the VENDORED interpreter path
    package_lock_digest: Optional[str]    # resolved set, so a rerun matches
    duration_ms: int
    provenance: Provenance                # ALWAYS Provenance.kind == "computed"
```

### 6.2 The provenance rule (the important part)

A single dataclass, and a renderer that must consult it:

```python
@dataclass(frozen=True)
class Provenance:
    kind: Literal["retrieved", "computed"]
    label: str          # plain words for the surface, from an i18n key
    detail: str         # the method / period sentence
    source_digest: Optional[str]     # computed only
    citation: Optional[str]          # retrieved only
```

**The rules, enforced in code:**

1. Every `analysis_run` output is `kind="computed"` — there is no code path that
   produces `retrieved` from an execution.
2. The answer renderer must **visually distinguish** the two: a computed number
   carries its "worked out by Eclipse" label and its method line; a retrieved
   number keeps its existing source line. A computed number **without** a
   provenance record is rendered `UNAVAILABLE`, never bare (a missing record is a
   bug, and it fails closed).
3. **A computed number cannot enter a research claim.** The one legal path for a
   derivation to become evidence is to be re-expressed through
   `research/calculations.py` — which already carries formula/version/input
   provenance and its own guards. Reaching that path is an explicit act, not an
   automatic promotion, and the receipt records it.
4. The existing comparability gate still applies: a computed period change across
   an incompatible basis is refused exactly as a retrieved one is
   (`research/comparability.py`).

Point 3 is the line that keeps this phase from quietly undermining the evidence
system. Without it, "run some code" becomes a laundering route into a claim.

### 6.3 The tool — `analysis_run`

`ToolDefinition`: `name="analysis_run"`, `read_only=False`,
`required_permissions=("analysis.execute", "code.execute")` — the first is already
in `SAFE_PERMISSIONS`, the second is the Phase 0 code permission, so the tool is
reachable only by a workspace-bound actor with the right autonomy profile.

**Default off per run.** The finance agent does not get it unless the operator
enables it for that run (`RunRequest.analysisEnabled`, default `False`) — the same
"discovery is not activation" discipline the MCP layer applies to a server's tools.

Refusals, structured: `SANDBOX_UNAVAILABLE` (the Phase 3 honesty rule),
`ANALYSIS_NOT_ENABLED`, `IMPORT_NOT_ALLOWED` (a module outside the allowlist),
`INPUT_INVALID`, `OUTPUT_TOO_LARGE`, `TIMED_OUT`.

### 6.4 Artefacts

- Produced files are written to `.black-eclipse/artifacts/<runId>/` (gitignored).
- Each is referenced by `ArtifactRef { name, path, sha256, bytes, media_type }`.
  The **digest is the identity** — a re-run producing identical bytes produces the
  same digest, which is what makes §6.5 meaningful.
- A CSV/JSON/PNG artefact may be attached to the answer as a deliverable; a
  `.pyc`, a cache, or anything outside the declared output set is **not** collected.
- Artefacts are scoped to their run and profile (Phase 11 proves the isolation).

### 6.5 Reproducibility

Recorded on the result and persisted with it: the interpreter path (the vendored
interpreter — never `PATH`'s `python`), the source digest, the input digests, and
the resolved package-set digest. The gate is behavioural: the **same source, same
inputs, same package set ⇒ same output digest**. A result that cannot be re-derived
from the trace alone is a bug in this phase.

### 6.6 The shipped analysis recipes

Data, not prose — each a tested, named analysis the agent can reach for instead of
writing code from scratch, and each with its own `UNAVAILABLE` path:

| Recipe | Answers | Inputs |
|---|---|---|
| `returns_series` | "what did this do over time" | prices |
| `drawdown_profile` | "how bad was the worst fall, and how long" | prices |
| `correlation_matrix` | "are these moving together" | a table of returns |
| `contribution_to_return` | "what drove the result" | holdings + returns |
| `reconciliation` | "do these two sets agree, and where not" | two tables |
| `period_comparison` | "this quarter vs last" (via `research/comparability.py`) | two series |
| `scenario_shock` | "what if this fell 20%" | holdings + a shock |

Every recipe must (a) run in the sandbox, (b) declare its inputs, (c) **fail
honestly** when an input is absent rather than substituting a default, and (d)
carry the §6.2 provenance record.

## 7. Work items (ordered)

1. `docs/harness/roadmap/progress/phase-08-progress.md` with §9's gates.
2. `code/execution.py` — contracts (§6.1), the import allowlist check (a real
   inspection, using `ast` to walk imports — **never** `eval`/`exec` on the source
   string), limits, and `AnalysisResult`.
3. The `Provenance` type + the renderer change (§6.2) — write the **fail-closed**
   test first: a computed number with no provenance renders `UNAVAILABLE`.
4. `analysis_run` tool, default-off per run (§6.3).
5. Artefact collection + digests (§6.4).
6. Recipes (§6.6) with a test each, including the missing-input path.
7. `RunRequest.analysisEnabled` (default `False`) + front-door wiring.
8. UI: the computed/retrieved distinction (a label + the method line + the
   "how did you get this" affordance). Strings via i18n keys.
9. Tests: `test_analysis_execution.py`, `test_analysis_provenance.py`,
   `test_analysis_recipes.py`, `test_plain_language.py` (extended).
10. ADR-H110; `docs/CHANGELOG.md`; `docs/NAVIGATION.md`.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/code/execution.py` | new — execution contract, import allowlist, limits |
| `python/harness/code/recipes.py` | new — the shipped recipes (data + tests) |
| `python/harness/code/tools.py` | register `analysis_run` |
| `python/harness/schemas.py` | `RunRequest.analysisEnabled` (default False) |
| `python/harness/persistence.py` | additive `AnalysisRecord` (old-row-safe) |
| answer/receipt renderer | the computed vs retrieved distinction (§6.2) |
| `python/tests/test_analysis_*.py` | new |
| `src/lib/i18n/dictionaries/en.ts` (+ index) | new keys for computed labels |
| `docs/harness/decisions.md` | ADR-H110 |
| `docs/harness/roadmap/progress/phase-08-progress.md` | new |

## 9. Acceptance gates

```bash
# G1 — execution + limits
./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_execution.py -v

# G2 — the provenance rule, including the fail-closed case
./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_provenance.py -v
# expected: every output is kind=computed; a missing provenance record renders
#           UNAVAILABLE (never a bare number); no path yields kind=retrieved

# G3 — reproducibility: same source + inputs ⇒ same output digest
./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_execution.py -k reproducible -v

# G4 — a computed number cannot become a research claim
./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_provenance.py -k "not_evidence or receipt" -v
# expected: the receipt contains no computed leg; the only legal path is
#           re-expression through research/calculations.py

# G5 — an import outside the allowlist is refused, and network still fails
./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_execution.py -k "import or network" -q

# G6 — recipes, each with its honest missing-input path
./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_recipes.py -v

# G7 — the suite, the gate, and the plain-language gate
npm run test && npm run check:all
npx vitest run src/lib/i18n/plain-language.test.ts

# G8 — nothing else moved
git status --short        # jdds.db must NOT appear; .black-eclipse/artifacts/ is gitignored
```

| Gate | Assertion |
|---|---|
| G2 | Computed ≠ retrieved is structural: no execution can produce `retrieved`; a missing provenance record fails closed to `UNAVAILABLE`. |
| G3 | Two runs of the same source and inputs produce the same artefact digest; the interpreter and package digests are recorded. |
| G4 | A computed result never appears as a research claim; the receipt is unchanged by an analysis run. |
| G5 | `import os`/`socket`/`subprocess` refused by the allowlist inspection; a network call inside the sandbox fails. |
| G6 | Each recipe produces a plain, provenance-carrying result, and **asks** rather than guessing when an input is missing. |
| G7 | Full suite + gate green; the computation labels pass the plain-language gate. |
| G8 | No `*.db` change; artefacts confined to the gitignored directory. |

## 10. Definition of done

- Every gate run, raw output pasted, counts recorded.
- The fail-closed case (computed number with no provenance ⇒ `UNAVAILABLE`) is
  tested and passing — this is the phase's real deliverable.
- No code path produces `retrieved` from an execution (grep + test).
- `analysis_run` is off unless the run enables it.
- ADR-H110 written; CHANGELOG + NAVIGATION updated; `status:` flipped.

## 11. Implementation prompt (copy this to OpenCode)

```text
Task: Phase 8 — Analysis sandbox: computing, not just retrieving
(Eclipse-as-a-Harness roadmap).

Read first, in full:
- docs/harness/roadmap/phase-08-analysis-sandbox.md  (this phase, verbatim)
- docs/harness/roadmap/README.md  (invariants §3 incl. 3.4 "never fabricate")
- docs/harness/roadmap/phase-03-command-broker.md §6.2 (the sandbox you build on)
- python/harness/research/calculations.py ← the provenance shape to match
  (formula/version/input provenance + hard input guards)
- python/harness/research/claims.py       ← the validator a computed number may
  NOT bypass
- python/harness/research/comparability.py ← the gate that still applies
- python/harness/research/receipt.py       ← the receipt that must stay untouched
  by an analysis run
- python/harness/mcp/execution.py / manager.py ← the MCP provenance precedent
  (verification: external, eclipseVerified: false, source, retrievedAt, and the
  result labelled external in its text) — a computed result gets the SAME
  treatment with `computed`
- AGENTS.md ("Never fabricate financial data… UNAVAILABLE… always labeled")

Goal: let Eclipse COMPUTE reproducibly in the Phase 3 sandbox, with the result
labelled by where it came from, so a computed number can never be mistaken for a
retrieved one.

In scope:
1. code/execution.py per §6.1: IMPORT_ALLOWLIST (math/statistics/decimal/fractions/
   datetime/json/csv/itertools/functools/collections/typing/numpy/pandas),
   AnalysisInput (data passed as DATA, never interpolated into source),
   AnalysisRequest, AnalysisResult (source_digest, input_digests, interpreter,
   package_lock_digest, duration_ms, provenance).
2. The IMPORT CHECK MUST USE ast TO WALK IMPORTS — never eval/exec the source and
   never a regex over the raw string as the only guard.
3. The Provenance contract + the renderer change per §6.2, written FAIL-CLOSED:
   every execution output is kind="computed"; there is NO code path producing
   kind="retrieved" from an execution; a computed number WITHOUT a provenance
   record renders UNAVAILABLE (never a bare number). Retrieved numbers keep their
   existing source line. The two must be visually distinct at a glance.
4. A computed number CANNOT enter a research claim. The only legal path is
   re-expression through research/calculations.py, and it is explicit — never an
   automatic promotion. The receipt must be unchanged by an analysis run.
5. analysis_run tool: read_only=False,
   required_permissions=("analysis.execute","code.execute"); DEFAULT OFF per run
   (RunRequest.analysisEnabled default False); refusals SANDBOX_UNAVAILABLE /
   ANALYSIS_NOT_ENABLED / IMPORT_NOT_ALLOWED / INPUT_INVALID / OUTPUT_TOO_LARGE /
   TIMED_OUT.
6. Artefacts: .black-eclipse/artifacts/<runId>/, ArtifactRef with a sha256 digest
   as identity, only declared outputs collected; gitignored.
7. Reproducibility: record the VENDORED interpreter path (never PATH's python),
   source digest, input digests and resolved package-set digest. Behavioural gate:
   same source + inputs ⇒ same artefact digest.
8. code/recipes.py per §6.6 — returns_series, drawdown_profile, correlation_matrix,
   contribution_to_return, reconciliation, period_comparison (via
   research/comparability.py), scenario_shock. Each tested, each failing HONESTLY
   when an input is missing (ask the user; never substitute a default).
9. UI: the computed/retrieved distinction + a "how did you get this" affordance;
   new strings as i18n keys in src/lib/i18n/ (dictionaries/en.ts canonical,
   dictionaries/index.ts, translate.ts, use-t.ts) — never hardcoded.
10. Tests: test_analysis_execution.py, test_analysis_provenance.py,
    test_analysis_recipes.py, and extend python/tests/test_plain_language.py.
11. ADR-H110 in docs/harness/decisions.md (Decision / Why / Consequences shape).
12. docs/CHANGELOG.md dated entry + docs/NAVIGATION.md rows.

Non-goals (do NOT do these):
- No notebook UI, no cell execution, no REPL.
- No second research engine; no route by which a computed number becomes evidence
  without the explicit research/calculations.py path.
- No network in the sandbox; no imports outside the allowlist.
- No reading jdds.db except as data the run already holds.
- Never commit, push, or open a PR. Do not commit jdds.db.

Constraints:
- One runtime: analysis_run registers on the existing ToolRegistry and runs through
  the existing graph.
- Policy in code; the provenance rule is enforced in the renderer, NEVER in a prompt.
- New logic in new modules; keep graph.py/persistence.py/main.py under their ratchets.
- The user sees plain words ("worked out by Eclipse" + the period/method), never
  interpreter/module/argv/stdout/exit-code vocabulary.

Acceptance gates — run each and paste the RAW output into
docs/harness/roadmap/progress/phase-08-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_execution.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_provenance.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_execution.py -k reproducible -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_provenance.py -k "not_evidence or receipt" -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_execution.py -k "import or network" -q
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_analysis_recipes.py -v
  npm run test && npm run check:all
  npx vitest run src/lib/i18n/plain-language.test.ts
  git status --short

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```

---

**Next:** [Phase 9 — Finance application scaffold kits](./phase-09-scaffold-kits.md)
