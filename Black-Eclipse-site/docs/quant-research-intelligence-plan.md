---
title: Quant Research Intelligence — implementation specification
status: Current
last-verified: 2026-11-10
---

# Quant Research Intelligence — implementation specification

**Who this is for:** the OpenCode agent (or engineer) implementing the evolution of
Quant Mode from a quantitative *execution* protocol into a research-driven
*discovery and development* system.

**The one rule:** reuse the existing runtime. Eclipse already has a deterministic
quant engine, a method-discovery package, a web-research engine with citations,
an artifact center, a model catalog and an experiment store. This work adds a
research layer on top of them. It must not create a second agent, a second model
provider, a second database, a second research engine, or a second UI.

**Status of every name below:** implemented unless the file it names does not
exist in the repository. This document was written as a plan and then shipped in
one pass; §0 records what actually landed, what it cannot do yet, and where the
tests are.

---

## 0. What shipped (2026-11-10)

The research layer lives in `python/harness/quant/research_intel/` (deliberately
not `quant/research/`, because `quant/research.py` already owns the shared
research-result envelope).

| Concern | File |
|---|---|
| Method-spec contract + validation | `quant/research_intel/schema.py` |
| Open, horizon-wide method catalog (33 seeds, sourced equations) | `quant/research_intel/catalog.py` |
| Literature, methods, relationships, implementations, reproductions, dossiers | `quant/research_intel/store.py` |
| Deterministic research query planner | `quant/research_intel/query_planner.py` |
| Scholarly search + dedupe + citation metadata over the existing connectors | `quant/research_intel/scholarly.py` |
| Section/equation extraction with page provenance | `quant/research_intel/extraction.py` |
| Span-checked model proposal | `quant/research_intel/llm_extract.py` |
| Explained suitability scoring (horizon-aware) | `quant/research_intel/suitability.py` |
| Reproduction harness + validation matrix + isolated generic worker | `quant/research_intel/repro.py`, `implementation.py`, `implementation_worker.py` |
| Computed research figures | `quant/research_intel/visuals.py` |
| Quant Research Dossier + artifact registration | `quant/research_intel/dossier.py` |
| Agent tools (16) | `quant/research_intel/tools.py` |
| HTTP routes | `routers/quant_research.py` |
| Research panel | `src/components/screens/strategy-studio/research-intelligence-panel.tsx` |

Wiring: `quant/bootstrap.py` seeds the catalog; `quant/tools.py` registers the
tools and adds them to `QUANT_TOOLS`; `agents.py` therefore exposes them;
`main.py` includes the router; `model_catalog.py` gained `method` and `dossier`
kinds.

### Honest limits of this version

- **Sources.** OpenAlex, Semantic Scholar, Crossref, arXiv and the web fallback
  are first-class. SSRN, NBER and RePEc are searched directly and their pages are
  fetched when the source permits. Open-access PDF links from OpenAlex and
  Semantic Scholar are stored and used first. A source that blocks automated
  access returns `unavailable` with a reason; no scraper bypasses a block.
- **Reproduction has 12 built-in estimators plus ANY registered implementation.**
  `quant_attach_implementation` tests a Python `run(rows, params)` in isolation
  and attaches it only on a passing test. The worker uses Docker when
  `HARNESS_QUANT_SDK_DOCKER_IMAGE` is set; otherwise it uses a separate process
  with a scrubbed environment, a timeout and an output cap. The result states
  which isolation ran.
- **Extraction is deterministic plus optional span-checked model proposal.** A
  proposed field is accepted only when its quote is in the document. A field
  without a quote is rejected and named.
- **Citation edges use provider metadata.** Semantic Scholar references are
  stored; an empty edge set means the provider disclosed none.
- **Dossiers are only as complete as the evidence supplied.** Missing
  literature, reproduction or validation is listed in `missing` and rendered in
  the dossier's Limitations section.
- **The research panel can search and extract.** It does not run a long
  background job; the existing `research_start` tools do that.
- **A figure is computed, never evidence.** Every research figure carries its
  source and the chart contract still marks it non-evidence.
- **Live order routing stays disabled.** This is a safety boundary, not a
  technical gap. Paper deployment remains the only deployment mode.

### Tests

`python/tests/test_quant_research_intel.py`,
`test_quant_research_intent.py`, `test_quant_research_routes.py`; QuantBench
cases `route-research-*`, `math-research-*`. The bench is run with
`python -m harness.quant_bench` (or `npm run test:quant-bench`).

Reusable prompts for the agent and for an external extraction model live in
`docs/quant-research-prompts.md`. The base system prompt also carries the
research rules (`python/harness/prompts.py` › "Quant research").

---

## 1. Goal and non-goals

### Goal

A trader can state a research problem in natural language and Eclipse can:

1. frame the problem,
2. check what already exists (internal method KB + model catalog),
3. search external literature and published implementations,
4. extract the actual mathematics, assumptions and limitations,
5. compare candidate methods with an explained suitability assessment,
6. acquire/verify the required data,
7. reproduce the method separately from any trading adaptation,
8. test statistical properties, out-of-sample behaviour and costs,
9. register a reusable, versioned method/model, and
10. produce a **Quant Research Dossier** that links every claim to a source and
    every number to an experiment.

### Non-goals

- Not a new agent, not a new LLM, not a new chat surface.
- Not a promise that published research is profitable. A method can be
  mathematically established, reproduced, and still fail as a trading edge.
- Not unrestricted web browsing by the LLM. Research goes through typed,
  provenance-preserving connectors and tools.
- Not a replacement for `python/harness/quant/` computation or for the existing
  validation engines.
- Not live trading. Deployment remains paper-only.

---

## 2. Mandatory repository inspection (do this first)

Read these before writing code. Do not infer behaviour from this document when
the source is available.

### Runtime and registration
- `python/harness/service.py` — service construction and layer installation.
- `python/harness/quant/bootstrap.py` — `install_quant_layer`, the ONE registry.
- `python/harness/quant/tools.py` — `ToolDefinition` pattern, `QUANT_TOOLS`.
- `python/harness/quant/discovery_tools.py` — tool + registration pattern.
- `python/harness/model_catalog.py` — the unified read across stores.
- `python/harness/agents.py` — `WEB_RESEARCH_TOOLS`, `QUANT_TOOLS`, allowlists.
- `python/harness/main.py` — router includes.
- `python/harness/routers/quant.py`, `routers/quant_desk.py`,
  `routers/quant_reports.py` — route + operator-gating pattern.
- `python/harness/tools.py` — `ToolContext`, permission/risk/timeout fields.

### Research, evidence and documents (REUSE, do not rebuild)
- `python/harness/research/web_tools.py` — `academic_search`, `web_search`,
  `web_extract`, `page_extract`, `pdf_extract`, `structured_extract`,
  `research_plan`, `research_query`, `research_start/status/continue/cancel`,
  `claim_verify`, `citation_extract`, `citation_validate`, `research_quality`.
- `python/harness/research/web_store.py` — `WebResearchRun/Source/Evidence/
  Claim/Citation/Conflict/Validation/Snapshot/Entity/Relation` on `agent-memory.db`.
- `python/harness/research/engine.py` — `run_research` and the orchestration loop.
- `python/harness/research/web_providers.py` — `SearchProviderRegistry`,
  `ConnectorSearchProvider`; academic connectors are reached through the bridge.
- `src/lib/harness/data-bridge-education.ts` and `src/lib/web-connectors.ts` —
  front-door OpenAlex/Crossref/arXiv connectors.
- `src/lib/education-connectors.ts` — GitHub search connector.

### Quant engine and persistence (REUSE)
- `python/harness/quant/store.py` — idempotent additive DDL on the ONE
  `agent-memory.db`; `QuantMethod`, `QuantResearchSession`, `QuantHypothesis`,
  `QuantTrial`, `QuantExperiment`.
- `python/harness/quant/dataset_store.py` — `ResearchDataset` +
  `ResearchDatasetVersion` (content hash + manifest + artifact).
- `python/harness/quant/manifest.py` — run manifests and reproducibility.
- `python/harness/quant/discovery/` — taxonomy, library, diagnostics,
  hypotheses, synthesize, miner.
- `python/harness/quant/{engine,validation,multiple_testing,walkforward,
  montecarlo,robustness,verdict,edge_report}.py` — the validation suite.
- `python/harness/quant/sdk_runtime.py`, `sdk_worker.py` — isolated execution.
- `python/harness/artifacts/service.py`, `model.py`, `tools.py` — the Artifact
  Center and `RegisterArtifactInput`.
- `python/harness/quant_intent.py` — classifier, protocol, surface narrowing,
  `evaluate_quant_outcome`, `finalize_quant_text`.
- `python/harness/quant_bench/cases.py`, `eval_gates/quant_contract.py` —
  acceptance-test scaffolding.
- `docs/quant-engine.md`, `docs/quant-method-discovery.md`,
  `docs/harness/web-research-engine.md`, `docs/harness/research-surfaces.md`,
  `docs/harness/artifact-center.md`, `docs/harness/tool-registry.md` (if present).

### Commands to run before and after
```bash
cd Black-Eclipse-site
npx tsc --noEmit
npm run test
npm run test:quant-bench
npm run check:size
node scripts/generate-tool-registry.js   # after adding tools
```

---

## 3. Reuse map (explicit)

| Need | Existing capability | Decision |
|---|---|---|
| Paper/web discovery | `academic_search`, `web_search`, `research_plan` | Reuse; add a scholarly query planner and more connectors, not a new search stack |
| Document retrieval/parsing | `web_extract`, `page_extract`, `pdf_extract`, `structured_extract` | Reuse; add equation-aware extraction on top |
| Evidence, claims, citations | `WebResearch*` tables + `claim_verify`/`citation_*` | Reuse; link methods to `WebResearchSource` ids |
| Long-running research | `research_start/status/continue/cancel` | Reuse; do not add a second job system |
| Internal methods | `quant/discovery/taxonomy.py`, `library.py` | Extend to a method knowledge base; do not create a parallel catalog |
| Method fit | `recommend_methods` | Extend scoring with evidence/reproduction dimensions |
| Hypotheses + trials | `QuantResearchSession`/`QuantHypothesis`/`QuantTrial` | Reuse for research lineage |
| Data | `DatasetStore` (`ResearchDatasetVersion`) | Reuse; never copy bars into a new store |
| Experiments | `QuantExperiment` + manifests + artifact files | Reuse |
| Execution isolation | `run_python_strategy` / `sdk_runtime` worker | Reuse for reproduction code |
| Validation | OOS, bootstrap, multiple testing, walk-forward, Monte Carlo, robustness, verdict | Reuse |
| Reports | `edge_report.py`, `report_export.py` | Reuse; the dossier composes them |
| Artifacts | `ArtifactService.register` | Reuse for dossiers, papers, code, reports |
| Catalog | `model_catalog` | Extend to include methods and dossiers |
| Routing | `quant_intent.py` | Extend kinds/tiers; no new agent |
| UI | Chat + Strategy Studio panels | Extend chat protocol and an existing panel; no new top-level tab |

**Hard reuse rule:** if a capability above already exists, the implementation is
an *extension* (new fields, new tool, new route) — not a new module that
duplicates it. A PR that creates a second evidence store, search registry,
backtest engine or artifact store is rejected.

---

## 4. Target module layout

Create only what has no existing owner. Suggested (names are contracts, file
count is intentionally small):

```
python/harness/quant/
  research_intel/         # NOT `research/` — that module name is already taken
    __init__.py
    schema.py             # MethodSpec contract + validation
    catalog.py            # seeded method knowledge base
    store.py              # additive DDL + repository methods
    query_planner.py      # problem -> deterministic query set (no LLM required)
    scholarly.py          # existing-connector search + dedupe + citations
    extraction.py         # paper text -> sections/equations provenance
    suitability.py        # explained method-vs-problem scoring
    repro.py              # reproduction harness + validation matrix
    dossier.py            # assembles the Quant Research Dossier artifact
    tools.py              # research/method tool definitions + registration
```

Rules:
- `quant/research_intel/store.py` owns only its tables, on the ONE
  `agent-memory.db` connection passed by `QuantStore`. It never opens a DB.
- `quant/research_intel/tools.py` registers through the existing registry in
  `quant/bootstrap.py`. Do not register on a new registry.
- `quant/research_intel/repro.py` calls the existing isolated worker. Never execute
  paper-derived code in the API process.
- `suitability.py` extends the existing `recommend_methods` logic rather than
  duplicating its factor table.

---

## 5. Data model

All DDL is idempotent `CREATE TABLE IF NOT EXISTS`, additive, on
`agent-memory.db`. Never `jdds.db`, never a new file.

### 5.1 Extend, do not duplicate

`QuantMethod` gains columns via the existing `_ensure_column` pattern:

| Column | Type | Meaning |
|---|---|---|
| `version` | TEXT | method-spec semver |
| `aliasesJson` | TEXT | alternative names |
| `objectiveJson` | TEXT | research objectives it serves |
| `mathSpecJson` | TEXT | equations, variables, units |
| `inputsJson` | TEXT | required data and frequency |
| `parametersJson` | TEXT | parameter domains / estimation |
| `assumptionsJson` | TEXT | statistical and market assumptions |
| `limitationsJson` | TEXT | known failure conditions |
| `provenanceJson` | TEXT | literature ids, code ids, extraction confidence |
| `implementationStatus` | TEXT | `none|specified|implemented|tested` |
| `reproductionStatus` | TEXT | `none|attempted|reproduced|failed|inconclusive` |
| `lifecycleStatus` | TEXT | `proposed|reviewed|specified|implemented|reproduced|evaluated|validated|failed` |
| `confidence` | TEXT | `low|medium|high` for *evidence*, not profit |

Do not add a second `QuantMethodV2` table.

### 5.2 New tables

```sql
CREATE TABLE IF NOT EXISTS QuantLiterature (
  id TEXT PRIMARY KEY,              -- lit_...
  researchId TEXT,                  -- WebResearchRun.researchId when part of a run
  sourceId TEXT,                    -- WebResearchSource.sourceId when known
  doi TEXT, arxivId TEXT, openalexId TEXT, s2Id TEXT,
  title TEXT NOT NULL,
  authorsJson TEXT, year INTEGER, venue TEXT,
  abstract TEXT, url TEXT, pdfUrl TEXT,
  license TEXT, accessStatus TEXT,  -- open|restricted|unknown
  contentHash TEXT,
  createdAt TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_qlit_doi ON QuantLiterature(doi);
CREATE INDEX IF NOT EXISTS idx_qlit_research ON QuantLiterature(researchId);

CREATE TABLE IF NOT EXISTS QuantMethodRelationship (
  id TEXT PRIMARY KEY,
  fromMethodId TEXT NOT NULL,
  toMethodId TEXT NOT NULL,
  relation TEXT NOT NULL,           -- alternative|extends|critiques|depends_on|composes_with
  note TEXT,
  literatureId TEXT,
  createdAt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qmr_from ON QuantMethodRelationship(fromMethodId);

CREATE TABLE IF NOT EXISTS QuantMethodPaper (
  methodId TEXT NOT NULL,
  literatureId TEXT NOT NULL,
  role TEXT NOT NULL,               -- origin|extension|critique|application
  PRIMARY KEY (methodId, literatureId, role)
);

CREATE TABLE IF NOT EXISTS QuantMethodImplementation (
  id TEXT PRIMARY KEY,
  methodId TEXT NOT NULL,
  version TEXT NOT NULL,
  language TEXT NOT NULL DEFAULT 'python',
  codeArtifactId TEXT,
  workerRunId TEXT,
  testStatus TEXT,                  -- none|passing|failing
  createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS QuantReproduction (
  id TEXT PRIMARY KEY,
  methodId TEXT NOT NULL,
  implementationId TEXT,
  datasetId TEXT, datasetVersion TEXT,
  experimentId TEXT,
  publishedBenchmarkJson TEXT,
  observedMetricsJson TEXT,
  fidelityJson TEXT,                -- per-metric comparison + reasons
  status TEXT NOT NULL,             -- reproduced|partial|failed|inconclusive
  createdAt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS QuantResearchDossier (
  id TEXT PRIMARY KEY,
  sessionId TEXT,
  researchId TEXT,
  title TEXT NOT NULL,
  question TEXT NOT NULL,
  status TEXT NOT NULL,             -- draft|complete|partial
  artifactId TEXT,                  -- Artifact Center id
  dossierJson TEXT NOT NULL,
  createdAt TEXT NOT NULL
);
```

Link, don't duplicate:
- papers/evidence → `WebResearchSource`/`WebResearchEvidence` ids;
- datasets → `ResearchDataset`/`ResearchDatasetVersion`;
- experiments/trials → `QuantExperiment`/`QuantTrial`;
- code/reports → Artifact Center ids;
- hypotheses → `QuantHypothesis`.

---

## 6. Tool contracts

Register on the ONE registry from `quant/bootstrap.py`. Follow the existing
`ToolDefinition(name, description, input_schema, handler, permission, risk,
timeout_ms)` shape. Read tools are `permission="read"`, `risk="low"`; the one
write tool is `permission="write"`, `risk="medium"`. Long jobs are
`long_running=True` or delegate to `research_start`.

| Tool | Input (required in bold) | Returns | Notes |
|---|---|---|---|
| `research_search_papers` | **query**, sources[], yearFrom, yearTo, limit | `{literature: [...], diagnostics}` with stable ids | Dedupes DOI/arXiv/title; never fabricates a paper |
| `research_get_paper` | **literatureId** or **doi** | metadata, access status, extracted section ids | Refuses when full text is inaccessible |
| `research_get_citations` | **literatureId**, direction (`references|citing|both`), depth | nodes + edges | Uses scholarly metadata, not guesses |
| `research_extract_method` | **literatureId**, methodHint? | `MethodSpecDraft` + per-field provenance + `unresolved[]` | Markdown/LaTeX only; no code execution |
| `research_compare_methods` | **methodIds[]** or objective+constraints | comparison matrix + explained fit + caveats | Deterministic scoring; no profit claim |
| `research_get_evidence` | methodId or literatureId | evidence, claims, citations, conflicts, quality | Reads existing `WebResearch*` |
| `quant_list_methods` | family, objective, status, limit | method summaries | Extends discovery library |
| `quant_get_method` | **methodId**, version? | full spec + relationships + provenance | |
| `quant_specify_method` | draft or **methodId**, target instrument/frequency | validated `QuantMethodSpec` | Schema + semantic validation; invalid does not persist |
| `quant_reproduce_method` | **methodId**, **datasetId**, version?, implementation? | `QuantReproduction` | Runs isolated worker; records deviations |
| `quant_validate_method` | **reproductionId**, checks[] | validation matrix | Reuses OOS/bootstrap/multiple-testing/robustness |
| `quant_register_method` | **spec**, status, evidenceIds[] | method id | Write; does not imply validated |
| `quant_build_dossier` | **sessionId** | `{dossierId, artifactId}` | Composes existing Edge Report + evidence |
| `quant_list_dossiers` | sessionId?, limit | dossier summaries | |

Do **not** add `model_catalog` alternatives. Extend `model_catalog` kinds with
`method` and `dossier` so one read still answers "do we already have this?".

### MethodSpecDraft contract (minimum)

```json
{
  "methodId": "volatility.har_rv",
  "name": "HAR-RV",
  "family": "volatility_modeling",
  "version": "1.0.0",
  "objective": ["realized_volatility_forecasting"],
  "inputs": [{"name": "realized_variance", "frequency": "daily"}],
  "parameters": [{"name": "daily_lag", "type": "int", "domain": [1, 5]}],
  "equations": [{"latex": "...", "variables": [], "source": {"literatureId": "...", "section": "...", "page": 4}}],
  "estimation": {"method": "ols"},
  "assumptions": ["..."],
  "outputs": ["volatility_forecast"],
  "validation": ["chronological_out_of_sample", "forecast_error_metrics"],
  "provenance": {"literatureIds": [], "implementationIds": [], "confidence": "medium"},
  "unresolved": ["..."]
}
```

Validation rejects: missing inputs, incompatible frequency/units, unknown
estimation, equations without provenance, a method whose required data does not
exist, and any field the extractor guessed (must be in `unresolved`).

---

## 7. HTTP and front door

Add to `python/harness/routers/quant_desk.py` (or a small
`routers/quant_research.py` included in `main.py`), operator-gated:

```
POST /quant/research/search
POST /quant/research/paper
GET  /quant/research/citations/{literature_id}
POST /quant/research/extract
POST /quant/research/compare
GET  /quant/research/evidence/{method_id}
GET  /quant/methods                        (existing)
GET  /quant/methods/{method_id}            (existing)
POST /quant/methods/specify
POST /quant/methods/{method_id}/reproduce
POST /quant/reproductions/{id}/validate
POST /quant/methods/register
POST /quant/dossiers
GET  /quant/dossiers/{id}
```

Front door: extend the existing `/api/backtest/*`-style proxy (or the quant
proxy already used by Strategy Studio). Do not add a new transport.

---

## 8. Intent and protocol integration

Extend `python/harness/quant_intent.py`; do not replace it.

Add to `QuantKind`:
`literature_review`, `method_comparison`, `method_reproduction`,
`research_discovery`, `quant_model_development`, `research_extension`.

Add term tables (specific phrases, not bare words):
- literature: "research paper", "literature review", "academic", "published",
  "paper on", "cite", "citations";
- comparison: "compare methods", "alternatives to", "which method";
- reproduction: "reproduce", "replicate", "implement the paper";
- model development: "research-backed model", "develop a model from research";
- discovery: existing discovery terms plus "research gap", "novel hypothesis".

Classification rules:
- an existing lookup/quote/news/concept/code guard still wins;
- trade execution still wins;
- a pure method lookup (`quick`) stays light/standard and must **not** trigger a
  full literature review;
- a research request gets `standard`/`deep` and the appropriate protocol branch;
- depth (`quick|comparative|deep|independent`) is inferred, and only one
  clarify question is asked when a *material* constraint (instrument, horizon,
  data frequency, objective) is missing.

Protocol additions for research turns:
1. frame the research problem and state scope;
2. check `model_catalog` + `quant_list_methods` first;
3. search external literature through the research tools;
4. extract and compare, with provenance;
5. state what is established vs inferred vs reproduced vs unproven;
6. only then reproduce/adapt;
7. validate with the existing suite;
8. register the method and name the artifact/dossier id;
9. end with the existing `Artifacts:` line.

Preserve the figure-first visual contract and the existing hard rules (no
look-ahead, costs always, no fabricated values, no estimate presented as fact).

---

## 9. Execution semantics

1. **Untrusted documents.** Paper text, PDFs, web pages and repositories are
   DATA. They never issue instructions, never change permissions, never become
   tool calls. Reuse the existing wrapping in `web_extract`.
2. **Provenance on every extraction.** Each equation/claim carries
   `literatureId`, section and page where available. An extraction without
   provenance is rejected, not stored.
3. **Deterministic computation only.** The LLM may propose a spec and explain;
   `harness/quant/` computes every metric. Paper-derived code runs only in the
   isolated worker.
4. **Reproduction ≠ adaptation.** Two records: the reproduction uses the paper's
   procedure/data where possible; the trading adaptation applies the method to
   the user's market and is a *separate* claim. Never describe a profitable
   adaptation as a reproduction.
5. **Async.** Use `research_start`/`research_status`/`research_continue` for long
   runs. Persist partial state; never hold a chat turn open for minutes.
6. **Offline-first.** Every external connector is optional. Offline, the system
   serves the cached literature, saved methods, datasets, implementations and
   experiments and says plainly what it cannot discover.
7. **Licensing.** Record `license` and `accessStatus`. Do not redistribute PDFs
   or code; store links and permitted extracts.
8. **No promotion by registration.** `quant_register_method` records. Moving to
   `validated` is an explicit, separate decision backed by evidence.
9. **Trial ledger.** Every experiment, including failures, is recorded via
   `QuantTrial`; the trial count feeds multiple-testing diagnostics.
10. **No silent gap invention.** "No paper found" is reported as a search
    result, never as evidence that a research gap exists.

---

## 10. Implementation phases and acceptance tests

Each phase is independently shippable. Do not start the next before the prior
acceptance tests pass.

### Phase 0 — Audit (no code)
Deliverable: a table mapping each capability in §3 to `exists / partial /
missing`, plus the exact files to touch. Findings must be based on read source,
not this document.

Acceptance: `npm run test`, `npx tsc --noEmit`, `npm run check:size` still pass;
the audit names every existing module the plan will reuse.

### Phase 1 — Scholarly search + acquisition
Implement: query planner; multi-provider search over the existing registry
(OpenAlex, Crossref, arXiv, Semantic Scholar, SSRN/NBER/RePEc where reachable,
GitHub code); dedupe; citation graph; `QuantLiterature`; `research_search_papers`,
`research_get_paper`, `research_get_citations`.

Acceptance:
- one query fans out to ≥3 providers and dedupes DOI/arXiv duplicates;
- a preprint and its published version link to one work;
- provider failure is reported per provider, not hidden;
- no network in tests (fixtures/mocks);
- inaccessible full text is `unavailable` with a reason.

### Phase 2 — Literature intelligence
Implement: section/equation extraction with page provenance; structured method
extraction; `research_extract_method`, `research_compare_methods`,
`research_get_evidence`; claim/limitation separation.

Acceptance:
- every extracted equation carries a source location;
- paper claims and Eclipse inferences are separate fields;
- a missing method field appears in `unresolved`, never fabricated;
- a scanned/unsupported PDF is reported honestly;
- an extraction that fails validation is not persisted.

### Phase 3 — Method knowledge base
Implement: extend `QuantMethod`; relationships; paper links; implementations;
`quant_list_methods`, `quant_get_method`, `quant_specify_method`; extend
`recommend_methods` with evidence/reproducibility/assumption dimensions; extend
`model_catalog` kinds.

Acceptance:
- a method can be registered without editing the intent classifier;
- variants and aliases are searchable;
- every recommendation prints its factors and caveats;
- `recommend_methods` never claims an edge or a profit probability;
- an unknown method is added only through the controlled write path.

### Phase 4 — Reproduction → model
Implement: spec compiler/validator; reproduction harness on the isolated worker;
`quant_reproduce_method`; separate adaptation path; `quant_register_method`; unit
tests for generated implementations.

Acceptance:
- invalid specs do not execute;
- generated code runs only in `sdk_runtime`;
- reproduction records published vs observed metrics and deviations;
- reproduction and adaptation are distinct records;
- registration does not imply validation;
- a reproduced method with no trading adaptation is still a valid deliverable.

### Phase 5 — Validation and dossiers
Implement: validation planner, trial ledger wiring, `quant_validate_method`,
`quant_build_dossier`; compose Edge Report + OOS + multiple testing +
robustness; store the dossier as an artifact.

Acceptance:
- every trial is recorded, including failed ones;
- the dossier links claims → sources and numbers → experiments;
- missing evidence is named (`not measured`), never zero;
- a candidate cannot be reported as validated without a validation record;
- `quant_build_dossier` returns an Artifact Center id.

### Phase 6 — Research memory
Implement: cross-session retrieval of literature, methods, failed hypotheses,
reproductions and dossiers; "have we researched this?" lookup; supersession of
updated papers without overwriting frozen method versions.

Acceptance:
- a repeat question returns prior work and avoids duplicate implementation;
- a failed experiment is retrievable with its failure reason;
- a new paper links to an existing method as `extension`/`critique`;
- validated versions are immutable.

### Phase 7 — UX and integration
Implement: research progress events (reuse run events); method comparison and
dossier panels inside Strategy Studio; source viewer; depth control; resume.
Keep Auto/Quant/Off unchanged.

Acceptance:
- research progress is visible and resumable;
- every dossier claim opens its source/experiment;
- Auto/Quant/Off behaviour and the existing quant contract gate still pass;
- no new top-level tab is required.

---

## 11. Test plan

### Python unit/integration
Shipped:
- `python/tests/test_quant_research_intel.py` — schema/catalog, store roundtrip,
  planner, dedupe, extraction provenance, suitability, reproduction,
  validation, dossier honesty.
- `python/tests/test_quant_research_intent.py` — the six research kinds and the
  unchanged existing routes.
- `python/tests/test_quant_research_routes.py` — operator gating and payloads.

Use fixtures/mocks for every network call. No live provider in CI.

### QuantBench additions (`quant_bench/cases.py`)
| Case | Check |
|---|---|
| `research-known-method` | finds/explains GARCH with real references |
| `research-method-compare` | compares GARCH/EGARCH/GJR-GARCH correctly |
| `research-reproduce` | reproduction runs and records deviations |
| `research-problem-to-method` | suitable regime-change methods |
| `research-data-incompatible` | refuses a method whose inputs are missing |
| `research-discovery-hypothesis` | produces a falsifiable hypothesis |
| `research-model-development` | research-backed model + validation |
| `research-memory` | retrieves a prior failed experiment and why |
| `research-no-fabricated-paper` | never invents a citation/DOI |
| `research-no-gap-from-empty-search` | empty search is not a gap |

### Quant contract gate
Extend `eval_gates/quant_contract.py` with research queries and the required
phrases (catalog-first, provenance, reproduction≠adaptation, `Artifacts:` line).

### Quality metrics (report, do not game)
Source accuracy, extraction accuracy, mathematical correctness, recommendation
relevance, reproduction fidelity, validation completeness, reproducibility,
evidence traceability, duplicate avoidance, failure honesty.

---

## 12. Non-negotiable guardrails

- No new agent, model provider, database, search stack or artifact store.
- No LLM-computed trading statistic.
- No paper content treated as instructions.
- No fabricated citation, DOI, equation, parameter or result.
- No promotion of a method to `validated` by registration, popularity or
  citation count.
- No live order routing; deployment remains paper-only.
- No silent zeros: missing data is `unavailable` with a reason.
- No new dependency unless the lighter existing option genuinely cannot work
  (and justify it in the PR).
- Keep files small and respect `scripts/size-budget.json`; re-pin deliberately.
- Run `npm run test`, `npx tsc --noEmit`, `npm run test:quant-bench` and
  `npm run check:size` before reporting done.
- Update `docs/` and append to `docs/CHANGELOG.md` in the same change.

---

## 13. Definition of done for v1

1. Eclipse searches ≥3 scholarly providers, dedupes and cites real papers.
2. It retrieves accessible full text and extracts equations/assumptions/limits
   with page provenance.
3. It checks the internal 14-family library and `model_catalog` before building.
4. It compares candidate methods against the user's actual constraints and
   prints the reasons.
5. It produces a validated `QuantMethodSpec`.
6. It reproduces a method separately from a trading adaptation.
7. It validates with the existing suite and records every trial.
8. It saves literature, methods, implementations, experiments and dossiers for
   reuse.
9. It distinguishes published evidence from Eclipse's own results.
10. A repeat request returns prior work instead of rebuilding it.

The differentiator is not more generated strategies. It is: **research what
already exists, understand the mathematics, reproduce it honestly, test it
properly, and remember what happened.**
