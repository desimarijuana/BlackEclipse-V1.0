---
title: Graph Studio — Research & Evidence Node Plan
status: Implemented (Waves A–C + query expansion)
last-verified: 2026-11-02
---

# Research & evidence node plan

**Scope:** the ten `research.*` nodes that exist today (nine requested plus
`research.source_rank`), the defects found while auditing them, and the new
nodes that turn a hand-wired chain of fetches into a complete evidence
pipeline.

**What this document is:** an implementation-ready plan — current inventory,
findings with file:line grounding, node contracts, work waves, a test matrix and
acceptance gates.

**What it is not:** a decision record. Items marked **DECISION** need an answer
before a ticket starts; accepted answers become an ADR in `skills/ARCHITECT.md`
plus a section in `docs/graph-studio.md`.

The governing rule for every node below: **reuse the existing web-research
engine, never build a second one.** Search, fetching, extraction, verification,
conflict detection, citations, freshness, supersession and quality are already
implemented in `python/harness/research/`. A research node is an adapter over
those modules plus the durable `EvidenceStore`; it is not a new engine.

## Progress

| Item | Status | Notes |
| --- | --- | --- |
| P0 — defects R1–R5, R7, R8 | **done** | Conflict status normalized + `candidates` decoded at the read boundary; `claim_verify` now passes conflicts/`asOf`/`freshness` and falls back to the claim's recorded links; reads return `total`/`truncated`; completeness gets an explicit coverage model, `verdict` and `gaps`; report degrades without a run row, escapes raw HTML, adds sources/gaps, numbered citations and a `maxItems` bound; `web_search` over-fetches then filters/dedupes, supports a provider preference and optional source persistence; `web_crawl` reports `linkDiscovery` failures and takes `maxDepth`/`delayMs`; `source_rank` scores recorded source-type authority. R6 and R9–R11 are now done. |
| Wave A — 10 local nodes | **done** | `research.latest`, `sources`, `gaps`, `freshness`, `conflict_scan`, `citation_audit`, `supersession`, `quality`, `entities`, `claims_verify` in `python/harness/graph_runtime/research_analysis_nodes.py` + `src/lib/graph-studio/registry-research.ts`, registered via `node_packs.py`. Tests: `python/tests/test_graph_research_analysis_nodes.py` (19 cases incl. query expansion) + the existing research suite. |
| Wave B — network adapters | **done** | `research.fetch_many`, `scrape`, `extract_facts`, `deep_dive` in `research_network_nodes.py` + `registry-research.ts`. `tests/test_graph_research_network_nodes.py` (10 cases: partial failures, dedupe, honest scrape status, span-validated extraction with a fake model, a stub engine, and test-run refusal). |
| Wave C — local writes | **done** | `research.start_run` (idempotent run bootstrap), `research.snapshot` (immutable, versioned payload), `research.ingest` (external agent/MCP/manual rows, origin-tagged and never Eclipse-verified) and `research.diff` (evidence/claims/conflicts/sources/coverage between two runs on the same question, snapshots preferred). `tests/test_graph_research_write_nodes.py` (10 cases). |
| Wave D — query expansion | **done** | `research.queries` (pure): question + named gaps + weak claims → answer/support/counter-evidence/primary-source queries, deduped and capped. The other Wave D candidates are declined with reasons in §3.4. |
| Manifest determinism | **done** | `manifest.ts` now sorts by codepoint, not `localeCompare`; ICU collation across machines could swap `broker_modify` / `broker_modify_order`. |

Deliberate deviations from the sections below: the new TS definitions live in
their own `registry-research.ts`, but the **existing** research definitions stay
in `registry.ts` (moving them would touch saved-graph presentation for no
contract benefit); `research.conflicts` gained a `summary` output (additive);
and the runtime file split is `research_analysis_nodes.py` registered from
`node_packs.py`, which keeps `nodes.py` under its 1200-line ceiling.

---

## 0. Current inventory (verified against the tree)

| Layer | File |
| --- | --- |
| TS contracts | `src/lib/graph-studio/registry.ts` (lines 928–1090) |
| Presentation | `src/lib/graph-studio/config-fields.ts` (967–1008), `node-ports.ts`, `node-examples.ts` |
| Manifest + parity | `src/lib/graph-studio/registry.manifest.json` (`npm run graph:manifest`) |
| Runtime | `python/harness/graph_runtime/research_nodes.py` (852 lines) |
| Registration | `python/harness/graph_runtime/nodes.py` (`build_research_nodes`) |
| Tests | `python/tests/test_graph_research_nodes.py`, `src/lib/graph-studio/registry.test.ts` |
| Store | `python/harness/research/web_store.py` (`EvidenceStore`) |
| Engine modules already available | `web_verify`, `web_freshness`, `web_quality`, `supersession`, `web_facts`, `web_extract`, `web_collect`, `web_store`, `web_sources`, `citations`, `receipt` |

Shipped nodes:

| Node | Kind | Effect / capability | Reads |
| --- | --- | --- | --- |
| `research.evidence` | local read + text filter | `read` / `research.read` | evidence |
| `research.citations` | local read | `read` / `research.read` | citations + claims |
| `research.conflicts` | local read | `read` / `research.read` | conflicts |
| `research.completeness` | local summary | `read` / `research.read` | counts + coverage |
| `research.report` | local Markdown | `read` / `research.read` | run + all rows |
| `research.web_search` | network | `network` / `network.egress` | provider chain |
| `research.web_fetch` | network (+ implicit store write) | `network` / `network.egress` | one page |
| `research.web_crawl` | network | `network` / `network.egress` | bounded same-site pages |
| `research.claim_verify` | local verify | `read` / `research.read` | one claim |
| `research.source_rank` | pure | `none` / — | wired evidence only |

The store already persists more than these nodes expose: **sources**,
**questions**, **claim↔evidence links**, **validations**, **snapshots**,
**entities** and **relations** all have tables and accessors but no node.

---

## 1. Findings — defects in the shipped nodes

These are correctness and honesty issues, not feature requests. Fix them before
adding new surface area.

| ID | Finding | Grounding | Impact |
| --- | --- | --- | --- |
| **R1** | `research.claim_verify` never passes `conflicts`, `as_of` or `freshness` to `verify_claim`, so the conflict-contradiction and point-in-time rules are dead in the graph path. | `research_nodes.py:515`; `web_verify.py:164` | A claim touching an unresolved material conflict can be reported `SUPPORTED` in a graph but `CONTRADICTED` through the engine/tools. |
| **R2** | Conflict status vocabulary is inconsistent: the engine writes `UNRESOLVED`/`EXPLAINED`, `_summary` only treats `RESOLVED`/`DISMISSED` as resolved, and the graph test seeds `OPEN`. | `web_verify.py:137–144`; `research_nodes.py:141–143`; `test_graph_research_nodes.py:44` | Completeness and report disagree with the engine; `OPEN` is counted as unresolved. |
| **R3** | `list_conflicts` returns `candidates` as a JSON **string** (no `_loads`), unlike evidence/entities. | `web_store.py:562–566` | Downstream nodes/report emit a string where an array is expected. |
| **R4** | Every local read truncates at `limit` without returning `total`/`truncated`. | `research_nodes.py:103, 118–126, 183–186` | The graph cannot tell "12 citations" from "the first 12 of 400". |
| **R5** | `completeness` falls back to `coverage = 1.0` whenever evidence exists and there are no questions, so `COMPLETE` can be declared with zero claims, zero citations and no coverage model. | `research_nodes.py:144–153` | Overstates completeness; contradicts the "no fabricated confidence" rule. |
| **R6** | `report` hardcodes 20 rows, has no source list, no numbered citations, no limitations/gaps section, and prints untrusted `sourceUrl`/claim text into Markdown unescaped. | `research_nodes.py:183–227` | A report can omit most evidence, cannot be traced citation-by-citation, and is injectable. |
| **R7** | `report` raises when the run row is missing, even if evidence rows exist under that `researchId`. A graph that starts at `web_fetch`/`ingest` with a fresh id never creates a run row. | `research_nodes.py:179–181`; `web_store.py:429–455` | The common "search → fetch → report" graph fails at the last node. |
| **R8** | `web_fetch` writes sources/evidence to the store when `researchId` is set but declares only `network.egress`; the local write is undeclared. | `research_nodes.py:355–362, 776` | Authorization text understates what the node does; a future non-network write path would inherit the gap. |
| **R9** | `web_search` filters domains **after** `limit`, so a run can return fewer than `limit` even when matching results exist; it does not persist sources, dedupe, or expose recency. | `research_nodes.py:268–284` | Provenance is lost between search and fetch; filters appear to under-perform. |
| **R10** | `web_crawl` swallows link-collection failures (`return []`), so "collector unavailable" is indistinguishable from "page has no links"; it also fetches each page twice (page + link collection) and keeps exact-URL dedupe only. | `research_nodes.py:380–401, 433–455` | Silent partial crawls; no canonicalization/depth control. |
| **R11** | `source_rank` ignores the authority/source-type signals the engine already records, ranking only on confidence + freshness. | `research_nodes.py:569–628`; `web_quality.py:67–70` | Under-ranks primary sources; inconsistent with `web_sources` ranking. |
| **R12** | No node resolves a research run. Every local node needs a hardcoded/wired `researchId`, and there is no "latest run for this question" entry point. | all local executors | A saved graph cannot be re-run against fresh research without editing config. |

Two more small ones worth folding into the same PR: `web_crawl`'s `seen` cap
(`maxPages * 5`) is a magic number with no summary field, and `web_search`
`diagnostics`/`error` are returned but never emitted to the run log.

---

## 2. Decisions to settle first

| # | Decision | Recommendation |
| --- | --- | --- |
| **D1** | What does `researchId` mean when a graph creates evidence with no run row? | Add `research.start_run` (local write) and make `report`/`completeness` degrade honestly (`runRow: false`) instead of raising. Do not auto-create run rows in a fetch node — a fetch should not invent a question. |
| **D2** | How are engine-computed artifacts (conflicts, citations, quality, freshness) surfaced — new nodes or extra outputs on existing ones? | New nodes, one verb each. `completeness` stays a summary; `conflict_scan`/`citation_audit`/`quality` do the computation. Folding them into existing ports would silently change saved graphs. |
| **D3** | Do analysis nodes read from the store or from wired arrays? | Both, with wired input winning. This lets a graph use `agent.research`/`ingest` output without persisting it, while still supporting the store-first path. |
| **D4** | Which capability covers a local evidence write? | New `research.write`, **not** in `TEST_RUN_CAPABILITIES`. Pair it with `SideEffect.LOCAL_WRITE`; a test run is then refused by the existing capability gate (`compiler.py:291–304`) even though `local_write` itself is normally allowed. |
| **D5** | `extract_facts` needs a model. How is that declared? | `SideEffect.MODEL` + `capability: agent.run` (the same rule as `agent.*`), with a bounded, span-validated extraction and a per-node timeout. It never persists unless a save node follows, so it stays a model effect, not a write. |
| **D6** | Expose the full engine (`ResearchEngine`) as one node? | Yes, but as one explicitly-named node (`research.deep_dive`), operator-only via `network`, with the engine's own budget caps and a hard timeout. It must be additive, not a replacement for the composable nodes. |
| **D7** | Port types | Keep `array`/`object`/`string`. Do **not** switch existing evidence ports to `PortType.EVIDENCE`; that changes `ports_compatible` and every saved edge. New nodes use the same array shape. |
| **D8** | Where do TS definitions live? | New `registry-research.ts` spread into `DEFINITIONS` next to `...TRADING_DEFINITIONS`. `registry.ts` is already 1142 lines; the Python side splits into `research_nodes.py` (local), `research_network_nodes.py`, `research_analysis_nodes.py`. |

---

## 3. Node catalog

### 3.1 Wave A — local, deterministic reads (ship first)

No network, no model, `capability: research.read`, `effect: read`, all modes.
Every one is a pure read over the store (or a wired array), so a **test run can
exercise it** with no operator grant.

#### `research.latest` — Resolve research run
- **Why:** every saved graph needs a stable entry point without a hardcoded id.
- **Inputs:** `question` (string, optional).
- **Outputs:** `researchId` (string), `run` (object), `summary` (object).
- **Config:** `researchId` (exact id wins), `questionMatch` (substring, case-insensitive), `latest` (boolean, default true), `limit` (1–50).
- **Reuses:** `EvidenceStore.get_run` / `list_runs` (already ordered by `createdAt DESC`).
- **Honesty:** no match is a named error (`no research run matches …`), never an empty success.
- **Unlocks:** `latest` → `evidence`/`gaps`/`report`; scheduled monitoring across runs.

#### `research.sources` — Sources
- **Why:** sources are the provenance backbone and currently invisible to graphs.
- **Inputs:** `researchId` (optional).
- **Outputs:** `sources` (array), `summary` (object: `total`, `returned`, `truncated`, `byType`, `byDomain`).
- **Config:** `researchId`, `limit` (1–1000, default 200), `domain`, `sourceType`, `authority`, `publishedAfter` (ISO), `dedupe` (boolean, default true).
- **Reuses:** `store.list_sources`; canonical-URL + `contentHash` + `familyId` dedupe (the store already records all three).
- **Honesty:** `publishedAfter` only compares rows that carry a date; undated rows are excluded **and counted** in `summary.excludedUndated`.

#### `research.gaps` — Coverage gaps
- **Why:** `completeness` says "PARTIAL" but not what is missing, so a graph cannot act on it.
- **Inputs:** `researchId` (optional).
- **Outputs:** `gaps` (array), `summary` (object: `total`, `unanswered`, `unsupported`, `uncited`, `hasGaps`).
- **Config:** `researchId`, `includeOptional` (boolean, default false), `limit` (1–500).
- **Gap kinds:** `question` (required && !answered), `claim` (status `UNSUPPORTED`/`CONTRADICTED`/`OUTDATED`), `citation` (material claim with no citation row), `evidence` (no evidence at all).
- **Reuses:** `store.list_questions` / `list_claims` / `list_citations`; the material-claim rule from `web_verify.validate_citations`.
- **Loop this enables:** `gaps` → `logic.condition hasGaps` → `web_search` → `fetch_many` → `claim_verify` → `gaps` (bounded by `flow.repeat`).

#### `research.freshness` — Point-in-time filter
- **Why:** the engine fails closed on stale/inadmissible evidence; graphs currently cannot.
- **Inputs:** `evidence` (array, optional), `researchId` (optional).
- **Outputs:** `evidence` (array admissible), `rejected` (array with `evidenceId`, `kind`, `reason`), `summary`.
- **Config:** `researchId`, `asOf` (ISO datetime), `freshness` (`any`|`day`|`week`|`month`|`quarter`|`year`), `limit`.
- **Reuses:** `web_freshness.filter_admissible` exactly — same five timestamps and the same fail-closed rules.
- **Honesty:** every rejection carries the engine's own reason string; nothing is dropped silently.

#### `research.conflict_scan` — Scan conflicts
- **Why:** `research.conflicts` only reads conflicts the engine happened to persist; most ad-hoc graphs fetch evidence but never run detection.
- **Inputs:** `evidence` (array, optional), `researchId` (optional).
- **Outputs:** `conflicts` (array), `summary` (object: `groups`, `unresolved`, `explained`).
- **Config:** `researchId`, `tolerance` (0–1, default the engine's `_NUMERIC_TOLERANCE`), `mergeStored` (boolean, default true), `limit`.
- **Reuses:** `web_verify.detect_conflicts` + `store.list_conflicts`.
- **Rules:** deterministic; no model; never writes. It reports a disagreement, never picks a winner. A merged row keeps `source: "scanned" | "stored"`.

#### `research.citation_audit` — Audit citations
- **Why:** nothing checks that every material claim is traceable before a report is emitted.
- **Inputs:** `researchId`, `claims` (array, optional), `citations` (array, optional), `evidence` (array, optional).
- **Outputs:** `audit` (object: `ok`, `coverage`, `issues`), `issues` (array).
- **Config:** `researchId`, `requireCitations` (boolean, default true), `asOf`, `freshness`, `limit`.
- **Reuses:** `web_verify.build_citations` (when none are wired) then `validate_citations`.
- **Honesty:** an uncited material claim is an issue, not a warning; `ok: false` is a normal outcome.

#### `research.supersession` — Revision chain
- **Why:** restatements/amended filings are a first-class finance problem; the chain already exists but is unreachable from graphs.
- **Inputs:** `evidence` (array, optional), `researchId` (optional).
- **Outputs:** `chain` (object: `coverage`, `links`, `currentByKey`, `historyByKey`, `issues`), `summary`.
- **Config:** `researchId`, `limit`.
- **Reuses:** `supersession.build_chain`.
- **Honesty:** `coverage: "unavailable"` when no evidence carries revision metadata — never an empty "no revisions" claim.

#### `research.quality` — Quality score
- **Why:** the composite, explainable quality score exists and is never surfaced.
- **Inputs:** `researchId`, optional `sources`/`evidence`/`claims`/`conflicts` arrays.
- **Outputs:** `quality` (object: `score`, `band`, `verdict`, `components`, `weights`, `contributions`, `raw`, `disclaimer`), `summary`.
- **Config:** `researchId`, `freshness`.
- **Reuses:** `web_quality.compute_quality`, with `citation_report` from `citation_audit` and coverage from the completeness summary.
- **Honesty:** the engine's `disclaimer` is passed through verbatim and the node docs say "internal heuristic, not truth".

#### `research.entities` — Entities & relations
- **Why:** the store already writes an evidence-anchored entity/relation graph; no node exposes it.
- **Inputs:** `researchId`.
- **Outputs:** `entities` (array), `relations` (array), `summary` (`anchored`, `unanchored`).
- **Config:** `researchId`, `name` (exact, case-insensitive), `kind`, `limit`.
- **Reuses:** `store.list_entities` / `list_relations` / `find_entity`.
- **Rule:** an entity/relation without an `evidenceId` is returned but counted `unanchored` (the writer should prevent it; the reader must not hide it).

#### `research.claims_verify` — Verify claims (batch)
- **Why:** one claim per node makes a 12-claim report a 12-node graph.
- **Inputs:** `researchId`, `claims` (array, optional), `evidenceIds` fallback (array).
- **Outputs:** `claims` (array with `status`/`confidence`/`issues`), `summary` (`supported`, `contradicted`, `outdated`, `unsupported`, `calculated`).
- **Config:** `researchId`, `asOf`, `freshness`, `limit` (1–200).
- **Reuses:** `web_verify.verify_claim` with the run's conflicts loaded and the same `asOf`/`freshness` as `freshness`/`claim_verify` (fixes **R1** for the batch path too).
- **Rule:** a claim with no evidence ids is `UNSUPPORTED`, never silently skipped.

---

### 3.2 Wave B — bounded network adapters

All are `side_effects: network`, `capability: network.egress` (plus the noted
extra capability), declared in all modes but refused by the compiler in a test
run and by `run-authorization.ts` without explicit network consent. They reuse
`web_extract.fetch` through the SSRF-hardened bridge; none of them talks to the
network directly.

#### `research.fetch_many` — Fetch pages
- **Why:** search returns 8–15 pointers; `web_fetch` handles one and `web_crawl`
  discovers links on one site. The missing verb is "fetch these known URLs".
- **Inputs:** `urls` (array, optional), `results` (array of `{url}` from
  `web_search`, optional), `researchId` (optional).
- **Outputs:** `pages` (array), `evidence` (array), `summary` (`requested`,
  `fetched`, `failed`, `deduped`, `status`).
- **Config:** `urls` (JSON array, max 10), `researchId`, `maxChars` (500–100_000,
  default 8 000), `allowBrowser` (boolean), `concurrency` (1–4, default 2),
  `dedupe` (boolean, default true), `saveEvidence` (boolean, default true when a
  research id is set).
- **Reuses:** `web_extract.fetch` + `fetch_to_evidence`; the same `allowBrowser`
  escalation as `web_fetch`.
- **Rules:** a failed URL is a row with `status`/`error`, never an exception that
  kills the batch; identical `contentHash` across URLs is fetched once;
  concurrency is `min(config, 4)`; saving requires `research.write` (D4).

#### `research.extract_facts` — Extract facts
- **Why:** the engine's page→structured-evidence step (model-assisted, then
  **span-validated**) is the one missing link between `web_fetch` text and
  `claim_verify`'s need for structured values.
- **Inputs:** `pages` (array of `{url,text}` or `page` objects), `legs` (array),
  `objective` (string), `researchId` (optional).
- **Outputs:** `evidence` (array), `rejected` (array with `metric`, `reason`),
  `summary` (`accepted`, `rejected`, `pages`).
- **Config:** `researchId`, `objective`, `legsJson` (metric/period/currency/basis),
  `permittedTiers` (array), `timeoutMs` (30–180 s), `saveEvidence` (boolean,
  default false), `maxPages` (1–5).
- **Reuses:** `web_facts.WebFactExtractor` → `parse_facts` → `validate_fact` →
  `fact_to_evidence`; `build_page_packet` bounds the prompt.
- **Rules:** a model response that does not validate is a `rejected` note; it
  never becomes evidence. The model has no tools and no loop. A bounded
  `set_fact_extractor` seam is bound in `bootstrap` (same pattern as
  `set_structured_runner`), so a headless run fails honestly.

#### `research.scrape` — Collect table / records
- **Why:** financial tables should become rows without a model and without
  parsing prose.
- **Inputs:** `url` (optional).
- **Outputs:** `rows` (array), `tables` (array), `page` (object).
- **Config:** `url`, `selector`, `attribute`, `fieldsJson`, `tables` (boolean),
  `maxRows` (1–200).
- **Reuses:** the existing bridge capability `web_collect` exactly as
  `web_collect.web_scrape` does (same request fields, same `UNAVAILABLE`
  handling, same untrusted-content boundary).
- **Rules:** `status: "UNAVAILABLE"` with an error is an outcome, not an empty
  result; rows are capped and `truncated` is reported.

#### `research.deep_dive` — Run research engine
- **Why:** the engine already plans, searches, fetches, extracts, verifies and
  persists a full run. Users should not have to rebuild twelve nodes to get one.
- **Inputs:** `question` (optional).
- **Outputs:** `researchId` (string), `answer` (string), `summary` (object).
- **Config:** `question`, `depth` (`quick`|`standard`|`deep`), `freshness`,
  `asOf`, `maxSearches`, `maxFetches`, `timeoutMs` (≤ 600 000).
- **Reuses:** `research.web_engine.ResearchEngine`, the same orchestration the
  `/research/web/*` routes and web-research tools use. It returns the run id so
  every local Wave-A node can read the result.
- **Rules:** operator only (`network`); it is a **bounded** engine invocation
  (`budget.py` caps), not a second agent loop; a missing model/bridge fails with
  the engine's own error. **DECISION D6:** expose it, but keep the composable
  path as the default documented workflow.

---

### 3.3 Wave C — local writes and reproducibility

`capability: research.write`, `effect: local_write`, refused in a test run
because `research.write` is not in `TEST_RUN_CAPABILITIES` (D4).

#### `research.start_run` — Start research run
- **Why:** a graph that begins with fetch/search needs a run row for
  `report`/`completeness`; today it does not exist (**R7**).
- **Inputs:** `question` (optional).
- **Outputs:** `researchId` (string), `run` (object).
- **Config:** `researchId` (empty = generate), `question`, `objective`, `asOf`,
  `freshness`, `depth`.
- **Reuses:** `store.save_run`.
- **Rule:** idempotent — an existing id is returned unchanged, never overwritten.

#### `research.snapshot` — Snapshot run
- **Why:** reproducibility and change detection need a frozen payload.
- **Inputs:** `researchId`.
- **Outputs:** `snapshotId` (string), `version` (number), `summary`.
- **Config:** `researchId`, `include` (`sources`/`evidence`/`claims`/`citations`/`conflicts`/`all`).
- **Reuses:** `store.create_snapshot` + `get_snapshot`; a content digest makes two
  identical snapshots distinguishable only by version, never by content.

#### `research.ingest` — Ingest research
- **Why:** `agent.research`, MCP tools and manual payloads produce evidence-
  shaped data that the local nodes cannot read because it was never persisted.
- **Inputs:** `research` (object, e.g. an agent run's `research` blob),
  `evidence` (array), `claims` (array), `findings` (array), `researchId`.
- **Outputs:** `researchId`, `evidenceCount`, `summary`.
- **Config:** `researchId`, `sourceLabel` (e.g. `mcp:server/tool`),
  `contentTrust` (default `UNTRUSTED`), `createRun` (boolean, default true).
- **Rules:** every ingested row keeps its **origin** (`provenance.source`) and is
  never labelled Eclipse-verified. `claim_verify` over ingested MCP evidence
  returns the deterministic status but the report must print "external source —
  not Eclipse-verified". This is the implementation of the AGENTS MCP rule, not
  an exception to it.
- **Reuses:** `store.save_source` / `save_evidence` / `save_claim`; normalizers
  already used by `source_collector.py`.

#### `research.diff` — Compare runs
- **Why:** scheduled research is only useful if "what changed" is visible.
- **Inputs:** `baseId`, `compareId` (or two snapshots).
- **Outputs:** `diff` (object: `addedEvidence`, `removedEvidence`,
  `statusChanges`, `openedConflicts`, `resolvedConflicts`, `coverageDelta`),
  `summary`.
- **Config:** `baseId`, `compareId`, `byContentHash` (boolean, default true).
- **Reuses:** `list_snapshots`/`get_snapshot` payloads when present, otherwise the
  live store rows. **Rule:** a comparison of different questions/entities is
  refused (`incomparable runs`), never loosely diffed.

---

### 3.4 Wave D — query expansion shipped; the rest declined

`research.queries` **shipped** in `research_query_nodes.py`: a pure node that
turns a question, the gaps a run named and weak claims into concrete queries,
including a disconfirming query per weak claim and an optional primary-source
query (`site:<filter>`). It is deterministic, has no store/network/model, and
feeds `research.web_search` (often through `flow.parallel`). This completes the
missing loop primitive the Wave A nodes exposed.

| Candidate | Decision | Why |
| --- | --- | --- |
| `research.counter_evidence` | **declined as a node** | Shipped as queries (`research.queries`) plus the existing `web_search`/`fetch_many`/`claim_verify` nodes. A second search pass inside one node would hide the plan and duplicate `flow.parallel`. |
| `research.save_claim` | **declined** | `research.ingest` already writes external claims with origin tagging; a standalone write would invite unverified claims into the store. Verification stays a read (`claim_verify`) and ingestion stays explicit. |
| `research.calculate` | **declined for now** | Deterministic finance math already exists (`finance_facts`, `research.calculations`, `finance.*`/`quant.*`). Add it only when a concrete graph needs a metric the finance pack cannot express. |
| `research.notebook` | **out of scope** | The notebook is a chat surface, not a graph primitive. |

A starter template (`research-brief`) now demonstrates the read path end to end:
stored run → evidence → conflict scan → citation audit → report.

---

## 4. Improvements to each existing node

### `research.evidence`
- Return `total` and `truncated`; add `order` (`stored`|`newest`|`confidence`) and
  `sourceType`/`domain`/`publishedAfter`/`minConfidence` filters.
- Validate `limit` bounds at compile time; keep the 1–1000 ceiling.
- Keep the text filter, but match `structuredValue` only when it is an object
  (today `json.dumps(None)` is fine; a huge blob is not — cap the haystack).

### `research.citations`
- Add outputs `links` (claim↔evidence relations) and `audit` (from
  `citation_audit`, optional `validate: true`).
- Support `claimId` filter; return `total`/`truncated`.
- If the store has no citation rows but claims cite evidence, **build** citations
  through `web_verify.build_citations` instead of returning empty.

### `research.conflicts`
- Normalize status to a closed set (`UNRESOLVED`, `EXPLAINED`, `RESOLVED`,
  `DISMISSED`; map legacy `OPEN`→`UNRESOLVED`) and decode `candidates` (**R2/R3**).
- Add `status`, `material`, `metric` filters; return `total`/`unresolved`.
- Consider `scan: true` to run `conflict_scan` in-place; otherwise keep the
  separation and point users at `research.conflict_scan`.

### `research.completeness`
- Replace the `1.0 if evidence` fallback with an explicit coverage model
  (`questions` when present, otherwise `evidence + support + citations`), and
  return `verdict: COMPLETE|PARTIAL|INSUFFICIENT` plus `gaps` (**R5**).
- Add `runRow` boolean and never fail when the run row is missing.
- Reuse the same summary function as `report` so they cannot diverge.

### `research.report`
- Configurable `maxItems` (default 50), optional `sections`
  (`answer`/`claims`/`citations`/`conflicts`/`gaps`/`sources`/`quality`/`limitations`).
- Number citations (`[1]`, `[2]`) and print the numbered source list with
  retrieved/published dates.
- Escape/fence untrusted claim text and URLs; never let page text inject Markdown.
- Print `UNAVAILABLE` for a missing answer instead of an italic placeholder, and
  keep the report deterministic (no timestamps from wall clock).
- Degrade when the run row is missing: emit the report from stored rows and set
  `runRow: false` (**R7**).

### `research.web_search`
- Fetch `limit * 3` from the provider, then filter/dedupe, then truncate (**R9**).
- Add `recency` (`day`/`week`/`month`/`year`), `provider` pin, `dedupeByDomain`,
  and `saveSources` (requires `research.write`).
- Emit `diagnostics`/`error` to the run log; summary keeps `status` and `provider`.

### `research.web_fetch`
- Declare `research.write` and say so in docs (**R8**); add `save` (boolean,
  default true when `researchId` is set) so a graph can read without persisting.
- Dedupe by `contentHash` against the run: an identical page returns the stored
  evidence id and `deduped: true`.
- Persist `publishedAt`/`section` when the extractor provides them; never invent.
- Report `escalation` in the summary (already returned in `page`).

### `research.web_crawl`
- Split link discovery from fetching: one `fetch` per page plus one collector
  call, and return `linkDiscovery: "ok"|"failed"` instead of hiding the failure
  (**R10**).
- Add `maxDepth` (0–2), `delayMs` (0–2 000), `allowPatterns`/`denyPatterns`,
  canonical-URL dedupe, and `deadlineMs` (hard stop at 240 s).
- Optional `saveEvidence` (requires `research.write`), off by default.
- Return `skipped` URLs with the reason (off-domain, already seen, depth limit).

### `research.claim_verify`
- Load the run's conflicts and pass `conflicts`, `asOf`, `freshness` into
  `verify_claim` (**R1**).
- Default `evidenceIds` to the claim's stored links when a matching claim text is
  found, otherwise keep the current explicit requirement.
- Return `confidence` and `issues`; add `status` values to the docs.

### `research.source_rank`
- Add an optional `authority` component derived **only** from recorded
  `sourceType`/`provenance.authority` (primary = 1, secondary = 0.6, unknown =
  absent), with weights exposed in `summary` (**R11**).
- Keep the current rule: an item with no recorded signal gets **no score**.

---

## 5. Cross-cutting contracts

### 5.1 Output envelope
Every research node returns a `summary` object containing at least:

```
{ "status": "OK" | "PARTIAL" | "EMPTY" | "UNAVAILABLE",
  "total": <known count>, "returned": <count>, "truncated": <bool> }
```

Network nodes add `status`, `error` and per-item failure rows. This mirrors the
broker nodes' `ok`/`reason` convention and makes `logic.condition` cheap.

### 5.2 Limits (bounded by default)

| Bound | Value |
| --- | --- |
| local read `limit` | 1–1 000 |
| batch verify | 1–200 claims |
| fetch_many URLs | 10 |
| fetch concurrency | 4 |
| fetch chars | 100 000 |
| extract pages | 5 |
| scrape rows | 200 |
| crawl pages / depth | 10 / 2 |
| deep-dive timeout | 600 s |

### 5.3 Capability matrix

| Node kind | Capability | Effect | Test run |
| --- | --- | --- | --- |
| local read/analysis | `research.read` | `read`/`none` | allowed |
| network adapter | `network.egress` | `network` | refused |
| model extraction | `agent.run` | `model` | allowed (no tools) |
| local write (`start_run`/`snapshot`/`ingest`) | `research.read` + `research.write` | `local_write` | refused |
| deep dive | `network.egress` + `agent.run` | `network` | refused |

`research.write` is deliberately **not** added to `TEST_RUN_CAPABILITIES`
(`compiler.py:48`), so the existing capability gate enforces D4 without a new
compiler rule.

### 5.4 Trust and honesty rules
- A search result is a pointer, never evidence.
- Extracted/scraped page text is untrusted until it is stored as evidence with
  provenance; `contentTrust` is `UNTRUSTED` unless a source type justifies more.
- External (MCP/agent) results ingested into the store keep their origin and are
  **never** labelled Eclipse-verified.
- A conflict is reported, never resolved by voting or averaging.
- An unavailable site is reported as unavailable, never as "content absent".
- Quality is internal and carries its disclaimer.

### 5.5 Naming, files and size
- Node type prefix `research.`; one verb per node; labels sentence case.
- New TS definitions in `registry-research.ts` (spread into `DEFINITIONS`).
- New runtime nodes in:
  - `research_nodes.py` — Wave A (store reads / pure analysis), already 852
    lines; move `source_rank` and the new analysis nodes to
    `research_analysis_nodes.py` if the file would exceed the size ceiling.
  - `research_network_nodes.py` — `fetch_many`, `extract_facts`, `scrape`,
    `deep_dive`; extend the existing three network nodes in place.
  - `research_write_nodes.py` — `start_run`, `snapshot`, `ingest`, `diff`.
- Register all three from `node_packs.py` (or `nodes.py` beside
  `build_research_nodes`) so registration order stays deterministic.
- Update `config-fields.ts`, `node-ports.ts`, `node-examples.ts`, the manifest,
  and both parity tests with every node.

### 5.6 Reference graph (the point of the whole plan)

```
research.latest ─► research.evidence ─► research.freshness ─► research.conflict_scan
        │                                                              │
        ├─► research.gaps ─► logic.condition ─► research.web_search ─► research.fetch_many
        │                                                              │
        │                        research.extract_facts ◄──────────────┘
        │                              │
        ├─► research.citation_audit ◄──┴─► research.claims_verify
        │                                      │
        └─► research.quality ─► research.report ─► output.result
```

The same run can start cold with `research.start_run → web_search → fetch_many →
extract_facts → …`, and a scheduled monitor can use `research.diff → output.notify`.

---

## 6. Work breakdown

| Phase | Work | Depends on | Estimate |
| --- | --- | --- | --- |
| **P0 — fixes** | R1–R5, R7, R8: conflict vocabulary/decoding, verify inputs, truncation totals, completeness verdict, report degradation, declared write capability | D1, D4 | 1–2 days |
| **P1 — Wave A** | `latest`, `sources`, `gaps`, `freshness`, `conflict_scan`, `citation_audit`, `supersession`, `quality`, `entities`, `claims_verify` + TS contracts/config/examples | P0, D2, D3, D7, D8 | 3–4 days |
| **P2 — Wave B** | `fetch_many`, `scrape`, `extract_facts`, `deep_dive`; improve `web_search`/`web_fetch`/`web_crawl` (R9, R10) | P1, D5, D6 | 4–5 days |
| **P3 — Wave C** | `start_run`, `snapshot`, `ingest`, `diff` | P0, D4 | 2–3 days |
| **P4 — polish** | Report sections, source list, escaping; source-rank authority; docs + templates + changelog | P1–P3 | 1–2 days |

### Exact touch list per new node
1. `src/lib/graph-studio/registry-research.ts` — definition (type, version
   `1.0.0`, ports, zod config, defaultConfig, capabilities, sideEffects,
   allowedModes, docs).
2. `src/lib/graph-studio/registry.ts` — spread the pack.
3. `src/lib/graph-studio/config-fields.ts` — inspector fields with ranges/help.
4. `src/lib/graph-studio/node-ports.ts` / `node-examples.ts` — display + example.
5. `python/harness/graph_runtime/research_*_nodes.py` — `NodeDef` + executor.
6. `python/harness/graph_runtime/nodes.py` / `node_packs.py` — registration.
7. `python/harness/graph_runtime/bootstrap.py` — only for a new seam
   (`set_fact_extractor`; `deep_dive` reuses the existing engine/bridge).
8. `registry.manifest.json` — `npm run graph:manifest`.
9. Tests (below).
10. `docs/graph-studio.md` research section + this plan's status table.

---

## 7. Test matrix and acceptance gates

### Unit / executor tests (`python/tests/test_graph_research_nodes.py` + new files)
- Each Wave-A executor over a seeded store: empty store, partial rows (NULL
  columns), unknown `researchId`, limit bounds, total/truncated.
- `freshness`: an item with no timestamp is rejected with the engine's reason;
  `asOf` before publication fails closed.
- `conflict_scan`: two disagreeing structured values → `UNRESOLVED`; a
  documented cause → `EXPLAINED`; identical values → no conflict.
- `citation_audit`: material claim without citation → `ok: false`; citation
  pointing at missing evidence → issue; `coverage` matches.
- `supersession`: amends/restates chain → current head; cycle → `unavailable`
  with an issue; no metadata → `unavailable`.
- `quality`: components/contributions sum to `score`; disclaimer present;
  weights sum to 1.
- `claims_verify`: a claim over a conflicted metric is `CONTRADICTED` (the R1
  regression); stale-only support is `OUTDATED`.
- `report`: deterministic across two calls; numbered citations; missing run row
  yields a report with `runRow: false`; max items honored.

### Network tests (`test_graph_research_network_nodes.py`)
- Fake bridge/stub: `fetch_many` returns per-URL failures without raising;
  dedupe by contentHash; concurrency bounded; no network when the bridge is
  absent (honest error).
- `scrape`: bridge `UNAVAILABLE` → status, not empty rows; row cap/truncation.
- `extract_facts`: model returns an unvalidated number → `rejected`, not
  evidence; validated number → evidence with the span; model timeout → notes.
- `deep_dive`: stub engine returns a run id; missing engine/model fails honestly.

### Contract / parity tests
- `src/lib/graph-studio/registry.test.ts`: manifest parity + every node has a
  `config-fields` entry where it declares config.
- Python registry test: TS and Python port/config/effect parity for each new
  type; unique ids; `1.0.0` versions.
- Authorization test (`run-authorization.test.ts`): a graph with
  `fetch_many`/`deep_dive` requires network consent; a graph with
  `start_run`/`ingest` is not granted `research.write` in a test run.

### Acceptance gates (every phase)
- `npm run graph:manifest` produces a clean, committed diff.
- `npm run test` and `npx tsc --noEmit` pass.
- No node invents a value: an unrecorded signal yields `null`/`UNAVAILABLE`, and
  a test asserts the field is absent rather than zero.
- Every network node fails with an actionable message when the bridge is absent.
- Report output is byte-identical across two runs of the same store state.

---

## 8. Compatibility, migration and risks

- **Additive only.** New types at `1.0.0`; no existing type's ports change. The
  only behaviour change to an existing node is `report` no longer raising on a
  missing run row (strictly more successful), and `conflicts` normalizing status
  (`OPEN` → `UNRESOLVED`), which flips completeness from `COMPLETE` to `PARTIAL`
  in graphs that seeded `OPEN` — the correct outcome.
- **No IR bump.** No new port types, no new IR fields (D7). `sideEffects` and
  `capabilities` are additive vocabulary; the manifest records them.
- **Manifest is the gate.** A TS node without a Python executor shows as
  "declared, not executable"; do not ship that state.
- **Memory/DB.** All new reads paginate; `ingest` bounds rows (≤ 200 per call)
  and reuses content hashes; snapshots already store bounded JSON.
- **Risk: duplicating the engine.** Every node must import from
  `research.web_*`; a review checklist item is "no new search/fetch/verify
  implementation".
- **Risk: false confidence.** `quality` and `completeness` must print their
  scope; `quality` keeps the engine disclaimer, `completeness` returns
  `INSUFFICIENT` rather than guessing.
- **Risk: file size.** `research_nodes.py` is at 852 lines and the TS registry
  at 1142; split before adding (D8) rather than growing either past its ceiling.

---

## 9. Out of scope

- Reworking the web-research engine, its providers or its budget model.
- A second agent loop for research (agent turns stay in `agent.*`).
- Browser automation nodes beyond the existing `allowBrowser` escalation.
- Persisting raw page text in the graph run payload (evidence stays in the
  store/artifact layer).
- Cross-database storage: research rows stay on `agent-memory.db`, never
  `jdds.db`.
