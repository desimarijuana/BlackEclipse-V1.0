---
title: Artifact Center
status: Current
last-verified: 2026-10-08
---

# Artifact Center

**Who this is for:** anyone asking "where did the file Eclipse produced go, and
how do I find/preview/download it again?" — and anyone extending the catalog.

The Artifact Center is the **one durable catalog of everything Eclipse and the
user produce**: reports, datasets, charts, images, code, backtest outputs, uploaded
documents. It is reachable from the Agentic sidebar (**Artifacts**), from the agent
(`artifact_*` tools), and from every producer subsystem through one service.

## The three layers (and what NOT to confuse them with)

| Layer | Where | Owns |
|---|---|---|
| Catalog rows | `agent-memory.db` tables `HarnessArtifact*` | metadata, provenance, lifecycle, tags, collections |
| File bytes | `.black-eclipse/artifacts/<owner>/<YYYY>/<MM>/<sha16>-<name>` | the content-addressed originals + thumbnails |
| Surfaces | `/artifacts/*` (FastAPI) → `/api/artifacts/**` (Next proxy) → Artifact Center UI | list/search/preview/download |

The catalog is **NOT JDdS** (`jdds.db`, market data) and **NOT** another
subsystem's tables. It adds its own tables through `artifacts/store.py`'s
`_ensure_schema`, on the ONE shared `agent-memory.db` connection — the same
pattern as `tasks/store.py` and `execution/store.py`.

## Code map

```
python/harness/artifacts/
  model.py       contracts: Artifact, ArtifactVersion, ArtifactCollection,
                 ArtifactPage, categories/statuses/preview states, input models,
                 the closed SORT_COLUMNS table
  content.py     the ONE MIME/category/preview-kind derivation (magic-byte sniff
                 where bytes exist; extension is a hint, never proof)
  storage.py     LocalArtifactStorage — confined, content-addressed, atomic,
                 size-bounded; OWNS storage keys (the service never sees a path)
  store.py       ArtifactStore — the tables + parameterized list/search; sort
                 keys are looked up, never interpolated
  preview.py     bounded text/CSV/JSON/code extracts + Pillow image/PDF thumbs;
                 office files read as ZIP+XML (never executed)
  service.py     ArtifactService — register/version/preview/tag/collect/archive/
                 restore/delete/purge/reconcile; owner scope + idempotency
  producers.py   the hook other subsystems call (analysis, task scheduler)
  tools.py       the `artifact_*` agent tools
  bootstrap.py   install_artifact_layer + the bounded reconciler singleton
python/harness/routers/artifacts.py   the /artifacts/* route group (operator-gated)
src/app/api/artifacts/[[...path]]/route.ts   the thin proxy (streams downloads)
src/lib/harness/artifacts-browser.ts         the client-safe UI client
src/components/screens/artifacts/artifacts-screen.tsx  the Artifact Center screen
```

## Registration contract (how files get in)

A producer calls `ArtifactService.register(...)` (or `register_bytes` /
`register_path`) with a **source** — a path inside an authorized workspace root, or
inline bytes. The caller **may never supply a storage key**. The service:

1. resolves + confines the source (refused if outside every authorized root),
2. copies the bytes into the content-addressed store (atomic temp + rename),
3. computes the sha256, MIME (with magic-byte sniff) and category,
4. inserts the row, the v1 version row, tags/collection links, and a lifecycle
   event, **then** generates the preview. A preview failure never invalidates the
   original — it is recorded as `previewStatus: FAILED`/`UNSUPPORTED`.

Idempotency: pass an `idempotencyKey`; a repeat returns the existing artifact
rather than creating a duplicate (this is how a run retry or a job replay stays
clean).

Producers wired today:

- `python/harness/analysis_tools.py` — every `ArtifactRef` an `analysis_run`
  produced (`register_run_artifacts`, idempotent per run+digest).
- `python/harness/tasks/scheduler.py` — a completed task's outcome artifacts
  (`register_reference_dicts`), mirrored beside the existing `HarnessTaskArtifact`.
- `python/harness/execution/orchestrator.py` — every file the Code Execution &
  Verification Layer collected from `dist/build/out/coverage/reports/…`
  (`_register_produced`, absolute paths from the workspace binding).
- Agents directly: `artifact_register`, `artifact_add_version`, `artifact_list`,
  `artifact_get`, `artifact_tag`, `artifact_create_collection`.

Terminal/filesystem discovery is the backstop: the bounded reconciler plus
explicit `artifact_register` cover files a command wrote, without ever scanning
arbitrary machine directories.

## Lifecycle

`ACTIVE → ARCHIVED → ACTIVE` (archive/restore are distinct and reversible) and
`→ DELETED → PURGED`. Delete is soft (bytes retained, recoverable); purge removes
every version's bytes and the rows, and **refuses while another artifact shares the
content**. State never changes without a recorded `HarnessArtifactEvent`.

## Authorization

Every `/artifacts/*` route (reads AND mutations) carries `require_operator`
(loopback or the runtime secret), and every query is scoped by `ownerId` (the
front door passes `x-harness-user`, defaulting to `local`). A caller can never
read, preview or download another owner's artifact — not by id, not by search, not
by thumbnail. Storage keys are validated against traversal, absolute paths and
symlink escape. Untrusted content is never executed; HTML/SVG is served as a
download and never rendered in the app origin.

## Reconciliation

`ArtifactService.reconcile()` is bounded and idempotent: it flags rows whose
storage object is gone as `MISSING`, recovers rows whose object reappeared, and
(opt-in) verifies checksums. With `discover`, it registers new files found under
the bounded workspace artifact directories. With `purge_expired`, it permanently
removes soft-deleted artifacts whose retention deadline (`retentionUntil`, else
`deletedAt + HARNESS_ARTIFACT_RETENTION_DAYS`) has passed — never ACTIVE/ARCHIVED
rows. A background reconciler runs reconcile+discover+purge every
`HARNESS_ARTIFACT_RECONCILE_SECONDS` (default 900, disable with
`HARNESS_ARTIFACT_RECONCILE=0`; disable purge with `HARNESS_ARTIFACT_AUTO_PURGE=0`).
On-demand: `POST /artifacts/reconcile`.

## Configuration

| Env | Meaning |
|---|---|
| `HARNESS_ARTIFACT_ROOT` | the storage root (default `<repo>/.black-eclipse/artifacts`) |
| `HARNESS_ARTIFACT_RECONCILE` | `0` disables the background reconciler |
| `HARNESS_ARTIFACT_RECONCILE_SECONDS` | reconciler interval (floor 60s) |
| `HARNESS_ARTIFACT_RETENTION_DAYS` | grace period before a soft-deleted artifact is auto-purged (default 30) |
| `HARNESS_ARTIFACT_AUTO_PURGE` | `0` disables automatic purge of expired soft-deleted artifacts |
| `AGENT_MEMORY_DB_PATH` | the catalog database (the ONE shared harness DB) |

## Tests

```
scripts/vendor/python/python.exe -m pytest python/tests/test_artifacts_store.py \
  python/tests/test_artifacts_security.py python/tests/test_artifacts_tools.py \
  python/tests/test_artifacts_api.py -v
npx vitest run src/lib/harness/artifacts-browser.test.ts src/app/api/artifacts/route.test.ts
```

## Realtime

Artifact lifecycle mutations publish canonical `artifact.*` events on the ONE
Event System bus (`event_system/registry.py`, `artifact` namespace) so an operator
console or a future live subscriber can react; the Artifact Center UI refreshes on
a bounded poll and recovers authoritative state by re-querying the API (so a
dropped realtime channel never leaves a stale view).
