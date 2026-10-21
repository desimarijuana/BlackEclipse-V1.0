---
title: "Phase 16 — Bounded Bulk Acquisition"
status: Done
phase: 16
depends_on: [13, 15]
unlocks: [18, 20]
last-verified: 2026-10-18
---

# Phase 16 — Bounded Bulk Acquisition

> **Progress (2026-10-13) — first slice shipped under ADR-H190.** Landed:
> `python/harness/acquire/` (`registry.py` with three REAL sources on the
> existing bridge capabilities — `price_history`, `macro_series`,
> `sec_filings`; `budget.py`; `writer.py`; `adapters.py`; `tools.py`), the
> `acquire` tool registered + allowlisted, the `data.collect` noun
> (`skills/permissions.py`, `code/policy.acquisition_grants`), the operator
> switch `acquisition_enabled` (eclipse-memory policy, default OFF;
> surface-dropped when off; handler fail-closed), and the collect authorizer
> seam. Tests: `python/tests/test_acquire.py` (9, hermetic). Repo-mapped
> deviations (recorded, per `AGENTS.md`): the transport is the existing
> read-only bridge (no new `fetch.py` HTTP path — R3-04's one-egress decision),
> the operator profile is the policy key above rather than a separate settings
> file, and the planned numbers for H120/H121 were long taken, so the decision
> is **ADR-H190**. **Cross-call accumulation + operator runbook + live smoke
> landed (2026-10-18):** `acquire.budget.RunUsage` is a run-scoped ledger carried
> on the tool context — every pull absorbs into it, the manifest carries BOTH
> budgets (`limits` + `limits.run`), and a later pull in the same turn is refused
> `RUN_LIMIT_REACHED` once the turn's ceiling is reached (env
> `HARNESS_ACQUIRE_RUN_MAX_{CALLS,ROWS,BYTES,SECONDS}`). The operator runbook
> `docs/harness/runbook-add-a-collection-source.md` documents one-row-one-adapter
> addition, and `test_live_macro_collection_through_the_real_bridge` (opt-in,
> `HARNESS_ACQUIRE_IT=1`) is the live smoke. **Remaining (not started):** SEC
> filing-LIST and operator-declared REST sources (both require NEW bridge
> capabilities in `data-bridge.ts` — a TS data-plane slice, not a Python row), and
> the chat manifest panel + `acquire.*` i18n keys (the tool text already carries
> the readable manifest: source, window, rows, completeness, licence).

> **Progress (2026-10-18) — the two remaining sources landed, exactly by the
> runbook (one capability + one row + one adapter + tests each).**
> **SEC filing-LIST** — `src/lib/harness/data-bridge-filings.ts`
> (`sec_filing_list`: the `data.sec.gov/submissions` index — form, filed,
> period, accession and the primary-document URL per filing; filters `form` /
> `date_from` / `date_to`; bounded at 1,000 filings per call with an explicit
> `truncated` + note; the cached SEC CIK map is the issuer authority, so an
> unknown ticker is `not_found` and a map read failure is `source_failure`) and
> the `filings_list` registry row (Python adapter in `acquire/adapters.py`:
> one call per symbol, rows
> `symbol, form, filed, period, accession, document, description`). **Operator-declared REST** — `src/lib/harness/data-bridge-datasets.ts`
> (`custom_dataset_records`: selects one dataset the operator declared in
> Settings → Data Sources, fills the connector's OWN declared parameters with
> caller `values` — never a URL/host/header/secret — and maps the response
> through the existing deterministic `mapResponseDetailed`; only a DECLARED
> dataset is reachable, an undeclared name is `not_found`; read-only — the
> bridge writes nothing) and the `operator_datasets` registry row (long rows
> `dataset, record, field, value`; a nested mapped value survives as JSON text,
> never a dropped field). Both capabilities are on the route whitelist
> (`src/app/api/harness/data/route.ts`) and dispatched through
> `src/lib/harness/data-bridge-extensions.ts` — `data-bridge.ts` is at its
> 1400-line ratchet and stays there (net zero). `recordCapabilityHealth` maps
> `sec_filing_list` to its own SEC route; operator dataset pulls are NOT
> recorded in the market-data ledger (the connector platform's own
> `DataConnector.healthState` owns that health). Python: `acquire/registry.py`
> rows + `acquire/adapters.py` collectors (`json` serializer for nested values),
> `tools.py` description, and `bridge.py` puts both capabilities in the slow
> network-timeout class (the front door's guarded transport may take longer than
> a vault read). Tests: `data-bridge-filings.test.ts` (6),
> `data-bridge-datasets.test.ts` (7, through the REAL custom-REST connector
> with a fake transport), route allowlist case, `test_acquire.py` +5.
> **Remaining (the only item left in this phase):** the chat manifest panel +
> `acquire.*` i18n keys (the tool text already carries the readable manifest:
> source, window, rows, completeness, licence).

> **Progress (2026-10-18) — the chat manifest panel landed; the phase is DONE.**
> The `acquire` tool now emits `acquire.completed` (the SAME manifest written
> beside the CSV — one contract, never a second rendering shape; best-effort,
> and a refusal emits nothing). The chat renders it through the new
> `src/components/chat/acquisition-panel.tsx` (source / window / rows /
> completeness chip / licence / attribution, glass system): a partial pull
> renders PARTIAL with its stated reason, an unknown row count renders honestly
> instead of a fabricated 0, and a blob that does not coerce renders nothing.
> The wire blob is narrowed by `src/lib/harness/acquisition-types.ts`
> (`coerceAcquisitionManifest` — completeness is structural: only a producer
> `true` reads Complete). `acquire.*` keys live in the domain dictionary
> `src/lib/i18n/dictionaries/acquire.ts`, spread into the ratcheted `en.ts`
> (the documented precedent, `dictionaries/analysis.ts`). Plumbing: the event
> rides the same seam as `analysis.completed` — Python `emit_code_event` →
> `src/lib/agent/events.ts` (`{kind: 'acquisition'}`) → `use-agent-run` turn →
> `Message.acquisition` (both message mappers) → chat-history. Tests:
> `test_acquire.py` (+2: the emitted event carries the manifest; a refusal emits
> none), `events.test.ts` (+2), `acquisition-types.test.ts` (4),
> `acquisition-panel.test.tsx` (4). **No planned items remain.** Verification
> (2026-10-18): eval gates ALL PASS (tasks=53), `npx tsc --noEmit` clean,
> vitest 3528/3529 (the pre-existing `graph-canvas.tsx` line-ending guard),
> full Python green except the documented pre-existing failure set.

| | |
|---|---|
| **Depends on** | Phase 13 (a bulk pull is only useful when the runtime can say which source won and how old it is) and Phase 15 (bulk data is a file in and a file out). |
| **Unlocks** | Phase 18 (a chart over 40 000 rows needs a bulk acquisition path to have rows) and Phase 20 (the gate grades the bounds). |
| **Estimated work** | 16–22 h of agent time. New capability with a new permission noun — the first phase since Phase 3 that adds one. |
| **Deliverable type** | one collection module + one acquisition tool + a declared source registry + a new permission surface. |
| **Decision records** | ADR-H120 (bulk acquisition is one bounded job with a declared source registry and a hard write ceiling), ADR-H121 (a new permission noun is required, and it is not `code.write`) |
| **Prompt to copy** | [§11 below](#11-implementation-prompt) |

---

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists](#2-why-this-phase-exists)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The source registry (data, one row per source)](#61-the-source-registry-data-one-row-per-source)
  - [6.2 The budget (beside `ResearchBudget`, not inside it)](#62-the-budget-beside-researchbudget-not-inside-it)
  - [6.3 The tool](#63-the-tool)
  - [6.4 The policy addition (the phase's decision)](#64-the-policy-addition-the-phases-decision)
  - [6.5 The manifest (what the user actually reads)](#65-the-manifest-what-the-user-actually-reads)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt](#11-implementation-prompt)

---

## 1. Goal

"Get me every filing for this sector", "collect the last two years of daily bars for
these 40 symbols", "pull the whole CPI series and the components" — a request for
**volume** rather than a single fact — is served by one bounded acquisition: an
explicit budget, a declared and screenable source set, a hard ceiling on how much is
written, honest partial results, and a data file the user can hold.

Today Eclipse answers such a request with four searches and eight fetches. That is
correct for an answer and useless for a dataset, and saying so is the honest
behaviour it currently lacks as a *capability*.

## 2. Why this phase exists

**(a) The retrieval budget is an answer budget, and it is global.** `research/budget.py`:

```python
@dataclass
class ResearchBudget:
    maxSearches: int = 4
    maxFetches: int = 8
    maxPages: int = 6
    maxSeconds: float = 90.0
    maxModelTokens: int = 24_000
```

`research/escalation.py` constructs it (`budget = budget or ResearchBudget()`) and
`research/run.py` too. So "collect the last two years of daily bars for 40 symbols"
can fetch at most 8 pages. The bound is right for a claim-verified answer; there is
no second budget for "the user asked for a dataset", and inventing one inside
`research/` would break the mandate/claims contract that Phase 4 froze.

**(b) The scraper machinery that could do this is on the other side of the
boundary, in TypeScript.** `src/lib/scraper/` ships `fetchers/` with `browser.ts`,
`http.ts`, `python.ts`, `scrapling.ts`, `tradingview.ts`, `yfinance.ts`,
`crypto.ts`, `psx-index.ts` and a `scheduler.ts` — eight fetcher shapes and a
scheduler, none of which the agentic runtime can call. The Python runtime's web
route is `retrieval/web.py::WebResearchSource`, which goes through the search/fetch
bridge capability and is bounded by (a). Nothing in the runtime knows what a
`fetcher` is or that a bulk pull exists as a concept: the vocabulary count is the
evidence, not an impression.

**(c) The analysis sandbox can compute but cannot acquire.** `code/execution.py`
constructs `sandbox_mod.RunSpec(..., network=False)` — verified in the tree — and
`IMPORT_ALLOWLIST` is:

```python
IMPORT_ALLOWLIST: tuple[str, ...] = (
    "math", "statistics", "decimal", "fractions", "datetime", "json", "csv",
    "itertools", "functools", "collections", "typing", "re", "random",
    "numpy", "pandas",
)
```

No HTTP client, no network. So a Monte Carlo over *downloaded* data cannot be built
inside Eclipse at all: the compute half exists, the acquisition half does not, and
the user is left to fetch the data themselves. That is exactly the report.

> **Superseded in part (2026-10-20, ADR-051).** The compute/acquire split still
> holds — `RunSpec(network=False)` is unchanged and the analysis sandbox still
> has no network. What changed is that the runtime can now **acquire** through a
> different door: the **scraper lane** (`docs/harness/scraper-lane.md`) runs a
> generated program whose only way out is the host-mediated `web_page` binding
> (the same `web_collect` capability `web_scrape` uses). The acquisition half
> therefore exists — for a site the user names, with the operator's per-domain
> consent — while the raw-network half still does not.

**(d) There is no permission noun for it.** `skills/permissions.py` holds
`SAFE_PERMISSIONS` (`data.read`, `research.read`, `analysis.execute`,
`report.generate`, `skill.invoke`, `portfolio.read`, `external.network`) and
`code/policy.py` holds `code.read`/`code.write`/`code.execute`/`command.execute`. A
bulk acquisition is not a file write (`code.write`) and not a single read
(`data.read`); forcing it into either makes the audit trail lie about what
happened. This is the phase's policy decision.

## 3. In scope

1. A **declared acquisition-source registry** as data: id, base host, what it
   serves, its licence/attribution, its rate ceiling, whether it needs a credential,
   and its effect class. Adding a bulk source is one row and one adapter — a test
   fails if a source has no row.
2. An **`AcquisitionBudget`** beside `ResearchBudget` (not inside it): max sources,
   max pages, max bytes written, max wall-clock, max rows; an explicit `exhausted`
   reason; a `snapshot()`.
3. One tool, `acquire`, registered on the existing registry, with the write ceiling
   enforced *in Python* — the model can ask for a scope, never for a byte count.
4. Output as an artifact on the existing per-run directory (Phase 15's serving
   routes hand it over): one `csv`/`jsonl` per source, plus a manifest naming
   source, window, row count, retrieval time and licence.
5. A **new permission noun `data.collect`** in `skills/permissions.py`, granted by a
   new autonomy-ish profile value and never by default; `code/policy.py` gains the
   corresponding `ACQUISITION_PROFILES` table, and the frozen constants
   (`PROTECTED_PATHS`, `WRITE_TOOLS`, `AUTONOMY_PROFILES`) are not edited.
6. Honest partial results: a source that fails mid-pull yields the rows already
   collected plus a stated failure, and the manifest marks the file partial. Never
   a silently short file.
7. Tests: the bounds are adversarial (an over-budget request is blocked **and
   recorded**), the registry is exhaustive, a missing credential refuses, and a
   partial pull is distinguishable from a complete one.

## 4. Who can use it (the non-expert obligation)

The user here is a research analyst, a quant, a student building a project — someone
who needs a dataset and would otherwise write a script. They must never meet a
fetcher, a rate limit, a byte cap or a licence field as *instructions*. What they
see:

- Ask in the language of the job: "get me the last two years of daily prices for
  these", "collect every filing in this sector".
- When the request exceeds what Eclipse may collect, the answer names **what it can
  do** and the reason in one sentence, then offers the smaller pull — never "budget
  exhausted".
- The manifest is readable: "Source: SEC filings · Window: 2024-01-01 to 2026-06-30
  · 1 284 rows · collected 2026-10-02 14:10 · licence: public domain". A machine
  field name never appears.
- Attribution is surfaced wherever the data is, because the licence row is part of
  the registry, not a footnote.

Strings live in the i18n layer under `acquire.*`; the mechanism denylist applies.

## 5. Non-goals (do not do these)

- **No unbounded crawler, no site mirroring, no HTML scraping of a whole domain.**
  Each source declares a bounded, parameterized query.
- **No credential the operator has not stored.** A source needing a key refuses with
  a pointer to Settings; it never reads an env var directly.
- **No bypass of `robots`/rate policy.** The per-source rate ceiling is enforced in
  code with a token bucket, and the SSRF guard (`mcp/ssrf.py`, mirrored from
  `src/lib/api-guard.ts`) applies to every outbound call.
- **No change to `research/budget.py` or the escalation ladder.** This phase *adds*
  a budget beside it; the claim-verified answer path is untouched.
- **No network inside the analysis sandbox.** `RunSpec(network=False)` stays; the
  acquisition is a separate tool that writes files the sandbox then reads as inputs.
- **No new database table for the data.** Files on the existing artifact convention
  plus a manifest; `prisma/` and `jdds.db` are untouched.
- Never commit, push or open a PR; do not commit `jdds.db`.

## 6. Exact contracts to create

### 6.1 The source registry (data, one row per source)

```python
# python/harness/acquire/registry.py
@dataclass(frozen=True)
class AcquisitionSource:
    id: str                      # stable, the manifest uses it
    label: str                   # plain words for the manifest and the surfaces
    base_host: str               # the ONLY host this source may reach
    serves: tuple[str, ...]      # data types it can produce (aligned with retrieval DataType)
    query_params: tuple[str, ...]  # the parameters the tool may pass — a CLOSED set
    rate_per_minute: int
    max_rows_per_call: int
    requires_secret: Optional[str]  # a PROVIDER_KEYS id, or None
    licence: str
    attribution: str
    effect: Literal["read", "write"]

SOURCES: dict[str, AcquisitionSource] = {
    "sec_filings_bulk": AcquisitionSource(
        id="sec_filings_bulk", label="Company filings",
        base_host="efts.sec.gov",
        serves=("financial_statements",),
        query_params=("cik", "form_type", "date_from", "date_to"),
        rate_per_minute=10, max_rows_per_call=200,
        requires_secret=None, licence="public domain",
        attribution="U.S. Securities and Exchange Commission",
        effect="read",
    ),
    "prices_daily": AcquisitionSource(
        id="prices_daily", label="Daily price history",
        base_host="query1.finance.yahoo.com",
        serves=("historical_prices",),
        query_params=("symbol", "interval", "date_from", "date_to"),
        rate_per_minute=60, max_rows_per_call=5_000,
        requires_secret=None, licence="vendor terms — see attribution",
        attribution="Yahoo Finance (unofficial endpoint)",
        effect="read",
    ),
    # macro series, exchange index series, and the operator's custom REST
    # connector as an explicitly declared source. One row each; a source
    # without a row is not usable.
}
```

### 6.2 The budget (beside `ResearchBudget`, not inside it)

```python
# python/harness/acquire/budget.py
@dataclass
class AcquisitionBudget:
    max_sources: int = 3
    max_calls: int = 60
    max_rows: int = 50_000
    max_bytes_written: int = 20 * 1024 * 1024
    max_seconds: float = 600.0
    calls: int = 0
    rows: int = 0
    bytes_written: int = 0
    started_at: float = field(default_factory=time.monotonic)
    exhausted: Optional[str] = None   # "maxRows" | "maxBytesWritten" | "maxSeconds" | ...
    attempted: list[str] = field(default_factory=list)

    def allow_call(self, source: AcquisitionSource) -> bool: ...
    def record_rows(self, n: int) -> None: ...      # sets `exhausted` at the ceiling
    def record_bytes(self, n: int) -> None: ...
    def snapshot(self) -> dict[str, Any]: ...
```

The **byte ceiling is enforced here, in Python**, at each flush — a model-chosen
row count or a single huge response cannot exceed it, because the writer stops and
marks the file partial at the ceiling.

### 6.3 The tool

```python
# python/harness/acquire/tools.py
class AcquireInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str                                  # a registry id; unknown ⇒ refuse
    purpose: str = Field(..., max_length=300)
    params: dict[str, str | int] = Field(default_factory=dict)  # validated against
                                                 # source.query_params — closed set
    symbols: list[str] = Field(default_factory=list, max_length=50)

async def acquire(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Collect a dataset from ONE declared source within the acquisition budget.

    Refuses (with a stable code and one plain sentence) when: the source is unknown
    or unconfigured, a required secret is missing, the request exceeds the row or
    byte ceiling, the actor does not hold `data.collect`, or no artifact directory is
    available. Writes at most the ceiling, marks a partial file as partial, and
    records every call in the run's ledger.
    """
```

Registered exactly like the existing tools — `registry.register(ToolDefinition(...))`
in a new `register_acquisition_tools`, called from `service.py` beside
`register_code_tools`. Listed in `agents.CODE_AGENT` and in the chat code profile
(Phase 14), **not** in `ECLIPSE_AGENT`'s declared list unless the permission gate
passes; the allowlist is the boundary, per README §3.2.

### 6.4 The policy addition (the phase's decision)

```python
# python/harness/code/policy.py — ADDITIVE. The frozen constants are not edited.
ACQUISITION_PROFILES: tuple[str, ...] = ("none", "declared_sources")

# A profile grants the collection verb for sources that HAVE a registry row and do
# not require a secret; a credentialed source additionally needs the operator's
# setting present at call time.
_ACQUISITION_GRANTS: dict[str, frozenset[str]] = {
    "none": frozenset(),
    "declared_sources": frozenset({"data.collect"}),
}

def acquisition_grants(profile: str) -> frozenset[str]:
    """Unknown profile → nothing (fail-closed, like `code_grants`)."""
    return _ACQUISITION_GRANTS.get(profile, frozenset())
```

`data.collect` is added to `skills/permissions.py`'s vocabulary as a **new noun**,
is **not** in `SAFE_PERMISSIONS`, and is not grantable through `OPERATOR_PERMISSIONS`
alone — it comes only from the acquisition profile, which an operator sets.

### 6.5 The manifest (what the user actually reads)

```json
{
  "purpose": "two years of daily bars for the watchlist",
  "collectedAt": "2026-10-02T14:10:33Z",
  "sources": [
    {
      "id": "prices_daily", "label": "Daily price history",
      "window": { "from": "2024-01-01", "to": "2026-06-30" },
      "rows": 4821, "file": "prices_daily.csv",
      "complete": false, "stoppedReason": "reached the collection limit (50 000 rows)",
      "licence": "vendor terms — see attribution",
      "attribution": "Yahoo Finance (unofficial endpoint)"
    }
  ],
  "limits": { "maxRows": 50000, "rowsUsed": 4821 }
}
```

`complete: false` plus a stated reason is the contract: a partial dataset is never
presented as the dataset.

## 7. Work items (ordered)

1. `python/harness/acquire/registry.py` — the registry + a test asserting every
   entry declares a host, a closed param set, a rate and a licence.
2. `python/harness/acquire/budget.py` — `AcquisitionBudget` + its bounds tests.
3. `python/harness/acquire/writer.py` — the ceiling-enforcing writer (csv/jsonl,
   partial marking, byte accounting). Pure, testable without network.
4. `python/harness/acquire/fetch.py` — the bounded HTTP path: the SSRF guard first,
   the token bucket, the closed parameter set, one host per source.
5. `python/harness/acquire/tools.py` — `acquire` + `register_acquisition_tools`.
6. `python/harness/service.py` — one registration line; `agents.py` — the allowlists.
7. `python/harness/skills/permissions.py` — the `data.collect` noun;
   `python/harness/code/policy.py` — `ACQUISITION_PROFILES` + `acquisition_grants`.
8. `python/tests/test_acquire.py` (+ `_bounds.py`, `_registry.py`, `_partial.py`) —
   offline, with a stubbed fetch; plus one opt-in live smoke, never in CI.
9. `en.ts` — `acquire.*`; the manifest renderer keys.
10. `src/components/chat/` — render the manifest as a readable panel (source, window,
    rows, completeness, licence) using the existing evidence-panel shape.
11. `docs/harness/roadmap/progress/phase-16-progress.md` — created, gates unchecked.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/acquire/registry.py` | new — the declared source registry |
| `python/harness/acquire/budget.py` | new — the acquisition budget |
| `python/harness/acquire/writer.py` | new — the ceiling-enforcing writer |
| `python/harness/acquire/fetch.py` | new — the bounded HTTP path |
| `python/harness/acquire/tools.py` | new — the `acquire` tool + registration |
| `python/harness/service.py` | changed — one registration line |
| `python/harness/agents.py` | changed — the allowlists |
| `python/harness/skills/permissions.py` | changed — the `data.collect` noun |
| `python/harness/code/policy.py` | changed — additive profiles/grants only |
| `src/components/chat/acquisition-panel.tsx` | new — the manifest surface |
| `src/lib/i18n/dictionaries/en.ts` | changed — `acquire.*` |
| `docs/harness/decisions.md` | changed — ADR-H120, ADR-H121 |
| `docs/harness/runbook-add-a-collection-source.md` | new — one row + one adapter |

## 9. Acceptance gates

```bash
# G1 — bounds are enforced AND recorded (adversarial).
./scripts/vendor/python/python.exe -m pytest python/tests/test_acquire_bounds.py -v

# G2 — the registry is exhaustive and declared.
./scripts/vendor/python/python.exe -m pytest python/tests/test_acquire_registry.py -v

# G3 — a partial pull is distinguishable from a complete one.
./scripts/vendor/python/python.exe -m pytest python/tests/test_acquire_partial.py -v

# G4 — the permission is not default and not reachable otherwise.
./scripts/vendor/python/python.exe -m pytest python/tests/test_acquire_permission.py -v

# G5 — the frozen constants and the claim path are untouched.
git diff --stat python/harness/research/ prisma/ jdds.db
./scripts/vendor/python/python.exe -m pytest python/tests/test_research_escalation.py -q

# G6 — the full release gate.
npm run check:all
```

| Gate | Assertion |
|---|---|
| G1 | Each of these is **blocked and recorded**: a request above `max_rows`; a source whose response would exceed `max_bytes_written`; a call after `max_seconds`; an unknown source id; a parameter outside the source's closed set; a host other than `base_host`; a request from an actor without the profile. Each produces a stable refusal code, one plain sentence, and a ledger row — a block with no record is a failure. |
| G2 | Every `AcquisitionSource` declares a label, a host, a closed param set, a rate, a row ceiling, a licence and an attribution; every source that names `requires_secret` resolves through `PROVIDER_KEYS`; adding a source without a registry row is impossible (the registry IS the gate). |
| G3 | A pull stopped at the ceiling writes a file whose manifest entry has `complete: false` and a `stoppedReason` in plain words; a pull that finished has `complete: true`; the row count in the manifest equals the file's real line count (asserted by reading the file, not by trusting the counter). |
| G4 | The default actor holds no `data.collect`; `acquisition_grants("none")` and an unknown profile both return the empty set; the tool is refused before its handler runs when the profile is absent. |
| G5 | `research/` is byte-unchanged by this phase (`git diff --stat` empty for it); `prisma/` and `jdds.db` unmodified; the escalation suite still passes unchanged. |
| G6 | `ALL GATES PASSED`; vitest and pytest counts reported as observed. |

**A gate not run is a gate not passed.** Paste the raw output of each into
`docs/harness/roadmap/progress/phase-16-progress.md`.

## 10. Definition of done

- One declared registry; a source with no row is unusable, and a row without a
  licence is a test failure.
- The budget bounds writes, not just requests — a huge response cannot exceed the
  byte ceiling.
- A partial dataset is never presented as complete, in the manifest or on the
  surface.
- `data.collect` is a real noun, default-denied, granted only by an explicit
  operator-set profile, and the audit trail names it.
- The claim-verified research path is byte-unchanged.
- ADR-H120 and ADR-H121 written; changelog appended; NAVIGATION updated with the
  registry row and the runbook; `status:` and the index row flipped.

## 11. Implementation prompt

```text
Task: Phase 16 — bounded bulk acquisition.

Read first, in full:
- docs/harness/roadmap/phase-16-bulk-acquisition.md (this file, verbatim)
- docs/harness/roadmap/README.md (§3 invariants — especially §3.2 prose is not a
  boundary and §3.4 never fabricate — and §6 non-goals)
- python/harness/research/budget.py and research/escalation.py (what you must NOT change)
- python/harness/code/{policy.py,sandbox.py,execution.py} (the policy-authority and
  bounded-execution patterns to mirror)
- python/harness/skills/permissions.py (the permission vocabulary)
- python/harness/mcp/ssrf.py + src/lib/api-guard.ts (the outbound guard you must reuse)
- python/harness/service.py (the ONE registry assembly point)

Goal: a request for a DATASET is served by one bounded, declared, attributable
acquisition that writes a file the user can hold — never by exhausting the
four-search answer budget and calling it research.

In scope: §3 items 1–7 and the ordered work items in §7. Implement exactly those.

Non-goals (do NOT do these):
- No unbounded crawler, no site mirroring. Every source declares a bounded,
  parameterized query in a CLOSED parameter set.
- No direct env-var credential read; a source needing a key refuses and points at
  Settings. Secrets resolve through PROVIDER_KEYS.
- No robots/rate bypass; the per-source token bucket and the SSRF guard are mandatory
  on every outbound call.
- Do NOT modify research/budget.py, research/escalation.py or the mandate/claims
  contract. ADD a budget beside it.
- Do NOT allow network in the analysis sandbox (RunSpec(network=False) stays).
- No new database table. Files on the existing artifact convention plus a manifest.
- Do NOT edit the frozen constants in code/policy.py (AUTONOMY_PROFILES,
  PROTECTED_PATHS, WRITE_TOOLS). Additions only. If a frozen constant appears to need
  a change, STOP and report it.
- Never commit, push or open a PR. Do not commit jdds.db.

Constraints:
- One runtime: register on the existing registry from service.py; driven by the
  existing execute_run. No second loop.
- The write ceiling is enforced in Python at each flush, never by trusting a
  model-supplied count.
- Every user-facing string is an i18n key; the mechanism denylist applies. The
  manifest names sources in plain words and always carries the licence.
- Measure before implementing; a corrected audit is a valid outcome. Do not weaken
  any existing test — name every changed expectation with old and new value.

Acceptance gates — run each from Black-Eclipse-site/ and paste the RAW output into
docs/harness/roadmap/progress/phase-16-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_acquire_bounds.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_acquire_registry.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_acquire_partial.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_acquire_permission.py -v
  git diff --stat python/harness/research/ prisma/ jdds.db          # expect empty
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_research_escalation.py -q
  npm run check:all

Finish by stating: "docs updated: <files>" or "no doc change — <reason>", plus one
honest non-property: what you did NOT verify.
```

---

**Next:** [Phase 17 — Working on a Cadence](./phase-17-working-on-a-cadence.md)
