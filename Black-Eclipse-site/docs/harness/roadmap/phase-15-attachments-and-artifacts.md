---
title: "Phase 15 — Documents In, Files Out, and Landing a Change"
status: In progress
phase: 15
depends_on: [14]
unlocks: [18, 20]
last-verified: 2026-10-11
---

> **Progress (2026-10-11).** The **promotion slice is Done** under **ADR-H176**
> (`python/harness/code/promotion.py`, `POST /code/tasks/{id}/promote/preview` +
> `.../promote`, the additive `patch.py` `overwrite` op, the chat/Code-Tasks
> control, `python/tests/test_code_promotion.py`). The document extractors
> (§6.1–§6.2, docx/xlsx/pptx), the artifact serving routes/renderer (§6.3) and the
> raised caps remain **Not started**.

# Phase 15 — Documents In, Files Out, and Landing a Change

| | |
|---|---|
| **Depends on** | Phase 14 (a change that cannot leave Eclipse's copy is not useful until a user can put it somewhere) and Phase 8 (`analysis_run`'s `ArtifactRef`, the artifact directory convention). |
| **Unlocks** | Phase 18 (a chart is an artifact of the same kind) and Phase 20 (the gate grades these shapes). |
| **Estimated work** | 14–18 h of agent time. Front-door extraction + one serving route + the promotion path. |
| **Deliverable type** | three extractors, one artifact-serving route group, one renderer, one promotion action. |
| **Decision records** | ADR-H118 (attachments are data of unlimited shape, bounded by size, never by format), ADR-H119 (a change lands only through an explicit, single-use, operator-confirmed promotion) |
| **Prompt to copy** | [§11 below](#11-implementation-prompt) |

---

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists](#2-why-this-phase-exists)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 Extraction, extended at the existing seam](#61-extraction-extended-at-the-existing-seam)
  - [6.2 The caps, with one authority](#62-the-caps-with-one-authority)
  - [6.3 Serving an artifact](#63-serving-an-artifact)
  - [6.4 The promotion decision (**the user's call — the one item that cannot be defaulted**)](#64-the-promotion-decision-the-users-call--the-one-item-that-cannot-be-defaulted)
  - [6.5 Refusal codes](#65-refusal-codes)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt](#11-implementation-prompt)

---

## 1. Goal

Three things a person expects from an assistant and cannot do today: hand it a
document in any ordinary office format, get a file back, and let a change it made
actually reach their project. After this phase all three work, each bounded, each
honest about what it could not read, and the third one gated on an explicit
confirmation that is the user's, never the model's.

## 2. Why this phase exists

**(a) The in-direction is text-only.** `src/lib/chat/extract.ts`:

```ts
const TEXT_EXTENSIONS = new Set([
  "txt", "md", "markdown", "csv", "tsv", "json", "log", "yml", "yaml",
  "xml", "html", "htm", "sql", "ini", "cfg", "toml",
]);
export function isTextExtractable(name: string): boolean {
  return TEXT_EXTENSIONS.has(extensionOf(name)) || extensionOf(name) === "pdf";
}
```

Verified in the tree: no `.docx`, `.xlsx` or `.pptx` extractor exists in either
language — `grep -niE "\"(mammoth|xlsx|exceljs|docx|pptx|pdf-parse|pdfjs)\"" package.json`
and the equivalent grep of `python/requirements.txt` both return **nothing**. So
the document a finance professional actually has — a model workbook, a board deck,
a filing converted to Word — is rejected at attach time. The file comment even
states the design intent:

> "Unknown/binary types are rejected rather than being fed to the model as
> mojibake."

That is right for the *prompt*; it is wrong as a statement about what the product
accepts. The repo already contains the Python stack that reads these formats in its
own vendored interpreter, so this is a wiring decision, not a capability gap.

**(b) The caps make "paste a document in" a half-measure.** `SESSION_LIMITS` in
`src/lib/chat/session-types.ts` and the mirror in `validation.ts`:

```
maxFileBytes        8 * 1024 * 1024
maxDocChars         20_000
maxTotalDocChars    60_000
maxContextFiles     20
MAX_DOCUMENTS       20   (validation.ts)
```

A 40-page deck truncates silently at 20 000 characters; the front door reports a
`note`, the run does not. A user who pastes a prospectus and asks a question about
page 30 gets a confident answer from page 1.

**(c) The out-direction renders filenames, not files.**
`src/components/chat/computed-result-panel.tsx` — the ONLY artifact surface in chat:

```tsx
{data.artifacts.length > 0 ? (
  <div>
    <p className="font-semibold text-foreground">{t('analysis.saved')}</p>
    <ul className="space-y-0.5 text-muted-foreground/80">
      {data.artifacts.map((a) => (
        <li key={a.sha256} className="flex items-center gap-1.5">
          <span>{a.name}</span>
          <span className="font-mono text-[9px] text-muted-foreground/60">{a.sha256.slice(0, 12)}</span>
```

A name and a truncated hash. The artifact itself lives at
`.black-eclipse/artifacts/<runId>/` (`analysis_tools.py::_artifacts_dir`) and **no
route serves it**: the only artifact route in the tree is the jobs one,
`src/app/api/jobs/[id]/runs/[runId]/artifact/route.ts`. `code/execution.py` already
sniffs MIME types including `image/png`, so the type system anticipates files with
no way to hand one over.

**(d) A change never leaves the disposable copy.** Verified this session:

- `worktree.allocate` is called only from `code/tools.py::_ensure_code_workspace`
  and `code/evolution_service.py` — nothing else.
- `worktree.release` deletes the disposable copy ("refuses outside scratch +
  idempotent") and **no function copies a change back** to the checkout:
  `grep -rniE "shutil.copy|copytree|apply.*to.*root|promote" python/harness/code/*.py`
  returns only the snapshot-fallback copy inside `allocate`.
- The external action's handler performs **no git operation at all**:

```python
async def handler(args, ctx):
    ws = getattr(ctx, "workspace", None)
    if ws is None:
        return _action_refusal(action_kind, "WORKSPACE_UNBOUND")
    await emit_code_event(ctx, "code.action.performed", {...})
    text = (f"Approved and recorded: {action_kind}. "
            "The action ran under your approval for this task.")
    return text, {"status": "approved", "action": action_kind, ...}
```

`code_commit` reports `status: "approved"` and takes no git action. Verified
`effect_metadata = {'actionKind': 'commit'}` on the registered definition and the
handler body above. So "Eclipse modified my code" is, today, a diff inside a
scratch directory that the release path deletes.

This is the user's complaint in its sharpest form, and the fix is **the user's
decision, not the agent's** — see §6.4.

## 3. In scope

1. Three extractors — `.docx`, `.xlsx`, `.pptx` — reached through the existing
   extraction seam (`extract.ts`), so no new pipeline and no new dependency on the
   client bundle: the heavy reading happens in the vendored Python interpreter the
   repo already ships, invoked from the route handler (server-side only).
2. Per-document **truncation that is visible in the run**, not only in a front-door
   note: the injected document carries its own `truncated: true` + original size, and
   the runtime states the limit in the run's limitations.
3. Higher, explicitly declared caps, with one constant as the authority
   (`SESSION_LIMITS`) mirrored rather than re-typed.
4. An artifact **serving** route group for chat runs, mirroring the jobs artifact
   route's derivation rule (the runtime derives the path; the route never accepts a
   caller-supplied path).
5. A renderer in the chat panel: images inline, tabular artifacts as a preview
   table, everything else as a download — with the provenance line unchanged
   (`analysis.notASource`).
6. **Promotion** — the chosen option from §6.4 — implemented behind the existing
   single-use approval primitive, with a mandatory preview of exactly what will
   change.

## 4. Who can use it (the non-expert obligation)

The formats chosen are the ones a non-engineer has: Word, Excel, PowerPoint.
Nothing about the surface mentions an extractor, a MIME type, a parser or a
sandbox: the user attaches a file, and if it cannot be read they read one plain
sentence — "I couldn't read that file's text; try exporting it as PDF" — with the
technical reason behind a details affordance. Truncation is stated in the answer
itself ("I read the first part of that workbook — the rest was too large to
include"), because a silently truncated document is the failure mode that produces
a confidently wrong answer.

For promotion, the copy names the job: "Put this change into my project" or "Give
me the change as a file I can apply myself" — never a commit, a branch, a patch, a
worktree or a diff as *user-facing* words (they may appear in the trace). Every
string is an i18n key under `attach.*` / `artifact.*` / `promote.*`.

## 5. Non-goals (do not do these)

- **No OCR.** A scanned PDF without a text layer still refuses, honestly. (The repo
  has an `ocr` concept in the PDF tooling skill; importing it here is a separate
  decision, not this phase.)
- **No new file storage system.** Artifacts stay on the existing on-disk convention
  (`.black-eclipse/artifacts/<runId>/`, gitignored per run); no database BLOB, no
  new table.
- **No auto-promotion, ever, and no promotion from a model's claim.** The change
  lands only via the user's explicit confirmation of a previewed change.
- **No `git` write from the runtime.** Promotion applies file content; committing
  remains the existing, separate, approval-gated action (and stays unreachable from
  chat, Phase 14 §5).
- **No arbitrary path in an artifact request.** The route derives the path from
  (runId, artifact name) recorded in the run; a traversal attempt is refused.
- Never commit, push or open a PR; do not commit `jdds.db`.

## 6. Exact contracts to create

### 6.1 Extraction, extended at the existing seam

```ts
// src/lib/chat/extract.ts — additive
const OFFICE_EXTENSIONS = new Set(["docx", "xlsx", "pptx"]);

/** True when we can turn the file into text the model can read. */
export function isTextExtractable(name: string): boolean {
  const ext = extensionOf(name);
  return TEXT_EXTENSIONS.has(ext) || ext === "pdf" || OFFICE_EXTENSIONS.has(ext);
}

/** Extracted text plus what the reader must know about it. */
export interface ExtractResult {
  ok: boolean;
  text?: string;
  /** Present when `ok` is false, or when the text was truncated. */
  note?: string;
  /** ADDITIVE: the doc was larger than the cap and the tail was dropped. */
  truncated?: boolean;
  /** ADDITIVE: characters in the source before truncation, when known. */
  sourceChars?: number;
  /** ADDITIVE: the part of the document that was read (e.g. "sheets 1–2"). */
  coverage?: string;
}
```

The office path shells out to the vendored interpreter
(`scripts/vendor/python/python.exe`) through a new server-only module
`src/lib/chat/office-extract.ts`, which calls a new script
`scripts/extract-office.py` (stdlib + the readers available in the vendored
interpreter; if a reader is genuinely absent, the script exits with a distinguishable
code and the extraction refuses — never a partial parse passed off as the document).
The **server-only** placement is mandatory: importing it from a client component
would pull `child_process` into the browser bundle and 500 the route (the exact
defect recorded in `surface-closure-progress.md`'s follow-up section).

### 6.2 The caps, with one authority

```ts
// src/lib/chat/session-types.ts — the ONE declaration
export const SESSION_LIMITS = {
  maxFileBytes: 24 * 1024 * 1024,   // was 8 MB: a workbook is often larger
  maxDocChars: 60_000,              // was 20 000
  maxTotalDocChars: 240_000,        // was 60 000
  maxContextFiles: 20,
} as const;
```

`src/lib/harness/validation.ts` **imports** these instead of re-declaring
`MAX_DOCUMENTS`/`MAX_TOTAL_DOCUMENT_CHARS`, and raises `MAX_DOCUMENTS` to match
`maxContextFiles` — one number, one place. `RunDocument` gains the additive
`truncated`/`sourceChars`/`coverage` fields, and `graph.py`'s document injection adds
a limitations line when any document is truncated:

```python
# python/harness/graph.py — the injected block, additive sentence
"\n\nNote: {n} attached document(s) were too large to include in full; the "
"answer may not cover their later parts."
```

### 6.3 Serving an artifact

```ts
// src/app/api/harness/runs/[id]/artifacts/route.ts        — GET: the list
// src/app/api/harness/runs/[id]/artifacts/[name]/route.ts — GET: one file
// The runtime derives the path (`analysis_tools._artifacts_dir`) from the run id
// and the artifact name RECORDED in the run; the route passes both through and
// never accepts a path. A name not recorded on the run is 404.
```

```ts
// src/components/chat/artifact-view.tsx — new
// image/* → inline <img> (via MEDIA-style local path), text/csv → a bounded
// preview table (first 50 rows), everything else → a download card with name,
// byte size and the provenance line. No client-side parsing of the file.
```

### 6.4 The promotion decision (**the user's call — the one item that cannot be defaulted**)

| | Option A — export only | Option B — confirmed promotion *(recommended)* |
|---|---|---|
| What the user gets | The change as a downloadable file they apply themselves | A "Put this change into my project" action that applies the previewed change to the real checkout |
| Mechanism | The diff + file contents as an artifact; no write outside scratch | A new `CodeActionKind` reusing `mcp/approvals.py` (`claim_guarded`), digest-bound to the exact file set, single-use, operator-gated, with a mandatory preview rendering |
| Risk | None to the user's tree | A write to the user's own checkout, bounded to the previewed file set, refused if the file changed on disk since the preview (the Phase-2 content-hash base already exists in `code/patch.py`) |
| Consequence on the rest of the system | `code_commit` stays a recorded no-op, which must be **fixed or removed** either way | Makes the existing external-action tool honest: a commit action has something to commit |
| Cost | ~3 h | ~8 h |

**Recommendation: B, with A shipped as the fallback for an unavailable git or a
failed base check.** The user's own words — "cannot modify and edit its own code" —
describe a capability that only exists if the change lands. The guardrails are
already in the tree: the content-hash base (`patch.apply`'s before/after hashes), the
single-use approval store, the protected-path policy, and `PROTECTED_PATHS` freezing
`policy.py`/`permissions.py`/`approvals.py`/`check-all.js` so a promoted change
cannot disable its own gate.

**Leaving this silent is the one unacceptable outcome.** If Option A is chosen, the
phase must also state in `code/action_tools.py` and in ADR-H119 that the four
external actions are *recorded approvals with no runtime effect*, so no reader is
misled by `status: "approved"`.

### 6.5 Refusal codes

| Code | Meaning |
|---|---|
| `EXTRACT_UNSUPPORTED` | the format has no reader (existing behaviour, now with a next step) |
| `EXTRACT_FAILED` | the reader ran and could not recover text; the document is NOT injected |
| `DOCUMENT_TRUNCATED` | not a failure — a stated limitation carried into the answer |
| `ARTIFACT_NOT_FOUND` | the name is not recorded on this run |
| `PROMOTION_BASE_CHANGED` | the file changed on disk since the preview; the promotion is refused and must be re-previewed |
| `PROMOTION_OUT_OF_SCOPE` | the file set exceeds the approved set, or touches a protected path |

## 7. Work items (ordered)

1. `scripts/extract-office.py` — new: docx/xlsx/pptx → text, with an explicit exit
   code when a reader is unavailable. Test it against fixtures in
   `python/tests/fixtures/office/` (small, generated, committed).
2. `src/lib/chat/office-extract.ts` — new, server-only.
3. `src/lib/chat/extract.ts` — the additive `ExtractResult` fields and the office
   branch; keep the existing truncation note.
4. `src/lib/chat/session-types.ts` + `src/lib/harness/validation.ts` — the raised,
   single-sourced caps.
5. `python/harness/schemas.py` (`RunDocument` additive fields) +
   `python/harness/graph.py` (the truncation limitation sentence).
6. `python/harness/analysis_tools.py` — record each artifact on the run
   (`HarnessRun.analysisArtifacts`, additive) so the serving route has an authority
   to check against. No schema change to `prisma/`.
7. `src/app/api/harness/runs/[id]/artifacts/…` — the two routes, deriving paths.
8. `src/components/chat/artifact-view.tsx` + the `computed-result-panel.tsx` change
   to render it, replacing the name+hash list.
9. **The promotion implementation for the chosen option** — `code/actions.py`
   (the new kind), `code/action_tools.py` (the real effect or the honest no-op
   note), `routers/code.py` (preview + decide routes), `src/components/screens/code/`
   (the preview rendering).
10. `en.ts` — `attach.*`, `artifact.*`, `promote.*`; extend the plain-language lists.
11. `docs/harness/roadmap/progress/phase-15-progress.md` — created, gates unchecked.

## 8. Deliverables

| File | Change |
|---|---|
| `scripts/extract-office.py` | new — docx/xlsx/pptx → text |
| `src/lib/chat/office-extract.ts` | new — server-only invoker |
| `src/lib/chat/extract.ts` | changed — office branch + honest `ExtractResult` |
| `src/lib/chat/session-types.ts` | changed — one cap authority |
| `src/lib/harness/validation.ts` | changed — imports the caps |
| `python/harness/schemas.py`, `graph.py` | changed — additive document fields + stated truncation |
| `python/harness/analysis_tools.py` | changed — artifacts recorded on the run |
| `src/app/api/harness/runs/[id]/artifacts/**` | new — the serving routes |
| `src/components/chat/artifact-view.tsx` | new — image / table / download |
| `src/components/chat/computed-result-panel.tsx` | changed — renders `ArtifactView` |
| `python/harness/code/{actions,action_tools}.py` | changed — the promotion kind (chosen option) |
| `docs/harness/decisions.md` | changed — ADR-H118, ADR-H119 |
| `python/tests/test_office_extract.py`, `src/lib/chat/extract-office.test.ts` | new |

## 9. Acceptance gates

```bash
# G1 — the office extractors read real fixtures, and an unreadable one refuses.
./scripts/vendor/python/python.exe -m pytest python/tests/test_office_extract.py -v
npx vitest run src/lib/chat/extract-office.test.ts

# G2 — truncation is visible in the RUN, not only in the front door.
./scripts/vendor/python/python.exe -m pytest python/tests/test_document_truncation.py -v

# G3 — an artifact is served from the run's own record, and traversal is refused.
npx vitest run src/app/api/harness/runs/artifacts.test.ts

# G4 — the client bundle stays server-free (the 500 this repo has already hit once).
npm run build   # must exit 0, and / must render

# G5 — promotion (Option B): a changed base refuses; a protected path refuses;
#      an unapproved file refuses; the approved set applies and is recorded.
./scripts/vendor/python/python.exe -m pytest python/tests/test_code_promotion.py -v

# G6 — the full release gate.
npm run check:all
```

| Gate | Assertion |
|---|---|
| G1 | Each fixture yields its real text (a `.xlsx` with two sheets, a `.docx` with a table, a `.pptx` with three slides); a corrupt file returns `ok: false` with a note and is **not** injected; a missing reader exits distinctly rather than emitting partial text. |
| G2 | A document over `maxDocChars` sets `truncated` on the `RunDocument` and the run's limitations contain the sentence; a document under it does not. |
| G3 | `GET .../artifacts/<recorded-name>` returns the bytes and content type; `../`, an absolute path and an unrecorded name are all 404/400 — asserted, not assumed. |
| G4 | `npm run build` exits 0 and the app renders — the specific failure mode a server-only import into a client component causes. |
| G5 | In Option B: a previewed set applies; the same set after the file changed on disk is refused with `PROMOTION_BASE_CHANGED`; a set containing `python/harness/code/policy.py` is refused with `PROMOTION_OUT_OF_SCOPE`; a second use of the consumed approval is refused; the applied change is recorded in the Phase-4 ledger. In Option A: the exported files round-trip and the ADR states the external actions have no effect. |
| G6 | `ALL GATES PASSED`; vitest and pytest counts reported as observed. |

**A gate not run is a gate not passed.** Paste the raw output of each into
`docs/harness/roadmap/progress/phase-15-progress.md`.

## 10. Definition of done

- A `.docx`, `.xlsx` and `.pptx` each attach and answer a question about their real
  content; a format with no reader refuses with a next step.
- Truncation is stated in the run, not only in a front-door note.
- A produced file can be viewed or downloaded from chat; an image renders inline.
- The promotion decision is made and named in ADR-H119: either the change lands
  through a previewed, single-use, digest-bound confirmation, or the phase states
  plainly that the four external actions have no runtime effect.
- No path is accepted from a caller anywhere in the artifact routes.
- ADR-H118 and ADR-H119 written; changelog appended; NAVIGATION rows 154 and 186
  updated; `status:` and the index row flipped.

## 11. Implementation prompt

```text
Task: Phase 15 — attachments, artifacts, and landing a change.

First, in your FIRST message, state which promotion option you are implementing
(A export-only, or B confirmed promotion — recommended) and why. Do not start
without naming it.

Read first, in full:
- docs/harness/roadmap/phase-15-attachments-and-artifacts.md (this file, verbatim)
- docs/harness/roadmap/README.md (§3 invariants, §6 non-goals)
- src/lib/chat/{extract.ts,session-types.ts}, src/lib/harness/validation.ts
- src/components/chat/computed-result-panel.tsx
- scripts/yfinance_fundamentals.py (the pattern: a server-side script the front door invokes)
- python/harness/code/{actions,action_tools,patch,store}.py
- src/app/api/jobs/[id]/runs/[runId]/artifact/route.ts (the derivation rule to mirror)
- docs/harness/roadmap/progress/surface-closure-progress.md (the server-only import defect)

Goal: a user can attach an ordinary office document and get a truthful answer about
it, receive a produced file back, and (per the option you named) put a previewed
change into their own project — each bounded, each refusing honestly.

In scope: see §3 (1–6) and §7 (the ordered work items). Implement exactly those.

Non-goals (do NOT do these):
- No OCR; a scanned PDF with no text layer refuses.
- No new storage system; artifacts stay on the existing per-run on-disk directory.
- No auto-promotion and no promotion based on a model's claim — the user confirms a
  previewed change; nothing else.
- No git write from the runtime; committing stays the separate approval-gated action
  and stays unreachable from chat.
- No caller-supplied path in any artifact route.
- Never commit, push or open a PR. Do not commit jdds.db.

Constraints:
- One runtime; new logic in new modules; keep the existing big files under their
  size ratchets.
- The office extractor MUST be server-only. A client component importing it pulls
  child_process into the browser bundle and 500s the route; gate G4 exists for that.
- One cap authority: validation.ts imports SESSION_LIMITS, it does not re-type it.
- Every user-facing string is an i18n key; the mechanism denylist applies.
- Measure before implementing; a corrected audit is a valid outcome. Do not weaken
  any existing test — name every changed expectation with its old and new value.

Acceptance gates — run each from Black-Eclipse-site/ and paste the RAW output into
docs/harness/roadmap/progress/phase-15-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_office_extract.py -v
  npx vitest run src/lib/chat/extract-office.test.ts
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_document_truncation.py -v
  npx vitest run src/app/api/harness/runs/artifacts.test.ts
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_code_promotion.py -v
  npm run build
  npm run check:all

Finish by stating: "docs updated: <files>" or "no doc change — <reason>", plus one
honest non-property: what you did NOT verify.
```

---

**Next:** [Phase 16 — Bounded Bulk Acquisition](./phase-16-bulk-acquisition.md)
