---
title: Eclipse Canvas
status: Current
last-verified: 2026-10-17
---

# Eclipse Canvas

**Who this is for:** anyone asking "what is the Canvas, and how do I change it?"
— and anyone extending the editable-artifact surface.

Eclipse Canvas is a persistent, editable workspace for **documents, code and
visual reports**. It renders as an **inline pane inside the ChatBot tab** (not a
standalone page), and is built **on top of the Artifact Center**, not beside it:
see ADR-049. Those two facts are the whole design — everything below follows
from them.

## Viewer-first (Canvas Dock)

Canvas is primarily a **spacious reading surface for what the chat produced** —
the same content at reading width instead of cramped in the chat column. The
right-hand **Canvas Dock** (`components/screens/canvas/canvas-dock.tsx`) is a real
sibling column in the shell row (so the header and active tab shrink, not an
overlay) and is resizable.

- **Content model** (`src/lib/canvas/content.ts`): `CanvasContent` with kinds
  `markdown` / `code` / `report` / `url` / `image`. `contentFromMessage` (and
  `contentFromResponse`) derive it from an assistant message with no new schema —
  it reuses `splitResponseSegments`, `parseResponsePayload` and
  `toMarkdownProjection`. An `eclipse-response` fence becomes a `report`, a lone
  code fence becomes `code`, everything else is `markdown`.
- **Rendering** (`canvas-viewer.tsx`): markdown uses the chat renderer, reports
  use the response block registry (`ResponseView`), code uses Monaco read-only,
  URLs use a sandboxed (`sandbox=""`) iframe, images a plain `<img>`. No second
  markdown or block engine.
- **Entry points**: `Open in Canvas` on a chat response (`response-actions.tsx`)
  and on any assistant message (`chat-history.tsx`) opens the viewer; the Artifact
  Center's `Edit in Canvas` opens the editable artifact. Ephemeral views offer
  **Save to edit**, which registers an artifact and switches to the editor.
- **Dock header** (`canvas-dock.tsx`): the inline chat dock opens as one rounded
  surface card — a rounded icon tile plus the surface label (`Writing` for a
  prose answer, otherwise `Code` / `Report` / `Web page` / `Image`) — with
  Save to edit and Close at its right edge. The actual document title is the
  card's tooltip.
- **No manual chooser.** There are no "New Document/Code/Visual" buttons; creation
  is chat-driven, and an empty dock is a ready state that points at the entry
  points.
- **Ephemeral by default**, editable once saved (per the P1 decision).

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

Canvas is **not a standalone page**. It renders as an **inline pane inside the
ChatBot tab**, like a chat-side canvas: `src/components/screens/stock-chat.tsx`
splits the chat column and a right-hand `CanvasPane` whenever
`useCommandStore.canvasInlineOpen` (or `pendingCanvasArtifactId`) is set, and a
close button dismisses the pane. `CanvasScreen({ initialArtifactId?, isOperator?,
inline? })` is the data container; in `inline` mode `CanvasWorkspace` **skips the
rail** and wraps the center + AI panel in a glass card with a header and close.

- **Center** — the editor for the kind, a toolbar (rename/archive, version
  history + restore, export: download / copy / print), debounced autosave,
  Ctrl/Cmd+S, and the `409` conflict UI.
- **AI panel** — mode selector, optional selection, a propose → **diff** →
  accept flow, collapsed by default in the inline pane. Nothing is reported
  saved until the server returns the saved version.

`CanvasWorkspace` still contains a **rail** (list, search, create
document/code/report and file **import** — client-side read; over the size limit
is refused honestly), but the inline pane does not show it: artifacts are opened
from the Artifact Center and the chat surfaces below.

## Integration points

- **ChatBot inline pane** — `src/components/screens/stock-chat.tsx` splits the
  chat column and a right-hand `CanvasPane` when
  `useCommandStore.canvasInlineOpen`/`pendingCanvasArtifactId` is set.
- **Composer "+" menu → Canvas** — `chat/chat-input.tsx` / `chat/chat-dock.tsx`
  call `useCommandStore.openCanvas()` and switch to the chat tab.
- **Artifact Center → "Edit in Canvas"** — `artifacts-screen.tsx`
  (`dispatch({tab:'chat', params:{artifactId}})`), shown on an artifact detail
  whose metadata carries the `canvas` key.
- **Response actions → "Canvas"** — `response-actions.tsx`
  (`dispatch({tab:'chat', params:{artifactId}})`) keeps the saved artifact id and
  opens it inline.
- **Store** — `src/lib/search/store.ts` gained `canvasInlineOpen`, `openCanvas(id?)`
  and `closeCanvas()`; `pendingCanvasArtifactId` is retained.
- **Retired** — the standalone `canvas` surface was removed: the `canvas` AppTab
  (`app-tabs.ts`), the sidebar section (`sidebar/config.ts`), the `nav.canvas`
  key, the deep-link `APP_TABS` entry, the mobile bottom-nav item, the keep-alive
  block in `stock-chat.tsx`, and the `/canvas` slash command
  (`command-registry.ts` + the `native.canvas` handler).

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
