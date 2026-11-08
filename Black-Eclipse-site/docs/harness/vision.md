---
title: Vision / Multimodal Subsystem
status: Current
last-verified: 2026-11-06
---

# Vision / Multimodal Subsystem

**Code:** `python/harness/vision/`
**Tools:** `vision_*`, `ocr_extract`, `visual_*`, `screenshot_analyze`,
`clipboard_analyze`, `chart_analyze`, `document_vision`, `image_*`,
`screen_compare` (registered by `vision/tools.py:register_vision_tools`)
**Config:** `python/harness/vision/config.py` (`vision.json` override + `HARNESS_VISION_*`)
**ADR:** `docs/harness/decisions.md` ADR-H146

## What it is

A single, provider-agnostic multimodal capability, integrated with the existing
agent runtime rather than bolted beside it. One orchestrator owns the whole
pipeline; individual tools never decode an image, pick a provider or call a model
themselves.

```
agent tool (vision_analyze, chart_analyze, ...)
        │
        ▼
VisionOrchestrator.orchestrate(input, ctx)        vision/orchestrator.py
        │
        ├─ resolve source        vision/load.py     (path/url/base64/clipboard/screenshot, PDF→page)
        ├─ preprocess            vision/image.py    (orientation, crop, downscale, re-encode PNG)
        ├─ store asset           vision/storage.py  (content-addressed, metadata in agent-memory.db)
        ├─ route                 vision/routing.py  (native-first → auxiliary fallback; privacy)
        ├─ capability detect     vision/capabilities.py (via model_runtime)
        ├─ cache                 vision/cache.py    (bounded in-process TTL, model-aware key)
        ├─ dispatch by mode:
        │     analyze/describe   vision/analyze.py   (structured JSON, injection guard)
        │     ocr                vision/ocr.py       (the existing Computer Use OCR engines)
        │     ground             vision/grounding.py (OCR-first, then model, coordinates)
        │     chart              vision/charts.py    (visual structure + market verification)
        │     document           vision/documents.py (PDF text layer + OCR + model)
        │     compare            vision/compare.py   (deterministic pixel diff + model prose)
        ├─ fallback across permitted candidates on a fallbackable failure
        └─ telemetry             vision/telemetry.py (vision.* events on the run emitter)
```

## Native-first (the central rule)

If the run's own model accepts images, the image goes to it. Only when it cannot
does the orchestrator fall back to an auxiliary vision model. Routing is pure
data (`routing.plan_route`) and is fully testable without a model; selection uses
the existing model registry and provider registry, reusing the runtime's
same-provider/keyless-local fallback rule. A different remote provider the run
holds no key for is never used (spec §31/§45).

## Privacy

`privacy_mode` is one of `cloud_allowed | cloud_preferred | local_preferred |
local_only`. A sensitive frame under a local-only policy is never sent to a
cloud provider; if no local model exists the request is refused
(`PRIVACY_REFUSED`), never silently uploaded. `vision/config.py` also supports a
`fallback_priority` list and an explicit auxiliary `vision_model`.

**One privacy story.** With `HARNESS_VISION_PRIVACY` (or `vision.json`) unset,
the mode INHERITS the app-wide switch: `ECLIPSE_PRIVACY=local-models` means
`local_only` for vision too. Before this, vision defaulted to `cloud_allowed`
regardless, so a screenshot could leave the machine while the app reported
local-only. A vision-specific setting may be stricter than the app switch; the
app switch is the floor.

**The fallback chain is bounded.** `max_attempts` (default 4) and
`max_per_provider` (default 2) cap how many candidates one call may try; a dead
vendor costs one timeout, not a walk through every configured provider
(measured 2026-11-06: 12 calls — five local models, LM Studio, then OpenRouter —
before one answered). A capped chain emits `vision.route.capped`. Every success
records `provider`/`model` in `provenance`, so the answer can say whether the
frame was read locally or sent to a named provider.

## Deterministic-first

- OCR runs before any model call (`ocr_extract` needs no model at all).
- Grounding tries OCR, then the model.
- Document vision reads the PDF text layer before the model.
- Image comparison computes the changed regions with a pixel diff; the model only
  describes them.
- Chart numbers are never a visual claim: when a symbol is given, the visual trend
  is verified against deterministic market data through the existing data bridge,
  and a disagreement is reported with market data authoritative.

## Security

Image input is untrusted input.

- **SSRF** — image URLs go through `mcp.ssrf.check_outbound_url` on every redirect
  hop (`vision/fetch.py`), with bounded redirects and a streaming byte ceiling.
- **Decompression bombs** — explicit byte/pixel ceilings plus Pillow's
  `MAX_IMAGE_PIXELS` (`vision/image.py`).
- **Prompt injection** — text recognized in an image (OCR or model transcription)
  is scanned and DELIMITED as untrusted data (`vision/security.py`, reusing
  `research.web_security`). Text inside an image is data, never an instruction.
- **Secrets/PII** — API-key / credential / PII-shaped strings are flagged so a run
  can avoid persisting or uploading a leaking frame; sensitive ephemeral sources
  are stored with a short TTL by default.

## Storage

Binary lives on the gitignored filesystem tier under
`.black-eclipse/vision/assets/`, content-addressed by SHA-256. Only metadata is
recorded in the `VisionAsset` table on the ONE `agent-memory.db` connection
(never `jdds.db`, never `eclipse-memory.db`). Identical images dedupe.

## Caching

There is no Redis in Eclipse (single-node, zero-config). The cache is a bounded
in-process TTL store keyed over image hash + model + provider + question + mode +
preprocessing options + result schema version, so a model/contract change can
never serve a stale answer. Hits/misses are emitted as telemetry.

## Evidence Engine integration

`vision/evidence.py` turns a result's observations into the SAME
`research.web_contracts.Evidence` object the web research engine uses and
persists it through `EvidenceStore.save_evidence` with full provenance (asset id,
region/bbox, page, model, provider, method, confidence). Recognized text is
`contentTrust=UNTRUSTED`.

## Agent context + right sidebar

`vision/collector.py` collects each `vision_*` result into a bounded run blob
(`asset ids, regions, OCR, confidence, chart/document/comparison, provenance`),
persisted on the `HarnessRun.vision` column and returned on
`RunResult.vision`/`client.final`. The TS `vision-view.ts` coerces it, and
`src/components/chat/vision-panel.tsx` renders it inline in the chat transcript —
the same provenance-panel idiom as `ResearchEvidencePanel`. Context stays compact:
the model sees a summarized `_summarize(result)`, not a blob dump.

## Capability detection

`vision/capabilities.py` wraps the model-runtime capability registry with the
vision-specific question ("can this model accept an image?") and records a
success as SUPPORTED / a specific failure as DEGRADED. Undeclared is UNKNOWN and
treated as "no" for native routing.

Vision is decided **per model family, not per SDK kind**: the `openai` kind is
shared by OpenAI, Ollama, LM Studio, DeepSeek, xAI, Groq and every
OpenAI-compatible endpoint, so it must not blanket-claim vision. The static
`MODEL_CAPABILITY_OVERRIDES` declares the vision-capable families (gpt-4o/4.1/
o-series/5, Claude, Gemini, grok-2-vision, and open-weight VLMs such as llava,
qwen2.5-vl, minicpm-v, moondream, pixtral, llama-3.2-vision, internvl, …) and the
text-only families, with longest-substring precedence (ADR-H148). `capabilities_for_model`
reads the RUN'S OWN model directly so a routed substitute is never misattributed.

## Providers

No new provider stack. Every model call goes through `harness.model_runtime`
(`resolve_for_run` → `build` → `invoke`), so OpenAI, Anthropic, Google,
OpenRouter, Ollama/LM Studio and OpenAI-compatible endpoints all work with the
routing, retry, fallback, health, usage and cost accounting the runtime already
provides.

When the run's own model cannot see images, the auxiliary vision model may live
on a DIFFERENT provider — but only when the process can actually reach it: a
keyless local server, or a hosted provider whose declared env-var credential is
present (`models.provider_has_credentials`). A remote provider the run holds no
key for is never selected. Common open-weight VLMs (llava, qwen2.5-vl, minicpm-v,
moondream, gemma-3) are declared for Ollama/LM Studio so a local VLM is found
without a discovery round-trip.

## Configuration

Env vars (`HARNESS_VISION_*`): `ENABLED`, `MODEL`, `FALLBACK`, `PRIVACY`,
`ALLOW_CLOUD_SENSITIVE`, `MAX_BYTES`, `MAX_PIXELS`, `MAX_DIMENSION`, `MAX_TILES`,
`TILE_OVERLAP`, `PREPROCESS`, `STRIP_METADATA`, `JPEG_QUALITY`, `OCR_ENABLED`,
`OCR_BACKEND`, `OCR_LANGUAGE`, `CACHE`, `CACHE_TTL`, `CACHE_MAX`, `URL_FETCH`,
`URL_SCHEMES`, `MAX_REDIRECTS`, `URL_TIMEOUT`, `INJECTION_GUARD`, `SENSITIVE_SCAN`,
`ARTIFACTS_DIR`, `TELEMETRY`, and `VISION_CONFIG` for the JSON file path.

## Tests

`test_vision_unit.py` (contracts, decode/validate, tiling, cache, routing,
security), `test_vision_orchestrator.py` (all modes + provider failure paths),
`test_vision_tools.py` (registry + storage + evidence), `test_vision_graph.py`
(a vision tool's result reaches the run blob) and
`src/lib/harness/vision-view.test.ts`.

## Known limitations (external)

- OCR depends on an OS engine: Windows-native (`winsdk`) or Tesseract. When
  neither is installed, `ocr_extract` reports `OCR_UNAVAILABLE` honestly.
- Clipboard and screen capture are OS/display dependent; a headless host reports
  `UNSUPPORTED_SOURCE`.
- Native vision depends on the model/provider genuinely accepting images; an
  undeclared capability is treated as unsupported and falls back.
- Image generation requires a provider that exposes an image-generation endpoint
  and a model that declares `image_generation`; without one it reports
  `NO_VISION_MODEL`.

## Capability-closure additions

Three areas that are genuinely implementable were closed rather than left as
limitations:

### PDF without `pypdfium2` (stdlib fallback)

`documents.py` now has TWO backends. `_PypdfiumDoc` is preferred (full text +
rasterization). `_StdlibPdf` is a dependency-free fallback that always extracts
the page text layer (uncompressed and FlateDecode content streams, `Tj`/`TJ`
operators) and rasterizes with Pillow when the page uses standard fonts. It
reports its `textMethod`/`rasterMethod` on the page, so the caller is told exactly
which method produced the result — and if it cannot rasterize, it says so (the
text is still returned). No PDF path is ever faked. `pdf_capabilities()` reports
what is available.

### Persistent visual memory (`vision_remember`)

Visual information is persisted ONLY when useful and permitted. `vision/memory.py`
does NOT bypass the memory gate: it goes through `authorize_proposal` +
`commit_decision` exactly like the `memory` tool, so a model-facing write still
requires explicit user intent. A compact TEXT summary is stored (never the image
bytes); the content-addressed `assetId` plus regions/model/provider/confidence go
into `structuredData`. A sensitive or ephemeral-source result is marked
low-importance and given a one-day TTL.

### Image generation (`image_generate`)

A dedicated `vision/generate.py` adapter speaks the OpenAI-compatible
`/images/generations` protocol (OpenAI, compatible gateways, local SD servers).
It never fabricates an image: no declared `image_generation` capability ⇒
`NO_VISION_MODEL`; HTTP 401/403 ⇒ `AUTH_ERROR`; 429 ⇒ `RATE_LIMIT`; a missing
image payload ⇒ `MALFORMED_RESPONSE`. The `image_generate` tool is registered as
`external_action` (effect `external_action`), so it is approval-gated by the run's
effect authorizer and removed at `plan_only` via `policy.VISION_EXTERNAL_TOOLS` —
the same boundary every other external (paid) tool uses.

## Operational hardening (the limitations cannot cause harm)

Two problems a "limitation" can otherwise cause were closed:

1. **Sensitive frames are decided BEFORE any model call.** The orchestrator runs
   `security.preflight_scan` (deterministic OCR over the frame) before routing, and
   merges the verdict into the privacy decision: a frame containing a real
   key/PII-shaped string or an injection attempt is marked sensitive, so under
   `local_only` it never goes to a cloud provider, and `_store_asset` gives it a
   TTL. The scan auto-flags only STRONG signals (real key/PII patterns or
   injection) — a bare word like "token" on a crypto chart does not over-refuse
   cloud analysis. Without an OCR engine the pre-scan is skipped and says so
   (never silently "clean").
2. **The TTL is real, not a claim.** `AgenticService.run_startup_maintenance`
   calls `VisionAssetStore.sweep_expired()`, deleting expired asset rows AND their
   files on boot — so a sensitive screenshot does not outlive its purpose and disk
   does not grow unbounded. Both were verified by test.

## Configuration

Env vars (`HARNESS_VISION_*`): `ENABLED`, `MODEL`, `FALLBACK`, `PRIVACY`,
`ALLOW_CLOUD_SENSITIVE`, `MAX_BYTES`, `MAX_PIXELS`, `MAX_DIMENSION`, `MAX_TILES`,
`TILE_OVERLAP`, `PREPROCESS`, `STRIP_METADATA`, `JPEG_QUALITY`, `OCR_ENABLED`,
`OCR_BACKEND`, `OCR_LANGUAGE`, `CACHE`, `CACHE_TTL`, `CACHE_MAX`, `URL_FETCH`,
`URL_SCHEMES`, `MAX_REDIRECTS`, `URL_TIMEOUT`, `INJECTION_GUARD`, `SENSITIVE_SCAN`,
`ARTIFACTS_DIR`, `TELEMETRY`, and `VISION_CONFIG` for the JSON file path.

## Tests

`test_vision_unit.py` (contracts, decode/validate, tiling, cache, routing,
security), `test_vision_orchestrator.py` (all modes + provider failure paths),
`test_vision_tools.py` (registry + storage + evidence), `test_vision_graph.py`
(a vision tool's result reaches the run blob), `test_vision_capabilities.py`
(stdlib PDF, image generation, persistent memory) and
`src/lib/harness/vision-view.test.ts`.

### Live provider smoke (opt-in)

`test_vision_live.py` runs a REAL multimodal call (native vision, deterministic
OCR, and auxiliary fallback) and is skipped by default with an explicit
`NOT RUN — ...` reason unless the operator enables it:

    BLACK_ECLIPSE_VISION_IT=1
    BLACK_ECLIPSE_VISION_PROVIDER=ollama            # default
    BLACK_ECLIPSE_VISION_MODEL=<a vision model>     # required
    BLACK_ECLIPSE_VISION_BASE_URL=http://127.0.0.1:11434/v1

It never runs in CI. The offline suites cover the same paths with a scripted
model; the live suite is the "does a real provider actually read an image" proof.
