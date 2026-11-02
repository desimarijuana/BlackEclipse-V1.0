---
title: Graph Studio — Files, Images, Agents & Memory Node Plan
status: Implemented (waves 0–5)
last-verified: 2026-11-02
---

# Files, images, agents & memory — node plan

**Scope:** four node families a trading-model workflow needs:

1. **Files** — upload a dataset/document once, then parse it in a graph.
2. **Images** — upload images and **read them through the vision API**:
   describe, OCR, read a candlestick screenshot, compare candidate candle
   references, and return one structured result per image/option.
3. **Agents** — an n8n-style agent node with a prompt, task, tools, memory and a
   declared output shape.
4. **Memory** — recall/write plus the missing context/list/update/forget
   primitives.

**What this document is:** an implementation-ready plan — current inventory,
the gaps, node contracts, storage/security design, UI work, test matrix and a
work breakdown. It is deliberately grounded in what is already in the tree.

**What it is not:** a decision record. Items marked **DECISION** need an answer
before a ticket starts. Accepted answers become an ADR in
`skills/ARCHITECT.md`, are mirrored to `docs/DECISIONS.md`, and are reflected in
`docs/graph-studio.md`.

**Governing rule:** *reuse the existing engine, never build a second one.* A
node is an adapter over a service that already exists.

- Image reading → the existing vision engine (`python/harness/vision/`):
  `analyze`, `ocr`, `ground`, `chart_analyze`, `compare`, `metadata`, plus the
  content-addressed `VisionAssetStore` and the ONE provider adapter.
- Image storage/upload → the same `VisionAssetStore`
  (`python/harness/vision/storage.py`), which already dedupes by SHA-256.
- Artifacts/downloads → the existing Artifact Center (`python/harness/artifacts/`).
- Agent execution → the existing agent run plane (`AgenticService.run`), already
  wrapped by `graph_runtime/agent_nodes.py`.
- Memory → the ONE Eclipse memory service, already wrapped by
  `graph_runtime/memory_nodes.py`.
- Local bounded storage → the existing dataset store pattern
  (`graph_runtime/datasets.py`).

---

## 0. Progress

Nothing in this plan is implemented yet. This table becomes the live state when
work starts.

| Item | Status |
| --- | --- |
| Wave 0 — `file`/`image` port types, `media` category, asset store, upload endpoint | **done** — `assets.py` (DB-backed `HarnessGraphAsset`, content-addressed per owner, 25 MB/200 files/512 MB caps), `/graph/assets` routes, Next proxy + inspector picker, test-run capabilities |
| Wave 1 — `data.file.attach`, `data.file.parse`, `data.file.export` | **done** — `file_nodes.py` + `registry-files.ts` + config fields/examples; `test_graph_file_nodes.py` (13 cases); manifest regenerated |
| Wave 2 — `image.attach`, `image.analyze`, `image.ocr`, `image.read_chart`, `image.compare`, `image.batch` (vision-read only) | **done** — `image_nodes.py` + `registry-media.ts`, vision runner/store bound at boot, image upload proxy + inspector picker, image read capabilities; `test_graph_image_nodes.py` (12 cases) |
| Wave 3 — `agent.task` + shared agent form + upgrades to existing agent nodes | **done** — `agent.task` executor/contract; instructions + tool allowlist added to `agent.research`/`agent.bot`/`agent.delegate`; output schema validation; memory read/write | 
| Wave 4 — `memory.context`, `memory.list`, `memory.update`, `memory.forget` | **done** — service `list_memories`/`update_memory`/`archive_memory`, scope resolver, runner bindings; `test_graph_agent_task_memory_nodes.py` (12 cases) |
| Wave 5 — canvas/inspector polish, examples, docs, ADRs | **done** — image picker/thumbnails, config-field groups, node examples, `Candle option review` template, ADR-060, docs |

Deliberate deviations from the sections below: the asset store is a BLOB table
on `agent-memory.db` (not files + sidecars) so there is one atomic store, one
owner check and no second path guard; uploaded images use the vision store as
specified; and graph memory scopes are `general|workflow|run` plus a literal
named scope (the run context has no project id, so `project` is not claimed).
Graph memory writes use the service's permitted `manual` source and still pass
through its capture policy; the existing `memory.remember` adapter was corrected
from an invalid `graph:<run>` source at the same time.

---

## 1. What exists today (verified against the tree)

| Capability | Today | Where |
| --- | --- | --- |
| Upload a file as chat context | Yes — user upload → session `context/`; extract text/CSV/PDF | `src/lib/chat/session-store.ts`, `src/lib/chat/extract.ts`, `src/app/api/chat/session/file/route.ts` |
| Uploaded image as an asset | Yes — content-addressed `ImageAsset` on the vision store | `python/harness/vision/storage.py`, `contracts.py` (`ImageAsset`) |
| Generate an image | Yes (chat/tools only — **not** used by this plan) | `python/harness/vision/generate.py`, tool `image_generate` |
| Analyze an image | Yes — describe/OCR/compare/chart analysis; **this is the engine the image nodes wrap** | `python/harness/vision/tools.py`, `orchestrator.py`, `charts.py`, `compare.py` |
| Candlestick chart | Yes — `ChartSpec.kind = 'candlestick'`, `candles[]`, drawn to PNG (separate `output.chart` surface; **not** part of the image nodes) | `python/harness/charts/spec.py` (`Candle`), `render.py` (`_draw_candlestick`) |
| Chart → PNG artifact | Yes — `render_spec` + `register_chart_artifact` (not used by this plan) | `python/harness/charts/service.py` |
| Persist a payload locally | Yes — bounded dataset refs | `graph_runtime/datasets.py`, `dataset_nodes.py` |
| Write a scoped file | Yes — relative path, scope grant, 8 MB | `graph_runtime/write_nodes.py`, `file.write` |
| Agent turn in a graph | Yes — `agent.research`, `.plan`, `.delegate`, `.bot`, `.classify`, `.extract`, `.summarize`, `.critique`, `.team` | `graph_runtime/agent_nodes.py`, `agent_structured_nodes.py`, `registry-agents.ts` |
| Memory in a graph | Yes — `memory.recall`, `memory.remember` (8 types, scope, importance) | `graph_runtime/memory_nodes.py`, `registry-utility.ts` |
| Agent tools allowlist / dry-run narrowing | Yes — `agents.dry_run_tools`, run-envelope capabilities | `python/harness/agents.py`, `graph_runtime/bootstrap.py` |
| Node manifest parity | Yes — TS registry → `registry.manifest.json` → Python suite | `src/lib/graph-studio/manifest.ts`, `npm run graph:manifest` |

**Conclusion:** two of the four asks are already partly built. Agents and memory
must be **extended**, not duplicated. Files and images are the real gaps, and
both can reuse engines that already exist.

---

## 2. Gap analysis

### 2.1 “Upload files / data”

Missing:

- No node can take a **user-selected file** and make it a stable graph input.
  `file.write` writes *out*; `data.dataset.save` stores JSON produced *by* the
  graph; chat uploads are tied to conversations and are not selectable in the
  inspector.
- No CSV/TSV/XLSX → `rows[]` parser node, so an uploaded dataset cannot feed the
  existing `transform.*`, `quant.*` or `logic.aggregate` nodes.
- No export-as-download node for a result (only a scoped disk write).

What we need: a bounded **graph asset store**, an inspector dropzone, a parse
node, and an export node. Bytes must never be serialized into the Workflow IR.

### 2.2 “Image nodes / how each candle should look”

**Decision (answered):** image nodes are **read-only**, powered by the vision
API. They **do not render** charts and they do not generate pictures. That
matches the intended workflow better: a trader supplies reference images of
candles/setups (one image per option, or a chart screenshot) and the graph reads
each one and returns a structured description/comparison.

Missing:

- No node turns an uploaded image into a graph input with a stable asset ref
  (`vision` assets exist and are content-addressed, but Graph Studio does not
  expose an uploader).
- No Graph Studio node wraps the existing vision capabilities: `analyze`
  (describe/answer), `ocr`, `ground` (locate elements), `chart_analyze` (read a
  chart image), `compare` (pixel + visual diff), `metadata`.
- No node runs the **same questions across several images** (“option A, option
  B, option C”) and returns one result per image.
- No honest labelling of vision output: it is a model observation, not verified
  market data and not evidence unless separately verified.

What we need: an image-input node plus thin adapters over the existing vision
engine, a batch node for multiple candidate images, and a strict provenance
label (`observation`, not `evidence`). No rendering, no image generation, no new
provider client.

> If a rendered candle chart is ever needed later, `output.chart` already draws a
> candlestick PNG through the chart engine. That is a **separate** future request
> and is explicitly out of scope here.

### 2.3 “Agent node with prompt/task like n8n”

Partially present. `agent.research` has agent preset, version, objective and
max steps; `agent.bot` runs a saved bot. Missing:

- No **system prompt / instructions** field separate from the objective.
- No per-node **tools allowlist** (the runtime binds the preset’s tools).
- No **declared output shape** (JSON schema) on the general agent node.
- No **memory mode** (`none` / `read` / `write` / `read_write`) on the agent node.
- No single “Agent” node that mirrors n8n’s Agent form: task + prompt + agent +
  tools + memory + output parser.
- No per-node sampling controls (temperature / max output tokens) even though
  run-level model settings exist.

What we need: one `agent.task` node with the full form, built on the same run
plane, plus a shared config fragment so `agent.research`/`agent.bot`/
`agent.delegate` gain instructions/tools/output schema without divergence.

### 2.4 “Memory nodes”

Already have recall + remember. Missing practical primitives:

- `memory.context` — assemble a **budgeted** prompt block without exposing raw
  records (recall already returns `context`, but there is no token-budget or
  formatting control).
- `memory.list` — deterministic browse by scope/type without a semantic query.
- `memory.update` / `memory.forget` — correct/retire a memory (operator-run only).
- Named **scopes** for graphs (`workflow:<id>`, `project:<id>`, `run:<id>`) so a
  graph does not pollute general memory.

Before promising update/forget, confirm the memory service exposes supported
mutations; if it does not, add them **inside the service** (policy, dedupe and
retention stay there) rather than writing SQL from the node.

---

## 3. Decisions needed (answer before ticket)

| ID | Decision | Recommendation |
| --- | --- | --- |
| **D1** | Who owns uploaded graph files: Next (TS) or the Python runtime? | **ANSWERED — Python owns** a bounded `GraphAssetStore`; Next is a streaming proxy. One store, one path guard, runtime can always read it. Images use the existing `VisionAssetStore`. |
| **D2** | New port types? | Add `file` and `image` (asset-ref types) to `PortType` in TS + Python. Additive; keep `object` compatibility via `any` only. |
| **D3** | Render images or read them? | **ANSWERED — READ ONLY.** Image nodes wrap the vision API. No chart rendering and no generative images in this plan. Vision output is labelled an observation, never evidence. |
| **D4** | How do multiple candle options work? | **One image per option, read individually.** `image.batch` applies the same question set to several candidate images and returns one result per image; `image.compare` compares two candidates. No specimen gallery, no rendering. |
| **D5** | Per-node model selection? | **No model picker on agent nodes** in v1. Use the run’s resolved model settings; allow only `temperature` and `maxOutputTokens` overrides if the run settings contract already supports them. Otherwise defer. |
| **D6** | Agent memory default? | `read` (recall allowed, write off) so a graph run cannot silently mutate memory. `write`/`read_write` are explicit. |
| **D7** | Agent tools field? | A comma-separated allowlist that can only **narrow** the preset’s tools. An unknown/disallowed tool fails by name, never silently dropped. |
| **D8** | Memory update/forget? | Only if the memory service gains `update`/`soft_delete`; otherwise defer. Operator-run only. |
| **D9** | New category? | Add `media` (image nodes) and keep files under `data`. Update the palette, icons and legend. |

---

## 4. Wave 0 — contract & storage plumbing

This wave unblocks all four families.

### 4.1 Port types and category

- `src/lib/graph-studio/types.ts`: add `'file' | 'image'` to `PortType`; add
  `'media'` to `NodeCategory`.
- `python/harness/graph_runtime/model.py`: mirror both.
- `src/components/screens/graph-studio/node-search-panel.tsx`: `media: 'Media'`
  in `CATEGORY_LABELS`.
- Port colour/shape: `file` and `image` get their own colour; `image` ports may
  render a 28 px thumbnail chip when the node has a produced asset (wave 5).
- `portsCompatible` already requires exact matches (or `any`), so no rule change.

### 4.2 Bounded graph asset store

New `python/harness/graph_runtime/assets.py`, modelled on `datasets.py`:

```python
class GraphAssetStore:
    root: Path                     # .black-eclipse/graph/assets/
    max_bytes_per_file = 25 * 1024 * 1024
    max_files_per_user = 200
    max_total_bytes_per_user = 512 * 1024 * 1024
    ttl_hours: int | None = None   # optional, same idea as datasets

    def save(self, *, name, data: bytes, mime, owner) -> AssetMeta: ...
    def get(self, asset_id, *, owner) -> AssetMeta: ...
    def open_bytes(self, asset_id, *, owner) -> bytes: ...
    def list(self, *, owner, limit=100) -> list[AssetMeta]: ...
    def delete(self, asset_id, *, owner) -> bool: ...
```

`AssetMeta` (JSON, returned to the graph and stored in node config):

```json
{
  "assetId": "gas_...",
  "name": "btc_1h.csv",
  "mime": "text/csv",
  "bytes": 184320,
  "sha256": "…",
  "createdAt": "2026-11-02T…",
  "expiresAt": null
}
```

Rules:

- Content-addressed bytes on disk; metadata alongside; atomic write.
- Owner check on every read; `..`/absolute paths refused; MIME sniffed, not
  trusted from the client.
- Uploaded images reuse the **vision** store (`VisionAssetStore`), not this one,
  so image dimensions, retention and content-addressed dedupe stay where they
  already live. `data.file.attach` handles data files only.
- Orphan sweep: assets referenced by no saved workflow version and older than
  N days are removed by a small GC helper (same spirit as video `gc.py`).

### 4.3 Upload endpoint

`POST /api/graph-studio/assets` (Next route, multipart):

1. Validate content length + MIME + filename (reuse the safe-name rules from
   `session-store.ts`).
2. Route by MIME:
   - `image/*` → Python `POST /graph/assets/images` → `VisionAssetStore.save`
     (content-addressed, width/height recorded).
   - everything else → Python `POST /graph/assets` → `GraphAssetStore.save`.
3. Both return a small `AssetMeta`; the Workflow IR stores only that ref.
4. `GET /api/graph-studio/assets/:id` returns metadata; a second route streams
   bytes for previews.

Uploads are **authoring-time local writes**, not run effects, so they do not need
an operator run envelope — but they are local-only, size-capped and never
forwarded to the network.

### 4.4 Capabilities

| Capability | Used by | Test-run policy |
| --- | --- | --- |
| `asset.read` | `data.file.*`, `image.attach` / image readers | allowed (local read) |
| `asset.write` | upload endpoints, `data.file.export` | authoring allowed; export allowed (`local_write`) |
| `image.read` | every `image.*` node | allowed (local asset read) |
| `model.vision` | `image.analyze` / `ocr` / `read_chart` / `compare` / `batch` | allowed with the run’s resolved model settings |
| `memory.write` | `memory.remember` / update / forget | refused in a test run |
| `agent.run` | all agent nodes | allowed with narrowed read-only tools |

---

## 5. Node contracts

Ports below use the repo’s `port()` convention; `control` ports are only added
where the node should be gated.

### 5.1 Files (category `data`)

#### `data.file.attach` — v1.0.0 — “File”

One uploaded file becomes a graph input.

| Port | Dir | Type | Notes |
| --- | --- | --- | --- |
| `file` | out | `file` | asset ref + metadata |
| `text` | out | `string` (nullable) | populated for text/CSV/JSON |
| `rows` | out | `array` (nullable) | populated when parsed as tabular |
| `meta` | out | `object` | name, mime, bytes, sha256, parse info |

Config:

```json
{
  "assetId": "gas_…",
  "name": "btc_1h.csv",
  "mime": "text/csv",
  "parseAs": "auto",          // auto | text | json | csv | xlsx | binary
  "delimiter": ",",           // csv/tsv only
  "header": true,
  "maxRows": 5000,
  "encoding": "utf-8"
}
```

Behaviour:

- Inspector shows a **dropzone**; uploading stores the asset and writes only
  `assetId`/`name`/`mime`/`bytes`/`sha256` into config.
- `parseAs: auto` sniffs by extension then MIME (`.csv/.tsv/.json/.txt/.xlsx`).
- CSV/TSV uses the Python stdlib `csv`; XLSX uses `openpyxl` (already a
  dependency); JSON accepts an object or an array; text is decoded with the
  declared encoding.
- Hard caps: 25 MB file, 5 000 rows by default, 100 000 cells; hitting a cap is
  reported (`truncated: true`), never silently accepted.
- A missing/expired asset is an explicit failure naming the file.
- Side effects: `read`. Capabilities: `asset.read`. All modes.

#### `data.file.parse` — v1.0.0 — “Parse file”

Parses a `file` produced by any node (e.g. `file.write` read back, or a file
reference flowing through a subworkflow). Same parser as above, no upload UI.

| Port | Dir | Type |
| --- | --- | --- |
| `file` | in | `file` (optional — else configured `assetId`) |
| `rows` | out | `array` |
| `columns` | out | `array` |
| `text` | out | `string` (nullable) |
| `meta` | out | `object` |

Config: `assetId`, `parseAs`, `delimiter`, `header`, `maxRows`, `sheet`,
`encoding`, `onMissingField`.

#### `data.file.export` — v1.0.0 — “Export file”

Turns `rows[]`/an object into a downloadable artifact (CSV/JSON/XLSX) through
the Artifact Center.

| Port | Dir | Type |
| --- | --- | --- |
| `in` | in | control (optional) |
| `rows` | in | `any` |
| `artifact` | out | `object` |
| `name` | out | `string` |
| `bytes` | out | `number` |

Config: `format` (`csv|json|xlsx`), `name`, `includeHeader`, `maxRows`.

- `sideEffects: local_write`; capability `asset.write`; test run allowed.
- This is distinct from `file.write`: export produces a run artifact the user
  can download; `file.write` writes into an operator-granted scope.

### 5.2 Images (category `media`) — vision-read only

These nodes **read** images through the existing vision engine. They do not
render charts and they do not generate images (D3).

Shared rules:

- Input is an `image` asset ref (uploaded or produced upstream). The vision asset
  store already dedupes by SHA-256 and keeps width/height/MIME.
- Each analysis is one bounded call through `vision.orchestrate` →
  `analyze_image` / `analyze_chart` / `compare_images` / OCR, using the run’s
  resolved model settings. No new provider client, no direct HTTP.
- The result is explicitly an **observation**: `kind: "observation"`,
  `verified: false`, with model/provider and any warnings. It is never written to
  the EvidenceStore and never labelled Eclipse-verified. A later verification
  step can promote it; the image node cannot.
- A provider without vision capability, or a missing model setting, fails by
  name. There is no placeholder observation.
- Side effects: `model`. Capabilities: `image.read` (asset) + `model.vision`
  (the call). A test run may read an image with a bounded model call, the same
  way `agent.*` nodes do.

#### `image.attach` — v1.0.0 — “Image”

Uploads or references one image.

| Port | Dir | Type |
| --- | --- | --- |
| `image` | out | `image` |
| `meta` | out | `object` |

Config: `assetId`, `name`, `mime`, `bytes`, `sha256`, `notes`.

- Inspector shows an image dropzone (PNG/JPEG/WebP/GIF/BMP/TIFF) and a
  thumbnail; `Replace` stores a new asset. Only the ref is stored in config.
- `meta` returns `{ assetId, name, mime, width, height, bytes, sha256, createdAt }`.
- Cap: 20 MB/image (the vision store’s existing limit), 100 images per workflow
  author. Reusing an identical image returns the same content-addressed asset.
- Side effects: `read`. Capability: `image.read`.

#### `image.analyze` — v1.0.0 — “Analyze image”

The general vision node. Describe, answer a question, locate elements, or extract
a structured object.

| Port | Dir | Type |
| --- | --- | --- |
| `image` | in | `image` (optional — else configured `assetId`) |
| `question` | in | `string` (optional) |
| `description` | out | `string` |
| `observations` | out | `array` |
| `data` | out | `object` (nullable; `extract` mode) |
| `meta` | out | `object` |

Config:

```json
{
  "assetId": "",
  "mode": "describe",             // describe | answer | ground | extract
  "question": "Describe every candle: body, wicks, direction and what it suggests.",
  "schemaJson": "",              // extract mode only
  "region": [0, 0, 0, 0],        // x, y, w, h; 0,0,0,0 = whole image
  "maxObservations": 40
}
```

- `describe` uses the vision engine’s guarded description.
- `answer` asks `question`; an empty question fails by name.
- `ground` returns elements with pixel bounding boxes (`{label, region, text}`).
- `extract` validates the model’s JSON against `schemaJson` with the same
  JSON-Schema subset as `agent.extract`; a mismatch is `data: null` with issues
  on the run log, never a coerced object.
- Output is capped and deduped; the model/provider is recorded in `meta`.

#### `image.ocr` — v1.0.0 — “Read text (OCR)”

| Port | Dir | Type |
| --- | --- | --- |
| `image` | in | `image` (optional) |
| `text` | out | `string` |
| `spans` | out | `array` |
| `meta` | out | `object` |

Config: `assetId`, `language`, `region`, `mode` (`text|spans|both`).

- Wraps the existing OCR path; spans carry text + pixel regions.
- Useful for reading a broker screenshot, an axis label or a table image before
  feeding `data.file.parse`-style transforms.

#### `image.read_chart` — v1.0.0 — “Read chart”

The node for “how should each candle look”: feed one candidate chart image per
option, get a structured reading of its candles and structure.

| Port | Dir | Type |
| --- | --- | --- |
| `image` | in | `image` (optional) |
| `question` | in | `string` (optional) |
| `reading` | out | `object` |
| `description` | out | `string` |
| `verified` | out | `boolean` |
| `meta` | out | `object` |

Config:

```json
{
  "assetId": "",
  "question": "Classify each candle pattern, then state the trend and the nearest support/resistance.",
  "symbol": "",                  // optional; enables market-data verification
  "timeframe": "",
  "strict": false,
  "maxObservations": 60
}
```

- Wraps `vision.analyze_chart` (the dedicated chart reader), which already can
  cross-check a reading against market data when a symbol is supplied.
- `reading` is a structured object: `{ trend, patterns[], candles[], levels[],
  indicators[], notes }` (bounded). The schema is returned even when empty.
- `verified` is `true` only when the engine’s market-data check actually
  confirmed the reading; otherwise `false` with the reason in `meta`.
- It never invents candles. A blurry/partial screenshot returns a low-confidence
  reading plus warnings, not a confident guess.
- Side effects: `model` (+ `market.read` only when `symbol` is set and
  verification is on). Capabilities: `image.read`, `model.vision`.

#### `image.compare` — v1.0.0 — “Compare images”

Compare a candidate against a reference (or two candidates).

| Port | Dir | Type |
| --- | --- | --- |
| `a` | in | `image` |
| `b` | in | `image` |
| `same` | out | `boolean` |
| `score` | out | `number` (0–1) |
| `differences` | out | `array` |
| `meta` | out | `object` |

Config: `mode` (`visual|pixel|both`), `threshold` (0–1), `question`.

- `pixel` uses the deterministic `pixel_diff` (no model); `visual` uses
  `compare_images` (model); `both` returns both and reports disagreement.
- `same` is `pixelScore >= threshold` in `pixel` mode; in `visual` mode it is the
  model’s verdict and is labelled as such.
- Use case: “does this live chart match my reference candle setup?” — the answer
  is an observation, not proof.

#### `image.batch` — v1.0.0 — “Read image options”

The multiple-options node. Apply the same question set to N candidate images and
return one result per image.

| Port | Dir | Type |
| --- | --- | --- |
| `images` | in | `array` (image refs) |
| `results` | out | `array` |
| `summary` | out | `object` |
| `failed` | out | `array` |

Config:

```json
{
  "questions": [
    "Describe the candle anatomy.",
    "What pattern is this and what would confirm it?",
    "Rate how closely this matches a valid entry setup (0-10) and why."
  ],
  "mode": "analyze",             // analyze | read_chart | ocr
  "concurrency": 2,              // 1-3
  "maxImages": 8,                // hard cap
  "outputSchemaJson": ""
}
```

- 1–8 images, 1–5 questions; each image is processed independently.
- `results[i] = { index, name, assetId, description, observations, data,
  meta }`; a failed image is a row with `ok: false` and the reason — the batch
  does not abort silently.
- `summary` is deterministic: counts, per-question answers grouped by image, and
  the images that differed. No extra model call for the summary.
- Concurrency is bounded; the node never exceeds the run’s concurrency budget.

### 5.3 Agents (category `agent`)

#### `agent.task` — v1.0.0 — “Agent”

The n8n-style node.

| Port | Dir | Type |
| --- | --- | --- |
| `input` | in | `any` (optional) |
| `context` | in | `object` (optional) |
| `task` | in | `string` (optional; overrides config) |
| `output` | out | `string` |
| `data` | out | `object` (nullable) |
| `finding` | out | `research_finding` |
| `run` | out | `object` (status, tokens, toolCalls, runId) |
| `valid` | out | `boolean` |

Config, grouped exactly like the inspector sections:

```json
{
  "agent": "eclipse-agent",
  "agentVersion": 0,

  "task": "Evaluate whether the uploaded CSV's setup matches the strategy rules and return a verdict.",
  "instructions": "You are a strict trading-model reviewer. Cite only fields present in the input. If a field is missing, say UNAVAILABLE.",

  "tools": "get_market_data, research_search",   // allowlist; may only narrow
  "maxSteps": 12,

  "memoryMode": "read",          // none | read | write | read_write
  "memoryScope": "workflow",     // general | workflow | project | run
  "memoryTypes": "",             // blank = all
  "memoryLimit": 8,

  "outputMode": "text",          // text | json
  "outputSchemaJson": "",
  "includeInput": true,
  "continueOnError": false,

  "temperature": 0.2,
  "maxOutputTokens": 0
}
```

Behaviour:

- Prompt is composed deterministically: instructions → task → optional context →
  optional bounded serialization of the input → memory `context` block (when
  `memoryMode` includes read). Order is fixed and documented so results are
  reproducible.
- Tools: normalize the allowlist, intersect with the preset’s tools. Do not
  silently grant; fail with the names that are unavailable. A test run applies
  `dry_run_tools` **after** the intersection.
- Output: `text` returns the turn output. `json` parses the output and validates
  it against `outputSchemaJson` using the same JSON-Schema subset as
  `agent.extract`; a mismatch returns `valid: false` with issues — never coerced.
- Memory: `write`/`read_write` call the ONE memory service through the existing
  runner injection; a write is refused in a test run. Default `scope: workflow`
  maps to `workflow:<id>` (resolved from the run context, not typed by the user).
- Run identity/replay: reuse `agent_run_identity` so a retried durable node
  re-enters the same agent run when a checkpoint exists.
- Failure is honest: a non-success run status fails the node with the run’s
  message (existing `agent_result_payload` behaviour).
- Side effects: `model`; capabilities `agent.run` (+ `memory.write` when enabled).

#### Shared upgrade to existing agent nodes

Add a small shared config fragment (TS + Python) used by `agent.research`,
`agent.bot`, `agent.delegate`:

- `instructions` (system prompt) — appended to the existing objective.
- `tools` allowlist — narrow-only, same parser as `agent.task`.
- `outputSchemaJson` — optional validation on the returned finding text.
- `memoryMode`/`memoryScope` — default `read`/`workflow` for research/research
  bots; `none` for classify/extract/summarize (they are bounded single calls and
  should stay predictable).
- Do **not** change existing defaults; old graphs keep their current behaviour.
  New fields must be optional with empty/default values.

Add `agent.task` to `registry-agents.ts` and a `build_agent_task_node` in
`agent_nodes.py` registered from `node_packs.py` (keeps `nodes.py` size).

#### Declined for now

- A generic “Tool” node wired into an agent (n8n’s sub-node pattern). It would
  require a tool-graph contract, per-node credentials and a permission model
  beyond the current registry. Record as a future ADR, not a wave-3 ticket.

### 5.4 Memory (category `data`)

Existing `memory.recall` / `memory.remember` stay. Add:

#### `memory.context` — v1.0.0 — “Memory context”

| Port | Dir | Type |
| --- | --- | --- |
| `query` | in | `string` (optional) |
| `context` | out | `string` |
| `memories` | out | `array` |
| `count` | out | `number` |

Config: `query`, `types`, `scope`, `limit` (1–50), `budgetTokens` (128–8 000),
`format` (`bullets | prose | compact`).

- Calls the same `retrieve` as `memory.recall`; formats a deterministic block
  under the token budget (drop lowest-importance records first, report the
  number dropped). No model call.
- This is the node an agent wires into its `context` input.

#### `memory.list` — v1.0.0 — “List memories”

Browses by scope/type with no semantic query. Outputs `memories`, `count`,
`scopes`, `types`. Config: `scope`, `types`, `limit`, `offset`, `order`
(`newest|oldest|importance`).

#### `memory.update` — v1.0.0 — “Update memory”

Operator-run only. Inputs `memoryId`/`content`; config `memoryId`, `content`,
`type`, `importance`. Calls the memory service’s update path (to be confirmed
under **D8**), preserving conflicts/dedupe. A test run is refused.

#### `memory.forget` — v1.0.0 — “Forget memory”

Operator-run only. Inputs `memoryId`; config `memoryId`, `hard` (default false).
Soft-delete by default through the service. A test run is refused.

#### Scopes

Add a shared resolver used by both agent and memory nodes:

| Config value | Resolved scope |
| --- | --- |
| `general` | `general` |
| `workflow` | `workflow:<workflow id>` |
| `project` | `project:<bound project id>` |
| `run` | `run:<run id>` |

If the id is unavailable in the run context, fail by name rather than falling
back to `general` (silent cross-workflow pollution is the failure mode).

---

## 6. UI / inspector work

| Surface | Change |
| --- | --- |
| Node library | New `Media` group; Files under `Data`; `agent.task` in `Agents`. |
| `data.file.attach` inspector | Dropzone (drag/drop + browse), filename/size/MIME chip, Replace, Preview (first rows or text), “stored locally, never uploaded to the network”. |
| `image.attach` inspector | Image dropzone + thumbnail + dimensions/MIME/size, Replace, “read locally; the model only sees the bytes you attach”. |
| `image.analyze` / `ocr` / `read_chart` inspector | Mode picker, question textarea, optional region selector on the preview, output-schema editor (`extract`), and a note that the result is an observation, not verified data. |
| `image.compare` inspector | A/B previews, mode, threshold slider; the score is labelled “pixel” or “model”. |
| `image.batch` inspector | Multi-image upload/reorder (up to 8), a question list editor (up to 5), concurrency 1–3; a **results table** with one row per image so each candle option is read individually. |
| `agent.task` inspector | Sections: Prompt (instructions), Task, Agent, Tools, Memory, Output, Advanced. Tool field shows the preset’s available tools as suggestions; unavailable names are flagged before save. |
| Memory nodes | Scope picker (`general/workflow/project/run`), type multi-select, budget slider, and a clear “operator run required” marker on update/forget. |
| Canvas card | File chip (name · size), image thumbnail for `image` inputs/outputs, memory record count; inline `task` summary. |
| Run panel | Image thumbnails with “open”; batch results grouped per image; compare A/B side by side. |
| Validation | Uploaded-but-unparsed file, empty image set, question missing in `answer` mode, unknown agent tool, missing memory scope. |

Presentation only: config semantics and saved IR stay unchanged.

---

## 7. Runtime, provenance & security

### Test-run matrix

| Node | Test run | Operator run |
| --- | --- | --- |
| `data.file.attach` / `parse` | allowed (local read) | allowed |
| `data.file.export` | allowed (`local_write`) | allowed |
| `image.attach` | allowed (local asset read) | allowed |
| `image.analyze` / `ocr` / `read_chart` / `compare` | allowed with a bounded model call | allowed |
| `image.batch` | allowed with a bounded model call (max 8 images) | allowed |
| `agent.task` | allowed, tools narrowed to read-only | allowed |
| `agent.task` with `memoryMode: write` | **refused** | allowed |
| `memory.context` / `list` | allowed | allowed |
| `memory.update` / `forget` / `remember` | **refused** | allowed |

### Provenance rules (non-negotiable)

- Vision output is `kind: "observation"`, `verified: false`, with model,
  provider and warnings. It is never written to the EvidenceStore and never
  labelled Eclipse-verified. A chart reading is not a price.
- `image.read_chart` sets `verified: true` **only** when the engine’s own
  market-data check confirmed it; otherwise it returns `false` with the reason.
- A provider without vision capability, or missing model settings, is an explicit
  failure — never a placeholder observation.
- Uploaded files and images keep their original name/hash and are never
  re-labelled as a market-data source. Parsed rows keep
  `source: "upload:<assetId>"`; image results keep `sourceAssetId`.

### Filesystem / network

- Asset IDs are opaque; every read validates owner + `..`/absolute-path refusal
  (same guard style as `session-store.ts` and `file.write`).
- The vision model call is the only network path in this plan; it goes through
  the existing vision provider adapter (no new HTTP client, no raw fetches).
- No node accepts an arbitrary URL to “upload from”; that would duplicate
  `research.web_fetch` and needs egress grants. Users fetch with the research
  node and then upload the bytes.

---

## 8. Test matrix

| Area | Tests |
| --- | --- |
| Manifest parity | `registry.manifest.json` regenerated; existing Python parity suite covers new nodes, ports, config constraints. |
| `data.file.*` | round-trip save/load; owner mismatch; traversal names; size/count/TTL caps; CSV header/no-header/truncation; TSV; JSON array/object; XLSX first sheet; invalid encoding; missing asset names the file. |
| `image.attach` | content-addressed dedupe; MIME/type rejection; size cap; owner check; metadata (width/height/hash). |
| `image.analyze` | describe/answer/ground/extract modes; empty question fails by name; schema mismatch → `data: null` + issues; result labelled observation; provider without vision → classified failure. |
| `image.ocr` | text/spans/both; region handling; empty result is honest, not fabricated. |
| `image.read_chart` | structured reading shape; `verified` only from the engine’s market check; low-confidence warnings; no invented candles. |
| `image.compare` | pixel vs visual vs both; threshold semantics; disagreement reported; A/B recovery. |
| `image.batch` | one result per image; failed image is a row with `ok: false`; 8-image / 5-question caps; bounded concurrency; deterministic summary. |
| `agent.task` | prompt order (instructions → task → context → memory); tool intersection can only narrow; unknown tool fails by name; JSON output schema valid/invalid; memory write refused in a test run; run-status projection; retry/resume identity. |
| `memory.*` | budget drops lowest importance and reports it; scope resolution fails when the id is absent; list ordering; update/forget refused in a test run; service policy still wins. |
| UI | inspector field tests (`config-fields.test.ts`), port visibility, upload dropzone validation, batch question list, result table grouping. |
| E2E | upload CSV → parse → quant/transform → upload 3 candle images → `image.batch` (one reading per option) → `image.compare` best option → agent task → memory context → result. |

---

## 9. Work breakdown

| Wave | Tickets | Estimate |
| --- | --- | --- |
| **0** | D1/D2/D9 decisions; port types; category; `GraphAssetStore` + tests; Next upload proxy; capabilities; manifest | 2–3 days |
| **1** | `data.file.attach` (UI + executor), `data.file.parse`, `data.file.export`; examples; parity | 3–4 days |
| **2** | `image.attach` + image upload proxy; `image.analyze`, `image.ocr`, `image.read_chart`, `image.compare`, `image.batch`; vision runner injection in `bootstrap.py`; result labelling | 3–5 days |
| **3** | `agent.task`; shared agent fragment; upgrades to research/bot/delegate; tools allowlist; output schema; memory mode | 3–4 days |
| **4** | `memory.context`/`list`; confirm + implement service update/forget; `memory.update`/`forget`; scope resolver | 2–3 days |
| **5** | Canvas image thumbnails; onboarding/examples; docs/ADRs | 2–3 days |

**Acceptance gates for every wave**

1. `npm run graph:manifest` regenerated; Python parity suite green.
2. `npm run test` and `npx tsc --noEmit` pass from `Black-Eclipse-site/`.
3. Every new node has: a TS contract, a Python `NodeDef`, an executor, a
   config-fields presentation entry, an example, and at least one test.
4. No new engine, no new network client, no second store for the same bytes.
5. Test-run behaviour matches the matrix in §7.

---

## 10. Compatibility & rollout

- All additions are **additive**: new node types, new optional fields, new port
  types, one new category. No saved graph changes behaviour.
- `image`/`file` ports are new; existing graphs never reference them.
- Existing agent/memory nodes keep their defaults; new fields default to
  “off/empty”.
- No Prisma migration is required for the graph asset store (files on disk +
  metadata sidecars), unless a later query surface needs SQL; prefer the
  existing artifact/vision DB if one is already available.
- Manifest regeneration is mandatory and is the cross-language proof.

---

## 11. Out of scope / declined

| Item | Why declined (for now) |
| --- | --- |
| A generic code-execution node | Already a separate sandbox surface; a graph node would duplicate it and widen risk. |
| Upload-from-URL node | Duplicates `research.web_fetch` + egress grants. Compose the existing nodes. |
| A second vector/semantic memory store | The ONE memory service owns policy, dedupe, conflicts and retention. Nodes stay adapters. |
| Agent “Tool” sub-nodes wired on the canvas | Needs a tool-graph contract and credentials model; record as a future ADR. |
| Per-node model picker | Run-level model settings are the authorization boundary; revisit only if the settings contract gains a scoped override. |
| Chart **rendering** / candle-style authoring | **Answered: not in this plan.** Image nodes only read through the vision API. `output.chart` remains the separate deterministic chart surface. |
| Image **generation** (text-to-image) | **Answered: not in this plan.** The existing vision adapter remains available to chat/tools; no graph node ships for it here. |
| Video frames → image nodes | The video pipeline already renders preview frames; link them later if a real need appears. |

---

## 12. Docs to update when implementation lands

- `docs/graph-studio.md` — new node sections, assets, vision-read nodes, agent
  form, memory scopes.
- `docs/NAVIGATION.md` — this plan’s row + the files/image/agent/memory entry.
- `docs/CHANGELOG.md` — one entry per wave.
- `skills/ARCHITECT.md` + `docs/DECISIONS.md` — ADRs for D1 (asset ownership),
  D3 (vision output is an observation, never evidence), D7 (tool allowlist
  semantics).
- `docs/harness/memory-skills-evolution.md` (or the current memory doc) if
  update/forget adds a service mutation.
