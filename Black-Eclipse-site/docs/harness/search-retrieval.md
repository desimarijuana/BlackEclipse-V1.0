---
title: Unified Retrieval / Search Intelligence Layer
status: Current
last-verified: 2026-11-19
---

# Unified Retrieval / Search Intelligence Layer

**Code:** `python/harness/search/`
**Store:** `.black-eclipse/search/search.db` (dedicated; `ECLIPSE_SEARCH_DB_PATH`)
**Tools:** `semantic_search`, `keyword_search`, `hybrid_search`,
`search_documents`, `search_research`, `search_memory`, `search_experiences`,
`search_skills`, `search_evidence`, `search_context`, `find_similar`,
`document_context`, `related_chunks`, `search_admin`
**HTTP:** `python/harness/routers/search.py` (`/search/*`, operator-gated) →
`src/app/api/harness/search/[[...path]]/route.ts`
**UI:** Search Intelligence tab (`src/components/screens/search/search-screen.tsx`)
**ADR:** ADR-H151

## What it is

One retrieval layer the agent and the operator UI share:

```
agent / UI
   │
SearchService ── router ── retrieve ── rerank ── context assembly
   │                          │
   │                    SearchIndexStore  (SQLite: vectors + FTS5)
   │                          │
   └────────────── EmbeddingService  (providers, batch, cache, retry)
```

Ask for **what** you need (a query, filters, a mode), never *which* provider or
index. The layer returns ranked hits that always carry full provenance and a
ready-to-render citation — never anonymous text blobs.

## Why SQLite, not PostgreSQL + pgvector

The reference design assumed PostgreSQL + pgvector. BlackEclipse is
SQLite-first and must run with zero configuration (`npm install && npm run dev`
with no manual setup). Adding a second database engine would break that core
promise, so the index lives in a dedicated SQLite file (the same pattern as the
code index at `.black-eclipse/code-index/`). Everything above the store is
storage-agnostic, so moving to pgvector later does not touch callers. Keyword
search uses SQLite **FTS5 BM25** — no Elasticsearch.

## Modules

| File | Responsibility |
|---|---|
| `config.py` | One config object (env `HARNESS_SEARCH_*`): provider/model, batch, chunking, ranking weights, cache, context, index path |
| `contracts.py` | `SearchRequest`, `SearchResult`, `SearchHit`, `Citation`, `Provenance`, filters, scope |
| `chunking.py` | Fixed / sliding / structural / semantic chunking (structure-aware keeps tables intact) |
| `store.py` | `SearchIndexStore`: documents, sections, chunks, vectors, FTS5, jobs, events, embedding cache; `scope_clause` |
| `indexer.py` | Idempotent index pipeline with states + content-hash dedup |
| `adapters.py` | Read existing rows (MemoryRecord, DiDocument/DiChunk, WebResearchEvidence, Skill) into `DocumentRecord`s |
| `retrieve.py` | keyword / vector / hybrid retrieval, filters, temporal, dedup, neighbors |
| `rerank.py` | Reranker abstraction (local deterministic + Cohere/Voyage when credentialed) |
| `router.py` | Query strategy (structured vs hybrid) + deterministic decomposition |
| `context.py` | Token-budgeted, diversity-limited context assembly |
| `citations.py` | Citation rendering + EvidenceStore bridge |
| `service.py` | `SearchService` façade + observability + admin |
| `tools.py` | The agent tools (read-only; go through the service) |
| `evaluate.py` | Golden dataset + Recall@K / Precision@K / MRR / NDCG |
| `embeddings/` | Provider abstraction, model registry, content cache, batcher |

## Embedding providers

Real providers only — none is registered to satisfy an interface:

- **OpenAI / OpenAI-compatible** (`/embeddings`): OpenAI, Ollama, LM Studio,
  vLLM, any custom base URL. Credentials resolve from the run's `ModelSettings`
  or the provider's env var (`OPENAI_API_KEY`, …); keyless local servers use the
  literal `local`.
- **Google** (`:batchEmbedContents`), **Cohere** (`/v2/embed`),
  **Voyage** (`/v1/embeddings`).

Configure the active provider with `HARNESS_SEARCH_EMBEDDING_PROVIDER` /
`HARNESS_SEARCH_EMBEDDING_MODEL` / `HARNESS_SEARCH_EMBEDDING_DIMENSIONS` (or a
per-run override). The registry knows declared model dimensions
(`text-embedding-3-small` 1536, `voyage-3` 1024, `nomic-embed-text` 768, …). A
model whose dimensions are unknown must be declared — a guessed dimension would
corrupt the vector space.

**No provider configured ⇒ semantic search is unavailable and reports it**;
hybrid and semantic requests degrade to keyword/FTS with a `fallback` flag. The
layer never fabricates a vector.

### Where the provider comes from, and how the user turns it on

Resolution precedence: an explicit operator choice (below) → `HARNESS_SEARCH_*`
env → the run's `ModelSettings` provider. If the chat provider itself declares an
embedding model (`openai`, `google`, `cohere`, `voyage`, `ollama`, `lmstudio`,
`local`), semantic search turns on automatically — no second key. A chat-only
provider (`anthropic`, `deepseek`, …) is reported as `unsupported_provider`; the
layer does **not** silently send indexed text to a different hosted provider, so
privacy is never traded for recall.

`EmbeddingService.resolution()` returns a structured, honest explanation:
`state` (`active | no_provider | unsupported_provider | missing_model |
missing_credentials | unreachable`), `source` (`explicit | env | run | none`),
`reason`, a plain-language `hint`, and `suggestions` — one representative model
per declared provider, ordered by how likely it is to work (credentialed first,
then keyless local).
This is what the Search Intelligence screen renders instead of a bare
"unavailable".

The operator's choice is **persisted in the search DB** (`SearchMeta.embedding_config`),
so it survives a runtime restart, and switching model schedules a background
re-embed: an existing vector belongs to its old model key and is never reused in
the new vector space.

## Indexing

```
Document → chunk → embed (batch + cache) → vectors + FTS → INDEXED
```

`SearchService.bulk_index(namespaces=…)` reads the existing stores via
`adapters.py` and indexes them idempotently. Adapters cover namespaces
`memory`, `evidence`, `documents`, `skills`, and `repository`. The `repository`
adapter (`documents_from_repository`) indexes the project's OWN source
(`python/harness/**`, `src/**`, `prisma/**`; `.py`/`.ts`/`.tsx`/`.prisma`) so the
agent can search its code — bounded by file count and size, binaries skipped;
disable with `HARNESS_SEARCH_INDEX_REPO=0`. A packaged install is never
indexed: `scripts/vendor/python` marks the app's own payload, which is not the
user's project (walking it cost thousands of files on every boot). Identical
content (by SHA-256) is deduplicated so a re-ingest does not create duplicate
vectors.

Because the boot warm-up now resolves the embedding provider from the front-door
environment (`HARNESS_JOB_*`, via `SearchService._boot_settings`), it EMBEDS and
stores vectors at index time. When no provider is configured the index stays
honestly keyword-only (`STALE`), and the first query that resolves one schedules
ONE background re-index (`SearchService._maybe_backfill_vectors`) to add the
vectors — so embeddings are persisted, never computed and then discarded. An
unchanged keyword-only document reports its chunks as missing vectors, and a
hybrid query whose query-embedding fails records a structured `fallback: "keyword"`
(not just a warning string). Embedding-failure events keep their `count`/`error` in
the event `detail`.

States: `PENDING → PROCESSING → INDEXED | STALE | FAILED` (`STALE` = indexed for
keyword but embeddings are missing/failed). Failures are recorded on the
document row and in `SearchEvent`; jobs live in `SearchIndexJob`.

## Retrieval

- **semantic** — cosine over vectors, served by a real **sqlite-vec `vec0` ANN
  index** when the extension is available (restricted to the caller's authorized
  ACL buckets before scoring); falls back to brute-force cosine when it is not.
- **keyword** — FTS5 BM25.
- **hybrid** — both fused; per-component scores (`vectorScore`, `keywordScore`)
  are exposed on every hit.
- **filters** — namespace, source type, language, source id, entity, tickers /
  sectors / industries (from document metadata), and `meta` equality.
- **temporal** — `as_of` (fail-closed point-in-time), `published_*`,
  `retrieved_*`, `effective_as_of`.
- **reranking** — optional second stage (local deterministic reranker by default;
  Cohere/Voyage when credentialed). A provider reranker failure falls back to the
  local one rather than dropping results.
- **dedup** — exact content hash + near-duplicate shingle Jaccard.
- **neighbors** — previous/next chunk and section path, so a hit is never
  isolated.
- **context assembly** — token budget, per-source and per-document limits,
  diversity. `ContextAssembler` (`search/context.py`, wired via
  `SearchService.build_context`) is exposed to the agent as the `search_context`
  tool: it returns a bounded, deduplicated block with neighbour context instead
  of raw snippets, delimited as untrusted data.

## Security boundary

The authorization scope is compiled into the candidate SQL **before scoring**;
results are never scanned-then-filtered. A non-operator caller sees public rows
plus rows in the run's workspace or owned by the run's user, for keyword, vector
and hybrid paths alike. Agent tools derive the scope from the run; only the
operator HTTP surface may request an unrestricted scope.

Retrieved content is additionally delimited as **untrusted DATA** before it
reaches the model: `search/tools.py` wraps chunk text (and `document_context`
output) in `<<<UNTRUSTED_SEARCH_CONTENT>>> … <<<END_UNTRUSTED_SEARCH_CONTENT>>>`
with an explicit policy note, mirroring the browser/web/vision untrusted-content
convention. An indexed chunk can never impersonate a system/user instruction.

## Observability & evaluation

`SearchEvent` records searches (latency, candidates, results, cache hits,
provider/model, fallback). `SearchService.admin_stats()` powers the Search
Intelligence tab. `evaluate.py` ships a 60-query golden dataset and computes
Recall@K, Precision@K, MRR and NDCG over the real index; a regression is a
measured failure.

## Scaling & correctness

- **ANN vector search.** The vector store builds a `sqlite-vec` `vec0` index per
  vector space (`SearchVectorAnnMeta`), with a cosine metric and a `chunkId`,
  `aclKey` schema. A KNN is restricted to the caller's authorized buckets
  (`aclKey IN (…)`, computed by `scope_acl_keys`) **before** scoring, then the
  candidate ids are validated against the full metadata/temporal + scope SQL. If
  `sqlite-vec` is absent, the layer uses brute-force cosine over the
  pre-filtered candidate set (still correct; `annBackend` reports which path is
  live). `SearchIndexStore.rebuild_ann()` rebuilds the ANN from `SearchVector`.
- **Metadata filtering is indexed.** `tickers`/`sectors`/`industries` and any
  scalar `meta` equality are projected into `SearchDocumentMeta` and compiled
  into the candidate SQL, so filtering does not degrade on a large corpus.
  `documentType` is a distinct column (no longer conflated with `sourceType`).
- **Incremental re-index.** `index_document` skips a document whose content hash
  and id already match an `INDEXED` row, so `bulk_index` (and the job worker)
  only pay for what changed. `force=True` overrides.
- **Embedding-based semantic chunking.** When the `semantic` strategy is used and
  an embedding provider is available, chunk boundaries follow real sentence
  embedding similarity; otherwise the deterministic lexical-cohesion fallback
  applies.

## Operations

- **Automatic boot indexing.** On runtime boot the layer builds the index from
  existing sources in a **background task** (`SearchService.schedule_warm_index`,
  called from `harness/boot.py`). Boot is never blocked and a failure is recorded
  as an event. Disable with `HARNESS_SEARCH_WARM_INDEX=0`. Repository collection
  runs in a worker thread and the indexing loop yields to the event loop every
  50 ms, so `/health` and every other request keep answering during a large or
  first-run index. Warm-up is incremental (unchanged documents are skipped), and
  a keyword-only index is re-run cheaply because no vectors are produced.
- **Configuration.** `HARNESS_SEARCH_EMBEDDING_PROVIDER` /
  `_MODEL` / `_DIMENSIONS` (or the provider's own key env var, or the run's
  `ModelSettings`). With none set the layer is honestly keyword-only.
- **Setup from the UI (no restart).** `GET /search/stats` and `/search/models`
  expose `resolution`; `POST /search/embedding/apply`
  (`{provider, model, dimensions, reindex}`) activates a model, persists it, and
  schedules a forced re-index (required for a new vector space);
  `POST /search/embedding/test` performs one real embedding round-trip;
  `POST /search/embedding/clear` reverts to automatic resolution. All are
  operator-gated and proxied through `/api/harness/search/*`.
- **Live verification (opt-in).** `python -m harness.search.live_smoke`
  (or `BLACK_ECLIPSE_SEARCH_LIVE=1` + `pytest python/tests/test_search_live.py`)
  contacts a real provider and asserts embeddings are non-degenerate and score a
  relevant passage above a distractor. It is the only search test that uses the
  network and is never part of the offline suite.
- **Release gate.** `scripts/test-evals.js` runs the **`search`** gate
  (`harness/search/eval_gate.py`): it seeds the golden corpus and fails if
  Recall@k, MRR or NDCG fall below the recorded floors. Offline and
  deterministic.

## Known limitations (explicit)

- **ANN is exact for small corpora.** `sqlite-vec` `vec0` is a flat index by
  default (no HNSW graph); it is fast and correct at local scale but a graph
  index (or pgvector) would be needed for millions of vectors. The store
  interface is storage-agnostic by design (ADR-H151).
- **The evaluation corpus is synthetic** (deterministic, offline). The metrics
  are real; the documents are fixtures. `run_evaluation(dataset=…)` accepts a
  caller-supplied labelled dataset.
- **Source change detection is content-hash based**, not a store-level
  change-data-capture: run `bulk_index`/a job after a source changes; unchanged
  documents are skipped.
- **Table/cell locators** live in the document-intelligence subsystem; the
  search layer preserves `kind`, page and section, and the full locator set is
  available via `document_context`.

