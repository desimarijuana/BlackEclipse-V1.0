---
title: Eclipse Canvas
status: Current
last-verified: 2026-10-17
---

# Eclipse Canvas

**Who this is for:** anyone asking "what is the Canvas, and how do I change it?"
— and anyone extending the editable-artifact surface.

Eclipse Canvas is a persistent, editable workspace for **documents, code and
visual reports**. It is built **on top of the Artifact Center**, not beside it:
see ADR-049. That single fact is the whole design — everything below follows
from it.

## The one invariant

> A canvas document **is** an Artifact Center artifact. There is no canvas
> database, no canvas storage root and no canvas version table.

- Content is canonical **UTF-8 text**, stored as the artifact's immutable
  content-addressed bytes and appended revisions (the Artifact Center's own
  versioning).
- The canvas **kind** (`document` / `code` / `visual`) and optional `language`
  live in the artifact's `metadata` under the key `canvas`
  (`CANVAS_METADATA_KEY`, schema version `CANVAS_SCHEMA_VERSION`).
- Because it is an ordinary artifact, it inherits owner scope, preview,
  download, tagging, collections, archiving and reconciliation for free.

## Kinds and editors

| Kind | Artifact category / MIME | Canonical content | Editor |
|---|---|---|---|
| `document` | `document` / `text/markdown` | **Markdown** | Tiptap rich editor |
| `code` | `code` / `text/plain` | source text | Monaco |
| `visual` | `report` / `application/vnd.eclipse.canvas.visual+json` | an Eclipse **response envelope** (JSON) | JSON editor + live `ResponseView` preview |

The document editor is a rich editor whose **canonical content is Markdown** —
the editor state is serialized back to Markdown on save, so content stays
portable and diffable. A visual artifact is the same JSON the Interactive
Response Engine renders in chat, so a visual report can be previewed in place.

## Code map

```
python/harness/canvas/
  model.py     contracts: CanvasKind/CanvasMode/CanvasOp, EditOperation,
               CanvasSnapshot/CanvasProposal/CanvasConflict/CanvasUnavailable,
               CreateCanvasInput/SaveCanvasInput/RestoreCanvasInput, limits
  ops.py       pure validation + deterministic application of typed ops
               (no eval, no template rendering, no arbitrary code)
  service.py   CanvasService — the ONE canvas writer over ArtifactService
               (create/read/list/save/restore; lock + revision guard)
  edits.py     CanvasEditOrchestrator — strict-JSON prompt → model → validate
python/harness/routers/canvas.py            the /canvas/artifacts* route group
src/lib/harness/canvas-client.ts            the typed browser client
src/app/api/canvas/[[...path]]/route.ts     the thin proxy (+ model injection)
src/components/screens/canvas/              the UI (rail / center / AI panel)
```

## Routes

All routes are operator-gated; the owner is taken from the runtime identity
header `x-harness-user` (default `local`). The Next proxy adds the CSRF/origin
guard for mutations and the runtime identity headers.

| Method + path | Purpose |
|---|---|
| `GET /canvas/artifacts` | list (`kind`, `q`, `limit`) |
| `POST /canvas/artifacts` | create |
| `GET /canvas/artifacts/{id}` | read a snapshot (content + versions) |
| `PUT /canvas/artifacts/{id}` | save (revision-guarded) |
| `POST /canvas/artifacts/{id}/restore` | restore a prior version |
| `POST /canvas/artifacts/{id}/edits` | propose an AI edit (does not apply) |

The front door is a pass-through **except** for `.../edits`, where Next resolves
the operator's configured model from the settings vault
(`resolveRunModelSettings`) and injects `modelSettings` — the Python runtime
cannot read the vault.

## Revision guard (why a save can be refused)

A save carries the `baseVersion` the editor loaded. The service takes a lock and
compares it to the artifact's current version:

- match → append a new immutable version;
- mismatch → **`409 CANVAS_CONFLICT`** with the server's `currentVersion`.

The client surfaces this as an honest conflict (`CanvasConflictError` carries
`currentVersion`) and offers reload-latest rather than overwriting. This exists
because keep-alive editors and AI proposals can both hold stale bytes, and a
silent overwrite would lose work.

## The operation contract

AI never returns content or a patch. It returns one or more **typed**
`EditOperation`s (max `MAX_OPERATIONS`), each validated and applied
deterministically to the current bytes by `ops.py`:

| op | meaning |
|---|---|
| `append` | append text at the end |
| `replace_text_range` | replace `[start, end)`; `expected_text` must match |
| `replace_section` | replace a Markdown section by heading |
| `insert_after_section` | insert after a Markdown section heading |
| `replace_document` | replace the whole document |
| `apply_code_patch` | unique `search` → `replace` patch |

Unknown, ambiguous or stale operations are **rejected**. There is no eval, no
template rendering and no arbitrary code execution, preserving the no-model-code
posture (SEC-001). Content limits: `MAX_CANVAS_BYTES` (2 MB artifact bytes),
`MAX_EDIT_CONTENT_CHARS` per operation field.

## AI orchestrator and modes

`CanvasEditOrchestrator` is the only model path, and it rides the ONE model
runtime — no bespoke provider adapter:

1. Build a strict-JSON prompt tailored to the kind (documents use section ops;
   code uses patches; visuals must not invent numbers).
2. Call `vision.providers.call_model` with task `canvas_edit`.
3. Validate the reply with `model_runtime/structured.py`.
4. Re-validate every operation against the revision the user loaded and compute
   `resultContent`.

Modes: `ask` (answer only — **never** proposes edits), `edit` (smallest
satisfying operation set), `review` (find gaps/errors/unsupported claims; propose
only safe fixes), `build` (create or extend). A missing model configuration
returns the honest `CANVAS_MODEL_UNAVAILABLE` — never a fake proposal.

Applying is always a **separate explicit save** that carries the same base
revision. On an AI-assisted save the client sends the operations and the server
re-applies them to the current bytes, so client-supplied content is never
trusted.

## UX surfaces

`CanvasScreen({ initialArtifactId?, isOperator? })` is the data container; a
three-region `CanvasWorkspace` presents it:

- **Rail** — list, search, create (document/code/report) and file **import**
  (client-side read; over the size limit is refused honestly).
- **Center** — the editor for the kind, a toolbar (rename/archive, version
  history + restore, export: download / copy / print), debounced autosave,
  Ctrl/Cmd+S, and the `409` conflict UI.
- **AI panel** — mode selector, optional selection, a propose → **diff** →
  accept flow. Nothing is reported saved until the server returns the saved
  version.

## Integration points

- **AppTab `canvas`** — `src/lib/app-tabs.ts`, sidebar `config.ts` (icon
  `SquarePen`, agentic group), `nav.canvas`, deep-link `APP_TABS`, mobile bottom
  nav and a keep-alive block in `stock-chat.tsx`.
- **`/canvas [document|code|report|visual]`** — `command-registry.ts` +
  `native.canvas` handler returning a link that opens Canvas in the chosen mode.
- **Artifact Center → "Open in Canvas"** — shown on an artifact detail whose
  metadata carries the `canvas` key (`artifacts-screen.tsx`).
- **Response actions → "Canvas"** — keeps the saved artifact id and offers to
  open it in Canvas.

## Explicit non-goals (documented, not faked)

- **No second store.** No canvas table, no canvas storage root, no separate
  version table. If you find yourself adding one, stop.
- **No collaborative/real-time multi-editor** editing and no CRDT merge — the
  revision guard detects concurrent writes; it does not merge them.
- **No model-authored content or patches** applied directly — operations only.
- **No Postgres.** Storage is SQLite (`agent-memory.db`) + artifact files under
  `.black-eclipse/artifacts`.

## Tests

```
scripts/vendor/python/python.exe -m pytest python/tests/test_canvas.py \
  python/tests/test_canvas_api.py -v
npx vitest run src/app/api/canvas/route.test.ts \
  src/components/screens/canvas/canvas-screen.test.tsx
```

## See also

- `docs/harness/artifact-center.md` → Canvas, for how canvas entries sit in the
  catalog.
- ADR-049 (in `skills/ARCHITECT.md` + `docs/DECISIONS.md`), ADR-043 (Interactive
  Response Engine) for the visual-envelope contract.
