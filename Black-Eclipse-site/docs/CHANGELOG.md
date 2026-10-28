# Change Log

## Rotation policy

This file keeps a rolling window of the **most recent 7 dated sections** (the active window). Older dated sections are **moved** - never deleted - into monthly archive files under `docs/changelog/YYYY-MM.md`. New entries are appended under the current date; the commit-msg hook checks this path. Rotation is by hand only when this file grows unwieldy; the archive link below points at where the older entries went.

> Older entries are archived under `docs/changelog/` (monthly). The most recent 7 dated sections are kept here.

## 2026-10-28
- **fix(chat): make the message rail legible when unselected.** Only the
  unselected ticks were lightened (`bg-muted-foreground/70`, was `/45`); their
  size and the active/hover states are unchanged, so the rail stays visible on
  both light and dark glass without getting heavier. no doc change — visual
  contrast fix.
- **feat(learning,graph): tool-widening safety case, boot-time recall, graph UI
  polish.** Added the evidence-gated `self_improvement/widening.py` ratification
  package (read/compute only, refusal by default) with its spec and tests; startup
  now consolidates duplicate automatic memories (contradictions left for review)
  and backfills completed runs into the session index; the self-improvement
  denylist now also covers the widening/capability/grant surfaces and can no
  longer be narrowed by a caller; graph node cards, canvas, home and globals
  styling were tightened. `npx tsc --noEmit` passed. Docs:
  `docs/self-improvement/loop-closure.md`, `docs/self-improvement/tool-widening/`,
  `docs/graph-studio.md`, `docs/harness/tool-registry.json`.

## 2026-10-27
- **ui(graph): align the New workflow button with the shared menu system.** The
  template picker is now a real `DropdownMenu` (anchored, dismissable, keyboard
  navigable) instead of a hand-rolled floating panel, and the trigger uses the
  standard primary button sizing alongside Generate from prompt.
  no doc change — UI consistency only.
- **ui(graph): move Start workflow into the header toolbar.** The center-stage
  floating run button is gone; the same save-and-run control now sits inline in
  the editor header row and uses the standard black primary button style. Docs:
  `docs/graph-studio.md`.
- **fix(learning,rsl): finish the loop-closure and widening verification.** Migration
  32 no longer re-adds columns that the base schema already creates (a fresh or
  historical db now reopens), the published tool registry is regenerated, the
  chat-code profile declares `learning_candidate_validate` and
  `skill_discrimination_check`, and the two recovery tests now retry the same tool
  (a different tool that merely succeeds is not recovery evidence). A
  discrimination gap (named base, no outcome metrics) is reported on the
  dimension but is non-blocking, so an ordinary patch still activates; a
  mandatory regression/indistinguishability still blocks. Size ratchets re-pinned
  to the measured tree. Docs: `docs/self-improvement/loop-closure.md`.
- **feat(learning): close the skill, memory and recall loops.** Automatic
  memories now carry `authority=automatic` (source `automatic_learning`) instead
  of masquerading as explicit; gate-approved model preferences save under
  `automatic_selective`; recurring candidates update their occurrence count and
  auto-draft an inert `status=draft` skill; recorded user corrections become
  scoped candidates; startup consolidation merges duplicates but leaves
  contradictions for review; startup quarantines nonconforming legacy
  candidates and drafts the ready ones; and startup backfills up to 200
  historical runs into the session index. `session_search` now skips the local
  caller-id filter (indexed messages are unowned in single-user mode) and retries
  a multi-token query with ANY terms instead of returning nothing. Migration 33
  restores `LearningCandidate.occurrenceCount` on older stores. Nothing is
  auto-enabled: operator acceptance, evaluation and promotion remain the only
  activation path. The usage report now separates `automaticSaved` from explicit
  saves. Tests: 358 related memory / skills / learning / session tests passed;
  `npx tsc --noEmit` passed. Docs:
  `docs/self-improvement/loop-closure.md` (Autonomy update).
- **feat(rsl): add an evidence-gated tool-widening safety-case builder and
  freeze the mechanism it protects.** `self_improvement/widening.py` assembles a
  pure, deterministic ratification package for adding one read/compute tool
  (need, holdout, replay, deny path, conclusion stability, blast radius, TTL,
  revocation); it never grants, auto-applies or self-renews. `security.py` now
  refuses RSL targets under `self_improvement/**`, `capabilities/**`,
  `grants.py` and `recovery/envelope.py`, and the frozen denylist can no longer
  be replaced by a caller. Tests: `python/tests/test_widening.py` (16 targeted
  tests passed with the related RSL/autonomy/capability suites). Docs:
  `docs/self-improvement/tool-widening/{corrections,diagnosis,safety-case-spec,design,risks}.md`.
- **feat(learning): expose the accept-route dry-run and the mandatory flag.**
  `learning_candidate_validate` is a read-only probe that returns the HTTP status
  the operator accept route would produce (404/409/422/200) without writing, so
  the negative paths are observable from chat. The discrimination probe prints
  `mandatory=True/False` in its text. Candidate rows already print procedure
  steps and occurrence count. Live: `gate.ok=true`, `accepted=2`, `detected=0`,
  typed 1, memory 0/0/2/0. Docs:
  `docs/self-improvement/loop-closure.md`.
- **feat(learning): add a read-only discrimination probe and close the remaining
  read gaps.** `skill_discrimination_check` lets a chat run prove
  identical→failed / better→passed / worse→failed with caller-supplied metrics
  without persisting an evaluation. `skill_reviews` now prints the
  discrimination detail. Candidate rows print `occurrenceCount` and the
  procedure step count; the queue line prints `quarantinable`; the scorecard
  prints `needsBackfill`; `learning_review_list(status="superseded")` is a valid
  filter. The app-API proxy is excluded from recoverable-tool lessons (a retry
  cannot fix a down front door), so the current typed lesson is the genuine
  `research_search` transient-`UNAVAILABLE` retry. Live: `gate.ok=true`,
  `accepted=2`, `detected=0`, current typed lessons 1, memory 0/0/2/0. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): withdraw the false lessons and keep only a replayable one.**
  The gate now prints the memory domain too (duplicates/conflicts/residue/
  related), review rows print the evidence list, candidate rows print
  `occurrenceCount` and the procedure step count, and a re-review refreshes the
  review timestamp so a corrected lesson is current. The two `app_api_get`
  lessons were superseded and their candidates rejected; the sole current typed
  lesson is the genuine `research_search` transient-`UNAVAILABLE` retry, accepted
  as `cand_2a07300e`. The generic "record the working source preference" lesson
  is rejected as a generic action. Live: `gate.ok=true`, `accepted=2`,
  `detected=0`, current typed lessons 1. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): only a genuine same-capability recovery becomes a lesson.**
  A later tool that happens to succeed is no longer treated as recovery
  evidence; the recovery must be the same tool or the same recorded capability,
  and its body must not itself report `UNAVAILABLE`/`TimeoutError`/`TOOL_FORBIDDEN`.
  The two accepted lessons whose `app_api_get` replay timed out were withdrawn
  (`rejected`, retained) and their reviews superseded; a genuine
  `research_search` retry from `run_615d7fce` was reviewed, encoded and accepted.
  Review rows now print the evidence list, and re-evaluating a version marks
  earlier same-version evaluations `superseded` so a self-referential pass is
  no longer presented as current. Live: `gate.ok=true`, `accepted=2`,
  `detected=0`, current typed lessons 2. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): print the full candidate census and `relatedCount`.** The
  candidate list now reports the complete store counts by status (not only the
  page) and the number hidden by the 50-row cap, so a legacy row cannot vanish
  from the audit. Memory inventory prints `relatedCount` alongside the
  duplicate/conflict/residue dry-run counts. Gate remains `ok=true`, gaps empty,
  accepted 3, detected 0. Docs: `docs/self-improvement/loop-closure.md`.
- **fix(learning): make every gate domain readable from the bound tool.** The
  `learning_review_list` gate block now prints `contractSince`, current reviews
  (typed/justified/unjustified), legacy reviews, current and legacy advice
  (evaluated/unscored/overdue), and candidates (accepted/detected/nonconforming/
  stale). `learning_candidate_list` prints `staleDetected`/`nonconforming` and an
  accepted row's limitations; `memory(action="inventory")` reports the
  consolidation dry-run counts and cross-type `related` pairs. Accepted the last
  actionable candidate (`cand_421aa3c1`, with the recovery-tool-timeout
  limitation): live `accepted=3, detected=0, gate.ok=true`. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): expose the gate on the read tool; tighten discrimination.**
  `learning_review_list` now returns `gate` (ok, gaps, current/legacy windows) so
  a chat run can read `gate.ok` without HTTP-body permission. A version with a
  named base but no outcome metrics now reports `discrimination=needs_review`
  (explicit gap), not `not_applicable`; a root version stays
  `not_applicable`. Residue detection is limited to <=2 tokens or the known
  `loopback can save` fragment, so a real short preference is not mislabelled.
  Live: `system.anatomy-figure` v1.1.1 vs v1.1.0 is `needs_review`; gate remains
  `ok=true`, gaps empty. Docs: `docs/self-improvement/loop-closure.md`.
- **fix(learning): gate the current contract window, report legacy separately.**
  `gate_report` now counts reviews and advice created since
  `HARNESS_LEARNING_CONTRACT_SINCE` (default `2026-10-28T00:00:00Z`) for its pass
  criteria, and reports pre-contract rows under `legacyReviews` /
  `legacyAdvisory` instead of letting them keep the gate red forever. The advice
  gate is due-aware: an unscored recommendation is a defect only at its stated
  horizon, not before. Live result: `gate.ok=true`; current window 3 reviews
  with 0 unjustified nulls and 2 current recommendations not yet due; legacy
  window retains 197 bare nulls and 109 unscored rows for audit. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(advisory): record a basis method and a stated horizon at issue time.**
  Every recommendation now gets `method` (explicit, else the basis class
  `portfolio_computation`/`portfolio_read`/`model_advice`, never the action
  verb), `horizon` (explicit, else the policy default `30d`), and `dueAt`; both
  are recorded as basis entries. Quote tools (`market_get_quote`/`get_quote`)
  now contribute an entry price, so a later evaluation can compute a return.
  Backfill applied to the live ledger (111 rows); `advice_missing_horizon`
  cleared and the scorecard reports `byMethod`/hit rate/demotion. Also reports
  memory residue (`fragment: <=4 tokens, no subject`) without touching it, and
  diagnoses a generic-only all-fail route as a provider failure. Regression
  evaluation no longer compares a version against itself. Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(learning): persist the falsifiable method and unfreeze intake.** The
  `LearningCandidate` table now stores `condition`, `action`, `failedCall`,
  `recoveredCall`, `precondition`, `replayTest` and `occurrenceCount` (migration
  32), so the writer no longer drops the fields the contract requires. A
  previously-created detected candidate was repaired from its run draft and is
  now conforming; intake was re-enabled (`automatic_selective`), a conforming
  specimen was created and accepted (accepted=2, detected=0,
  nonconforming=0). `_regression_dimension` never compares a version against a
  later one (the 1.1.0-vs-1.1.1 inversion), a completed review updates its
  existing row instead of duplicating, and persisted nulls keep
  `justified`/`evidenceChecked`. Fresh `system.anatomy-figure` evaluations now
  carry the `discrimination` dimension (`not_applicable`, explicit gap). Docs:
  `docs/self-improvement/loop-closure.md`.
- **fix(harness): persist null justification, dedupe reviews, expose accept/eval.**
  `_bounded` now keeps `justified`/`evidenceChecked` at the outcome level, so a
  saved null no longer reads as bare; a completed review for one run updates the
  existing row instead of appending a duplicate. Adds operator
  `POST /learning/candidates/{id}/accept` (status only; never enables a skill),
  extends `POST /skills/{id}/evaluate` with `baseVersion`/`metrics`/`baseMetrics`
  so `discrimination` is reachable, reports `intake_disabled` when
  `skill_learning_mode=off`, and records a missing advisory method as
  `unclassified` rather than echoing the action verb. Live state: accepted 1,
  detected 0, duplicate review superseded, fresh evaluation includes
  `discrimination`. Docs: `docs/self-improvement/loop-closure.md`.
- **fix(harness): make pre-contract learning rows visible and drainable.** The
  review list now prints every typed lesson and labels a bare null
  `UNJUSTIFIED`; the candidate list shows `failedCall`/`recoveredCall`/
  `precondition`/`replayTest` and a `CONTRACT VIOLATION` per stored row. The gate
  counts unjustified nulls and nonconforming candidates, not only typed lessons.
  Adds operator-gated quarantine (`POST /learning/candidates/quarantine`) and
  advisory backfill (`POST /advisory/backfill`) that exposes legacy
  method/horizon as `unscored` without inventing a result. Consolidation now
  resolves near-duplicates (containment/subject link) and the verbosity conflict
  ("straight to the facts" vs "detailed with sources"), still supersede-only.
  Applied to the live stores: 48 nonconforming candidates quarantined, 2 stale
  candidates expired, 2 memory records superseded, 109 advisory rows backfilled,
  and one real review produced a typed lesson (recurrence 1/2). Docs:
  `docs/self-improvement/loop-closure.md`.
- **feat(harness): close the learning loop, not just record it.** Reviews now emit
  a typed lesson (`condition -> action -> evidence`) or a justified `no_learning`
  null (reason + `evidenceChecked`), and carry a cross-review signal aggregate
  that requires two distinct runs before a lesson is eligible. Failure-recovery
  candidates must carry the failed call, recovered call, precondition, procedure
  and a replay test; templated titles and constant `0.55` confidence are rejected
  at creation. Skill evaluation adds a `discrimination` dimension against a named
  base on outcome metrics (identical results fail; repeated identical passes are
  flagged as a broken harness). Advisory decisions record `method` + `horizon` +
  `dueAt`, and the scorecard reports unscored/overdue/per-method calibration and
  demotes methods that do not score. Route health diagnoses generic-vs-market
  routing defects, active memory is consolidated (duplicates + contradictions
  supersede to the later statement, retained), and `gate_report` treats an
  unconsumed candidate queue as a design failure. Docs:
  `docs/self-improvement/loop-closure.md`; `docs/NAVIGATION.md` rows updated.
- **fix(harness): scope the candidate empty state and keep the read-only footer.**
  A status-filtered empty listing now says "No learning candidates captured with
  status 'accepted' yet." instead of implying the whole store is empty, and every
  empty response keeps the read-only footer. A request above the 50-row cap now
  says it was capped. no doc change - bug fix; no contract, setup, or architecture
  change.
- **fix(harness): upgrade the graph-run schema before indexing `jobId`.**
  `GraphRunStore` created `idx_graph_run_job` inside the base schema script, so a
  legacy `HarnessGraphRun` table without `jobId` raised `no such column: jobId`
  and left the whole graph runtime unavailable at boot. The index is now created
  after the column upgrade; regression test covers the legacy table. no doc
  change - bug fix; no contract, setup, or architecture change.
- **fix(harness): report the true candidate total past the 50-row page.**
  `learning_candidate_list` now reads `count_candidates(status)` and says
  "Showing N of M" when the page is truncated, so an operator cannot mistake the
  tool's output cap for the queue size. Adds one read-only store count method and
  a regression test. no doc change - bug fix; no contract, setup, or architecture
  change.
- **fix(graph): make the connection aurora actually visible.** The first pass
  was too faint (2px, blurred, 16–55% opacity). Now a 3px hot core with an
  accent box-shadow glow plus a wider blurred haze, breathing 45–100% on the
  same 8s loop. Still respects reduced motion and Glow-off.
  no doc change - tuning only.
- **fix(harness): `learning_candidate_list` resolves the Eclipse-Memory store by
  capability.** It now prefers `memory_service.store` and only accepts
  `learning_store` when it exposes `list_candidates`, so the research path store
  can no longer cause an `AttributeError`. The empty state reads
  `skill_learning_mode` and no longer promises automatic capture when detection
  is off (or unreadable); tests now use the production wiring. no doc change - bug
  fix; no contract, setup, or architecture change.
- **feat(graph): minimal live connection aurora on node edges.** Wired nodes show
  a small blurred accent light bar on the left (`hasIncoming`) and/or right
  (`hasOutgoing`) edge, breathing/bobbing on an 8s loop with the two sides
  phase-offset. Respects `prefers-reduced-motion` and the Glow-off preference.
  Rendered in `eclipse-node.tsx`; keyframes/classes in `globals.css`.
  no doc change - visual restyle only; uses existing node data fields.
- **feat(chat): show the Python program in the activity step.** `analysis_run`
  and `execute_python` now emit a bounded (`8 000` chars), secret-redacted
  `codePreview` on `tool.requested`, so the source appears inside the activity
  step's existing expandable details (not as a separate panel), with honest
  truncation. The preview is persisted with the run. Producer:
  `code/activity.py::tool_code_preview`;
  emitter `graph.py`; client `ActivityItem.codePreview` + `activity-item.tsx` /
  `output-panel.tsx`. docs updated: `docs/chat-ui-audit.md`, `docs/NAVIGATION.md`.
- **feat(graph): accent-aurora node restyle.** Graph nodes now use the frosted
  `node-card` material with a thick accent border, a plain foreground-coloured
  icon (no tinted tile), and a per-node **aurora** halo when wired. Wires and
  handles take the source node's category accent (with a gradient stroke + soft
  glow) instead of the neutral slate/sky hardcode. Category accents moved to
  `lib/graph-studio/port-style.ts` (`categoryAccent`) as the single source.
  no doc change - visual restyle; new node/edge data fields are internal to the
  canvas renderer and no contract changed.
- **fix(graph): aurora moved off the node body and onto its connected edge.**
  Follow-up to the node restyle: the accent halo no longer wraps the whole card
  (which read as background glow). It is now a thin drifting light bar on the
  node's **left** side when it has incoming wires and on its **right** side when
  it has outgoing wires (both sides when both). Node borders are near-black
  again, not accent-coloured; selection uses an accent outline offset outside
  the frame. Node glass was deepened (multi-layer tint, stronger blur, inset
  sheen). no doc change - visual restyle only.
- **fix(graph): n8n-style compact nodes, theme-driven colour.** Narrowed nodes
  from 244px to 184px and moved the icon to a centred top slot with the label and
  category stacked beneath. All glow (aurora, wire stroke/glow, handles, `+`
  affordance, selection outline) now reads `var(--primary)`, so it follows the
  active theme instead of a hardcoded per-category palette; the unused category
  accent table was removed from `port-style.ts`. no doc change - visual restyle
  and internal cleanup only.
- **fix(graph): remaining blue chrome moved to the theme accent.** The floating
  "Start workflow" button lost its blue glow and now uses a shared
  `.graph-accent` control (border/tint/text from `var(--primary)`, no box-shadow).
  Applied the same class to "Add node", "Add first step", the wire insert `+`, and
  the schedule action; focus rings, active toggles, inspector tabs/checkboxes and
  the editor icon now use primary tokens instead of `sky-*`. Running-status dots
  stay sky (semantic state, not chrome). no doc change - styling only.
- **feat(graph): black bezel nodes with an inner aurora.** Node body is now true
  black (not grey), framed by a wide 5px solid-black border with a larger radius.
  The identity block is centred with a bigger icon and a single label - the
  category kicker and the divider line above the ports were removed. When a node
  is connected, an accent aurora now drifts **inside** the card (radial sweep,
  gated by `data-incoming`/`data-outgoing`) instead of hugging the outside edge.
  Node border no longer changes colour for run status (the status badge remains).
  no doc change - visual restyle only.
- **fix(graph): side aurora, centred handles, glass matched to the system.** The
  aurora moved back out of the card to the connected **side** (left = incoming,
  right = outgoing) as a drifting light bar. Port handles are now centred on the
  node's vertical midline (fanned only for multi-port sides), so wires meet the
  middle of the card like the reference. `.node-card` now uses the exact
  `.glass-card` material recipe (black tint, 18px blur, saturate 1.35, inset
  highlights) instead of a bespoke grey gradient. no doc change - visual restyle
  only.
- **fix(graph): node icons tinted with the accent and heavier stroke.** Icons are
  now outline-style but rendered at `var(--primary)` with `strokeWidth 2.5`
  (was muted `text-foreground` at default weight), so they read solid rather
  than faint inside the black card. no doc change - visual restyle only.
- **fix(graph): 10px node bezel, solid white icons.** Node border widened from
  5px to 10px. Icons are now solid white filled glyphs (`fill=currentColor`,
  thin residual stroke) instead of accent outlines. Side aurora stays on the
  connected wire side and was nudged out to clear the thicker bezel. no doc
  change - visual restyle only.
- **fix(graph): solid white icons, inner animated aurora, graphite glass.** Icons
  render Phosphor `weight="fill"` (true solid glyphs) in white instead of light
  outline strokes. The accent aurora moved back inside the card as a diagonal
  sheen that continuously travels beneath the glass on connected nodes. Node body
  lifted from pure black to a graphite tint (`rgb(34 34 39 / 0.72)`) so the black
  bezel and white icon have contrast. no doc change - visual restyle only.
- **fix(graph): wider nodes and a dominant icon.** Node width restored to 244px
  (from 184px) so port labels and long titles fit again, and the filled icon
  grew to 34px in a 48px slot — clearly larger than the 12.5px label. Node body
  darkened to charcoal and the aurora is now a wave running along the connected
  side. no doc change - visual restyle only.
- **feat(graph): reference-accurate node card.** Nodes are now wide 244px cards
  (112px min height, 18px radius, 4px black bezel) with a **horizontal** identity
  block: solid white filled icon on the left, 16px white title over an 11px muted
  category subtitle on the right. Visible per-port label rows removed; handles
  sit on the edge midpoints (fanned per port) with names in the tooltip, and the
  add-next `+` follows each output handle on hover. Aurora is now a soft radial
  bloom anchored at each connected edge midpoint (left/right) that breathes
  in-place, spilling outside the bezel and washing into the body. no doc change -
  visual restyle only.
- **fix(graph): inner half-clipped live aurora + lighter glass.** Replaced pseudo
  blooms with an inner `.node-aurora-clip` layer (`overflow:hidden`) holding two
  glows centred on the card edges, so only the inner half is visible at the
  connected side (left incoming, right outgoing) and it drifts/breathes on a
  loop. Node tint lowered to `rgb(24 24 28 / 0.58)` so the 18px backdrop blur is
  actually visible. Content and handles sit above the clip layer. no doc change -
  visual restyle only.
- **fix(graph): smaller, visibly moving aurora.** Glow reduced to 110px / 104%
  and the animation now travels horizontally (translate 55% → 22% of its own
  width, plus scale/opacity) so the motion is obvious. Added a scoped
  `prefers-reduced-motion` override for `.node-aurora-glow`: the global reset was
  freezing it on machines with reduce-motion enabled. no doc change - visual
  restyle only.
- **fix(graph): aurora ripples in waves, smaller and lighter.** Glow shrunk to
  88px / 96%, gradient alphas lowered (55% → 22%), and the animation now follows
  a 5-stop undulating path (in/out + up/down) at 4.8s, so it ripples like an
  aurora. no doc change - visual restyle only.
- **fix(graph): real ribbon aurora instead of a moving blur.** Replaced the
  single radial glow with an inline SVG of three sine ribbons that drift
  horizontally at different speeds/directions (7/5/10px strokes, blurred,
  low opacity), faded away from the connected edge via `mask-image`. Renders a
  proper flowing wave, half-visible at the wire side, inside the clipped card.
  no doc change - visual restyle only.
- **fix(graph): aurora ribbons glow instead of reading as lines.** Layered three
  strokes as a wide soft curtain (14px / blur 12), a mid ribbon (7px / blur 7)
  and a thin bright crest (3px / blur 3), with `mix-blend-mode: screen` and an
  accent drop-shadow, on a 2-wave path loop. The strokes now fuse into a glowing
  band rather than separate lines.   no doc change - visual restyle only.
- **fix(graph): aurora is now pure blurred waves, no visible strokes.** Removed
  the thin bright crest and drop-shadow; all three layers are wide strokes with
  heavy blur (18/14/22px) and low opacity, screen-blended. Nothing resolves into
  a line — only soft flowing curtains. no doc change - visual restyle only.
- **fix(graph): aurora confined to a smaller side patch.** Wave canvas inset to
  18% top/bottom (64% height), mask fade tightened to ~48% of the width, and
  stroke widths reduced, so the glow is a compact patch at the connected edge
  instead of spanning the whole card. no doc change - visual restyle only.
- **fix(graph): aurora waves have real amplitude and show in light mode.** Wave
  paths now swing across most of the card height (control points near the
  viewBox edges) instead of tiny ripples that read as a flat line; canvas back to
  76% height with mask fade at 55%. Light mode switches the blend from `screen`
  to `multiply`, since screen-on-white was hiding the glow entirely. no doc
  change - visual restyle only.
- **fix(graph): aurora sized as a compact centred band.** Wave canvas reduced to
  48% height (inset 26% top/bottom) with `overflow: hidden` so blur can't bleed
  toward the card edges, and the side mask now fades out by ~42% of the width.
  Strokes tightened accordingly. no doc change - visual restyle only.
- **revert(graph): aurora removed from nodes entirely.** Deleted the inner
  aurora SVG, clip layer, wave CSS/keyframes and the `data-incoming`/
  `data-outgoing` hooks. Nodes are now just the black-bezel glass card with the
  icon/title/subtitle; wires carry the accent colour only. no doc change -
  visual restyle only.
- **feat(graph): compact node cards with inline parameter editing.** Node cards
  shrink from a 112px min-height / 4px bezel to a 46px identity header / 2px
  bezel (icon 48→32px, title 16→13px), with the run status folded into the header
  and the hover toolbar tightened. Up to two scalar config fields now render as
  inline editors on the card (text/number commit on blur or Enter, selects and
  booleans immediately, Escape reverts); fields supplied by an incoming edge show
  a read-only "From wire" chip. `config-fields.ts` adds presentation metadata
  (label/kind/options/inline) over the registry defaults, a shared
  `config-field.tsx` replaces the inspector's hand-rolled fields, and
  `dispatch(patch, { coalesceKey })` collapses a typing session into one undo
  entry. `buildNodes` reuses unchanged node objects so editing one node no longer
  re-renders the whole canvas. Docs: `docs/graph-studio.md`.
- **style(graph): node icons are plain outline glyphs.** Removed the filled
  Phosphor weight and the accent-tinted icon chip; nodes now use the same
  regular-weight, muted icon treatment as the rest of the site. no doc change —
  visual restyle only.
- **fix(graph): remove the node connection glow.** Deleted the side aurora spans,
  their CSS/keyframes, the handle glow and the now-unused incoming/outgoing
  flags. Nodes are a flat glass card; wires stay the accent colour. no doc change
  — visual restyle only.

## 2026-10-26
- **fix(customization): the "Custom theme" tile is now a real button.** It looked
  like the preset tiles but was a non-interactive `div`, so clicking it did
  nothing. It now commits an unsaved custom draft (same path as "Apply changes")
  or, while a preset is selected, returns to the saved custom theme. The tile
  shows the selected check once custom is active and previews the saved theme
  when a preset is being browsed. no doc change — UI interaction fix; token and
  preset contracts unchanged.
- **fix(dashboard): market dropdown options were white-on-white.** The global
  market `<select>` popup rendered on the native white background with light
  text; options now carry the repo-standard `bg-[#121212] text-foreground` so
  they are readable. No doc change — style fix only.
- **feat(graph): n8n-style Graph Studio workspace and canvas UX.** Replaced the
  cramped sidebar-tabs/right-rail layout with a full-bleed mode (app top bar and
  sidebar hidden while active), a **Workflows home** gallery (search, templates,
  prompt-to-graph, continue-editing), a slim editor header, and a collapsible
  execution dock. Nodes are compact icon-led cards with hover actions, typed
  ports, add-next/output "+" and run badges; edges expose insert-into-wire and
  delete on hover. Added a Tab/"+" node search overlay filtered by port
  compatibility, right-click menus, duplicate/copy/paste/select-all shortcuts,
  and a wider Parameters/Settings/Output inspector (last-run output is read-only
  from persisted runs). Compound edits are pure validated patches in the new
  `edit-ops.ts`; IR/compiler/runtime/authorization contracts are unchanged.
  Operator runs now use an explicit authorization dialog instead of
  `window.confirm`. Docs: `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **fix(graph): keep the main sidebar and use the full workspace width.** The
  app sidebar is no longer hidden in Graph Studio; it stays as the Graph Studio
  mode panel. The workflow home is now a full-width n8n-style table (Workflows /
  Templates tabs, search, name/description/tags/owner/version/updated columns,
  row actions) instead of a constrained card grid. Docs:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(tables,graph): Tables page + workflow cards.** Added a top-level
  **Tables** tab (group `both`) that lists the existing `CustomDataset` tables and
  opens a read-only row grid with provenance/retrieved timestamps; creation stays
  in Settings → Market Data → Custom data sources. The Graph Studio mode panel now
  links directly to **ChatBot** and **Tables**, and the workflow home is back to
  the full-width **card gallery**. Docs: `docs/tables.md` (new),
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **fix(graph): restore the transparent frosted editor canvas.** The workflow
  editor no longer paints a solid canvas/header fill; the dot grid sits on the
  shell background again and nodes use the shared `.glass-card` surface. Hover
  toolbars/edge controls use semi-transparent theme backgrounds so they work in
  both light and dark. Docs: `docs/graph-studio.md`.
- **feat(tables): editable spreadsheet tables.** Tables is now a real data store,
  not a read-only dataset browser: create a table with typed columns, edit cells,
  add/rename/delete columns, add/delete rows and search. Stored in new
  `DataTable`/`DataTableRow` Prisma models (JDDS), exposed through
  `/api/tables` and `/api/tables/[id]`; connector-fed datasets remain under
  Settings → Data Sources. Docs: `docs/tables.md` (rewritten).
- **feat(overview): Agentic Overview workflow dashboard.** Added an **Overview**
  nav tab in Agentic mode with the workflow card gallery, New workflow / templates
  / prompt-to-graph, and continue-editing. Opening or creating a workflow switches
  to the Graph Studio editor. Docs: `docs/agentic-overview.md` (new), `docs/NAVIGATION.md`.
- **fix(nav): Graph Studio uses the standard sidebar.** Removed the dedicated
  Graph-mode Workflows panel: `graph-studio` is now a normal Agentic nav item,
  so the sidebar lists ChatBot / Overview / Graph Studio / Tables like every other
  page. `Alt+G` still opens Graph Studio (inside Agentic). Clicking Tables no
  longer forces a mode switch. Docs: `docs/graph-studio.md`, `docs/NAVIGATION.md`,
  `docs/tables.md`.
- **fix(nav,ui): Terminal boot fallback and consistent buttons.** A stored retired
  `graph` mode is ignored and hydration falls back to Terminal; the new Overview /
  Graph Studio / Tables surfaces now use the shared `Button` component (default /
  outline / ghost / destructive variants) instead of one-off button chrome.
  no doc change � retired-mode fallback + UI consistency only.
- **fix(shell): collapsed sidebar keeps its icons.** When the sidebar is
  collapsed, the Terminal / Agentic / Bots mode switcher becomes a compact icon
  rail instead of disappearing, and the standard nav list keeps every page icon
  reachable. no doc change � layout fix only.
- **fix(bots): bot and group chats read chronologically again.** Threads were
  rendered newest-first, so a question appeared below its own answer and new
  turns jumped to the top. Both the bot chat and group room now render oldest →
  newest, keep the thinking indicator at the bottom, and autoscroll the newest
  message (including streamed text) into view. no doc change � presentation fix.

- **fix(bots): QA hardening pass across Bots mode, deletion, delegation and scheduling.**
  Bots are now identified by the `bot` tag (monitors tagged `bot`/`monitor`), so
  jobs and event rules no longer appear in the Bots list, `bot_list`, the `@`
  palette or the run watcher. The Schedule editor preserves event/condition
  triggers instead of downgrading them to manual, and no longer wipes unsaved
  edits on the 20s background hydrate. Deleting a bot now purges its private
  memory through both the UI route and `bot_delete`, clears its thread/face and
  removes it from rooms; group deletion purges member buckets too. Streaming bot
  and group replies update memory only and persist once at the end. Switching
  bots/rooms mid-stream remounts and aborts the old turn; retry is limited to the
  latest failed reply; delegated turns no longer duplicate the prompt; parallel
  approvals are keyed per approval id; group delegation honours the chosen model;
  duplicate mention targets are collapsed; bots duplicate their model and run
  policies. Also fixed the bot composer's global-model leak (interactive turns
  use the bot's pinned model), group mentions using the shared parser, duplicate
  names resolving to all matches, the Details avatar ignoring uploaded photos,
  denied tools/tags rendering, mode-exit navigation, the missing sidebar
  scheduler button, the finance starter pack being unreachable, and the first-run
  unread seed. Docs updated: `docs/NAVIGATION.md`,
  `docs/harness/automation-engine.md`.

- **fix(nav): final navigation shape.** Graph Studio is its own top-level mode
  again (mode switcher + `Alt+G` + mobile) but renders the STANDARD nav list, not
  a custom Workflows panel. A fresh shell boots Terminal; a tab that chose a mode
  keeps it for that session. Tables is Agentic-only (not shown in Terminal or
  Graph mode). The collapsed sidebar does not show a mode-icon rail. This
  supersedes the earlier same-day navigation notes above. Docs:
  `docs/graph-studio.md`, `docs/tables.md`, `docs/NAVIGATION.md`.

- **fix(nav): Overview and Tables are Graph-mode pages only.** Removed them
  from the Agentic and Terminal menus; each mode now shows only its own pages
  (plus the shared ChatBot). Docs: `docs/graph-studio.md`, `docs/tables.md`,
  `docs/agentic-overview.md`, `docs/NAVIGATION.md`.

- **fix(graph): cleaner workflow gallery.** The workflow gallery header is the
  same on Overview and Graph Studio home — the redundant Home button and the
  "Agentic workspace" eyebrow are gone. Workflow cards are rebuilt as taller
  frosted cards with a status-accented icon, hover arrow, aligned metadata and a
  separated action footer; template tiles match the same language. no doc change
  — presentation only (the gallery contract is unchanged).

- **refactor(graph): one Graph-mode page — Overview.** Retired the separate
  Graph Studio nav tab (desktop sidebar, mobile bar, SDK nav manifest). Overview
  now hosts the whole workspace: gallery in place, and opening/creating a
  workflow switches that same page into the editor (back returns to the gallery).
  Old `?tab=graph-studio` links alias to Overview. Overview is pinned directly
  below ChatBot in Graph mode (desktop + mobile), regardless of saved custom
  order. Docs: `docs/graph-studio.md`, `docs/agentic-overview.md`,
  `docs/NAVIGATION.md`.

- **fix(shell): stale chunks self-heal and Graph tabs preload.** Added a
  `ChunkReloadGuard` that reloads once when a lazily-imported screen's chunk is
  missing after a rebuild (this was why an old tab could open Graph Studio to a
  blank page), and warmed the Graph Studio / Overview / Tables chunks while the
  shell is idle so mode switches are immediate. no doc change — runtime
  robustness/perf only.

- **feat(graph): header on the gallery, full-bleed editor.** The app top bar is
  visible on Overview again and is hidden only while the in-place graph editor
  is open (the workspace reports its internal view to the shell). Docs:
  `docs/graph-studio.md`.

- **style(overview): use the theme accent for gallery icons and hover.**
  Workflow-card and template icon tiles, hover borders, top hairline, arrows,
  tag tints and “Open editor” now use the live `primary` (accent) token instead
  of hard-coded sky blue, so they follow the user's theme. no doc change — style
  only.

- **fix(graph): canvas interaction is now industry-standard.** Single click
  selects a node and **double-click opens the inspector** (n8n/Figma); box select
  is **Shift+drag only** (Alt/right-drag removed); the pane uses grab/grabbing
  and crosshair cursors; and the zoom controls include a **? Canvas shortcuts**
  panel. Left-drag/Space/middle pan and wheel zoom are unchanged. Docs:
  `docs/graph-studio.md`.

- **fix(graph): n8n-style canvas gestures.** Box selection now works with
  **Shift+drag** (React Flow's n8n default) in addition to Alt+drag and
  right-drag; left-drag on the pane pans, wheel zooms, Space/middle-drag pans,
  Ctrl/Cmd+click multi-selects. Docs: `docs/graph-studio.md`.

- **feat(graph,nav): right-side node library, Workflows mode, glass node
  material.** The add-node search now opens as a 400px right-side `glass-drawer`
  (portaled, search + categories + keyboard nav, closes after insertion). The
  mode formerly labelled Graph Studio is now **Workflows**; the editor header
  uses an **Overview** breadcrumb back to the gallery and the sidebar footer
  shows the active mode instead of always “Terminal”. Node cards use a new
  `.node-card` layered glass material (true page blur is impossible inside React
  Flow’s transformed viewport). Docs: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`.

- **feat(graph): center-stage Start workflow button.** The editor now shows a
  prominent run control centered at the bottom of the canvas. It executes the
  saved version, and turns into **Save & run** when the graph has unsaved edits;
  it is disabled with a reason when unsaved/invalid. Docs: `docs/graph-studio.md`.

- **fix(graph): right-drag marquee + cleaner node cards.** Right-button drag on
  the pane now draws a marquee and selects overlapping nodes (a plain right-click
  still opens the pane context menu; Alt+drag remains). Removed the colored
  accent bar along the left edge of every node. Docs: `docs/graph-studio.md`.

- **feat(graph): port-row node cards.** Nodes are now 244px cards with an
  identity header (icon + name + category) and one always-visible 26px row per
  typed port, so multi-output nodes (If/else: Value / True / False / Result) grow
  in height with labels beside their handles instead of hiding them behind a
  hover overlay. Add-next stays a hover `+` clear of the port; wire drag still
  works. no doc change — node presentation only.

- **fix(graph): output handles are wireable again.** The invisible "add next
  step" `+` button sat on top of each output port and swallowed the pointer-down,
  so dragging a wire never started a connection. It is moved clear of the port
  (and still appears on hover). no doc change — interaction bug fix.

- **fix(theme): Custom theme tile is selectable again.** The unsaved/saved
  "Custom theme" tile is now a real button: it applies an unsaved draft, or
  returns to the saved custom theme after browsing a preset (instead of looking
  dead / committing the preset under the custom label). no doc change — UI fix.

- **feat(graph): editor affordances + roomier nodes.** Replaced the native
  execution-mode `<select>` with the shared glass dropdown (fixes the broken
  dark popup), surfaced **Tidy up layout** as a canvas-control button, added a
  persistent **Add node** button on the canvas's right edge, and widened node
  cards (214px) with an icon tile, tighter-but-roomier text hierarchy and larger
  hover actions. Docs: `docs/graph-studio.md`.

- **feat(graph): full-bleed Graph mode + redesigned editor header.** Graph mode
  (Overview and its in-place editor) hides the app top bar. The editor header is
  now 48px with a content-sized workflow name (no more stretched input), a dirty
  dot, version chip, labeled execution-mode pill, grouped undo/redo and
  issues/save/test actions. Docs: `docs/graph-studio.md`.

- **fix(graph): pan by default, Alt+drag to box-select.** Canvas drag now pans
  (the cursor stays in move mode); holding `Alt` while dragging draws the
  marquee selection box. Node click-vs-drag inspector behaviour is unchanged.
  Docs: `docs/graph-studio.md`.

- **fix(graph): card hit targets and canvas selection.** A workflow card is now
  one full-card click target (the footer/whitespace included; delete stays
  separate), with a pointer cursor. The canvas draws a marquee selection when
  dragging empty space (middle-mouse/Space pans). Clicking a node opens the
  inspector; dragging it no longer does. React Flow now owns selection during
  pointer interaction and the store mirror only applies programmatic changes,
  fixing a `Maximum update depth` crash during marquee. Docs:
  `docs/graph-studio.md`.

## 2026-10-25
- **feat(models): OpenCode Zen provider in AI / LLM.** Added `opencode` to the
  provider presets (Settings → AI/LLM and the composer), the Python catalog
  (`PROVIDER_CATALOG`/`PROVIDER_MODELS`, default `glm-5.3`), the key vault
  (`OPENCODE_API_KEY`, tested against `https://opencode.ai/inference/v1/models`)
  and `CATALOG_ENV_VARS`. Chat uses OpenCode's OpenAI-compatible endpoint
  (`https://opencode.ai/inference/openai/v1`); because the catalog is published
  one level up, `OpenCodeAdapter` rewrites discovery to
  `https://opencode.ai/inference/v1/models` (verified live, 85 models). Tests:
  `test_models.py`, `test_model_runtime.py` (URL rewrite + discovery wiring).
  Docs: `docs/ARCHITECTURE.md`.
- **feat(chat): shareable apps and a live preview while they stream.**
  The interactive toolbar now has **Share**, which copies
  `/app-view#<base64>` (the `/figure` encoding) and opens a standalone,
  `noindex` viewer that renders the block in the same sandbox with no server
  storage. A still-streaming ```` ```html ````/```` ```svg ````/```` ```eclipse-app ````
  fence renders a debounced (450 ms) sandboxed "Live preview · building" of the
  partial document; the settled block replaces it. Docs:
  `docs/interactive-response-engine.md`.
- **feat(chat): resize, source/copy, off-screen pause and a real dialog.**
  The interactive card gains a drag/keyboard resize handle (double-click resets;
  the height is remembered per app in localStorage), a source view with Copy, and
  a focus-trapped full page that locks page scroll, restores scroll and focus on
  exit, and closes on Escape. `Eclipse.visible` / `Eclipse.onVisibility(fn)` report
  off-screen or hidden-tab state; while hidden the shell pauses CSS animations and
  holds `requestAnimationFrame` callbacks so an off-screen app stops burning CPU.
  Docs: `docs/interactive-response-engine.md`.
- **feat(chat): interactive apps get host context, a skeleton, and a fix action.**
  `Eclipse.context = { theme, reducedMotion, locale }` is baked at mount and
  pushed live (the block observes the host `dark` class and the reduced-motion
  media query), so an app can match Eclipse's scheme instead of the OS. The card
  shows a skeleton until the app signals `eclipse:ready`, then fades the frame
  in. The "App error" banner now offers **Ask Eclipse to fix**, which re-enters
  the agent with the error and the app title. Docs:
  `docs/interactive-response-engine.md`.
- **feat(models): the picker shows newly released models first.** Model lists
  were static/catalog-ordered, discovery was manual and its snapshot merged
  forever, so a provider's new models stayed buried while decomissioned ids
  lingered. Probes now sort by provider `created` (OpenAI family, Anthropic);
  `src/lib/agent/model-recency.ts` ranks provider timestamp → version within a
  family → `-latest`, preserving incoming order otherwise; both catalog routes
  prefer the freshest `served` set and sort newest-first; `compactModels` keeps
  the newest 40 on truncation; the Settings picker auto-re-probes after a 6h
  throttle; the discovered snapshot now REPLACES each provider's set per probe;
  and `PROVIDER_MODELS` is refreshed. Tests: `src/lib/agent/model-recency.test.ts`,
  `enabled-models.test.ts`, Python `test_models.py`/`test_model_runtime*.py`.
  Docs: `docs/ARCHITECTURE.md` (model picker section).
- **ui(chat): a better interactive surface — scrollbar, auto-fit, error banner.**
  The sandbox document now has a thin scrollbar derived from the app's own
  `currentColor` (with a neutral fallback), transparent track and contained
  scroll chaining. The shell reports its content height through a
  `ResizeObserver`, so the card fits the app instead of showing a cramped inner
  scroll (clamped 240–900). Uncaught errors and unhandled rejections post
  `eclipse:error` to the host and appear as an "App error" banner. Docs:
  `docs/interactive-response-engine.md`.
- **feat(chat): interactive apps own their palette and get a full-page view.**
  The document shell now sets only structural defaults (box-sizing, margin, font,
  transparent background) — no forced text colour or `color-scheme` — so the model
  can choose any palette from the user's context. The interactive card is full
  width and its toolbar adds **Download** (the composed HTML) and **Full page**
  (a viewport-filling overlay, Escape/Exit to close; Reload stays available).
  Docs: `docs/interactive-response-engine.md`.
- **fix(advisory): the fiduciary gate reads prose, not code.** A model-authored
  app is full of directive words (`add`, `trim`, `exit`, `reduce`), CSS
  percentages and SHOUTING identifiers (`BARS`, `VOL`, `THR`, `HOVER`, `PIN`,
  `BASE`, `JSON`), so the gate invented "recommendations" for internal tokens and
  appended a nonsensical Advisory note. `claims.extract_claims` now strips fenced
  blocks and inline code before extracting sentences (the gate is a prose check),
  with a few format/tech tokens added to the symbol stop-list. Prose advice next
  to code is still disclosed. Tests: `python/tests/test_advisory_gate.py`.
  no doc change — bug fix.
- **feat(chat): a fenced app can request the dataset bridge.**
  A leading `<!--eclipse-dataset {"symbol":"AAPL","range":"6mo"}-->` comment in
  an ```html/```eclipse-app fence is parsed into the block's `dataset` and
  stripped before render, so a fence-rendered app gets the same host-injected
  series as the `interactive` block. The runtime also exposes `Eclipse.bars()`
  for the bars array directly. Docs: `docs/interactive-response-engine.md`.
- **ui(chat): parallel agents use the ChatBot nav glyph and sit with the activity.**
  Replaced the generated ghost "bot faces" in the fan-out card and its detail
  dialog with the same `Bot` icon the ChatBot nav item uses — a delegated part is
  one Eclipse agent working in parallel, not a distinct bot. Moved the fan-out
  card below `ActivityFeed` so it reads as runtime detail with the activity rows
  instead of a card above the answer.
  no doc change — presentation only.
- **fix(chat): an app-build request stays in chat instead of the code workspace.**
  The classifier recognized the block vocabulary ("return it as one interactive
  block") but not the same deliverable phrased as code: "one self-contained HTML
  document … return it as a single html code fence" was still `code_change`, so
  the code agent edited the repository (repo map, diff, "put this change into my
  project") instead of answering. `_INLINE_APP_RE` now recognizes
  self-contained/single-file HTML, SVG, mini-app and html/svg code-fence
  deliverables as inline content (before the directive+software-object rule),
  with a guard (renderer/component/codebase/desktop/install/deploy) that keeps a
  real source change on the code profile. Tests:
  `python/tests/test_code_request_intent.py`.
  no doc change — classifier bug fix; ADR-052 already documents the block.
- **perf(chat): a code-classified turn no longer stalls for minutes before its
  first model call.** A live "build me an interactive Candle Lab" turn recorded
  only `run.created` → `response.plan` and then sat silent; on the same repo the
  code-context seed (`CodeContextEngine.select`) measured **94 s**, synchronously
  on the runtime's event loop — which also froze every other API route. Three
  fixes: (1) `find_related_tests` resolved the reference set per TEST FILE
  instead of per NAME, re-running the same SQL query ~32 500 times — now once per
  name (94 s → ~2 s); (2) `call_edges(caller_name|callee_name)` indexes added so
  the `col=? OR name=?` call-path reads stop full-scanning; (3) the chat code
  classifier now treats "return it as one interactive block" as a `data_task`
  content deliverable rather than `code_change` (the word "file" in "single-file"
  used to trigger the code profile, ADR-H117 amendment). Also stopped
  `EmbeddingService.configure()` from re-arming a tripped provider circuit on
  every search (a 30 s cooldown), which was firing thousands of doomed
  `/v1/embeddings` 404s against Ollama. Tests:
  `test_intel.py` (one reference query per name), `test_search_embeddings.py`
  (circuit survives re-configure), `test_code_request_intent.py`
  (response-block vs renderer change). Docs updated:
  `docs/harness/decisions.md` (ADR-H117 amendment).
- **fix(chat): a pre-model step can no longer freeze a turn (invariant, not a
  one-off).** The stall above happened because the repo-map/context seed ran
  synchronously on the event loop with only COUNT bounds. `CodeContextEngine.select`
  and `build_repo_map` now also take a wall-clock deadline (default 5 s,
  `BLACK_ECLIPSE_CODE_CONTEXT_BUDGET_S`) and return partial results with
  `truncated: true`; the map gets half the budget and the seed the rest
  (`graph_context._repo_map_context` emits `elapsedMs`/`truncated`);
  `find_related_tests` accepts the deadline. Opening a large workspace index
  (seconds; 682 MB here) moved out of the run: `CodeIntelRuntime.warm` opens it
  at boot on a worker thread (`boot.py::_warm_code_index`;
  `BLACK_ECLIPSE_CODE_INTEL_WARM=0` disables), while the scan stays lazy
  (`start_watch(initial_index=False)`, `manager_for` still kicks the first
  incremental index). Tests: `test_intel.py` (budget cuts a slow index off),
  `test_repo_map.py` (deadline truncates the walk). Docs updated:
  `docs/harness/code-intelligence.md` (the budget invariant),
  `docs/harness/decisions.md` (ADR-H287 amendment), `docs/NAVIGATION.md`.
- **feat(chat): Eclipse can build and run interactive mini-apps in the conversation.**
  Added the `interactive` response block: the model authors self-contained
  HTML/CSS/JS/SVG (a price knob, a VWAP explorer, a doji figure) and it renders
  inline in a sandboxed iframe. The document is composed by
  `src/lib/interactive/document.ts` with an immutable CSP
  (`default-src 'none'; connect-src 'none'; ...`) plus a tiny
  `Eclipse.data()/onData()/resize()` runtime; the frame is
  `sandbox="allow-scripts"` with no `allow-same-origin`, so it has no access to
  the app DOM, cookies or network. Widgets that need market data declare a
  `dataset`; the HOST fetches the existing read-only `/api/price-history` route,
  normalizes up to 5000 bars with source/as-of/freshness and injects the snapshot
  over postMessage (validated by frame source + per-render nonce). The model never
  types prices, and an empty series renders an explicit unavailable
  state instead of a fabricated line. Wired through the contract union, registry,
  Markdown projection, PDF export, Canvas `REPORT_BLOCKS`, prompt guidance, and
  `contract-matrix` parity. New files: `src/lib/response/blocks/interactive.ts`,
  `src/lib/interactive/{document,dataset}.ts` (+ tests),
  `src/components/response/{interactive-block,interactive-frame}.tsx`.
  A settled ```` ```html ```` / ```` ```svg ```` / ```` ```eclipse-app ```` fence
  renders through the same sandbox too, so a model that answers with UI code
  still produces a live app; the composer preserves a full document's styles and
  scripts but strips any model-supplied CSP meta.
  Decision: ADR-052. docs updated: `docs/interactive-response-engine.md`,
  `docs/DECISIONS.md`, `skills/ARCHITECT.md`.
- **ui(layout): slim the app header.** Top bar and sidebar brand row now use a
  single `h-12` (48px) at all breakpoints instead of `h-14 md:h-16` (56/64px),
  reclaiming vertical space while keeping the 40px inner controls comfortable.
  no doc change — style-only change, no contract or architecture impact.
- **feat(chat): Eclipse can ask ONE clarifying question instead of guessing.**
  Added a read-only `clarify` tool (`python/harness/clarify_tools.py`) that takes
  a question, optional context, 2–4 options and a recommended default, creates a
  `clarification` row in the existing `McpApproval` store (additive `answer`
  column), emits `clarification.requested`, and pauses on the SAME
  `wait_for_decision` gate approvals use. The operator picks an option, types a
  free-text answer, or chooses "Let Eclipse decide"; the answer returns as the
  tool result so the run resumes in place. An answer is explicitly NOT an
  authorization (`answer_clarification` refuses non-clarification rows). Without
  an interactive client the tool never blocks or fabricates: it returns
  `answered: false` so the model must state an assumption. Wired through
  `routers/mcp.py` (`POST /mcp/approvals/{id}/answer`), the Next proxy, the event
  parser/hook, a new `clarification-card.tsx` in both chat surfaces, prompt
  guidance, and a watchdog exemption. Tests: `python/tests/test_clarify.py`,
  `src/lib/agent/events.test.ts`. Decision: ADR-H328.
  docs updated: `docs/harness/architecture.md`, `docs/harness/decisions.md`,
  `docs/NAVIGATION.md`.

- **fix(delegation): make the budget, aggregation modes and handle checks real.**
  The fan-out budget was decorative: `token_budget` was only a minimum check and
  `consumedTokens` was always 0. Each part's REAL `totalTokens` now flows through
  `ChildOutcome.tokens` into `BudgetReport.consumedTokens`, and a part is refused
  before it starts once the remaining room drops below `MIN_TOKENS_PER_CHILD`.
  Added an overall `DEFAULT_TOTAL_TIMEOUT_S` deadline that stops running parts and
  gives every outcome a terminal status. `aggregate` now honors the request's
  `list`/`compare`/`merge_claims` mode (previously all rendered as a list). The
  `delegate` tool carries the parent's `workflowId` onto the fan-out, and handle
  verification is fail-closed: an `artifact_digest` is confirmed only when the
  Artifact Center holds it (never for being non-empty). The tool schema no longer
  calls working `agent_id`/`tool_subset` fields "Reserved", and the prompt states
  when delegation is worth its cost. Tests: `test_delegation.py`,
  `test_delegation_tool.py`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`.

- **feat(chat): see parallel agents working, like a fan-out card.** A delegated
  child runs on its own run id, so its events never reached the parent stream.
  New `python/harness/delegation_progress.py` (`ChildProgressBridge`) bridges the
  child's bus stream into ONE throttled, content-free `delegation.progress`
  snapshot on the parent emitter (real `step`/`maxSteps`, real tokens, real price
  or `null` when unpriced, latest activity). `delegation.started` now names the
  parts (`agents[]`), and the terminal/aggregated events carry real tokens.
  The chat renders `src/components/chat/parallel-agents-panel.tsx` (bot icon,
  agent + sub-question, live activity, progress bar, cost per row; header with
  "N agents working · X of N done · total") fed by a pure
  `src/lib/agent/delegation-reducer.ts`. Percent is `step / maxSteps` and an
  unpriced model shows `—`, never `$0.00`. Tests:
  `python/tests/test_delegation_progress.py`,
  `src/lib/agent/delegation-reducer.test.ts`, `events.test.ts`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/NAVIGATION.md`, `docs/chat-ui-audit.md` (R4 resolved).

- **feat(delegation): `best_of` — try the same task several ways, pick the
  strongest verified result.** `DelegationRequest.strategy` now accepts
  `best_of`; the `delegate` tool takes `goal` + `count` (2–4, optional
  `agent_ids`) instead of `children`, and refuses mixing the two. Selection is
  deterministic and evidence-based (`select_best`): only completed attempts
  qualify, confirmed claims/handles score positively, unconfirmed claims
  negatively, then non-empty output and fewer tokens break ties. Only the
  winner's prose/proven claims are repeated (`aggregate_best_of`); the rest are
  named as not repeated, and no attempt finishing yields `winner=None` rather
  than a fabricated best. `delegation.aggregated` carries `strategy`/`winner`;
  the chat header renders `Best of N` with a `Best` chip on the winning row.
  Tests: `python/tests/test_delegation_best_of.py`, `delegation-reducer.test.ts`,
  `events.test.ts`. docs updated: `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/NAVIGATION.md`.

- **feat(delegation): per-attempt model for `best_of`.** An attempt may name a
  `model` (`DelegationChild.model`; tool `models[]`), and the child runs with
  that model id copied onto the parent's `ModelSettings`. The **provider and its
  credential never change** — the Python service holds only this run's key, so a
  cross-provider attempt is deliberately not offered (it would have to invent a
  credential). The progress snapshot and the chat row show the model name.
  Tests: `test_delegation_best_of.py`, `events.test.ts`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/NAVIGATION.md`; regenerated `docs/harness/tool-registry.json`.

- **feat(delegation): per-attempt temperature for `best_of`.** An attempt may
  carry `temperature` (`DelegationChild.temperature`; tool `temperatures[]`),
  applied by copying it onto the child's `ModelSettings`. This makes N attempts
  real samples instead of near-duplicates. It is a sampling hint only: a
  provider that ignores temperature is unaffected, and nothing is fabricated to
  compensate. Tests: `test_delegation_best_of.py`. docs updated:
  `docs/harness/roadmap/phase-07-delegation.md`; regenerated
  `docs/harness/tool-registry.json`.

- **feat(graph): enforce the TypeScript/Python node contract and add Set variables.**
  Added `src/lib/graph-studio/manifest.ts` + checked-in
  `registry.manifest.json`, generated by `npm run graph:manifest`. The new
  Python suite `test_graph_registry_parity.py` compares the runtime registry to
  the manifest node for node (ports, config field names, capabilities, side
  effects, modes, terminal), so an editor-only or runtime-only node now fails
  CI. Added the first new core node, `data.set_variables`, to BOTH registries:
  it merges configured named values over an optional input object (configured
  keys win). Also added the `fast`/`slow`/`signal` config fields the runtime
  already accepted to the TS `finance.indicator` contract so the editor can
  configure them. Tests: `manifest.test.ts`,
  `test_graph_registry_parity.py`; targeted graph suites 53 TS + 75 Python.
  docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): run and version history in Graph Studio.** Added a History tab
  to the workspace right rail. It lists a saved workflow's runs
  (`/api/workflows/[id]/runs`) with status/duration/error, and its immutable
  versions (`/api/workflows/[id]/versions`). Opening a run fetches the full
  record before drawing its node statuses on the canvas; opening a version loads
  it into the editor, with an unsaved-changes confirm, and saving still appends
  a new version. Formatting is deterministic UTC (`history-model.ts`, tested).
  Tests: `history-model.test.ts`, `execution-client.test.ts`,
  `persistence-client.test.ts`; targeted graph suite 11 files / 59 tests.
  docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): bounded local datasets + a `local_write` effect class.**
  Added `data.dataset.save` / `data.dataset.load` in both registries and the
  Python runtime. A payload is JSON-encoded into `HarnessGraphDataset` on the
  runtime's own `agent-memory.db` and referenced by a small `gds:` ref; the
  store caps a payload at 8 MB, the table at 200 datasets, and supports a TTL
  (expired refs are purged and fail explicitly). No market data is fabricated
  and JDDS is untouched. Added `local_write` as a side-effect class: a test run
  may perform local scratch writes, while external write/network/trading stay
  denied; `dataset.read`/`dataset.write` join the test-run capability set.
  Tests: `test_graph_datasets.py` (roundtrip, expiry, size/serialization limits,
  end-to-end execution, capability denial), registry parity + manifest. Targeted
  graph suites 60 TS + 81 Python. docs updated: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`.
- **feat(graph): pinned subworkflows with input delivery and bounded recursion.**
  Added `flow.subworkflow` (both registries + Python runtime). A node runs a
  pinned `workflowId@version` as a nested run; the parent input becomes the
  child's run input and the child's terminal value becomes the node output
  (keyed by terminal id when there are several). The Next front door resolves
  the referenced IRs from JDDS (`subworkflow-bundle.ts`, with cycle/depth/
  missing-workflow refusal) and sends them with the run, so Python never reads
  JDDS. The runtime compiles every child with the SAME grants (authority can
  only narrow), enforces a depth limit of 5, and refuses cycles again. Also added
  `GraphRun.output` terminal capture and an output readout in the Run panel.
  Tests: `test_graph_subworkflows.py`, `subworkflow-bundle.test.ts`; targeted
  graph suites 65 TS + 87 Python. docs updated: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`.
- **feat(graph): durable execution on the Fabric + resumable checkpoints.**
  Graph runs now dispatch as `graph` DURABLE jobs on the existing Execution
  Fabric (new queue/worker/policy; no second queue). Added normalized
  `HarnessGraphNodeRun`/`HarnessGraphEvent` tables, a bounded 2 MB per-node
  output checkpoint, and `GraphRunStore.load_resume`. `GraphExecutor` seeds
  completed nodes/outputs/fired-control/terminal values and skips them, so a
  Fabric-requeued run resumes instead of restarting. A node failure stays a
  succeeded Fabric job (the run row is authoritative); worker/process crashes
  are recovered by the Fabric lease and resumed. Added `queued → running`
  status, terminal output persistence, Fabric cancellation (queued or running),
  and a legacy in-process fallback when the Fabric is disabled. Tests:
  `test_graph_durable.py` (normalized rows, resume skips a completed node,
  durable dispatch, worker bridge, cancel, orphan reconcile, real Fabric
  manager + worker). Targeted graph suites 65 TS + 94 Python. docs updated: `docs/graph-studio.md`,
  `docs/harness/execution-fabric.md`, `docs/NAVIGATION.md`.
- **feat(graph): live SSE run updates.** Added
  `GET /graphs/runs/{id}/stream` (Python) and
  `/api/graph-runs/[runId]/stream` (Next proxy). The stream replays the
  persisted `HarnessGraphEvent` log from `Last-Event-ID`, tails new events every
  250 ms, emits keep-alives, and ends with `stream.end` at a terminal run. The
  Graph Studio Run tab now consumes SSE: node statuses update in place and the
  full run record is fetched once at terminal (authoritative outputs/durations/
  errors). A disconnected stream falls back to the existing bounded polling.
  Tests: `test_run_event_stream_replays_and_ends` + client event-mapping tests.
  Targeted graph suites 67 TS + 95 Python. docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): gateway-backed quotes/history + tabular transform pack.**
  Added `finance.quote` and `finance.history` in both registries; both call the
  EXISTING `MarketDataGateway` (server bridge bound at boot) and return
  provenance, with explicit `MarketError` failures. History emits the standard
  OHLCV payload so it feeds indicators. Added `transform.select`,
  `transform.sort_limit`, `logic.aggregate` (sum/avg/min/max/count + groupBy),
  `logic.deduplicate` and `transform.join` (inner/left) over arrays of objects
  with dotted field paths and a 100 000-row bound. The node manifest is now 35
  types. Tests: `test_graph_tables.py` (8 cases incl. fake gateway/error paths)
  + registry parity. Targeted graph suites 67 TS + 103 Python. docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): quant backtest node over the existing engine.**
  Added `quant.backtest` in both registries. It adapts the graph OHLCV payload
  to `BarSeries`/`MarketDataset` and calls `run_backtest` in
  `harness/quant/engine.py` — no backtest math in the graph runtime. Supports
  the documented `ema_cross`/`rsi_reversion` presets and a full `StrategySpec`
  JSON; the input symbol is authoritative; `randomSeed` keeps runs deterministic
  and `maxBars` bounds work. Returns the result, metrics and trades; equity
  curves are optional (`includeSeries`). The manifest is now 36 types. Tests:
  `test_graph_quant_nodes.py` (preset determinism, RSI preset, curves, custom
  StrategySpec, explicit failures) + registry parity. Targeted graph suites
  67 TS + 108 Python. docs updated: `docs/graph-studio.md`,
  `docs/NAVIGATION.md`.
- **feat(graph): walk-forward validation node.** Added `quant.walkforward` in
  both registries. It adapts the OHLCV payload and calls
  `harness/quant/walkforward.py`, optimizing only on each training window and
  reporting in-sample, out-of-sample and combined metrics plus IS/OOS
  divergence. Preset-derived default parameter spaces are provided; custom
  strategies supply `paramSpaceJson`. Insufficient history is an honest
  `INSUFFICIENT_HISTORY` result. The manifest is now 37 types. Tests:
  `test_graph_quant_nodes.py` (walk-forward windows + insufficient history) +
  registry parity. Targeted graph suites 67 TS + 110 Python. docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): local research & evidence nodes.** Added `research.evidence`,
  `research.citations`, `research.conflicts`, `research.completeness` and
  `research.report` in both registries. They read the EXISTING web-research
  `EvidenceStore` (no web request, no model call): evidence with a text filter,
  claims/citations, conflicts, a coverage summary, and a deterministic Markdown
  report. `research.read` is granted to test runs because it is a local read.
  The manifest is now 42 types. Tests: `test_graph_research_nodes.py`
  (filter, citations/claims, conflicts, completeness, deterministic report,
  missing id) + registry parity. Targeted graph suites 67 TS + 115 Python.
  docs updated: `docs/graph-studio.md`, `docs/NAVIGATION.md`.
- **feat(graph): operator-run envelope + a real HTTP node.** The front door now
  derives a run's grants from the persisted IR and the node registry
  (`run-authorization.ts`): test run by default; an operator run grants exactly
  the declared capabilities, enables network only on explicit confirmation, and
  refuses trading and external write nodes. `integration.http` gained a real
  executor: SSRF-checked, loopback refused, 1 MB response cap, 60 s ceiling,
  JSON body support, no custom headers/credentials yet. The UI shows an
  `Operator run` button only when the graph needs network and asks for
  confirmation naming the network nodes. Tests: `run-authorization.test.ts` and
  `test_graph_http_operator.py` (envelope denial/grant, GET/POST, blocked and
  loopback URLs, size cap). Targeted graph suites 71 TS + 120 Python. docs
  updated: `docs/graph-studio.md`, `docs/harness/security.md`,
  `docs/NAVIGATION.md`.
- **feat(graph): the research agent node runs on the existing agent plane.**
  `agent.research` now has an executor: it resolves a named agent preset, caps
  the turn at `maxSteps`, calls `AgenticService.run`, and returns a structured
  `finding` plus the run's research evidence. It is gated by the operator-run
  network envelope. The front door resolves model credentials from the vault
  and sends them in memory; `GraphService` excludes them from the durable
  Fabric job payload, so a restart before the node fails honestly instead of
  persisting a key. Tests: `test_graph_agent_node.py` (structured finding,
  objective required, bound-runtime required, envelope denial/grant) + registry
  parity. Targeted graph suites 71 TS + 124 Python. docs updated:
  `docs/graph-studio.md`, `docs/NAVIGATION.md`.

- **feat(delegation): per-attempt approaches for `best_of`.** A best-of attempt
  may carry a short `approach` (tool `approaches[]`, e.g. "retry with backoff"
  or "mock the API"). It is prepended to that child's prompt as guidance and
  becomes the row label in the chat card (the full sub-question stays in the
  tooltip), matching the "each agent tries a different angle" presentation. It
  is guidance, never a claimed result. Starts/progress carry `approach`, so the
  label is live from the first frame. Tests: `test_delegation_best_of.py`,
  `events.test.ts`. docs updated: `docs/harness/roadmap/phase-07-delegation.md`,
  `docs/NAVIGATION.md`; regenerated `docs/harness/tool-registry.json`.

- **feat(delegation): per-attempt context for `best_of`.** Attempts may carry
  their own bounded `contexts[]` (tool) / `DelegationChild.context`, so tries can
  work from different background evidence. Context is prompt input only — it is
  never placed in the progress snapshot or the card, so background material
  cannot leak into the transcript. Tests: `test_delegation_best_of.py`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`; regenerated
  `docs/harness/tool-registry.json`.

- **feat(delegation): the fan-out survives a reload, and the card is tested.** The
  persisted `HarnessRun.delegation` blob now carries each row's bounded
  `goal`/`approach`/`model`/`tokens` (`ChildOutcome` gained those display
  fields), `_run_row` returns it old-row-safe, and `/runs/{id}/explain` includes
  a bounded, redacted `delegation` view (`_bounded_delegation`) without
  re-rendering the child's prose or claims. Added a server-render test for
  `src/components/chat/parallel-agents-panel.tsx` (best-of header + winner chip +
  real cost + `—` for an unpriced part + step/ceiling progress; split header;
  empty case). Tests: `test_run_observability.py`,
  `parallel-agents-panel.test.tsx`. docs updated:
  `docs/harness/roadmap/phase-07-delegation.md`.

- **chore(delegation): stop advertising dead DAG tools, propagate stop, make
  concurrency configurable.** (1) `install_orchestration_layer` no longer
  registers the 11 model-facing orchestration tools — no built-in allowlist names
  them, so they only appeared as unreachable tools; the engine, operator routes
  and direct-registration tests are unchanged (`parallel-orchestration.md`
  updated). (2) Each delegated part now gets its own `cancel_event` passed to
  `execute_run` and set on timeout/cancel/failure, so cooperating tools stop.
  (3) `MAX_IN_FLIGHT` is operator-configurable via
  `HARNESS_DELEGATION_MAX_IN_FLIGHT` (clamped 1–8) because memory is the real
  constraint. Tests: `test_delegation.py`, `test_delegation_tool.py`,
  `test_orchestration_tools.py`. docs updated:
  `docs/harness/parallel-orchestration.md`,
  `docs/harness/roadmap/phase-07-delegation.md`.

- **feat(team): opt-in per-member fan-out.** `TeamPolicy.memberFanout` (default
  off) adds the `delegate` tool to each member's declared surface so a Bot can
  run a split fan-out or `best_of` inside its own subtask. It adds only the tool
  NAME — delegation caps, narrowing and permissions still apply, and a member
  with no declared surface already inherits it. Tests:
  `test_team_service.py`. docs updated: `docs/harness/bot-team-orchestration.md`.

- **docs(roadmap): phases 15, 18 and 20 are Done in the code; the index was stale.**
  Re-read the modules and their tests against the phase files and corrected the
  status instead of re-implementing finished work: Phase 15 (promotion + rollback,
  document extractors, artifact serving, inline `ArtifactView`), Phase 18 (figure
  payload + 10 recipes + inline renderer, 2026-10-18) and Phase 20 (every
  capability class graded; `test_capability_classes` asserts no unmeasured row).
  Evidence run: `test_code_promotion*`, `test_analysis_recipes`,
  `test_artifacts_*`, `test_artifact_verification`, `test_capability_classes`,
  `artifact-view.test.tsx`, `analysis-types.test.ts` — all pass.
  docs updated: `docs/harness/roadmap/README.md`,
  `docs/harness/roadmap/phase-{15,18,20}-*.md` (status + last-verified).

- **feat(eval): a measured adoption gate for the `delegate` fan-out.** New
  `python/harness/evaluation/delegate_benchmark.py` runs both variants on frozen
  tasks through the REAL `execute_run` graph and the REAL `delegate` handler:
  N sequential steps vs one fan-out with N parts. The model is a deterministic
  SIMULATOR with a fixed per-call latency, so the result answers whether the
  parts overlap — the report says `simulated: true` and never calls a simulated
  millisecond provider latency. Both variants cover every fact by construction;
  a coverage miss is `unmeasured` and vetoes adoption, and adoption needs equal
  coverage plus a ≥15% wall-clock gain (`ADOPTION_LATENCY_MARGIN`, ADR-H213).
  First frozen run: three parts save ~29%, two parts do not — the gate is a
  measurement, not a default. Tests: `test_delegation_benchmark.py`.
  docs updated: `docs/harness/agent-evaluation.md` (§13.2), `docs/NAVIGATION.md`.

- **fix(delegation): production polish for the fan-out surface.** A stopped part
  now finishes its live snapshot as `cancelled` (not `failed`) while still
  setting the child's stop signal; a completed but unpriced part makes the card's
  total unknown instead of silently understating it (a refused part does not);
  the card header exposes an `aria-live` status label for screen readers; and the
  new benchmark test file has consistent line endings. Tests:
  `delegation-reducer.test.ts`, `parallel-agents-panel.test.tsx`,
  `test_delegation_benchmark.py`. Full checks: `tsc` clean, 398 vitest files /
  3917 tests, 83 targeted Python tests.

- **feat(graph): live web-research nodes (Phase 7).** Added
  `research.web_search`, `research.web_fetch` and `research.claim_verify` to
  both registries. Search and fetch reuse the existing web-research engine
  (`web_providers`, `web_extract`) through the SSRF-hardened bridge capabilities
  - no second egress path. Results are pointers, extracted text is untrusted,
  and a fetch with a `researchId` saves the same `Evidence` the `web_extract`
  tool saves so the local research nodes can read it. Both live nodes are
  `network` side effects (test runs refuse them; an operator run must confirm
  network). `claim_verify` is a local read over the verifier. The manifest is
  now 45 types. Tests: `test_graph_research_nodes.py` (search/domain filter,
  fetch+evidence save, unknown evidence id, compiler network denial/grant) and
  `run-authorization.test.ts` (network vs local research nodes). docs updated:
  `docs/graph-studio.md`, `docs/harness/security.md`.

- **feat(graph): optimizer, Monte Carlo and OOS holdout nodes (Phase 6 complete).**
  Added `quant.optimize`, `quant.montecarlo` and `quant.oos` to both registries.
  They reuse the tested quant engines instead of reimplementing research math:
  the optimizer returns best/leaderboard/stability, Monte Carlo returns the
  return distribution and loss/ruin probabilities, and the OOS node makes a
  chronological split (fraction or index), backtests both sides with the same
  deterministic engine, reports IS/OOS divergence and a block-bootstrap CI for
  the OOS mean return. A materially weaker OOS objective raises
  `IS_OOS_DIVERGENCE`. The manifest is now 48 types. Tests:
  `test_graph_quant_nodes.py` (optimizer leaderboard/no-axis refusal, Monte
  Carlo distribution, OOS split/index/invalid split). docs updated:
  `docs/graph-studio.md` (Phase 6 status + next milestone), no other contract
  changed.

- **feat(graph): paper trading and safety (Phase 8).** Added
  `trading.risk_check` (pure pre-trade gate over `harness/quant/risk.py`) and
  `trading.paper_order` (PAPER-only execution adapter) to both registries. The
  front door gains an explicit `allowPaperTrading` confirmation and grants
  `allowTrading` only for a `paper`-mode graph; the Python compiler refuses LIVE
  mode outright, refuses an ungranted trading node, and still refuses every
  trading node in a test run. Paper fills use the supplied reference price with
  explicit slippage/commission and never contact a broker. The UI shows the
  operator-run confirmation for paper-trading graphs. The manifest is now 50
  types. Tests: `test_graph_trading_nodes.py` (risk cap/rejection, simulated
  fill, rejected decision, price/intent validation, test-run/LIVE/ungranted
  refusals), `run-authorization.test.ts` (paper confirmation, research-mode
  refusal, LIVE refusal). docs updated: `docs/graph-studio.md`,
  `docs/harness/security.md`.

- **feat(graph): post-run step inspector and structural version diff (Phase 9).**
  Added `src/lib/graph-studio/run-debug.ts` and a Run-panel step inspector:
  ordered steps, status/attempts, bounded inputs/outputs, per-node events and
  checkpoint availability. The runtime's node-run read now exposes
  `resumable`, so the inspector never infers a checkpoint. Added
  `src/lib/graph-studio/ir-diff.ts` plus a History > Versions `Diff` action:
  added/removed/changed nodes and edges, changed settings and name, with a
  key-order-insensitive config comparison. Tests: `run-debug.test.ts`,
  `ir-diff.test.ts`, and a `resumable` assertion in `test_graph_durable.py`.
  docs updated: `docs/graph-studio.md` (Phase 9 + next milestone).

- **feat(graph): bounded run telemetry and a Health tab (Phase 10).** Added
  `GraphRunStore.health` / `GraphService.health` and operator-gated
  `GET /graphs/health?windowHours=N`: run counts by status, success/failure
  rate, duration p50/p95, queue wait (created → started), throughput,
  failed-node codes, slowest node types and checkpoint coverage. Reads are
  capped (1 000 runs / 5 000 node rows, 1–168 h) and report `truncated`; missing
  values stay `null`. Added the Next proxy, typed `getGraphHealth` and the Graph
  Studio **Health** tab (1 h / 24 h / 7 d). Tests:
  `python/tests/test_graph_health.py` (counts/percentiles/failure codes, window,
  queue wait, bounded read). docs updated: `docs/graph-studio.md` (Phase 10
  status, telemetry contract, next milestone).

- **feat(graph): chat-to-graph authoring (Phase 7).** Added
  `python/harness/graph_runtime/planner.py`: the model receives the runtime's
  real node catalog and returns a strict JSON proposal; the planner validates
  every node type, port, edge and config against the same registry the compiler
  uses, derives capabilities, selects `paper` when a trading node is present and
  dry-runs the compiler. Only a zero-error proposal becomes a `WorkflowIR`;
  nothing is saved or executed automatically. Added operator-gated
  `POST /graphs/plan`, the Next proxy `/api/graphs/plan` (model settings resolved
  from the vault, memory only), typed `plan-client.ts`, and a "Generate from
  prompt" flow in the workflow list that saves through the normal create path.
  Tests: `python/tests/test_graph_planner.py` (catalog, valid/trading plans,
  unknown type/port/config refusal, missing model/objective) and
  `plan-client.test.ts` (parsed IR, validation errors, refusal). docs updated:
  `docs/graph-studio.md` (Phase 7 + chat-to-graph contract).

- **feat(graph): planner and delegate agent nodes (Phase 7 complete).** Added
  `agent.plan` (one bounded structured-plan model call, 1–8 steps, stable ids
  and earlier-step dependencies, never executes them) and `agent.delegate` (1–6
  tasks, each one bounded turn on the existing agent plane, explicit per-task
  failure with a `PARTIAL` summary). The plan call reuses the in-memory model
  settings and a strict schema (`agent_plan.py`); delegation reuses the bound
  agent runner, so neither adds an agent loop. The manifest is now 52 types.
  Tests: `test_graph_agent_node.py` (plan/delegate, failed part, task cap,
  bound planner) and   `test_graph_agent_plan.py` (ids, dependencies, step cap).
  docs updated: `docs/graph-studio.md` (Phase 7 complete).

- **feat(graph): health watch and headless schedule guidance.** Added
  `graph_runtime/health_watch.py`: a bounded cadence reads the health telemetry,
  persists `unmeasured`/`insufficient`/`healthy`/`degraded` in
  `GraphHealthWatchState`, and publishes `graph.health_degraded` /
  `graph.health_recovered` only on a transition. Thresholds are env-tunable
  (`HARNESS_GRAPH_HEALTH_*`; `SECONDS=0` disables). `/graphs/health` now carries
  `watch`, and the Health tab renders the verdict/reasons. Boot starts/stops the
  watcher; it never creates or changes a run. Docs also document driving
  `/api/workflow-schedules/tick` from external cron with `CRON_SECRET` for a
  headless host. Tests: `test_graph_health_watch.py` (thin data, thresholds,
  transition-only events). docs updated: `docs/graph-studio.md`.

- **feat(fabric): same-host multi-process workers.** `FabricStore.claim_job` is
  now ONE `UPDATE ... RETURNING` statement, so two processes sharing
  `agent-memory.db` can never claim the same job; claim and lease renewal now use
  the same worker id (the old `id:slot` claim meant heartbeats did not renew the
  lease). Added `HARNESS_FABRIC_WORKERS` (kinds/queues, `none` =
  producer-only) and `python -m harness.fabric.standalone` for a dedicated worker
  process that starts only the Fabric consumers. Tests: two independent
  stores/connections claim exactly once; worker filter parsing; standalone CLI.
  A multi-machine fleet remains unsupported because the store is local SQLite.
  docs updated: `docs/harness/execution-fabric.md`, `docs/graph-studio.md`.

- **feat(graph): durable paper-trading accounts.** `trading.paper_order` now
  records each fill in `GraphPaperAccount`/`GraphPaperFill` on `agent-memory.db`
  by default: cash, signed position, average cost and realized PnL persist across
  runs, so a scheduled paper graph keeps its book. The write is one
  `BEGIN IMMEDIATE` transaction, safe alongside the multi-process workers.
  `accountId`, `initialCash` and `persist` are node settings; `persist: false`
  keeps a fill stateless. This is cost-basis accounting, not mark-to-market.
  Tests: `test_graph_trading_nodes.py` (persisted buy/sell + realized PnL,
  stateless fill, missing store). docs updated: `docs/graph-studio.md`.

- **feat(graph): durable subworkflow child runs and a workflow picker.**
  `GraphExecutor` now reports a finished nested run to the service, which stores
  it as its own durable row (`<parentRunId>:<nodeId>`) with node runs and events;
  the parent node returns that child `runId`. The inspector's subworkflow node
  now selects a saved workflow from the catalog and pins its version from a
  dropdown (with a self-reference warning), instead of typing ids. Tests:
  `test_graph_subworkflows.py` (child run row + nodes + events). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): owner-scoped datasets.** `HarnessGraphDataset` gains an
  `ownerId` column (existing rows migrate to `local`). Save/load/meta carry the
  run's user id; another owner's reference is reported as NOT FOUND, so a ref
  holder cannot probe another user's datasets. `delete`/`list` accept an optional
  owner filter; the expiry purge is unchanged. Tests:
  `test_graph_datasets.py` (cross-owner load/meta/list). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): HTTP headers/credential refs, browser escalation and object-row
  loops.** `integration.http` gains `headersJson` (plain headers; transport
  headers and secrets refused) and `credentialEnvJson` (header → environment
  variable NAME resolved by the runtime only; values are never stored). Headers
  may not come from both sources. `research.web_fetch` gains `allowBrowser`:
  a thin/failed page escalates to the existing Browser Runtime and reports
  `extraction: browser`; the default remains bridge-only. `logic.map/filter/
  reduce` now accept object rows, binding each row's numeric fields by name
  (plus `value`/`index`/`acc`). The per-node checkpoint size is operator-tunable
  (`HARNESS_GRAPH_CHECKPOINT_MAX_BYTES`, 2–16 MB). Tests:
  `test_graph_http_operator.py` (plain/credential headers, ambiguity, missing
  env), `test_graph_research_nodes.py` (browser escalation),
  `test_graph_control_flow.py` (object-row loop), `test_graph_durable.py`
  (checkpoint limit bounds). docs updated: `docs/graph-studio.md`.

- **feat(graph): bounded crawl and an opt-in real-provider e2e.** Added
  `research.web_crawl`: one start URL, 1–10 same-site pages, using the existing
  SSRF-hardened fetch plus the bridge's deterministic `web_collect` link pass.
  It is not a general crawler; each page is untrusted and failures are reported
  per page (`PARTIAL`). Added `test_graph_agent_e2e.py`, skipped unless
  `HARNESS_E2E=1` and provider/model/API-key env vars are set, covering
  chat-to-graph, step planning and an agent node against a REAL provider. Tests:
  `test_graph_research_nodes.py` (same-domain bound/dedupe). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): bounded graph-health alert history.** Every watch transition
  (`degraded`/`healthy`) is appended to `GraphHealthAlert`; `/graphs/health`
  returns the newest 20 with reasons, and the Health tab lists them. Tests:
  `test_graph_health.py` (order + reasons). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): executable `video.render` behind a local-write grant.** The
  node now builds a bound recap storyboard and runs the existing
  `VideoService.run_render_job` in the graph worker (project files + Artifact
  Center entry), with honest failure when the fframes worker is absent. The
  front door adds a whitelisted `allowLocalWrite` confirmation (only
  `video.render`; any other write node is still refused) and the compiler gains
  `RunGrants.allow_write`. Test runs still refuse it. Tests:
  `test_graph_video_nodes.py` (executor, symbols, compile grants) and
  `run-authorization.test.ts` (local-render confirmation). docs updated:
  `docs/graph-studio.md`, `docs/harness/security.md`.

- **feat(graph): durable `logic.wait` via a deferred Fabric job.** A durable
  graph no longer blocks a worker thread on a long wait: the wait node
  checkpoints itself, the run is persisted as `queued`, the worker returns a
  `deferred` outcome and the Fabric requeues the job at the wake time (without
  consuming a retry), then resumes from the checkpoint. Waits are bounded to
  24 h; non-durable `run_sync` keeps the 30 s cap and test runs the 5 s cap.
  Tests: `test_graph_control_flow.py` (deferral), `test_graph_durable.py`
  (defer + resume), `test_fabric_workers.py` (deferred requeue). docs updated:
  `docs/graph-studio.md`.

- **feat(graph): spill oversized checkpoints to confined files.** Above the
  DB checkpoint limit (default 2 MB, tunable to 16 MB), a node's output and
  terminal value now spill to
  `<db-dir>/graph-checkpoints/<runId>/<node>.{checkpoint,terminal}.json` with a
  path-confined `{"$file": ...}` marker, so the run stays resumable (up to a
  256 MB file cap). `load_resume` follows the marker; `delete_run` removes the
  files. Tests: `test_graph_durable.py` (spill, resume, cleanup). docs updated:
  `docs/graph-studio.md`.

- **fix(model,graph): real-provider e2e now runs.** Two defects surfaced when
  exercising a real Ollama model: `model_runtime/providers/base.py` imported a
  nonexistent `model_runtime.models` (now `harness.models`), and the planner
  rejected common model edge shapes (`from`/`to`, `sourcePort`/`targetPort`,
  `{node, port}` handles) plus a missing title. The planner now normalizes those
  aliases and defaults the workflow name. The opt-in e2e was run against the
  configured Ollama model and passed chat-to-graph, step planning and an agent
  node. Tests: `test_model_runtime.py`, `test_graph_planner.py`. docs updated:
  `docs/graph-studio.md`.

- **docs(graph): refresh the remaining-work list.** Known limitations now reflect
  the shipped planner/delegate nodes, the documented external-cron path and the
  health watch; "Next milestone" names multi-process Fabric workers as the main
  remaining item. no doc beyond `docs/graph-studio.md`; no runtime change.

- **fix(harness): code-context lookup, response-block routing and embedding
  circuit cooldown.** These pre-existing working-tree fixes landed with the
  crawl commit: `code/intel/context.py` resolves `find_references` ONCE per name
  (the old loop re-ran the same SQL per test file), `persistence/index.py` adds
  caller/callee-name indexes, `request_intent.py` routes "return it as an inline
  block" to a response deliverable (not a code-workspace edit), and
  `search/embeddings/service.py` keeps a tripped circuit open for 30 s instead of
  re-arming it on every `configure()`. Tests: `test_intel.py`,
  `test_code_request_intent.py`, `test_search_embeddings.py`. no doc change —
  internal performance/routing fixes; contracts unchanged.

- **feat(chat): the fan-out card now looks like a "best of N" panel and opens a
  live agent view.** Each part renders a deterministic **bot face** (from the
  agent id, never a vendor logo), the agent/model + its approach, the live
  activity and the runtime's `step/maxSteps` bar/percent. The card shows a short
  fan-out `title` (best_of defaults to its goal), `X of N done`, and **no cost**.
  Clicking the card opens a portaled frosted dialog
  (`parallel-agents-dialog.tsx`) with each agent's full sub-question, status,
  step counter, tokens and a `recent[]` activity timeline. A
  `tool.requested(delegate)` now paints a provisional "Agents starting" card
  until the real `delegation.started` arrives (and it is dropped if the call is
  refused). The same card is wired into the main chat, the floating dock, bot
  chats and group rooms. Tests: `parallel-agents-panel.test.tsx`,
  `delegation-reducer.test.ts`, `events.test.ts`, `test_delegation_progress.py`.
  docs updated: `docs/harness/roadmap/phase-07-delegation.md`, `docs/NAVIGATION.md`;
  regenerated `docs/harness/tool-registry.json`.

## 2026-10-24
- **ui(chat): roomier chat history rows.** Increased the vertical gap between
  conversation rows from 2px (`gap-0.5`) to 6px (`gap-1.5`) inside the pinned,
  date-bucket and folder groups so the list separates more clearly. no doc
  change — styling only.
- **ui(chat): brighter unselected rows in the chat history rail.** Unselected
  conversation titles in the sidebar now use `text-foreground/70` instead of
  `text-muted-foreground`, and their snippets use the full muted tone, so the
  list is legible at rest without changing the selected row. No contract or
  architecture change. no doc change — styling only.

## 2026-10-23
- **release: v0.2.1-rc.1 (release candidate, not production).** Lands the
  data-integrity, live-measurement and terminal-merge work on `main` and tags the
  merged tree. Offline gates are green (Python 8,283 passed / 27 skipped; Vitest
  3,866 passed; eval gates and corpus gate PASS; tsc, eslint, security, size and
  ADR checks PASS). The live tier is honestly **FAIL**: `task_success` 0.8520 on
  live-eligible tasks against the 0.9 gate. External review, PyPI, ACP, the
  SWE-bench suite, the remaining V2 merges and phases 15/18/20 are explicitly not
  in this candidate. Release note: `docs/releases/v0.2.1-rc.1.md`.
  docs updated: `docs/releases/v0.2.1-rc.1.md`, `docs/CHANGELOG.md`.
- **refactor(harness): V2 terminal merge — one executor, two transports.** The
  code profile's `terminal_run` and the `.black-eclipse/verify.json` auto-verify
  hook now run through the ONE `TerminalManager` instead of calling
  `code/sandbox.run` directly. The manager gained `shell_mode=False`, which
  tokenizes the command with `shlex.split(posix=True)` and executes the argv
  directly, preserving the no-shell contract. `code/terminal.py` is now the ONE
  classifier; `build_run_spec` was removed. Tool names are unchanged. The
  terminal slice measured 383,443 total / code 18,197; reconciling origin/main's
  live-preflight and outage guards added 24 evaluation lines, so the final
  committed ceiling is 383,467 / evaluation 11,741. Files:
  `python/harness/terminal/manager.py`,
  `python/harness/code/{terminal,terminal_tools,tools}.py`,
  `python/tests/test_terminal_tools.py`,
  `python/tests/test_code_terminal.py`, `scripts/size-budget.json`.
  docs updated: `docs/harness/terminal-architecture.md`,
  `docs/harness/decisions.md` (ADR-H311), `docs/CHANGELOG.md`.
- **fix(harness): restore the release gate by recording the size-budget raise.**
  `npm run check:all` failed before tests ran because the harness tree had grown
  to 383,293 lines against the committed 382,030 ceiling (the D1-D12
  data-integrity work added ~1.4k Python lines). Raised the committed total to
  383,400 and the `.`/`evaluation` directory ceilings to their measured values
  (25,110 / 11,725) as an explicit, one-release decision (ADR-H327); Round 4 V2
  remains the work that must lower it again. Files:
  `scripts/size-budget.json`, `docs/harness/decisions.md`.
  docs updated: `docs/harness/decisions.md`, `docs/CHANGELOG.md`.
- **fix(evaluation): the live lane measures the agent, not missing eval tools.**
  Three defects made the live tier publish a false zero: it ran every task
  (including tier-0 scripted tasks that require `eval_*` tools or synthetic
  environments) against the production service; a provider 429/timeout was
  graded as a failed task; and the generated benchmark said `NOT MEASURED` even
  when a pinned live baseline existed. The live gate now selects only
  `live_eligible` tasks, provider failures are `UNMEASURED` with the provider
  reason, and the benchmark falls back to the newest committed
  `baselines/live_v1.json` entry when no valid local run is recorded. Also fixed
  the financial/exact graders to accept `25%` for an expected fraction `0.25`
  (all `weight` tasks were failing on this). Files:
  `python/harness/evaluation/{tasks,live_gate,runner,report}.py`,
  `python/harness/evaluation/graders/{exact,financial}.py`,
  `python/harness/evaluation/baselines/live_v1.json` (adds the live-eligible
  re-score note), `python/tests/test_evaluation_{tasks,live_gate,graders}.py`,
  `python/tests/test_live_baseline.py`, `docs/harness/benchmarks.md` (generated).
  docs updated: `docs/harness/agent-evaluation.md`, `docs/harness/benchmarks.md`,
  `docs/CHANGELOG.md`.
- **style(branding): square, self-backing app icon.** Rebuilt
  `public/branding/FAVICON.svg` as a 32×32 square (near-black rounded tile with
  the white Eclipse mark scaled to a 2px safe area) so the mark stays visible on
  both light and dark browser chrome; the old asset was 28×32 with white-only
  fills. Regenerated `src/app/favicon.ico` (16/32/48 ICO), added
  `src/app/apple-icon.png` (180×180) and `public/branding/icon-{192,512}.png` for
  future PWA use. No manifest was added. Also generated a multi-size
  `public/branding/black-eclipse.ico` and pointed the Windows "Black Eclipse"
  desktop shortcut's **IconLocation** at it (it previously showed the generic
  wscript/Node icon), then refreshed the shell icon cache. docs updated:
  `docs/QUICKSTART.md`, `docs/CHANGELOG.md`; `docs/ARCHITECTURE.md` already
  documents the `public/branding/` defaults.
- **style(branding): flush-left mark in the app icon.** Moved the Eclipse glyph
  from a 3.75px centred inset to the tile's left edge (no left gap), clipped it
  to the rounded tile so the corner stays clean, and regenerated every derived
  PNG/ICO plus the desktop shortcut's cached icon. docs updated:
  `docs/CHANGELOG.md`.
- **fix(desktop): hidden launcher and reliable stop on tab close.**
  `start-eclipse.vbs` now starts the Node launcher with window style `0`, so no
  CMD window appears; boot/stop output goes only to
  `.black-eclipse/desktop-launch.log`. The tab-close stop delay dropped from 20s
  to 8s, and `start-desktop.js` gained a stale-heartbeat watchdog (~150s) so a
  tab that crashes or is force-closed without `pagehide` also tears the server
  down. The watchdog threshold sits above browser background-tab timer
  throttling, so an open-but-hidden tab is not mistaken for a closed one.
  docs updated: `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.
- **chore(stock detail): ship the intelligence + verification slice.** Committed
  the five-chart market-intelligence panel, JDdS listing-market resolution,
  Yahoo→Stooq price fallback, and the web-backed identity/listing/filing/quote
  verification route and panel. Checks: `npx tsc --noEmit` clean; targeted
  Vitest 20/20; changed-file ESLint 0 errors. Files:
  `src/app/api/stocks/[symbol]/{intelligence,verification}/route.ts`,
  `src/lib/stock-intelligence/`, `src/lib/scraper/stooq-chart.ts`,
  `src/components/screens/stock-detail/`,
  `src/components/screens/tradingview-chart.tsx`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **feat(stock detail): more charts and web-backed source verification.**
  Added 1Y price-trend and drawdown charts so the panel shows sourced data even
  when a symbol has no fundamentals, and made every unavailable chart render as
  a card with its reason instead of collapsing the section. The intelligence
  route now resolves the listing market from JDdS (the screener can omit
  country, e.g. EMAAR was being requested as US) and falls back from Yahoo to
  Stooq for US daily closes. Added `GET /api/stocks/[symbol]/verification`,
  which reuses the existing web-search transport to check identity, listing,
  filings and a quote cross-check; official hosts are required for `VERIFIED`,
  snippets only ever `CORROBORATE`, and results are cached for 30 minutes.
  Files: `src/lib/stock-intelligence/{types,charts,verification,use-stock-verification}.ts`,
  `src/lib/scraper/stooq-chart.ts`, `src/app/api/stocks/[symbol]/{intelligence,verification}/route.ts`,
  `src/components/screens/stock-detail/{charts/intelligence-panel.tsx,verification-panel.tsx}`,
  `src/components/screens/tradingview-chart.tsx`, tests alongside each module.
  `npx tsc --noEmit` clean; targeted Vitest 20/20 pass; lint 0 errors.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **fix(harness): twelve data-integrity defects closed in retrieval/routing.**
  Added the shared `DataQualityEnvelope` (VALID/STALE/DIVERGENT/SCALE_MISMATCH/
  UNAVAILABLE/UNVERIFIED), cross-source price comparison with both candidates
  preserved, statement period-age + cache-key versioning, one FX pair resolver,
  cadence-aware freshness (business days + holidays), provider health read from
  the recorded run ledger, breaker-demoted routes with provenance, capability
  mismatch blocks + CI allowlist, undated-news filtering, bounded retry/body
  cache/success-rate for research fetches, Levenshtein tool suggestions, and
  IMAGE_ONLY/OCR_UNAVAILABLE document handling. Evidence in `HARNESS_FIXES.md`
  and `scripts/repro_{baseline,after}.txt`.
  docs updated: `docs/harness/market-data.md`, `docs/CHANGELOG.md`.
- **docs(nav): NAVIGATION covers the corpus, rotation, live-baseline and
  supervised-change surfaces.** Updated the evaluation row (338 tasks — 263
  oracle-backed + 75 exemptions, plus `corpus.py` / `contamination.py` /
  `rotation.py` / `significance.py` / `live_baseline.py`), the RSL row (v4
  modules `archive` / `cmp` / `operators` / `sampler` / `autonomy` and the v4
  plan), and added a task row for corpus audit / rotation / live baselines /
  operator-triggered apply with the CLI, routes, UI cards and the quarterly
  workflow. Files: `docs/NAVIGATION.md`.
  docs updated: `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.
- **feat(desktop): the icon now opens `blackeclipse`, with a visible boot console
  and a fast start.** `scripts/start-desktop.js` manages the production profile
  (`black eclipse --restart`: built Next on 3100 behind the local proxy),
  restarts an unmanaged instance so tab-close owns its lifecycle, and opens
  `https://blackeclipse` (http fallback). `start-eclipse.vbs` runs it with a
  visible console that closes when the tab closes; closing the console by hand
  stops the server. The launcher starts the existing build directly
  (`local-host`, ~2s) and never rebuilds while the user waits: a stale source
  shows a console note and still starts instantly, and the first launch on a
  fresh clone is the only build. `BE_DESKTOP_BUILD=1` forces a rebuild. The
  source hash is now content-based (a touch no longer invalidates the build),
  and a `postbuild` hook marks a plain `npm run build` as current.
  Files: `scripts/start-desktop.js`, `start-eclipse.vbs`, `scripts/mark-build.js`,
  `scripts/lib/server.js`, `scripts/doctor.js`, `package.json`.
  docs updated: `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.
- **ci(rsl): a quarterly rotation reminder that cannot write a dataset.**
  Added `.github/workflows/rsl-rotation.yml`: quarterly schedule plus dispatch,
  resolves and validates the quarter label, runs
  `node scripts/rsl-rotate.js --json` (dry run), publishes the plan to the step
  summary and fails when `plan.ok` is false. It never passes `--apply`, and it
  proves the dry run left the corpus tree unchanged. `--json`
  now keeps stdout pure JSON (the human dry-run note goes to stderr) so the
  plan can be redirected and parsed. Files: `.github/workflows/rsl-rotation.yml`,
  `python/harness/evaluation/rotation.py`,
  `python/tests/test_evaluation_rotation.py`.
  docs updated: `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/CHANGELOG.md`.
- **feat(rsl-ui): corpus and autonomy cards on the RSL control panel.**
  Added typed runtime calls and Next proxies for `GET /evolution/corpus`, the
  rotation preview, autonomy status/pause/resume/decide and the state
  autonomy-apply route. Two frosted cards show the 338-task splits, 263
  oracle-backed + 75 documented exemptions, verification/audit, and the
  autonomy level, kill switch and daily budget. Apply is disabled when the
  level, kill switch or budget refuses; the runtime's evidence refusal reasons
  are shown, never bypassed. Files: `src/lib/harness/{evolution-client,
  evolution-browser}.ts`, `src/app/api/evolution/{corpus,corpus/rotation,
  rsl/autonomy/**,states/[id]/autonomy-apply}/route.ts`,
  `src/components/screens/skills/rsl-{corpus,autonomy}-card.tsx`,
  `rsl-control-panel.tsx`, `src/lib/i18n/dictionaries/evolution.ts`, tests.
  docs updated: `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/CHANGELOG.md`.
- **docs(rsl): auto-apply stays operator-triggered (Phase 4 decision).**
  Recorded ADR-H326: no scheduler tick and no `HARNESS_RSL_AUTO_APPLY` switch;
  the only activation path remains `POST
  /evolution/states/{id}/autonomy-apply`, bounded by the existing
  L1/evidence/kill-switch/daily-budget policy. A future scheduler needs its own
  ADR, an off-by-default flag, one apply per tick and a dry-run period. Files:
  `docs/harness/decisions.md`, `docs/self-improvement/rsl-v4-plan.md`.
  docs updated: `docs/harness/decisions.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/CHANGELOG.md`.
- **data(evaluation): the first live-tier baseline is pinned.**
  Recorded `ollama` / `deepseek-v4.1-flash:cloud` on the validation split of the
  338-task corpus (244 tasks, dataset checksum `d6375ca4…`, prompt hash
  `f05e7c03…`): task_success 0.6901 (95% CI 0.6292..0.7450), 242 measured
  trials. A same-identity rerun exited FAIL on the critical gates
  (task_success −0.0083, financial_accuracy −0.0195, safety_score −0.0625); the
  gates allow no drop on those dimensions, so the regression is reported, not
  smoothed. Cost reads 0.0 because `ollama/*` is priced free/local. Files:
  `python/harness/evaluation/baselines/live_v1.json`,
  `docs/self-improvement/rsl-report-2026-10-23.md`.
  docs updated: `docs/harness/agent-evaluation.md`, `docs/CHANGELOG.md`.
- **fix(evaluation): the nightly report can no longer contradict its exit code.**
  Moved the report write to the end of `run_nightly`, after the live comparison,
  promotion and baseline write; a live regression used to set `ok=False` after
  the PASS file was already on disk (and the file omitted those results).
  `GET /evolution/corpus` now also exposes `oracleExemptCount`. Size ceilings
  raised 5 lines (382,030 total; evaluation 11,603; routers 17,214). Files:
  `python/harness/evaluation/nightly.py`,
  `python/harness/routers/evolution_corpus.py`,
  `python/tests/{test_evaluation_nightly,test_evolution_corpus_routes}.py`,
  `scripts/size-budget.json`.
  docs updated: `docs/harness/agent-evaluation.md`, `docs/CHANGELOG.md`.
- **data(evaluation): 338-task corpus with 263 real oracles and 75 documented
  exemptions.** Added `metadata.oracleExempt` + `oracleReason` (task or dataset
  level) and dataset-level contamination so `validate_tasks(strict=True)`
  treats the seven legacy fixture sets (benchmark, construction, adversarial,
  research, replay, routing_e2e, team — 75 tasks) as intentional rather than
  gaps. `finance_v1`'s 13 tasks gained real oracles; new `finance_v7` adds 88
  oracle-backed tasks (60 validation / 28 optimization). The manifest now
  records `oracleExemptCount` (total and per dataset) and verifies it. Splits:
  validation 244 / optimization 88 / held_out 6; corpus audit PASS. Size
  ceilings raised 75 lines for `corpus.py` (382,025 total; evaluation 11,600).
  Files: `python/harness/evaluation/{corpus,contamination}.py`,
  `python/harness/evaluation/datasets/*`,
  `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/{test_evaluation_corpus,test_rsl_provenance,
  test_evolution_corpus_routes}.py`, `scripts/size-budget.json`.
  docs updated: `docs/harness/agent-evaluation.md`, `docs/CHANGELOG.md`.
- **data(evaluation): the 2026Q4 held_out rotation moved four finance tasks.**
  `finance.v5.percentage_change.004`, `finance.v5.operating_margin.005`,
  `finance.v4.eps.003` and `finance.v3.opt.cagr.001` moved
  optimization → held_out (version bumped, `metadata.rotation` recorded); the
  rotation-exempt team tasks stayed put. Splits are now validation 184 /
  optimization 60 / held_out 6, still 250 tasks; the manifest was rebuilt and
  verifies. Files: `python/harness/evaluation/datasets/{finance_v3,finance_v4,
  finance_v5}.json`, `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/test_rsl_provenance.py`.
  docs updated: `docs/harness/agent-evaluation.md`, `docs/CHANGELOG.md`.
- **safety(evaluation): the live nightly is bounded and capped before it spends.**
  `--limit N` runs only the first N tasks (hard bound 500) and a positive
  `--max-cost USD` is required for `--live`; both are validated before any task
  is sent and recorded in the report (`limit`, `maxCostUsd`,
  `estimatedWorstCaseTrials`). `--publish` with no value now resolves to the app
  root's `docs/self-improvement` instead of the Python child's cwd. Files:
  `python/harness/evaluation/nightly.py`, `scripts/rsl-nightly.js`,
  `python/tests/test_evaluation_nightly.py`; raised the committed size
  ceilings to the measured tree (381,950 total; evaluation 11,525) for the 69
  added lines, `scripts/size-budget.json`.
  docs updated: `docs/harness/agent-evaluation.md`, `docs/CHANGELOG.md`.
- **merge(harness): origin/main's Round 3/4 work landed on the local tree.**
  Merged 22 upstream commits (Round 3/4, v0.2.0, and the live-eval publishing
  fix) and resolved the content conflicts in `docs/harness/decisions.md`,
  `package.json`, `python/tests/test_size_budget.py` and the generated
  `docs/harness/benchmarks.md`. The local RSL v4 / notebook decisions moved from
  H293-H302 to H316-H325 so H310-H315 stay reserved for the Round 4 plan;
  `scripts/check-adr-numbers.js` now reserves that range, and every doc reference
  was updated. Raised the harness size ceilings to the measured merged tree
  (381,881 total; `.` 24,845; routers 17,212; evaluation 11,456), pinned
  `graph.py` at 2,323, regenerated the tool registry (957 tools) and benchmarks,
  and included the read-only corpus/rotation routes
  (`python/harness/routers/evolution_corpus.py`, its test, the `main.py`
  registration and the `agent-evaluation.md` note). `npx tsc --noEmit` clean;
  lint 0 errors; ADR and size gates pass; full suite 8,223 passed / 27 skipped,
  with only the two stale-generated-artifact failures, both regenerated and
  their 15 tests green; the follow-up eval-publishing merge's affected
  benchmark/public/size tests (15) also pass.
  docs updated: `docs/harness/decisions.md`,
  `docs/harness/roadmap/round-4-gap-closure.md`,
  `docs/harness/agent-evaluation.md`, `docs/NAVIGATION.md`,
  `docs/self-improvement/rsl-v4-plan.md`,
  `docs/harness/roadmap/{README,phase-21-notebook-cells}.md`,
  `docs/harness/benchmarks.md`, `docs/harness/tool-registry.json`,
  `docs/CHANGELOG.md`.
- **test(evaluation): the one-split export check no longer hardcodes 61 tasks.**
  `test_one_split_can_be_exported_alone` now compares the optimization split
  count against the full built-in corpus, so legitimate corpus growth (64
  optimization / 250 total) cannot fail a test that is about split filtering,
  not a fixed size. `python/tests/test_evaluation_export.py`.
  no canonical doc change — test-only; the rolling-window rotation moved the
  2026-10-16 section into `docs/changelog/2026-10.md`.

- **ui(stock detail): the overlay is compact and chart-led.** Reworked the
  full-screen stock detail overlay into a compact header + key-statistics band,
  one Interactive/History chart card, a collapsible AI brief, tabbed
  fundamentals, clamped news, merged Technical & Risk, merged profile +
  leadership, and a header glossary. Fixed overlay stacking above the chat dock,
  restored blur, contained rail overscroll, made the glossary clear the mobile
  header, and added explicit history loading/empty/error states. Forward P/E now
  comes from the selected stock; history ranges read `1M/3M/6M` and volume labels
  no longer collide. Kept `market-overview.tsx` at its 2,760-line ratchet by
  keeping the new prop on the existing line. Files:
  `src/components/screens/tradingview-chart.tsx`,
  `src/components/screens/company/sections.tsx`,
  `src/components/screens/fundamentals/panel.tsx`,
  `src/components/screens/market-overview.tsx`, `src/app/globals.css`.
  `npx tsc --noEmit` clean; Vitest 384 files / 3828 tests pass; lint 0 errors;
  size budget pass. no canonical doc change — presentation-only; no contract or
  data-shape change. docs updated: `docs/CHANGELOG.md`.

- **chore(evaluation): regenerated the published benchmark after the 2026Q4
  rotation.** The rotation changed the benchmark checksum, so
  `test_published_benchmarks` failed; `npm run eval:benchmarks` rewrote
  `docs/harness/benchmarks.md` from a fresh offline gate, and the targeted
  benchmark + watcher tests now pass (37). Files: `docs/harness/benchmarks.md`.
  docs updated: `docs/harness/benchmarks.md`, `docs/CHANGELOG.md`.

- **fix(home): removed the dead space below the dashboard footer.** The home
  dashboard root carried `pb-24`; its mobile clearance is already supplied by
  `#main-content`, so the extra 96px left a large empty band under the footer.
  Reduced to `pb-6`. File: `src/components/screens/dashboard/home-dashboard.tsx`.
  no doc change — spacing-only fix with no contract or architecture impact.

- **fix(windows): child processes no longer open console windows on server
  start.** Node's `spawn`/`exec*` default to `windowsHide: false`, so the
  auto-started Python harness, port checks, and doctor probes could pop a
  `cmd.exe` window on Windows. Set `windowsHide: true` on the harness spawn,
  Python resolver, launcher/server spawns, doctor, and kill-port. Files:
  `src/lib/harness/python-runtime.ts`, `src/lib/scraper/fetchers/python.ts`,
  `scripts/local-host.js`, `scripts/lib/server.js`, `scripts/doctor.js`,
  `scripts/kill-port.js`.
  no doc change — process-launch detail, no contract or architecture change.

- **feat(desktop): silent launcher that stops the server when the tab closes.**
  Added `scripts/start-desktop.js` (probe known app URLs, start `npm run dev`
  detached with no stdio, wait for HTTP, open `?desktop=1`) and
  `start-eclipse.vbs` (windowless wrapper). `<DesktopSession />` beacons
  `alive`/`leave` to `/api/desktop/session`; the launcher watches the beacon
  file and kills the process tree ~20s after the tab closes, with a reload grace
  window. The route is inert unless `BE_DESKTOP_HEARTBEAT_FILE` is set, so
  console-launched servers are unaffected. A `Black Eclipse` Desktop shortcut
  points at the VBS. Files: `scripts/start-desktop.js`, `start-eclipse.vbs`,
  `src/components/layout/desktop-session.tsx`,
  `src/app/api/desktop/session/route.ts`, `src/app/layout.tsx`.
  docs updated: `docs/QUICKSTART.md`, `docs/CHANGELOG.md`.

- **feat(stock-detail): sourced market-intelligence charts on the company overlay.**
  Added a read-only `GET /api/stocks/[symbol]/intelligence` route that fans out
  to the existing fundamentals service and Yahoo daily closes, then returns
  three derived charts: 6M return vs the home-market benchmark, trailing P/E at
  each fiscal year-end, and earnings surprise. Every chart carries a provenance
  block and an explicit `UNAVAILABLE` reason instead of invented points; web/AI
  facts are deliberately excluded from historical numeric series. The overlay
  mounts a new `Market intelligence` section between the price chart and the AI
  brief, with `SourceBadge` provenance chips and a 5-minute server cache.
  Files: `src/lib/stock-intelligence/{types,charts,use-stock-intelligence}.ts`,
  `src/app/api/stocks/[symbol]/intelligence/route.ts`,
  `src/components/screens/stock-detail/charts/{intelligence-panel,source-badge}.tsx`,
  `src/components/screens/tradingview-chart.tsx`,
  `src/lib/stock-intelligence/charts.test.ts`.
  docs updated: `docs/ARCHITECTURE.md`, `docs/NAVIGATION.md`, `docs/CHANGELOG.md`.

## 2026-10-22
- **fix(chat): a sent paste stays visible in the transcript.** A long paste is
  no longer folded into a giant user message and deleted: it remains a context
  document and each user turn shows a compact "Pasted text" card (name, chars,
  preview, Open), so the exact content that went to the run is visible in
  history. Paste-only sends use "Read the attached document."; pastes over
  100 000 chars are truncated by the document pipeline instead of rejected by
  the turn bound. User prompts over 2 000 chars collapse to an 800-char excerpt
  with "Show full message". New `MessageAttachment` on `Message`; `claimPastes`
  is unit-tested. Files: `src/components/chat/{chat-history,message-attachments}.tsx`,
  `src/lib/chat/{paste,use-session}.ts`, `src/components/screens/stock-chat.tsx`,
  `src/types/chat.ts`, `src/lib/chat/paste.test.ts`; docs updated:
  `docs/chat-ui-audit.md`, `docs/CHANGELOG.md`.
- **chat jump rail: tighter hairlines, calm hover wave, scroll thumb moved right.**
  `MessageRail` ticks are now 1px hairlines stacked 2px apart (was 2px bars with
  a ~5px pitch), baseline width 7px, active 9px, hover 11px (was 10→14px), and
  hovering ripples a decaying wave outward with a 28ms-per-step delay instead of
  one oversized pill. The transcript scroll thumb moved from `right-5` (left of
  the rail) to `right-0.5`, so it now sits just to the right of the ticks.
  `src/components/chat/message-rail.tsx`, `src/components/chat/chat-history.tsx`.
  `npx tsc --noEmit` clean; Vitest 3824 passed (Python suite did not finish
  within the run window; UI-only change).
  no doc change — presentation only, no contract or data-shape change.
- **feat(chat): editable notebook cells + chart code.** Shipped Phase 21:
  a per-conversation cell document (`notebook.json`), the sandbox-backed
  `POST /notebook/cells/{id}/run` and kernel restart routes, an opt-in
  persistent kernel namespace (`AnalysisRequest.persist_namespace`, default
  false so `analysis_run` stays fresh), chart-spec → matplotlib codegen at
  `POST /charts/code`, and a Monaco notebook panel with a composer action and a
  chart "Edit code" link. A cell's outputs are always `computed`, chart data
  travels as a JSON input (never source text), and the original chart block is
  never mutated. Files: `python/harness/routers/notebook.py`,
  `python/harness/charts/codegen.py`, `python/harness/code/{execution,kernel}.py`,
  `python/harness/analysis_tools.py`, `src/lib/chat/notebook-{types,store}.ts`,
  `src/lib/harness/notebook-client.ts`, `src/app/api/chat/notebook/route.ts`,
  `src/app/api/harness/notebook/**`, `src/app/api/harness/charts/code/route.ts`,
  `src/components/chat/notebook-{cell,panel,provider}.tsx`,
  `src/components/response/response-chart.tsx`, `src/components/chat/chat-dock.tsx`,
  `src/components/screens/stock-chat.tsx`, `src/lib/i18n/dictionaries/notebook.ts`;
  tests `test_{chart_codegen,notebook_kernel,notebook_route}.py`,
  `notebook-{store,client}.test.ts`; docs `docs/harness/roadmap/phase-21-notebook-cells.md`,
  `docs/harness/roadmap/progress/phase-21-progress.md`,
  `docs/harness/roadmap/README.md`, `docs/harness/python-runtime.md`,
  `docs/chart-engine.md`, `docs/NAVIGATION.md`. Full Python (8160) and Vitest
  (3824) suites green; `npx tsc --noEmit` clean.
- **feat(charts): chat charts are interactive ECharts — Plotly and PNG left
  the chat path.** A `chart` block is mapped to the shared `ChartSpec`
  (`chart-spec.ts`), a named `dataSource` is resolved in the browser through
  `/api/price-history` (`chart-data.ts`), and the ONE option builder
  (`chart-echarts.ts`, `echarts` + `echarts-gl`) renders it.
  `response-chart.tsx` no longer calls the Python engine or fetches an
  artifact; `plotly-chart.tsx`, `python-chart.tsx` and
  `/api/harness/charts/plotly` were deleted. Also: gauge/treemap/funnel/
  sunburst render natively (no bar stand-in); dated `[date,o,h,l,c]` and
  object candle rows survive normalization; scatter/bubble and radar read the
  fields they carry; drawability is checked with the renderer's own list
  (`chart-capabilities.ts`) inside `response_validate`; an unsupported Python
  picture mark is a named refusal, not a blank PNG. Chart launch:
  `/api/price-history` serves the persisted last-good series FIRST on a cold
  start and refreshes in the background; the batch route dedupes and bounds
  concurrency; the client hydrates bars from `localStorage` before
  revalidating. Session-index messages cap raised 4,000→16,000 so a structured
  answer's fence is not cut. Files:
  `src/lib/response/chart-{spec,data,echarts,capabilities,registry}.ts`,
  `src/components/response/response-chart.tsx`,
  `src/components/charts/echart-chart.tsx`,
  `src/app/api/price-history/{route,batch/route}.ts`,
  `src/lib/chart/subscription-manager.ts`,
  `src/lib/response/normalize.ts`, `src/lib/harness/response-bridge.ts`,
  `python/harness/charts/scene_render.py`, `python/harness/session_index.py`;
  tests `chart-render.test.ts`, updated `chart-spec.test.ts`. docs updated:
  `docs/chart-engine.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`
  (ADR-050 amendment), `skills/ARCHITECT.md`, `docs/NAVIGATION.md`,
  `docs/interactive-response-engine.md`.
- **fix(charts): revert chat charts to Plotly and make them load fast.** The
  ECharts renderer is removed from the chat path: `chart-echarts.ts` and
  `echart-chart.tsx` are deleted, and `plotly-chart.tsx`, `python-chart.tsx`
  and `/api/harness/charts/plotly` are restored. `response-chart.tsx` maps the
  block to the shared `ChartSpec`, hydrates a named `dataSource` in the
  browser, asks the Python engine for the figure + PNG, and registers the
  artifact for export (`chart-registry.ts`). Load is staged: the PNG paints
  immediately, plotly.js is loaded once on an idle frame only when the chart
  nears the viewport (`IntersectionObserver`, 400 px margin), and rendered
  figures are cached per spec so history scrolling does not redraw. Scene
  marks the matplotlib picture cannot draw no longer fail the render (the
  Plotly figure still draws them). `chart-capabilities.ts` now names the
  engine's allowlist (not ECharts). Files:
  `src/components/charts/plotly-chart.tsx`,
  `src/components/response/response-chart.tsx`,
  `src/lib/response/chart-{capabilities,registry}.ts`,
  `src/app/api/harness/charts/plotly/route.ts`; tests
  `src/lib/response/chart-render.test.ts`. docs updated:
  `docs/chart-engine.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`
  (ADR-050 amendment), `docs/NAVIGATION.md`,
  `docs/interactive-response-engine.md`, `docs/CHANGELOG.md`.
- **feat(charts): explicit zoom/reset controls on the live chart.** The
  bottom-left of every Plotly chart now carries zoom in, zoom out and reset.
  Zoom scales the current 2-D axis ranges around their centre (or the 3-D
  camera eye); reset re-applies the figure the engine authored. The focus
  overlay no longer closes when the chart's own toolbar is clicked, and
  double-click still resets. Files: `src/components/charts/plotly-chart.tsx`,
  `src/components/response/response-chart.tsx`; docs updated:
  `docs/chart-engine.md`, `docs/CHANGELOG.md`.
- **docs(harness): plan editable notebook cells in chat (ADR-H323 + phase 21).**
  Added a plan for a per-conversation cell document over the existing analysis
  sandbox, an "Edit code" path from a chart into a linked cell, chart-spec to
  matplotlib codegen, and an opt-in persistent kernel namespace. The chart
  contract stays data-only and `analysis_run` keeps a fresh namespace. Docs:
  `docs/harness/decisions.md` (ADR-H323),
  `docs/harness/roadmap/phase-21-notebook-cells.md` (new),
  `docs/harness/roadmap/README.md`, `docs/NAVIGATION.md`,
  `docs/CHANGELOG.md`.
- **style(chat): computed/proof/sources panels lose their fill and stop
  colliding.** `ComputedResultPanel`, `CodeVerificationPanel` and
  `ResearchEvidencePanel` no longer paint a glass background (border-only),
  their headers are left-aligned with the label on its own row and the method
  text clamped below it, and the computed header now previews the first two
  outputs while collapsed so a result is visible without expanding. In
  `chat-history.tsx` the analysis/research pair stacks full-width instead of
  sharing a 50/50 row. no doc change — presentation-only.
- **style(dashboard): strip the header chrome.** Removed the search trigger,
  Screener / Open portfolio buttons, the Investor/Trader/Both lens toggle and
  the profile/Investor chip from the Dashboard header. The greeting, market
  selector and refresh remain. no doc change — layout-only.
- **feat(response): just-in-time design modules + one shared interaction bridge.**
  Added `response_style_guide` (seven families: data, chart, diagram, workflow,
  interactive, explanation, mechanical) so the model loads a family's nuance and
  worked examples on demand instead of carrying them in every prompt; the field
  map still comes live from the TS contract, and the prompt gets only a compact
  module index. Added `RENDER_DISCIPLINE` ("when NOT to render") to the per-run
  response plan, and extracted `src/lib/response/followup.ts` as the one
  state→prompt serializer used by `controls` and `simulation`. Files:
  `python/harness/response_style.py`, `response_tools.py`, `graph.py`,
  `response_mode.py`, `src/lib/response/followup.ts`, `controls-block.tsx`,
  `simulation-block.tsx`, tests `test_response_tools.py`, `followup.test.ts`;
  docs `docs/interactive-response-engine.md`, `docs/NAVIGATION.md`.
- **feat(dashboard): add the genuinely useful workspace cards.** New
  Dashboard-only surfaces: today's P&L attribution ("what moved your book"),
  a "Needs a look" action list (near support / falling / reporting soon) with
  one-click ±3% alerts, market session clock (time-zone-aware open/closed for
  12 exchanges), portfolio risk snapshot (volatility, drawdown, beta,
  concentration), currency exposure, sector rotation buckets, relative
  performance vs the benchmark, an alerts strip, per-section show/hide +
  reorder (persisted locally), keyboard shortcuts (J/K, Enter, A, R, /), and a
  data-freshness strip. Files:
  `src/components/screens/dashboard/home-alpha-insights.tsx`,
  `home-{dashboard,alpha-cards,primitives}.tsx`,
  `src/lib/dashboard/{home-model,use-home-data,home-prefs}.ts`, tests
  `home-model.test.ts`. no doc change — UI/data additions only.
- **style(dashboard): remove Getting started and tighten the footer.** The
  Dashboard no longer shows the onboarding checklist (and its prefs are no
  longer stored), Portfolio value now leads the feed at full width, and the
  footer spacing is reduced. no doc change — layout-only.
- **style(dashboard): the feed fills the full content width.** Removed the
  1120px max-width cap on `home-dashboard.tsx` so the AlphaGen-style feed uses
  the whole main panel. no doc change — layout-only.
- **feat(ui): the Dashboard becomes an international-first, AlphaGen-style decision feed.**
  The `home` tab is now a borderless single-column feed rather than a widget
  grid: greeting + display name + Investor/Trader/Both lens + search + market
  selector, getting-started checklist, portfolio value vs S&P 500, a personal
  feed over JDDS news/alerts/published results, four-state holdings health,
  this-week events (company results + macro), global market pulse, confirmed
  results season, Eclipse-momentum leaders you don’t hold, research/theses on
  holdings, sector exposure, and a track record drawn from the journal and
  closed theses. No sidebar, tab, or other-screen changes. Data stays real:
  no AlphaGen scores, invented report windows, or fabricated track record;
  unavailable inputs are labelled. Files:
  `src/components/screens/dashboard/home-{dashboard,alpha-cards,primitives}.tsx`,
  `src/lib/dashboard/{home-model,use-home-data,home-prefs}.ts(x)`, and
  `src/app/api/harness/charts/route.test.ts` (typed the fetch mock so the lint
  gate passes). docs updated: docs/CHANGELOG.md (no other doc change — the
  Dashboard data path is already documented in docs/ARCHITECTURE.md).
- **chore(harness): regenerate the committed capability statement.** The full
  Python suite's `test_the_committed_statement_matches_a_fresh_generation`
  caught the generated `docs/harness/capability-statement.md` drifting from
  `render_statement()` after the in-flight capability changes. Regenerated it
  from the module; the statement is derived data and the test now passes. Files:
  `docs/harness/capability-statement.md`. no other doc change - generated
  artifact.

- **feat(evaluation): read-only corpus and rotation operator routes.** Added
  `routers/evolution_corpus.py` (mounted in `main.py`):
  `GET /evolution/corpus` returns the compact committed manifest, its
  verification and the authoring audit; `GET /evolution/corpus/rotation`
  returns a deterministic rotation PREVIEW. Neither writes a dataset - rotation
  apply stays the deliberate `npm run rsl:rotate -- --apply` CLI action. Files:
  `python/harness/routers/evolution_corpus.py`, `python/harness/main.py`,
  `python/tests/test_evolution_corpus_routes.py`, `package.json`. Docs updated:
  `docs/harness/agent-evaluation.md`.

- **feat(evaluation): a deterministic, operator-applied held_out rotation.**
  A held_out task a candidate has seen is no longer a clean canary. Added
  `evaluation/rotation.py` and `npm run rsl:rotate`: the plan is seeded by the
  quarter label (reproducible), moves N optimization tasks to `held_out` and
  returns the current `held_out` tasks to `optimization`, never touches
  validation, and skips datasets marked `metadata.rotationExempt` (the frozen
  team benchmark). The CLI is a dry run unless `--apply` is given; an apply
  writes the split, bumps each task version, records `metadata.rotation`, and
  refreshes the manifest. Re-applying the same quarter is a no-op. Files:
  `python/harness/evaluation/rotation.py`,
  `python/harness/evaluation/datasets/team_v1.json` (`rotationExempt`),
  `python/tests/test_evaluation_rotation.py`, `scripts/rsl-rotate.js`,
  `package.json`. Docs updated: `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/harness/decisions.md`
  (ADR-H325).

- **feat(evaluation): finance tranche 6 - the corpus reaches 250 tasks.** Added
  `datasets/finance_v6.json`: 50 deterministic fixtures (three validation and
  one optimization per metric, plus two extra validation fixtures), each with
  `metadata.oracle` and `metadata.contamination` and graded by the independent
  `financial` recomputation. The corpus reaches the 250-task target (validation
  184, optimization 64, held_out 2), oracle coverage 0.648 (162/250), and the
  evaluation gate reports `finance: 182/182 measured, 100%` at
  `task_success=1.0`. The committed manifest is refreshed. Files:
  `python/harness/evaluation/datasets/finance_v6.json`,
  `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/test_rsl_provenance.py`. Docs updated:
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`.

- **feat(evaluation): finance tranche 5 - the corpus reaches 200 tasks.** Added
  `datasets/finance_v5.json`: 60 deterministic fixtures across the same twelve
  metrics (three validation and two optimization per metric), each with
  `metadata.oracle` and `metadata.contamination` and graded by the independent
  `financial` recomputation. The corpus grows 140 → 200 (validation 146,
  optimization 52), oracle coverage 0.371 → 0.560, and the evaluation gate
  reports `finance: 132/132 measured, 100%` at `task_success=1.0`. The committed
  manifest is refreshed. Files:
  `python/harness/evaluation/datasets/finance_v5.json`,
  `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/test_rsl_provenance.py`. Docs updated:
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`.

- **feat(rsl): supervised autonomy can apply one measured L1 surface state.**
  The P6 policy could decide "allowed" but nothing acted on it. Added
  `RSLLoop.auto_apply_surface(state_id)`: it accepts only a `candidate` state
  whose `EvolutionCandidate` is a surface with a valid `surfaceConfig`, derives
  per-task rates from the recorded baseline and candidate `EvaluationRun`s, runs
  the paired bootstrap and the regression gates, classifies the risk, and calls
  the existing `decide(...)` policy (kill switch, L1, lift floor, canary/replay,
  daily budget). On success it uses the existing
  `HarnessStateStore.activate_surface`, so the returned `HarnessActivation` row
  is the rollback handle; missing paired evidence is a refusal. The activation
  counter is persisted (`rsl.autonomy.activations`) so a restart cannot reset
  the budget. `POST /evolution/states/{state_id}/autonomy-apply` is the
  operator-triggered seam. Files:
  `python/harness/self_improvement/{autonomy,loop}.py`,
  `python/harness/routers/evolution_autonomy.py`,
  `python/tests/test_autonomy_apply.py`, `package.json`. Docs updated:
  `docs/self-improvement/rsl-v4-plan.md`, `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H324).

- **feat(evaluation): finance tranche 4 - 36 generated oracle-tagged tasks.**
  Added `datasets/finance_v4.json`: 36 deterministic fixtures across twelve
  metrics (two validation and one optimization per metric), each with
  `metadata.oracle` and `metadata.contamination` and graded only by the
  independent `financial` recomputation. The corpus grows 104 → 140 tasks
  (validation 110, optimization 28), oracle coverage 0.154 → 0.371, and the
  evaluation gate reports `finance: 72/72 measured, 100%`. The committed
  manifest is refreshed. Files:
  `python/harness/evaluation/datasets/finance_v4.json`,
  `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/test_rsl_provenance.py`. Docs updated:
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`.

- **feat(evaluation): optimization-split finance tranche 3.** Added
  `datasets/finance_v3.json` (6 deterministic finance tasks: EPS, P/E, P/S,
  FCF, CAGR, gross margin) reserved for the **optimization** split, so the RSL
  search has measured material it may train on while validation stays the
  acceptance set. Every task carries `metadata.oracle` and
  `metadata.contamination`; the corpus grows 98 → 104 (optimization 10 → 16,
  oracle coverage 0.154) and `finance` is 36/36 measured in the gate. The
  committed manifest is refreshed. Files:
  `python/harness/evaluation/datasets/finance_v3.json`,
  `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/test_rsl_provenance.py`. Docs updated:
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`.

- **chore(rsl): keep the autonomy routes out of the ratcheted evolution router,
  and re-pin the shared graph.** The P6 routes pushed
  `routers/evolution.py` past its size ratchet, so they now live in
  `routers/evolution_autonomy.py` and are included by the existing evolution
  router (the same pattern as `evolution_drift`/`evolution_models`/
  `evolution_report`). `graph.py` re-pinned 2305→2316 for the in-flight
  response-style JIT index wiring; the tool loop is untouched and the
  subsystem-wiring block remains the split candidate. Files:
  `python/harness/routers/{evolution,evolution_autonomy}.py`,
  `python/tests/test_size_budget.py`. Docs updated:
  `docs/self-improvement/rsl-v4-plan.md` (P6 route module).

- **feat(evaluation): finance tranche 2, with an independent oracle on every
  task.** Added `datasets/finance_v2.json` (10 deterministic tasks: gross
  margin, percentage change, CAGR, P/E, P/S, FCF, portfolio weight,
  reward-to-risk, operating margin, EV/EBITDA). Every task declares
  `metadata.oracle` (the recomputation) and `metadata.contamination`
  (source/authored date), so the corpus grows from 88 to 98 tasks and oracle
  coverage from 0.0 to 0.102. All ten are graded by the independent
  `financial` grader plus `exact`; the evaluation gate is 98 tasks with finance
  30/30 measured. The committed manifest is refreshed. Files:
  `python/harness/evaluation/datasets/finance_v2.json`,
  `python/harness/evaluation/baselines/corpus_manifest.json`. Docs updated:
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`.

- **feat(rsl): autonomy is risk-classed, evidence-gated and killable.** Added
  `self_improvement/autonomy.py`: risk classes `L0` (code, tool widening,
  guardrail removal, model identity — never automatic), `L2`
  (capability-widening — human only) and `L1` (bounded surface: prompt wording,
  tool guidance, narrowed context policy, delegated-child prompt, added
  guardrails). The pure `decide(...)` policy requires supervised/bounded level,
  no kill switch, L1 risk, a paired `deltaCiLow` above the floor, no critical
  regression, a clean canary/replay, a matching predicted direction and a daily
  budget; it names every refusal reason. `AutonomyKillSwitch` persists under
  `rsl.autonomy.kill` on the ONE agent-memory DB; `/evolution/rsl/autonomy/
  pause|resume` stop/allow decisions without a restart, and
  `/evolution/rsl/autonomy/decide` previews a decision without activating
  anything. `GET /evolution/rsl` now reports `autonomyStatus`. New opt-in,
  clamped flags `HARNESS_RSL_AUTONOMY` (off), `HARNESS_RSL_AUTO_MIN_LIFT`
  (0.02), `HARNESS_RSL_AUTO_MAX_PER_DAY` (1), `HARNESS_RSL_AUTO_RISK` (low),
  accepted by hot config. Activation remains the existing single-use surface
  path; auto-applying an L1 winner is a supervised follow-up after a dry run.
  Files: `python/harness/self_improvement/{autonomy,config,runtime_settings,
  loop,__init__}.py`, `python/harness/routers/evolution.py`,
  `python/tests/test_autonomy.py`, `package.json`, `.env.example`. Docs
  updated: `docs/self-improvement/rsl-v4-plan.md`,
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H322).

- **feat(evaluation): only the live tier may be pinned, and the key includes the
  prompt and corpus.** The scripted tier cannot see a prompt change, so pinning
  it as a model baseline would manufacture evidence. Added
  `evaluation/live_baseline.py`: a baseline is keyed by provider + model + base
  URL + temperature + prompt hash + corpus checksum; `build_live_baseline`
  refuses the scripted tier and an empty provider/model, and stores the Wilson
  CI, per-category rates, task rates, cost/latency and provenance without ever
  storing a key. `write_live_baseline`/`read_live_baselines`/
  `find_live_baseline` maintain a committed registry (created on first write);
  `compare_live_baseline` runs the existing regression gates plus a paired CI;
  `publish_report` writes Markdown that names the tier, identity, prompt hash,
  corpus checksum and verdict, with `NOT COMPARED` when unpinned (never PASS).
  `nightly.py` gained `--live-baseline`/`--write-live-baseline`/`--publish`
  (all require `--live`); the one recorded live run remains an operator action.
  Files: `python/harness/evaluation/{live_baseline,nightly}.py`,
  `python/tests/test_live_baseline.py`, `scripts/rsl-nightly.js`.
  Docs updated: `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/harness/decisions.md`
  (ADR-H321).

- **feat(evaluation): a lift must clear its paired noise floor.** A Wilson
  interval describes one arm; the acceptance decision was comparing point
  estimates from samples too small to distinguish from noise. Added
  `evaluation/significance.py`: `paired_bootstrap` (resamples TASKS, percentile
  CI + one-sided p-value), exact `mcnemar` for paired pass/fail, a
  `required_trials` planning estimate, and `paired_rates` (a metrics dict or a
  `SuiteResult`). `ablation.compare_arms` now reports `deltaCi`/`pValue`/
  `pairedTasks` and renders the CI. `utility.acceptance` gained the opt-in
  `require_significance`: when `HARNESS_RSL_SIGNIFICANCE=on`, at least
  `HARNESS_RSL_SIGNIFICANCE_MIN_TASKS` paired tasks are required and the CI low
  bound must be above zero, so a two-task "win" is refused. It is an acceptance
  rule, never a sampling signal. Files:
  `python/harness/evaluation/{significance,ablation}.py`,
  `python/harness/self_improvement/{utility,hillclimb,config,loop}.py`,
  `python/tests/{test_significance.py,test_rsl_significance.py}`, `package.json`,
  `.env.example`. Docs updated: `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/harness/decisions.md`
  (ADR-H320).

- **feat(evaluation): a committed corpus manifest and one split per purpose.**
  The corpus count had drifted between documents (76 vs 88) with nothing
  checking a dataset change against a recorded summary. Added
  `evaluation/corpus.py` (build/verify/audit; every checksum is recomputed from
  the task files, never trusted) and `baselines/corpus_manifest.json` (88 tasks,
  8 datasets, split counts, oracle coverage, canary count). The new
  `corpus-manifest` gate in `scripts/test-evals.js` fails on drift; refresh it
  deliberately with `npm run rsl:manifest -- --build`. Added
  `evaluation/contamination.py`: each purpose reads exactly one split
  (`optimization`/`validation`/`canary`/`release`), `access_guard` refuses a
  cross-split read, and a decoy canary (`metadata.canary`) makes a PASS a
  `CANARY_HACK` instead of a win. `--audit --strict` reports/enforces the
  oracle + contamination metadata rule for new tasks; the legacy corpus reports
  `0.0` oracle coverage honestly. Files:
  `python/harness/evaluation/{corpus,contamination}.py`,
  `python/harness/evaluation/baselines/corpus_manifest.json`,
  `python/tests/{test_evaluation_corpus.py,test_evaluation_contamination.py}`,
  `scripts/{rsl-manifest.js,test-evals.js}`, `package.json`. Docs updated:
  `docs/harness/agent-evaluation.md`,
  `docs/self-improvement/rsl-v4-plan.md`, `docs/harness/decisions.md`
  (ADR-H319).

- **feat(rsl): type every proposal, veto near-duplicates, and let islands migrate
  evidence.** A proposal now names the surface it mutates (prompt, tool guidance,
  tool subset, ceilings, context policy, guardrail, subagent prompt, model
  identity, skill draft, code patch, composition) via the new
  `self_improvement/operators.py`; `CandidateProposal.operator` carries it as
  evidence, never authority. `propose_many` gained `novelty_min` and
  `exclude_signatures`: a Jaccard-near-duplicate of an already-tried proposal is
  dropped, and if nothing new remains it raises `PROPOSAL_ALL_DUPLICATES`
  instead of returning a smaller comparison silently. The archive now treats a
  non-global scope as an island: every `HARNESS_RSL_ISLAND_MIGRATION` measured
  states, `StateArchive.migrate_best` copies the island's best measured state
  into `global` as an inert `stepping_stone` (same digest, new row), and
  `parent_for(island=...)` can restrict sampling. Migration copies evidence, not
  a decision; acceptance is untouched and the per-scope lease still allows two
  scopes to climb concurrently. New opt-in, clamped flags
  `HARNESS_RSL_NOVELTY_MIN` (0), `HARNESS_RSL_ISLANDS` (off),
  `HARNESS_RSL_ISLAND_MIGRATION` (5), accepted by hot config. Files:
  `python/harness/self_improvement/{operators,proposer,archive,config,recursion,loop,__init__}.py`,
  `python/tests/{test_rsl_operators.py,test_rsl_islands.py}`, `package.json`,
  `.env.example`. Docs updated: `docs/self-improvement/rsl-v4-plan.md`,
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H318).

- **feat(rsl): rank exploration parents by what their descendants achieved.**
  The archive ranked a state by its own score; HGM showed that is a poor proxy
  for self-improvement potential. Added `self_improvement/cmp.py` (descendant
  lift: depth-discounted mean of `utility(descendant) - utility(state)` over
  measured descendants, bounded horizon, explicit `coldStart` when there is too
  little evidence). `StateArchive` persists `cmpScore` on a state and its
  ancestors when a measured state is retained, and attaches a read-path estimate
  for older rows; `sampler.scores` blends it (weight 0.30). It remains a sampling
  signal only — `utility.acceptance` is untouched, so a high-lift state cannot
  promote itself or its children. New opt-in, clamped flags `HARNESS_RSL_CMP`
  (off) and `HARNESS_RSL_CMP_HORIZON` (3, 1–6), accepted by hot config. Files:
  `python/harness/self_improvement/{cmp,archive,config,loop,__init__}.py`,
  `python/tests/test_rsl_cmp.py`, `package.json`, `.env.example`. Docs updated:
  `docs/self-improvement/rsl-v4-plan.md`, `docs/harness/architecture.md`,
  `docs/harness/decisions.md` (ADR-H317).

- **feat(rsl): the climb may explore from a measured stepping stone, and only the
  champion can be replaced.** Greedy ascent proposed only from the incumbent and
  discarded every measured loser; the DGM ablation reports that exact shape as
  the weakest (50.0% with an archive vs 39.7% greedy vs 23.0% no archive). Added
  `self_improvement/sampler.py` (seeded `uniform`/`weighted`/`uct` parent
  sampling) and `self_improvement/archive.py` (`StateArchive` retains measured
  states as inert `stepping_stone` rows, refuses unmeasured ones, dedupes by
  snapshot digest, and evicts only stepping stones). `hillclimb.run_hillclimb`
  now takes an optional `archive=`/`rng=`, records `proposalParentId`, and
  retains rejected measured neighbors; acceptance is unchanged and still compares
  against the champion. `HarnessState` gained additive `visitCount`/`novelty`/
  `island`/`cmpScore`/`lastSampledAt` columns plus the `stepping_stone` status
  (never promotable/activatable). New opt-in, clamped env flags
  `HARNESS_RSL_ARCHIVE` (off), `HARNESS_RSL_ARCHIVE_MAX` (200),
  `HARNESS_RSL_ARCHIVE_SAMPLE` (weighted), accepted by hot config. Archive-off
  behavior is byte-identical. Files: `python/harness/self_improvement/{archive,sampler,state,hillclimb,config,loop,__init__}.py`,
  `python/tests/{test_rsl_archive.py,test_rsl_loop.py}`, `package.json`,
  `.env.example`. Docs updated: `docs/self-improvement/rsl-v4-plan.md` (new),
  `docs/harness/architecture.md`, `docs/harness/decisions.md` (ADR-H316).

- **fix(ui): the Dashboard is monochrome white and its portfolio panels wait honestly.**
  Replaced the initial gold/amber chrome with a white/grey treatment (green/red
  reserved for up/down and trend semantics), fixed the sidebar migration so an
  existing nav gets Dashboard directly after ChatBot, and removed the misleading
  zero-value/unavailable flash while quotes and price history load:
  `useAggregatePortfolio` now exposes `loading`, `usePriceHistories` marks a new
  symbol set loading immediately, and the Dashboard cards render explicit
  loading states instead of `$0.00` / "history missing". Files:
  `src/components/screens/dashboard/home-{dashboard,cards,primitives}.tsx`,
  `src/lib/dashboard/{use-home-data,portfolio-store}.ts`,
  `src/hooks/use-price-histories.ts`, `src/lib/sidebar/config.ts`,
  `src/lib/sdk/app-shell-types.ts`. no doc change — UI/data-loading polish; the
  Dashboard architecture and data path are already documented.
- **fix(tests): type the chart-route fetch mock so the lint gate passes.** The
  mock was declared `Promise<any>`; `npx eslint .` is a step of the release gate
  (`check:all`) and of the CI workflow, so one `no-explicit-any` error kept the
  whole gate red. It is now typed `Promise<Response>`. Files:
  `src/app/api/harness/charts/route.test.ts`. Docs updated: none - test-only.
- **fix(chat): a display formula after a prose line is typeset, not printed
  between dollar signs.** A real run wrote `**Return definition**\n$$r_t = ...$$`
  with no blank line; `$$` was not a block start, so the paragraph swallowed the
  formula line and the inline parser saw `$` + math + `$`, leaving literal
  dollar signs around a cramped inline formula. Display math (`$$...$$`, and
  `\[...\]`) now opens a block regardless of the preceding line, a mid-line
  `$$...$$` is display mathematics, and `\(...\)` / `\[...\]` are recognised
  (models emit them even when told to use dollars). Inline `$...$` also trims
  surrounding spaces (`$ x $` typesets) and accepts compact digit/letter terms
  (`$2x$`); escaped `\$100` stays money. Files:
  `src/lib/chat/markdown.ts`, `src/components/chat/markdown.tsx`; tests
  `src/lib/chat/math.test.ts`, `src/components/chat/math-render.test.tsx`.
  docs updated: `docs/chat-ui-audit.md`.

- **fix(harness): repair the broken merge state, regenerate the two published
  artifacts, and hold `graph.py` under its ratchet.** The tree about to land was
  internally inconsistent: `boot.py` imported
  `harness.self_improvement.session_watch`, but that module only existed on
  main's newer commit, so four a2a tests and two recovery tests failed with
  `ModuleNotFoundError`. Merging main fixed all six. Three conflicts resolved:
  the RSL lab ADRs claimed H290/H291/H292, which were already the sandbox ADRs,
  so they became **H306/H307/H308** with a provenance note on each (the decision
  text is untouched; the gate now reports 303 entries, H1..H308, contiguous); the
  `package.json` kept both sides; and their `Promise<Response>` on the chart-route
  mock does not compile, because the mock returns a plain object - `unknown` is
  the form that passes both `tsc` and `eslint`. The merge also made both generated
  artifacts stale, so `docs/harness/tool-registry.json` (956 tools, digest
  `cc523b84547c456c`) and `docs/harness/benchmarks.md` were regenerated, and
  `graph.py` (2,314 lines, past its pinned 2,309) was compacted to 2,308 rather
  than raising the ceiling.
  docs updated: docs/harness/decisions.md.

- **release(harness): v0.2.0 is tagged, and `main` is the released tree.** Round 4
  V1 is closed. `origin/main` fast-forwarded to `b3e08d1c` (no force), the branch
  was pushed, and an annotated `v0.2.0` (`8068674e`) was pushed and verified with
  `git ls-remote`. The release was only cut after the full `check:all` passed on
  the exact tree that was tagged - the gate had failed four times first, each time
  on something real (a divergent `main`, stale generated artifacts, a module over
  its ratchet, and CRLF this tool wrote into an LF file). The plan's ADR
  reservations were shifted to H309-H314, because the merge resolution consumed
  H306-H308. The other stream's local `main` is behind and must `git pull`.
  docs updated: docs/harness/roadmap/round-4-gap-closure.md,
  docs/releases/v0.2.0.md.

- **refactor(git): nine diff ops, one argv builder.** Round 4 / V2, first slice.
  The nine `diff_*` operations differed only by a flag prefix and whether the
  revision pair was `(base)` or `(from, to)`, so they are now one `_diff_argv`
  plus a nine-row table. Every name, argument list and argv string is unchanged
  (verified by building all nine against sample args and diffing the output), so
  no caller and no shim is affected. 319 git tests pass; the total falls from
  377,242 to 377,238 lines. The saving is small on purpose: the audit found the
  catalog was already dense, so V2 cannot deliver its promised reduction this
  way and that is recorded in the plan rather than papered over.
  no doc change — internal refactor, no contract or architecture change.

- **docs(adr): the 15 legacy entries now carry the full shape.** Round 4 / V3a.
  The gate had been exempting 15 decisions below H295. Every one was closed by
  re-labelling prose that was already written, never by inventing a rationale:
  `Impact` became `Consequences` (H45-H50, six), `Context` became `Why`
  (H147-H151, five - each Context paragraph already stated the motivation),
  `Consequences (non-goals)` became `Consequences` (H96), `Why this supersedes
  ADR-H75's choice (b)` became `Why` (H76), and H7's marker was welded to its
  heading by a missing line break. One heading - H70's `Consequences` - had no
  prose to relabel, so it restates what that entry's own Decision section already
  says about subscriptions, conditional registration and inert prompt text.
  The gate now reports **zero** legacy exemptions: 303 entries, H1..H308, all
  shaped. docs updated: docs/harness/decisions.md.

- **test(graph): the cancellation test waits for the retry instead of guessing.**
  Round 4 / V3a. `test_cancellation_during_retry_still_cancels` slept a fixed
  0.3 s and then cancelled, assuming the first attempt had already overflowed and
  the retry had begun. On a loaded machine that race went the other way, so the
  cancel landed during the *first* attempt and the assertion described a state
  the run had not reached. The model now sets an `asyncio.Event` on its second
  call and the test awaits it (10 s ceiling) before cancelling - the same
  assertion, no race, and a failure to reach the retry now reports as a timeout
  rather than a wrong status. 16/16 in the file, twice.
  no doc change — test-only fix, no contract or behaviour change.

- **fix(bridge): the structured-read budget is now measured, not assumed.** Round
  4 / V5. The bridge gave structured reads 8 s because "the smallest market-tool
  budget is 10 s" — true, and still too tight. Timed against the live front door:
  `market_data` 3.91 s, `live_quote` 3.57 s, `market_snapshot` 0.04 s cached, and
  **`financial_statements` 8.56 s cold** — permanently over the line, so the live
  lane could not measure a single finance dimension. Bridge is now 15 s and the
  finance tools' `timeout_ms` 25 s, preserving the ordering the contract depends
  on (15 s < 25 s), which the existing timeout test still enforces. Live-suite
  bridge failures fell 15 -> 6 -> 3 across the runs. It did not reach zero: the
  three remaining calls include `market_snapshot`, measured at 42 ms, so they are
  connection faults under suite load and not budget faults - recorded as the next
  open item rather than claimed fixed. ADR-H309 carries the measurement and the
  reasoning; the plan's V1-V6 ADR reservations shift to H310-H315.
  docs updated: docs/harness/decisions.md,
  docs/harness/roadmap/round-4-gap-closure.md.

- **fix(bridge): a bridge failure now names its exception, and a dropped peer is
  retried.** The three remaining live-suite failures logged as
  `data bridge failed (market_snapshot):` with nothing after the colon, which made
  them indistinguishable from a timeout. The logger now always prefixes the
  exception type and the returned error carries the same text. That immediately
  identified them: **`ConnectError: All connection attempts failed`** - the front
  door was not listening, not a budget problem. `RemoteProtocolError` (a peer that
  accepts then drops the request, and whose `str()` is empty) is now retried once
  alongside `ConnectError`; a timeout still never is. The residual failures are
  environmental: the local server is not surviving between runs in this
  environment, so they are recorded as an operations issue rather than a harness
  defect.
  no doc change — diagnosability and retry class only, no contract change.

- **fix(eval): the published benchmarks show the live run that exists.** The
  generator accepted `--live-run <id>` and then never loaded the suite, so it
  published *"no live run has been recorded"* while six completed live runs sat in
  the store. `_load_live_suite` now rebuilds the publishable view from the
  `EvaluationRun` row plus its metrics and recomputes the thresholds with the same
  `check_thresholds` the live gate uses. `write_benchmarks()` selects the most
  recent completed live run itself, so the canonical regeneration and the
  committed file agree - which the `generated not hand-edited` test enforces.
  The live tier now publishes `deepseek-v4.1-flash:cloud` with gate **FAIL** and
  its real dimensions (`task_success 0.0`, `tool_accuracy 0.2985`,
  `planning_quality 0.9872`, `safety_score 0.6667`, `reliability 1.0`). A failing
  measurement is published, not hidden - that is the point of recording it.
  docs updated: docs/harness/benchmarks.md.

- **fix(eval): pin the published live run, because "latest" was not reproducible.**
  Auto-selecting the newest completed live run made the published file depend on
  mutable store state: running the test suite records more live runs, so
  regeneration and the committed file disagreed by test ORDER and the
  generated-not-hand-edited gate failed inside the full suite while passing alone.
  The run is now a named constant, `PUBLISHED_LIVE_RUN`, reviewed with the
  artifact. A published number that changes because a test ran is not
  reproducible. Benchmarks regenerated after merging main (their new tasks moved
  the offline counts).
  no doc change — the generated artifact is updated in the same commit.

- **revert(eval): do not embed a live run that exists on one machine.** Publishing
  `evalrun-1792772393137` in the committed artifact made it unreproducible: the
  run lives in this machine's `agent-memory.db`, while the test suite generates
  against an isolated store, so the generated file and the committed one disagreed
  inside the full suite while agreeing alone. The loader (`_load_live_suite`) stays
  - it is correct and usable with `--live-run <id>` locally. `PUBLISHED_LIVE_RUN`
  is empty and says why: publishing a live run needs a checked-in snapshot of that
  run, which is the recorded next step. The file reports honestly that no
  reproducible live measurement is committed instead of a number nobody else can
  regenerate. docs updated: docs/harness/benchmarks.md.

- **chore(ownership): CODEOWNERS names a real owner.** Round 4 / V3. The twelve
  harness paths were assigned to `@harness-owner`/`@code-owner`/`@docs-owner` -
  names that resolve to nobody. They are now `@desimarijuana`, so every path has
  an owner who can be requested for review. The file states plainly what this does
  NOT do: one person reviewing their own work is not a second pair of eyes, so the
  external-review criterion stays open.
  no doc change — ownership metadata, recorded here.

- **chore(ownership): CODEOWNERS uses a role, not a personal account.** The paths
  were assigned to `@desimarijuana`, which bakes a maintainer's personal GitHub
  account into a public source tree. They now name `@BlackEclipse/maintainers` - a
  role that resolves once the project has an org or team, and until then shows as
  unresolved, which is honest. Ownership is still assigned; no individual identity
  is committed.
  no doc change — ownership metadata, recorded here.

- **fix(eval): a dead environment is a REASON, and two samples are not a rate.**
  Round 4 / the RSL's empirical foundation. Two changes, both about not measuring
  the machine and calling it the agent.
  1. `live_gate.preflight_bridge()` spends one cheap capability
  (`market_snapshot`) before the suite. A front door that is not answering now
  produces one sentence and exit 0 instead of twelve failed trials and ~179
  `ConnectError` lines. Verified against a dead port: `NOT MEASURED - the data
  bridge at ... answered UNAVAILABLE (ConnectError...)`.
  2. `runner.MIN_SAMPLES_FOR_RATE = 5`: a dimension measured on fewer trials is
  persisted as `None` (published UNKNOWN) instead of a number. `safety_score
  0.6667` from n=2 was one coin flip presented as a finding; `None` never fails a
  gate, so the hole stays visible without pretending.
  Tests: `test_live_preflight.py` (dead bridge, healthy bridge, the sample floor).
  docs updated: none needed — behaviour is documented in the module docstrings.

- **chore(size): the ceiling moves 27 lines, on purpose, for the preflight.** The
  preflight is real code with a real test, so it cannot fit inside a budget that
  was pinned to the last line. Raising a ceiling is the thing this repo normally
  refuses, so it is recorded rather than slipped in: `totalLines`
  381,881 -> 381,908 and `evaluation` 11,456 -> 11,483, exactly the 27 lines the
  preflight and its test add. The alternative - deleting the tests - would have
  bought a lower number at the cost of the check that the number is honest.
  no doc change — the budget file is the record.

- **revert(eval): drop the minimum-sample rule; it collided with RSL baselines.**
  `MIN_SAMPLES_FOR_RATE = 5` fixed `safety_score 0.6667` from n=2 by publishing
  `None` instead - but a surface candidate's baseline is verified through the same
  metrics, so any baseline with fewer than five measurable trials became
  `SURFACE_BASELINE_UNMEASURED` and `test_surface_candidate_reuses_a_matching_
  recorded_baseline` failed. The rule is right and the collision is real: a
  baseline and a published rate have different sample requirements, and deciding
  that needs design, not a constant. Reverted rather than special-cased. The
  preflight stays (it is independent and verified). Budget re-pinned to the
  actual tree: 381,900 total, 11,475 evaluation.
  docs updated: none needed.

- **fix(eval): an outage is not an agent failure.** Round 4 / the RSL's empirical
  foundation, root cause. `score_trial` turned every non-completed trajectory into
  a failed task and a `reliability 0.0` sample - including trials that failed
  because the data bridge was down. The signal is the explicit `UNAVAILABLE`
  error code on the trajectory outcome: a trial carrying it is now `unmeasured`,
  excluded from `task_success` and from `reliability`, so `task_success 0.0` stops
  counting an outage as the agent's inability. The taxonomy's `infrastructure`
  label was tried first and rejected - it is the catch-all for ANY unlabeled
  failure, so honouring it would have excused real agent failures too (it broke
  `test_the_lab_never_invents_a_winner_on_the_scripted_tier`).
  Tests: `test_an_outage_is_not_an_agent_failure`. Budget re-pinned to the tree.
  docs updated: none needed.

## 2026-10-21
- **feat(quant): the backfill says out loud that no subscription is needed.**
  The durable cache only holds what has been fetched, and the backfill is how
  you fill it - but the honest question is whether bundling a universe costs
  money. It does not: the keyless providers (Yahoo Finance, Stooq, Binance,
  the ECB reference rates, Treasury/FRED) are enough, and the backfill now says
  so. It names the provider that served each symbol, whether that provider
  needs a key, and which providers are usable right now with NO credential; a
  keyed provider that is not configured is reported as needing a key, never as
  free. The difference between hosting and owning the data: the hosted
  platform rents you a decade of ticks, this one KEEPS what it fetched, on
  your machine, and serves it from there forever. Files:
  python/harness/market/tools.py, python/tests/test_gallery_venues.py. docs
  updated: docs/quant-engine.md.

- **test(harness): a production smoke test - the real app, the real routes.**
  The other tests check units. This one starts the actual FastAPI application
  (the same `harness.main:app` the runtime serves) and asks it the questions
  a user's first minute would ask: is it alive, what does it hold, what can it
  run, and does it refuse HONESTLY when something is missing - a request for a
  report that does not exist must be a named refusal, not a fake success, and a
  Pine run must say whether the engine is installed. It is deliberately
  read-only: a smoke test that mutates production state is not a smoke test.
  Files: python/tests/test_production_smoke.py. no doc change - a test.

- **feat(quant): bundle it, see the venues, and publish it.** Three closers.
  **(1) The backfill.** The durable cache only holds what has been fetched, so
  `backfill_history` (tool and POST /market/history/backfill) fetches a window
  ONCE and keeps it - that is how a local-first runtime holds a universe the way
  a hosted platform "bundles" one: the user decides what to keep, and every
  later run is served from the machine. **(2) The venue seam.**
  `quant/venues.py` makes the multi-DSL promise explicit instead of implied: a
  venue is a language a strategy can be written in, and each declares whether
  it can run, what it needs and how to reach its engine. Pine runs (the isolated
  engine, on Eclipse's bars); NinjaScript, PowerLanguage and EasyLanguage are
  NAMED gaps that say exactly what is missing - "no NinjaScript engine is
  installed; the venue needs a C# runtime" - because a venue that never claims
  to work is better than a promise the runtime cannot keep. The seam exists so
  that adding a venue is a registration, not a refactor. **(3) The gallery.**
  `python/harness/gallery/` is the community layer, done honestly for a
  local-first, single-operator runtime: a catalogue of FROZEN, GRADED
  strategies. Publishing freezes a strategy and the Edge Report that graded it
  into an immutable record; cloning copies the spec into the quant store as a
  NEW strategy, so the published record and the live strategy never share an
  identity; favouriting counts interest locally. Surfaces: the tools
  `backfill_history`, `list_strategy_venues`, `publish_strategy`,
  `list_gallery`, `favourite_published_strategy`, `clone_published_strategy`;
  the routes /market/history/backfill, /quant/venues and /gallery*; and the
  Strategy Gallery widget on the Command Center. Files:
  python/harness/gallery/ (new), python/harness/routers/gallery.py (new),
  python/harness/quant/venues.py (new), python/harness/market/tools.py,
  python/harness/routers/market.py, python/harness/boot.py,
  python/harness/agents.py, src/lib/dashboard/gallery-widget.tsx (new),
  src/lib/dashboard/registry.tsx, src/app/api/harness/gallery/ (new).
  Tests: python/tests/test_gallery_venues.py (13),
  python/tests/test_market_history_cache.py (11). docs updated:
  docs/quant-engine.md.

- **feat(ui): a global-first Dashboard tab now sits above Command Center.**
  The new `home` tab (`/?tab=home`, F2 by default) folds market weather,
  sector/market leadership, portfolio trend health + trend mix, the review
  queue, portfolio watch, watchlist radar, sector concentration, screener CTAs
  and the alerts archive into one daily decision surface. It reads real JDDS
  data only (`/api/regime`, `/api/heatmap`, `/api/global-overview`,
  `/api/price-history`, `/api/alerts`) plus the existing seeded fund book
  (labelled **Demo book**). When the explainable regime read is stale or
  unavailable, the hero falls back to a labelled breadth-derived weather read;
  the regime card stays honestly **Unavailable**. Files:
  `src/components/screens/dashboard/home-{dashboard,cards,primitives}.tsx`,
  `src/lib/dashboard/{use-home-data,home-model}.ts(x)`, plus the `home`
  AppTab/deep-link/sidebar/search/i18n/mobile-nav wiring and 23 model tests.
  docs updated: docs/OVERVIEW.md, docs/NAVIGATION.md, docs/ARCHITECTURE.md.

- **feat(quant): the local data vault, made visible.** A cache nobody can see
  is a cache nobody trusts. The **Local History** widget on the Command Center
  now shows what the machine actually holds - which instruments, how many bars,
  how fresh, from which provider - with the coverage of one instrument on
  demand, and the agent can ask the same question through the new
  `history_catalog` tool. The runtime serves it from the durable cache
  (`GET /market/history`, `/market/history/{symbol}`,
  `/market/history/{symbol}/bars`), so it works OFFLINE and can never claim a
  bar the runtime does not have. Files: python/harness/routers/market.py,
  python/harness/market/tools.py, python/harness/market/series_store.py,
  python/harness/market/bootstrap.py, src/lib/dashboard/history-widget.tsx
  (new), src/lib/dashboard/registry.tsx, src/app/api/market/history/route.ts
  (new), src/app/api/market/history/[symbol]/route.ts (new). Tests:
  python/tests/test_market_history_cache.py (11). docs updated:
  docs/quant-engine.md.

- **feat(quant): the durable history cache - one copy of the history Eclipse
  has already seen.** The gateway cached history IN PROCESS, so every restart
  re-fetched every bar from the provider. The durable half now lives on the ONE
  agent-memory connection, and a later request for the same window is served
  from it. This is the engineering half of "bundled data": it does not buy a
  vendor's history, it buys ONE copy of the history Eclipse has already paid
  for - on the machine, offline, reproducible - and the SAME bars then feed the
  backtest, the regime classifier, the Monte-Carlo, the Pine engine and the
  trade-log analysis, so all five agree by construction. Two rules keep it
  honest: a cached window is served only when it actually COVERS the request (a
  partial cache is a miss, not a short answer), and a stale tail is refetched -
  with no explicit window the cache is only the whole history if its last bar is
  still fresh, because a cache that never refreshed would silently freeze the
  market. A backtest that pins its window is served from the cache; an
  open-ended request refetches the tail. Files:
  python/harness/market/history_cache.py (new),
  python/harness/market/bootstrap.py, python/harness/quant/datasets.py.
  Tests: python/tests/test_market_history_cache.py (9). docs updated:
  docs/quant-engine.md.

- **feat(sdk): eclipse_data - ECLIPSE's data and research from a notebook.** The
  runtime is the authority; this package is a thin client for it, so a notebook
  and the app see the SAME bars, the SAME verdict and the SAME project. It
  speaks to the local runtime (the operator token when one is configured) and
  exposes: normalized OHLCV with its provenance, the coverage the runtime
  already holds, the projects and their curated digests, the proposals, the
  Edge Report, a prop-firm evaluation of a trade log, and a Pine script with
  and without its grade. It has NO third-party dependency - the standard
  library alone - and it never invents a value: a refusal from the runtime is
  raised with the runtime's own code and message. A test checks every path the
  client calls against the runtime's OWN OpenAPI schema, so the client cannot
  drift away from the surface it talks to. Files: sdk/eclipse_data/ (new:
  __init__.py, pyproject.toml, README.md), python/tests/test_eclipse_sdk.py.
  docs updated: docs/quant-engine.md.

- **feat(harness): the proposer reads the project's own notes.** A note is a
  finding a human wrote down, and it is evidence like any other. If a note
  names a regime that no attached result was ever measured in - "the NQ cross has
  never been traded in up_high" - the proposer raises it and proposes the
  backtest that would answer it. If a result already covers that regime,
  nothing is proposed: a note that has been tested is a note that has been
  answered. That is the proposer's content edge: it is a function not only of
  what the project HOLDS, but of what it SAYS. Files:
  python/harness/projects/propose.py. Tests:
  python/tests/test_project_proposals.py (12). docs updated: docs/projects.md.

- **feat(harness): a project may act on its own - inside a policy the operator
  can see.** The loop that runs a proposal existed, but only when the agent or
  the user asked. A project can now act unattended, and the bound is explicit
  and enforced BY THE RUNTIME rather than by the model's good intentions. The
  policy says whether the project is enabled (OFF for every project until
  someone turns it on), how many runs a day and how many seconds a day it may
  spend, how far apart two runs must be, and which tools it may run - and that
  tool list is filtered to **compute only** (a backtest, a sweep, a rule
  evaluation), so a project can never act on the world by itself, whatever the
  policy asks for. Every tick, each project whose policy allows it runs ONE
  proposal through the same tool path an agent would use, and the outcome goes
  into a ledger - the successful runs and the refusals alike. A project that
  cannot act is a NORMAL outcome, not an error: it is skipped with the reason
  (`daily_run_budget`, `min_interval`, `no_runnable_proposal`) recorded. The
  policy and what is left of its budget are visible in the curated view, so the
  agent can see that a project acts on its own and what it has spent today.
  Surfaces: the tools `project_auto_policy` and `project_auto_run`; the routes
  GET/POST /projects/{id}/auto and POST /projects/auto/run. The loop starts at
  boot and stops at shutdown, and the implementation lives in
  `python/harness/projects/` - `service.py` and `graph.py` are untouched, so
  their size ratchets do not move. Files:
  python/harness/projects/policy.py (new), python/harness/projects/auto.py
  (new), python/harness/projects/curate.py, python/harness/projects/propose.py,
  python/harness/projects/tools.py, python/harness/projects/bootstrap.py,
  python/harness/routers/projects.py, python/harness/boot.py.
  Tests: python/tests/test_project_auto.py (10). docs updated: docs/projects.md.

- **feat(harness): a project runs its own proposal and records the outcome.**
  The proposer named the next experiment; now it is RUN - through the same tool
  the agent would have called, so the policy gate, the allowlist, the sandbox
  and the persistence are the agent's own path, not a second one - and the
  outcome is recorded back into the project, so the next proposal is made
  against a project that knows what just happened. Three rules: a proposal is
  only run when it names a tool and the arguments it needs (a proposal that
  cannot be run is reported, not attempted); a FAILURE is recorded as a
  failure - a refused or failed run is attached as a note that says what went
  wrong, because a project that hides its failures cannot learn; and nothing is
  attached that did not happen - the executor attaches the experiment the run
  really produced, by the id the run really returned. The proposal actions are
  now real, executable tool calls (a strategy that was never run names
  `run_backtest` with its id and instruments; an unsafe tail names
  `run_robustness_analysis` with the cost multipliers). Surfaces: the tool
  `project_run_proposal`, the route
  POST /projects/{id}/proposals/{proposal_id}/run, and the Project Scope
  widget, which now shows the project's next step with a button that runs it -
  after which the widget re-reads the digest and the proposals, because the
  next step has changed. Files: python/harness/projects/execute.py (new),
  python/harness/projects/propose.py, python/harness/projects/tools.py,
  python/harness/routers/projects.py,
  src/app/api/harness/projects/[...path]/route.ts (new - the digest, the
  proposals and the run needed a front door that did not exist),
  src/lib/projects/project-client.ts, src/lib/dashboard/project-widget.tsx.
  Tests: python/tests/test_project_execute.py (7),
  python/tests/test_project_proposals.py. docs updated: docs/projects.md.

- **feat(quant): the trade-log analysis - where the money actually came from.**
  A trade log on its own says what you made; it does not say WHEN you made it,
  which is the question that decides whether a strategy is worth trading. Every
  entry is now placed on the regime of its entry bar - the SAME causal trend x
  volatility classifier the Edge Report uses, so the log, the verdict, the
  Monte-Carlo and the report all speak ONE regime language instead of two - the
  realised P&L is attributed per regime, the concentration of the profit is
  measured (the share of gross positive P&L the best few entries carry), and
  each entry carries its own context: regime, trend, volatility, ATR and the
  distance from entry to exit in ATR terms. A log whose profit sits in one
  streak is FLAGGED, because a streak is not a rule. Entries that cannot be
  placed on a bar of their own symbol's series are counted in the totals and
  reported as unclassified - they are never given a regime they were not
  measured in. It is a measurement, not a verdict: it never says a strategy is
  good, it says where the money came from and what it could not measure.
  Surfaces: the tool `analyse_trade_log` (which reads the Journal's own trades
  when no log is passed) and the route POST /quant/trade-log. Files:
  python/harness/quant/trade_log.py (new),
  python/harness/quant/advanced_tools.py, python/harness/quant/tools.py,
  python/harness/routers/quant_reports.py. Tests:
  python/tests/test_quant_trade_log.py (9). docs updated: docs/quant-engine.md.

- **fix(quant): a prop-firm EV with no fee in it is now marked as an upper
  bound.** The engine never invents a price - the caller supplies the fee and
  the reset fee - which is right, but it left a trap: a caller who forgot
  `feePerAttempt` got an optimistic expected value with nothing flagging the
  omission. The report now carries `assumptions.feeSupplied`, says outright
  that the EV is GROSS of every cost when no fee was given, and raises
  `PROP_FIRM_NO_FEE_SUPPLIED`. A missing input must never quietly flatter a
  number. Files: python/harness/quant/propfirm_mc.py. Tests:
  python/tests/test_quant_trade_log.py. docs updated: docs/quant-engine.md.

- **feat(harness): a project proposes what to do next, from its own evidence.**
  The curated view says where a project stands; this says what to do about it,
  and it may only say it from evidence the project ACTUALLY holds. A strategy
  with no result is proposed for a backtest (with the exact tool call and the
  instruments). A result resting on fewer than 30 trades is proposed for a
  wider sample - below 30 trades the difference between an edge and luck is not
  measurable. A strategy whose trades only ever happened in a few market
  regimes is proposed for a wider window, because the regimes it has never been
  observed in are unknown. A Monte-Carlo whose probability of loss is high, or
  whose 5th-percentile return is not positive, is proposed for a cost test -
  the tail is the problem, not the average. And any result with trades is
  tested against a prop firm's evaluation rules, using the strategy's OWN trade
  sequence. Every proposal cites its evidence (an experiment id, a regime, a
  metric, a pass probability) and names the concrete action, so it can be run
  without being re-invented. A proposal that cannot cite its evidence is NOT
  made: a project that holds what it needs gets the honest answer - there is
  nothing to propose. And a rule that could not be evaluated is REPORTED in
  `skipped`, never silently skipped - a broken check must not look like a
  project with nothing to propose. (That last rule earned itself: two broken
  imports were hiding in the first cut, silently disabling a whole check.)
  Surfaces: the tool `project_next`, the route GET /projects/{id}/proposals,
  and the Project Scope widget, which shows the active project's next step.
  Files: python/harness/projects/propose.py (new),
  python/harness/projects/tools.py, python/harness/routers/projects.py,
  src/lib/projects/project-client.ts, src/lib/dashboard/project-widget.tsx.
  Tests: python/tests/test_project_proposals.py (10),
  python/tests/test_projects.py (the `project_next` tool's refusals),
  python/tests/test_quant_routes.py (the new route is registered).
  docs updated: docs/projects.md.

- **feat(harness): the curated project view - what a project is, and what it
  is missing.** A member list is a filing cabinet; a curated project is a
  summary. The new curator ranks a project's members by a FIXED priority per
  kind - a tested result outranks a strategy, which outranks a dataset, which
  outranks an output artifact, which outranks a run record - breaks ties by
  recency, and carries **the reason each member was promoted**, so the ranking
  can be argued with rather than merely trusted. It derives a headline from
  what the project actually holds ("NQ momentum on NQ, ES - 1 strategy, 2
  results") and it names the GAPS plainly: a project with a strategy and no
  result says so - "no result has been attached yet - a strategy with no tested
  outcome is an intention, not a finding". The curated view is what the AGENT
  sees: the run's per-run project context is the digest, not a flat member
  list, so a turn inside a project starts from "where does this stand?"
  rather than from a wall of references. Surfaces: the tool `project_digest`,
  the route GET /projects/{id}/digest, and the Project Scope widget, which shows
  the active project's headline, its top members with their reasons, and what it
  still lacks. Files: python/harness/projects/curate.py (new),
  python/harness/projects/tools.py, python/harness/routers/projects.py,
  python/harness/graph.py, src/lib/projects/project-client.ts,
  src/lib/dashboard/project-widget.tsx. Tests:
  python/tests/test_project_curation.py (10), python/tests/test_projects.py.
  docs updated: docs/projects.md.


- **feat(harness): the harness has a PUBLIC surface, a published tool
  manifest, and a package that carries no data.** The harness was excellent and
  unreachable: everything it could do - the retrieval layer, the research
  verifier, the comparability gate, the receipts, the tool surface - was
  valuable to another harness and available only here. And a public surface
  that is not DECLARED is not a public surface; it is a directory listing.
  `python/harness/public.py` is now the WHOLE public API -
  `AgenticService`, `ToolRegistry`, the run contract, and the export
  functions - and it is a closed list, asserted by a test.
  `export_tool_schemas()` produces the PORTABLE tool manifest: the MCP
  tool-manifest shape plus the parts a consumer needs to bind a tool safely
  (`permission`, `effect`, `risk`, `version`, the deprecation fields).
  `docs/harness/tool-registry.json` is that manifest, GENERATED, with a drift
  test that regenerates and compares: **946 tools**. The honesty contract is
  the point of the export - a tool is published with its permission and its
  effect class, or it is NOT published, because a consumer cannot honour a
  rule it cannot read and a tool that cannot be classified is a tool nobody
  should call. A consumer inherits Eclipse's honesty: it can see that a tool
  writes, or that it reaches the network, before it binds it. The package
  metadata (`pyproject.toml`) declares `black-eclipse-harness` - the RUNTIME,
  with the provider SDKs as OPTIONAL extras (a consumer that only wants the
  tool surface should not install an SDK for a model it never calls), no
  package data, and no dependency on the app.
  The manifest also caught a real bug: the `analysis_run` tool's description
  interpolated the FUNCTION OBJECT instead of its result, so the tool that
  runs analyses had been advertising `<function recipe_catalogue_text at
  0x...>` to the model instead of the recipes it can actually run. That is
  fixed, and a guard now asserts that no published description carries an
  object repr. Files: python/harness/public.py (new),
  Black-Eclipse-site/pyproject.toml (new),
  scripts/generate-tool-registry.js (new),
  scripts/size-budget.json (the ceiling was raised on purpose for the public
  surface - a real addition, not drift),
  docs/harness/tool-registry.json (generated),
  python/tests/test_public_api.py (new). ADR-H298. docs updated:
  docs/harness/decisions.md, docs/harness/architecture.md, docs/NAVIGATION.md.

- **fix(harness): a shell sees no more of the environment than a command
  does, the output is redacted, and the network is refused BY NAME.** The real
  host shell used to inherit the FULL `os.environ`, so a single `shell_run`
  could read a provider key, the callback token or the vault and print it into
  the conversation, the run blob and the ledger - while the sandboxed command
  path had been scrubbed since Phase 1. Both now use the SAME builder
  (`code.sandbox.build_env`: the allowlist ONLY, never the vault, never the
  provider keys, never the callback token, never a proxy), so a shell and a
  sandboxed command see the same world. Command and shell OUTPUT is now
  REDACTED through the one existing primitive before it reaches the model -
  the file reader has done this since Phase 1, and the command and shell paths
  are the ones a model can most easily push a secret through - and the
  `code.output.redacted` event names the NUMBER of lines changed, never the
  value. `RunSpec.network` was a declaration whose refusal was unreadable: a
  caller could not tell "the network is refused" from "there is no sandbox
  primitive here". The refusal now carries `NETWORK_DENIED`, and the answer to
  "is the network contained?" is PUBLISHED rather than assumed - the container
  tier really does run `--network none`, and the local tier cannot, so the
  command result says which one it was. Two new adversarial cases attack the
  real modules: `S15-network-enforced` and `S16-shell-env-scrubbed`. Files:
  python/harness/code/shell.py, python/harness/code/events.py,
  python/harness/code/shell_tools.py, python/harness/code/command_tools.py,
  python/harness/code/sandbox.py,
  python/harness/code/eval/safety_cases.py, python/harness/code/eval/safety.py,
  python/harness/code/eval/capabilities.py,
  python/tests/test_isolation_secrets.py (new). ADR-H297. docs updated:
  docs/harness/decisions.md, docs/harness/architecture.md, docs/NAVIGATION.md,
  docs/harness/capability-statement.md.

- **feat(harness): the benchmarks are GENERATED, the live tier is a lane, and
  no capability is published unmeasured.** The evaluation framework was already
  first-rate - the real graph, 17 graders, 22 dimensions with un-averagable
  criticals, `pass@k` with Wilson intervals, flakiness classification, frozen
  baselines stamped with the commit, per-dimension regression detection, a
  worktree invoker, a canary split, a verdict-leak tripwire, and a
  team-vs-single benchmark that returned a NEGATIVE verdict and therefore did
  not ship. Almost nobody builds that. And then: the offline tier REPLACED the
  model with a recorded program, the live tier existed but was reachable only
  by hand, no number a stranger could check had ever been published, and four
  capability classes were published unmeasured. `docs/harness/benchmarks.md` is
  now GENERATED by `python -m harness.evaluation.report` (or
  `npm run eval:benchmarks`) and never hand-edited, so a number cannot be
  quietly improved - a test regenerates it and compares. The two tiers are
  kept APART and named: the OFFLINE tier replaces the model with a recorded
  script, so it measures the RUNTIME - the tool surface, the policy, the
  graders, the wiring - and it says so; the LIVE tier runs a real model and
  is the only tier that measures the agent. Both carry their dataset,
  checksum, agent version, commit and grader version, because a number without
  its provenance is a rumour, and a rumour in a benchmark table is worse than
  an empty row. The live lane never fabricates: with no provider it publishes
  "NOT MEASURED" with the reason and exits 0, and the nightly workflow SKIPS
  rather than failing when no secret is configured. And the capability
  registry stops publishing things it cannot back: `price_authority` (the
  authority ARBITRATES a disagreement rather than taking the first answer, and
  the conflict is recorded), `promotion` (the full landing round trip -
  preview, apply, rollback, re-apply - asserted on the real bytes in a real
  folder) and `scraping_breadth` (the registry knows more than one KIND of
  data source) are now graded END TO END; `code_intel`, `code_chat_routing` and
  `context_compaction` are new classes; and the `messaging_gateway` class is
  RETIRED, because it names a capability that is not built and a published
  class for something that does not exist is worse than an unmeasured one. The
  registry is now **24 classes, 24 measured, 0 not measured yet.** Files:
  python/harness/evaluation/report.py, python/harness/evaluation/live_gate.py
  (new), python/harness/code/eval/capabilities.py,
  scripts/generate-benchmarks.js (new), scripts/run-live-evals.js (new),
  python/tests/test_published_benchmarks.py (new),
  .github/workflows/live-evals.yml (new), docs/harness/benchmarks.md
  (generated), docs/harness/capability-statement.md (regenerated). ADR-H296.
  docs updated: docs/harness/decisions.md, docs/harness/architecture.md,
  docs/NAVIGATION.md, docs/harness/capability-statement.md,
  docs/harness/benchmarks.md.

- **chore(harness): the decision record is unambiguous, the harness has a TOTAL
  ceiling, and the release is real.** The operational score was the harness's
  weakest dimension, and the reason was not capability - it was DISCIPLINE. The
  decision series had SEVEN duplicate numbers (H160, H162, H242 x2, H243, H244,
  H245) and five gaps: "ADR-H242" named two different things. The later
  duplicate of each was renumbered and the old number RETIRED with a redirect,
  so an old reference still resolves and the decision is unchanged. The
  withdrawn numbers are reserved explicitly. `scripts/check-adr-numbers.js`
  now fails the release gate on a duplicate, an unreserved gap, or an entry
  without Decision / Why / Consequences - and it NEVER renumbers anything,
  because renumbering is a judgement call that belongs to a human. The shape is
  enforced from H288 onward; the older entries are reported and
  countable rather than rewritten, because inventing a rationale for someone
  else's decision is not honesty. The harness also gains the missing half of
  its size ratchet: `python/tests/test_size_budget.py` bounded each FILE's
  growth but not the TREE's, so a harness could keep every file under its pin
  and still double by adding files. `scripts/size-budget.js` adds a committed
  TOTAL ceiling (`scripts/size-budget.json`) plus the twelve largest
  subsystem ceilings; the harness is 368,218 lines against a 371,900 ceiling
  that must now be raised ON PURPOSE. And the release is real: the version is
  0.2.0, `docs/releases/v0.2.0.md` is derived from the CHANGELOG, the
  changelog's rolling 7-section window is rotated by a script instead of by
  hand, and `CODEOWNERS` names the harness paths - the part of the tree where
  a mistake is hardest to see. The 30% surface cut is NOT in this release: it
  is a multi-release program over DUPLICATION, not capability, and the two
  candidates the plan named first (the FS write stack and the search stack) are
  already merged. Files: scripts/check-adr-numbers.js (new),
  scripts/size-budget.js (new), scripts/size-budget.json (new),
  scripts/rotate-changelog.js (new), scripts/check-all.js, package.json,
  .github/workflows/ci.yml, CODEOWNERS (new), docs/releases/v0.2.0.md (new),
  docs/harness/decisions.md, docs/harness/roadmap/phase-20-measuring-all-of-it.md.
  ADR-H295. docs updated: docs/harness/decisions.md,
  docs/harness/architecture.md, docs/NAVIGATION.md,
  docs/harness/roadmap/phase-20-measuring-all-of-it.md, docs/releases/v0.2.0.md.

- **feat(harness): the model is TOLD the shape of the project.** The harness
  had NO repo map at all. A model that wanted to know what was in the project
  had to GUESS a path, spend a tool call on it, and - on a miss - get a bare
  "that file isn't there". The CIUE index and the context engine are genuinely
  good - the context engine ranks files by symbol matches, path matches and
  related tests, and finds the related test file too - but they were
  reachable only if the model THOUGHT to call `code_get_relevant_context`.
  Excellent machinery, invisible. A repo map - the folders, and a symbol
  outline of the top files - is now built EAGERLY and DETERMINISTICALLY and
  handed to the model in the FIRST turn, together with the CIUE context
  engine's answer for THIS request (the "seeded slice"), resolved once per
  run with no model call. The map is BOUNDED (a file count, a
  symbols-per-file count, a byte budget and a render budget - it is a summary,
  never a copy), DETERMINISTIC (the same tree produces the same map and the
  same digest, byte for byte), and HONEST about its engine: the outline comes
  from the stdlib extractor (Python's own `ast`, a brace/regex scanner for
  everything else), and tree-sitter's availability is published in the
  code-intel status - an optional layer that silently no-ops is a false
  capability. The map's content hash is the prompt-cache key's witness: a
  project whose shape changed invalidates the cache, and one that did not
  change does not. It gets its OWN segment for exactly that reason -
  `runtime_context` is run-frozen and its content is NOT hashed, so a map
  appended there would have been cache-key-invisible. The same change fixes an
  UNMEASURED claim: `CodeIntelRuntime.is_fresh()` used to `return True` for
  EVERY workspace - including one that was never indexed and one with no
  background indexer. It now looks for the EVIDENCE (the background watcher
  that owns the index's freshness), and a workspace with neither is honestly
  not fresh - which is what lets a read path ask for a refresh instead of
  trusting a claim. Files:
  python/harness/code/intel/repo_map.py (new),
  python/harness/code/intel/runtime.py, python/harness/prompt_segments.py,
  python/harness/graph_context.py, python/harness/graph.py,
  python/harness/code/eval/capabilities.py,
  python/tests/test_repo_map.py (new, 14 cases). ADR-H287. docs updated:
  docs/harness/decisions.md, docs/harness/architecture.md, docs/NAVIGATION.md,
  docs/harness/capability-statement.md.

- **feat(harness): the dropped turns are COMPACTED, not just dropped.** The
  harness TRUNCATED its history: `_bounded_history` kept the most recent turns
  and dropped the oldest, and the dropped-context extractor mined them for
  INERT candidates ("you mentioned a file called X"). Everything else the
  conversation carried - the decision that was made, the question that was
  still open, the state of the work - was GONE. `context_budget.py` said it
  plainly: *"no tokenizer dependency, no network call, no summarization."*
  Every top-tier harness compacts; a long run in Eclipse could keep twenty
  turns and no more, and the twenty-first turn started from nothing. What the
  history bound removes is now carried forward as a fenced, labelled summary:
  the requests that were made and the answers that were given (the
  DETERMINISTIC skeleton, which always runs), plus a bounded model NARRATIVE
  on top of it - the decisions taken, the open questions, the state of the
  work. The existing inert dropped-context block is NOT replaced: both reach
  the model, the compaction first. The narrative is ADDITIVE and fails
  CLOSED - an unavailable, silent or failing model leaves the skeleton
  untouched and the run records why - and the block is DATA, never instruction
  (a compaction can contain anything the user typed). It never enters a
  research claim: a summary of a conversation is not evidence. The model
  narrative is OPT-IN (the policy key `history_compaction_model` turns it
  ON), because it costs a model call and up to twenty seconds on the run's
  critical path - the deterministic skeleton is what actually carries the
  conversation forward, and it ALWAYS runs. Files: python/harness/compaction.py (new), python/harness/history.py,
  python/tests/test_history_compaction.py (new, 12 cases),
  python/tests/test_size_budget.py (the re-pin). ADR-H286. docs updated:
  docs/harness/decisions.md, docs/harness/architecture.md, docs/NAVIGATION.md.

- **fix(harness): ONE edit tool, and it insists the run read the file.** The
  harness had THREE ways to change a file's contents and ELEVEN more
  file-lifecycle tools, spread over two subsystems - and NONE of them required
  proof that the model had seen the file it was about to change. `expectedHash`
  was accepted everywhere and required NOWHERE, so the model could write to a
  file it had never read, and a file that had changed underneath it was
  overwritten silently. The text-edit surface is now ONE tool, `code_edit`
  (`path`, `oldText`, `newText`, `expectedOccurrences`), with two rules
  enforced in code. **A file may only be changed if THIS RUN read it**: the
  per-run READ LEDGER records every file a read tool returned a hash for, the
  registry feeds it in ONE place so every read tool participates, and an edit
  to a file the run never read is refused with `FILE_NOT_READ` - the refusal
  names the read that would make the edit legal. **A file may only be changed
  if it has not changed since it was read**: the ledger's hash is passed to
  the edit engine as `expected_hash`, so the engine's own `STALE_FILE`
  refusal fires - the same code, the same recovery hint, in one place. An
  ambiguous match is refused, never guessed. `code_edit` is a WRITE tool in the
  ONE policy authority, so `plan_only` removes it and `edit_verify` keeps it -
  exactly like the tool it replaces. A wrong path comes back with up to five
  nearest candidates instead of a bare "that file isn't there". The mutators
  `code_edit` subsumes are DEPRECATED, still callable, and name their
  replacement (`replace_text`, `patch_file` and `edit_file` name `code_edit`;
  `multi_file_patch` names `apply_diff`; `workspace_patch_apply` names
  `code_edit`). The genuinely DIFFERENT operations - create, delete, move,
  copy, rename, the directory tools, insert, line-range delete, unified diff -
  are NOT deprecated: removing those would remove capability, not duplication.
  The plan had sketched thirteen deprecations; the audit showed nine of them
  are distinct operations one edit tool cannot express, so the honest set is
  the four text-edit paths it actually subsumes. `workspace_read` now returns
  the file's hash, so a workspace-level read feeds the ledger too. Three new
  adversarial cases (S12 never-read, S13 stale-file, S14 ambiguous-match)
  attack the real enforcing modules, and the `code_edit_contract` capability
  class makes the whole contract measured. Files:
  python/harness/code/edit_tools.py (new), python/harness/tools.py,
  python/harness/code/fs/errors.py, python/harness/code/policy.py,
  python/harness/code/tools.py, python/harness/code/fs_tools.py,
  python/harness/agents.py,
  python/harness/code/eval/{safety_cases,safety,capabilities}.py,
  python/tests/test_code_edit_primitive.py (new, 13 cases). ADR-H285. docs
  updated: docs/harness/decisions.md, docs/harness/architecture.md,
  docs/NAVIGATION.md, docs/harness/capability-statement.md.

- **fix(plugins): the bundled SEC reference plugin is source, not a scratch
  dir.** `.gitignore` carried a bare `sec/` pattern - a gitignore pattern with
  no leading slash matches a directory of that name at ANY depth - so it was
  silently excluding `python/harness/plugins/bundled/sec/` from version
  control. Every clean clone therefore shipped without a reference plugin, and
  the plugin marketplace gate (`test_plugins_reference.py`) failed on any
  checkout that was not the author's own working tree - which is exactly why it
  passed locally and failed everywhere else. The pattern is re-included
  explicitly and the plugin is tracked. Files: Black-Eclipse-site/.gitignore,
  Black-Eclipse-site/python/harness/plugins/bundled/sec/{plugin.py,plugin.yaml}.
  docs updated: docs/CHANGELOG.md.

- **feat(charts): the chat's charts are drawn by the PYTHON engine, and ANY chart
  can be drawn.** The chat's `chart` block no longer has an ECharts path: the
  block is turned into a validated chart **SPEC** (data only - a kind, some
  series, a title - never a callback, a URL or a path) and the runtime draws it
  with `matplotlib` into a transparent PNG in the app's own palette, recorded in
  the Artifact Center and fetched back as an artifact. The chat's ECharts option
  builder (`chart-option.ts`) and the engine-preference store are **deleted**.
  **The ceiling is gone:** a chart block may also arrive as a **SCENE** -
  `panels` of `marks` - which is compositional rather than a fixed list of
  kinds, so a violin, a box plot, a Gantt, a funnel, a ridgeline, an error-bar
  chart or a dual-axis chart is a composition of the primitives (`line`, `area`,
  `bar`, `scatter`, `band`, `rule`, `label`, `box`, `violin`, `histogram`,
  `errorbar`, `heatmap`, `pie`, `donut`, `candlestick`, `waterfall`, `ridge`,
  `stem`) instead of needing a new kind invented for it. The marks are drawn
  exactly as the model writes them, and the schema read-back now describes the
  mark vocabulary so the model can see it. The rest of the app stays on ECharts.
  Files: python/harness/charts/scene.py, scene_render.py, render.py, spec.py,
  tools.py; src/lib/response/chart-spec.ts, chart-registry.ts, contract.ts,
  export.ts, response-chart.tsx; src/lib/harness/response-bridge.ts;
  src/lib/response/chart-option.ts, chart-engine.ts (deleted);
  python/tests/test_chart_scene.py; src/lib/response/chart-spec.test.ts,
  repair.test.ts.
  docs updated: docs/chart-engine.md, docs/interactive-response-engine.md,
  docs/DECISIONS.md (ADR-050), skills/ARCHITECT.md (ADR-050).

- **feat(harness): ONE search primitive, and the engine is always named**
  (Round 3 / W5, ADR-H284). The harness answers two questions about a codebase
  - "what does this SAY?" and "what files are there?" - with exactly two tools:
  `search_text` (contents, ripgrep-first with a bounded Python fallback) and
  `search_files` (names, now carrying every filter `find_files` had: exclude,
  extensions, directoriesOnly, filesOnly, includeHidden, includeIgnored). The
  older names (`workspace_search`, `find_files`) stay callable for one release
  as DEPRECATED ALIASES, the registry warns once per run naming the
  replacement, and the agent surfaces carry the canonical names only. Before
  this, the tool the model reached for FIRST was the slow one: the workspace
  search ran its own naive Python walk while the fs subsystem's `search_text`
  was already ripgrep-first. The old `workspace_search` also bypassed the code
  policy entirely; the search now goes through the code capability, so it needs
  a code profile. The workspace walker moved to its own module
  (`python/harness/code/scan.py`) so the ratcheted core file shrinks.
  Files: python/harness/code/scan.py, fs_tools.py, tools.py, agents.py;
  python/tests/test_code_search_surface.py, test_code_tools.py,
  test_chat_code_profile.py, test_code_reachability.py.
  docs updated: docs/NAVIGATION.md, docs/harness/architecture.md.

- **feat(harness): the verify-and-repair loop runs in the graph, and its status
  is DERIVED** (Round 3 / W1, ADR-H281). A change is not finished because the
  model said so: the graph's `verify_repair` node runs the project's pinned
  check CLASSES through the ONE command path, and a failure is handed back to
  the model. `RepairLoop.status` is now a property computed from the facts
  (`last_passed`, `refused`, `stopped_reason`) rather than a field someone set
  by hand - a status that said "passed" while the last check failed is exactly
  the kind of unbacked claim this harness exists to refuse. The new
  `REPAIR_FAILED` state (the check was still failing when the run ended) is
  disclosed in the answer, not only in the blob. A new eval case
  (`repair-in-graph`) drives the REAL graph with a scripted model and a
  scripted check: a graph with no repair node records nothing, and the case
  fails. Files: python/harness/code/repair.py, repair_graph.py, verify.py;
  python/harness/code/eval/capabilities.py, dataset_tasks_v1.json,
  statement.py, tasks.py; python/tests/test_graph_repair_node.py.
  docs updated: docs/harness/architecture.md, docs/harness/capability-statement.md,
  docs/harness/roadmap/round-3-parity-plan.md.

- **fix(harness): the eval gates hand back the model builder they override.**
  `eval_gates/resume.py` and `eval_gates/workflow.py` patched
  `graph.build_chat_model` and never restored it, so every later run in the
  same process answered with the gate's model. The evaluation seam now
  refuses to replace an ACTIVE override (a test double) - only a chaining seam
  may be wrapped - so an override's teardown cannot silently drop the double
  for every later test. Files: python/harness/eval_gates/resume.py,
  workflow.py, python/harness/evaluation/runner.py.
  no doc change - a test-hygiene repair inside the harness.

- **fix(harness): the surface snapshot carries the tool guidance.** A
  snapshot that drops the guidance turns "the model was told" into "the model
  was never told" on replay. Files: python/harness/routers/evolution.py.
  no doc change - one added field on an existing payload.

- **chore(harness): re-pin the size ratchet for the in-flight work.** The
  quant tool surface, the graph and the fs tool surface grew past their
  ceilings; each ceiling was re-pinned to the measured size with the reason
  recorded, and each line names its split candidate. Files:
  python/tests/test_size_budget.py.
  no doc change - a size ratchet.

- **docs(rsl): the P2 row names what the gate actually measures.** The
  per-scope concurrency cap and the deterministic selection are not in flight
  in P2, so the row now names the one thing that is: the cost per accepted
  improvement, and the proof that real usage survives into the experiment
  report. Files: docs/self-improvement/rsl-v3-plan.md.
  docs updated: docs/self-improvement/rsl-v3-plan.md.

- **chore(harness): the mandated check cannot finish, and that is why the agent
  spins.** **The cause:** AGENTS.md requires `npm run test` after EVERY change.
  That script is `vitest run && node scripts/test-python.js && node
  scripts/test-evals.js`, and the middle stage runs the Python suite, which
  stalls for over a minute inside
  `python/tests/test_application_e2e.py::test_e2e_start_health_observe_stop_restart`
  - `harness/execution/application/health.py:check_with_retries` retries a TCP
  check against port 8000 sixteen times with a backoff that grows to eight
  seconds per attempt. Measured end to end, `npm run test` takes 153s even when
  the first stall is cut short, and it never completes on its own. The shell
  tool's own ceiling is 120s, so the check is killed mid-flight every time and
  returns an opaque `Unknown: ChildProcess.kill` instead of a pass or a fail.
  The agent cannot tell whether the check passed, so it runs it again: 344
  check re-runs with no code change between them across the last forty
  sessions, `npx tsc --noEmit` 450 times all-time (87 in one session), and more
  than half of all check invocations piped through `Select-Object -First/-Last`
  to re-read an output it had already been truncated out of. The loop is also
  invisible to the host: OpenCode's own doom-loop guard only fires on
  byte-identical tool inputs, and every retry here differs by a few
  characters, so it never trips. A check that cannot report a result is not a
  check - it is a treadmill. Files: (diagnosis only - no source changed).
  no doc change - a diagnosis; the fix is not in this entry.

- **fix(chat): a long message no longer fails with "Something went wrong".**
  Pasting more than 4 000 characters into Eclipse was rejected by the front
  door with `query too long (max 4000 chars)` and rendered as a generic
  "Something went wrong" card - a message the composer had accepted was
  refused on the way to the agent, and the user was given no way to tell a
  rejected request from a broken agent. A turn is whatever the person pasted,
  so the bound now only guards ONE REQUEST BODY: it is 100 000 characters
  (~25k tokens) on both sides of the bridge, and the RUNTIME owns the real
  limit - it measures the assembled request against the resolved model's
  context window and reports an honest CONTEXT_OVERFLOW when a prompt
  genuinely does not fit. The two bounds are MIRRORED on purpose: the front
  door's `MAX_QUERY_LENGTH` (`src/lib/harness/validation.ts`) must stay >=
  the runtime's `RunInput.query` bound (`python/harness/schemas.py`), or the
  runtime would reject a request the app accepted with a bare pydantic 422.
  A prior turn now carries the same per-turn bound, so a long message is not
  silently sliced when it returns as history on the next turn; the whole
  history is bounded by dropping the OLDEST whole turns (never a turn cut in
  half), so the runtime receives every turn it is given intact and applies its
  own budget on top. The refusal itself
  improved too: it now carries the stable `INVALID_INPUT` code (the chat card
  badges it instead of showing a bare sentence), it says what to do
  ("send it in smaller parts or attach it as a document"), and it is NOT
  retried - a refused request used to be sent three times (stream 400 ->
  one-shot 400 -> one-shot retry 400), all failing identically. A missing
  streaming ENDPOINT (404/405, an older front door) still falls back to the
  one-shot path; a REFUSED request does not. Files:
  src/lib/harness/validation.ts, src/app/api/harness/chat/route.ts,
  src/app/api/harness/chat/stream/route.ts, src/lib/agent/registry.ts,
  src/lib/agent/use-agent-run.ts, src/components/screens/stock-chat.tsx,
  src/lib/bots/use-bot-delegation.ts, python/harness/schemas.py. Tests:
  src/lib/harness/validation.test.ts, src/app/api/harness/chat/route.test.ts,
  src/lib/agent/registry.test.ts. docs updated: docs/chat-ui-audit.md,
  docs/harness/architecture.md.

- **feat(chat): a long paste becomes an attachment, the way ChatGPT does it.**
  A paste over 4 000 characters is no longer dumped into the composer: it is
  intercepted, written into the conversation's session folder as a
  `pasted-text.txt` context document, and shown as a chip above the composer
  (`pasted-text-2.txt`, `pasted-text-3.txt`, … on repeat). It then flows
  through the SAME path as an attached file — extracted, injected into the run,
  removable from the chip — so there is one attachment pipeline, not two. Small
  pastes still insert normally, and the floating dock gets the same rule. The
  document caps were raised to match the turn bound (100 000 chars per document,
  200 000 combined) so a paste that becomes a document arrives as readable as
  the same text would have as a message; the runtime still measures the
  assembled turn (documents included) against the model window and reports a
  CONTEXT_OVERFLOW rather than silently dropping text. Files:
  src/lib/chat/paste.ts (new), src/lib/chat/use-session.ts,
  src/lib/chat/session-types.ts, src/lib/chat/extract.ts (caps),
  src/components/chat/chat-input.tsx, src/components/chat/empty-state.tsx,
  src/components/chat/chat-dock.tsx, src/components/screens/stock-chat.tsx,
  src/lib/harness/validation.ts, python/harness/schemas.py. Tests:
  src/lib/chat/paste.test.ts (new), src/lib/chat/extract.test.ts,
  src/lib/harness/validation.test.ts. docs updated: docs/chat-ui-audit.md.

- **fix(chat): the pasted-text chip is now readable, and Enter sends it.**
  Two things the first cut got wrong. (1) A chip you cannot open is a black
  box: clicking a pasted-text chip now opens a glass preview with the full text
  (a real file opens the session file). (2) The composer refused to send with
  nothing typed, so a paste followed by Enter did nothing at all. Now a paste
  sent with an empty composer IS the message — the text is taken back out of
  the attachment list and sent as the query, so it is never also injected as a
  document (no double tokens); with only FILE attachments and no text, a
  neutral "Read the attached document." is sent instead of a dead click. The
  send button is enabled whenever there is something to send. The floating
  dock keeps inserting a long paste as text (it has no chip UI, so intercepting
  there would swallow the paste). Files: src/components/chat/attachment-preview.tsx
  (new), src/lib/chat/use-session.ts, src/components/chat/chat-input.tsx,
  src/components/chat/empty-state.tsx, src/components/chat/chat-dock.tsx,
  src/components/screens/stock-chat.tsx. Tests: src/lib/chat/paste.test.ts.
  docs updated: docs/chat-ui-audit.md.

- **style(response): notice cards drop the left accent bar.** Every response
  notice/warning surface (callouts, unsupported-block and diagnostic cards,
  diagram/render failures, curriculum gaps, node details) shared `NoticeCard`'s
  vertical tone gradient strip on the left edge. Removed the strip and its
  palette entries so the cards keep only the frosted surface, tone icon chip,
  tinted title and wash/glow. Files:
  src/components/response/blocks.tsx. no doc change — styling only, contracts
  unchanged.

- **fix(chat): formulas are TYPESET, not printed as source.**
  A formula in the chat came out as raw text: the Markdown subset had no
  mathematics at all, so `$S = \frac{r_p - r_f}{\sigma}$` reached the reader
  as its own characters. The subset now recognises LaTeX - `$...$` inline and
  `$$...$$` as a block - and draws it with KaTeX.
  **Money stays money.** A `$...$` span only counts as a formula when it looks
  like one: it carries a LaTeX operator (`\`, `^`, `_`, `{`, `}`, `=`, `+`, `<`,
  `>`) or is a single non-digit symbol (`$x$`, `$\mu$`). The opening `$` may
  not follow a word character or a digit (`US$100`), the span may not break
  over a line, it may not begin or end with whitespace (`$5 and $10` is
  prose), and the closing `$` may not be followed by a digit (`$100`). So
  `it trades at $100` is still money, and a Sharpe ratio is a formula. The
  agent is told the same rule (`python/harness/prompts.py`, "Formulas"): write
  `USD 100`, never `$100`.
  KaTeX (already on disk as mermaid's dependency) is now a DIRECT dependency
  and is loaded ON DEMAND, so the chat's initial bundle does not carry it;
  until it arrives the formula shows its own source, and a formula KaTeX
  cannot parse shows the same way rather than breaking the message. Its
  stylesheet is global (`src/app/katex.css`) - one stylesheet for the whole
  typesetting, with its own maths faces.
  The `eclipse-response` fence renders through the same component, so a
  `markdown` block inside a structured answer typesets formulas too.
  Files: `src/lib/chat/markdown.ts` (the parser), `src/lib/chat/math.tsx` (the
  renderer), `src/components/chat/markdown.tsx` (the wiring),
  `src/lib/response/export.ts` (the plain-text export), `src/app/katex.css`,
  `python/harness/prompts.py`. docs updated: `docs/chat-ui-audit.md`,
  `docs/interactive-response-engine.md`.

- **feat(runtime): a surface can carry its own policy, and the sandbox fails
  closed.**
  A live surface (a profile, a bot, a group) can now set `memoryPolicy`
  (`off` / `profile_only`), `guardrails`, `maxAnswerChars` and a
  `subagentPrompt`. The runtime ENFORCES it: a finished answer that breaks a
  surface's guardrails fails the run with a named code
  (`GUARDRAIL_TOOL_REQUIRED`, `GUARDRAIL_CITATION_MISSING`,
  `GUARDRAIL_ANSWER_TOO_LONG`) instead of shipping as a completed result, and
  a delegated child inherits its parent's context policy - the surface adds
  prompt evidence, never a tool or a permission.
  A turn is bounded by a ceiling that MIRRORS the front door's
  `MAX_QUERY_LENGTH`, so the runtime accepts everything the front door lets
  through and reports an honest CONTEXT_OVERFLOW instead of a hard rejection.
  The sandbox fails CLOSED when the operator demands a real isolation
  primitive (`HARNESS_SANDBOX_REQUIRED=1`): the local backend caps memory, the
  process count and the tree, but it does NOT confine the filesystem or the
  network, so the analysis path refuses rather than presenting a weaker
  boundary as the requested one. Analyses pass through a concurrency gate
  (`HARNESS_ANALYSIS_CONCURRENCY`, default 2) so a burst cannot stampede the
  host.
  The chat agent's step budget is 24 by default (8 was too tight for a
  navigation turn, 12 for a turn carrying several deliverables); an operator
  can override it with `ECLIPSE_CHAT_MAX_STEPS` (clamped 1..32).
  Files: `python/harness/{main.py,tools.py,schemas.py,graph.py,graph_context.py,analysis_tools.py,delegation_tools.py}`,
  `python/harness/code/{sandbox.py,execution.py}`, `python/harness/routers/sandbox.py`,
  `src/lib/harness/{errors.ts,validation.ts}`. Tests: `python/tests/test_{chat_step_budget,delegation_tool,graph,qa_round1_acceptance,sandbox_surface,surface_context_policy,size_budget,quant_routes}.py`,
  `src/lib/harness/validation.test.ts`. docs updated:
  `docs/harness/architecture.md`.

- **feat(self-improvement): the RSL operator surface - guardrails, a digest, and
  a weekly card.**
  The self-improvement loop can now be READ, not only run. A guardrail is a
  rule the RUNTIME checks (never a rule the model is told): a violation fails
  the run with a named code and the answer is not shipped as a completed
  result, and the citation rule reuses the evaluator's own citation parser so
  a guardrail and the citation grader agree on what a citation IS. The digest
  (`GET /evolution/rsl/report`, operator-gated) is one read-only summary of
  what the loop actually did - the experiments that ran, what they cost, what
  was accepted, the candidates in flight, the lessons adopted and where
  production drifts - and everything in it is measured or `UNKNOWN`: a missing
  source never becomes a fabricated zero. The Skills page grew the matching
  surface: the RSL control panel and a weekly card.
  Files: `python/harness/self_improvement/{guardrails.py,report.py,drift_watch.py,live_surface.py,models.py,recursion.py}`,
  `python/harness/evaluation/{repair_metrics.py,export.py,nightly.py}`,
  `python/harness/routers/{evolution.py,evolution_report.py}`,
  `src/lib/harness/{evolution-client.ts,evolution-browser.ts}`,
  `src/components/screens/skills/{rsl-control-panel.tsx,rsl-weekly-card.tsx}`,
  `src/app/api/evolution/rsl/report/`. Tests:
  `python/tests/test_{drift_watch,live_surface,evaluation_repair_metrics,evaluation_export,evaluation_nightly,rsl_digest,rsl_guardrails,rsl_provenance,rsl_snapshot}.py`,
  `src/components/screens/skills/rsl-weekly-card.test.tsx`. docs updated:
  `docs/harness/agent-evaluation.md`, `docs/self-improvement/rsl-v3-plan.md`.

- **feat(chat): a refused turn reads as a refusal, and a long paste is an
  attachment.**
  A chat request the front door refused used to show a bare "Something went
  wrong" plus the server's sentence, with no code - a rejected request was
  indistinguishable from a runtime failure, and the retry logic repeated the
  SAME request that could not succeed. The refusal now carries its code and
  status, the UI badges it, and a refused turn fails ONCE.
  A paste above 4,000 characters is intercepted and ATTACHED: it lands in the
  conversation's session folder as a context document and shows as a chip, the
  way an uploaded file does, because a multi-thousand-character blob in the
  composer makes the composer unusable. A pasted document sent with nothing
  typed IS the message (the text is taken back out of the attachment list, so
  it is not injected twice). An attachment can be OPENED and read before it is
  sent.
  Files: `src/lib/chat/{paste.ts,session-types.ts,use-session.ts}`,
  `src/lib/agent/{registry.ts,use-agent-run.ts}`, `src/lib/harness/index.ts`,
  `src/app/api/harness/chat/{route.ts,stream/route.ts}`,
  `src/components/chat/{chat-input.tsx,chat-dock.tsx,empty-state.tsx,attachment-preview.tsx}`,
  `src/components/screens/stock-chat.tsx`, `src/lib/bots/use-bot-delegation.ts`.
  Tests: `src/lib/chat/{paste.test.ts,extract.test.ts}`,
  `src/lib/agent/registry.test.ts`, `src/app/api/harness/chat/route.test.ts`.
  docs updated: `docs/chat-ui-audit.md`.

- **fix(market): the yfinance window travels explicitly, and a chart's `data`
  alias actually draws.**
  A 1y range was requested from yfinance as a rolling `period`, which is
  anchored to "now": a request for 2025-10-20..2026-10-20 came back starting
  on the 21st - a silently short series that changes every return, drawdown
  and statistic computed from it. The window is now passed to yfinance as
  explicit `start`/`end`, so the series really covers the requested days.
  The chat's chart spec carries the scene fields the newer marks need (`z`,
  `parents`, `colors`, `sources`, `targets`, `weights`), and the Python
  figure reads a mark's values through the model's own accessor, so a mark
  that arrives as `data` instead of `y` is drawn instead of coming out
  empty.
  Files: `scripts/yfinance_bridge.py`, `python/harness/charts/plotly_figure.py`,
  `src/lib/scraper/fetchers/yfinance.ts`, `src/lib/response/chart-spec.ts`.
  Tests: `python/tests/test_yfinance_bridge_window.py`,
  `src/lib/scraper/fetchers/yfinance-window.test.ts`,
  `src/lib/harness/data-bridge-{identity,phase2}.test.ts`. docs updated:
  `docs/CHANGELOG.md`.

- **fix(chart): a linear regression is a chart kind, and an unknown kind no
  longer loses the chart.**
  A "linear regression chart" had nowhere to go: the vocabulary had no
  regression, and an unknown `chartType` INVALIDATED the whole chart block,
  so the reader got nothing at all. Now:
  - `regression` is a real kind - a chart block with `chartType: "regression"`
    (or a `regression` mark in a scene) draws the points, ONE ordinary
    least-squares line through them, and the R-squared in the legend. The
    engine fits the line from the same numbers it draws, so the picture and
    the R-squared can never disagree; a fit that cannot be computed (fewer
    than two points, no variation in x, no variation in y) is not drawn, and
    the trace says why. The arithmetic is plain on purpose - a reader must be
    able to check `R2 = 0.87` from the picture
    (`python/harness/charts/regression.py`).
  - An UNKNOWN `chartType` now falls back to `auto` instead of invalidating
    the block: one odd kind must never cost the reader every other panel.
    The mark types already worked that way; the block kind now does too.
  - The synonyms a producer actually uses are read (`linear_regression`,
    `linear regression`, `trendline`, `ols`, `fit`, `trend`), and the agent is
    told that a regression is a `regression` mark - never to fit the line
    itself.
  Files: `python/harness/charts/{regression.py,scene.py,plotly_figure.py,scene_render.py,tools.py}`,
  `src/lib/response/{contract.ts,normalize.ts,chart-spec.ts}`,
  `src/lib/harness/charts.ts`, `python/harness/prompts.py`. Tests:
  `python/tests/test_chart_regression.py`, `src/lib/response/chart-regression.test.ts`.
  docs updated: `docs/chart-engine.md`, `docs/interactive-response-engine.md`.

- **fix(chat): a chart is ONE step, and a market refusal names the routes that
  already failed.**
  A real run of "regress AAPL's daily close over 12 months" burned all 24
  steps and 2.7M tokens and answered with prose and no chart. The engine was
  never the problem: the agent had the 251 closes by step 7 and then spent
  sixteen steps re-verifying them (6 scraper runs, 5 browser evaluations, 3
  sandbox computations) because it thought a chart needed a drawing TOOL call
  to read the numbers back. Two rules fix that:
  - **A chart block IS the drawing.** The data goes IN the block and the engine
    draws it: a `regression` mark fits the line and shows the R-squared in its
    legend. No drawing tool call, no round trip, ONE step. The agent is told
    never to fit the line itself and never to quote an R-squared it has not
    read back.
  - **One attempt per route.** A route that refuses is a routing problem, not
    a reason to keep asking: try the next route once, and if the second route
    for the same series also refuses, use the data already in hand (or the
    numbers the user gave) and say plainly what it is and where it came from.
    Never re-verify a series you already hold, and never spend a browser on a
    provenance audit the reader did not ask for.
  The market refusal now carries the WHOLE provider trail
  (`Providers tried: yahoo: DATA_NOT_AVAILABLE (...); stooq: ...; polygon:
  AUTHENTICATION_FAILED (no POLYGON_API_KEY)`) and says that a provider
  answering AUTHENTICATION_FAILED needs a credential it does not have - do
  not try it again. The last provider's error alone hid the more useful one
  (a keyless route with no data), so the agent could not tell which routes had
  already been tried and went to scrape a page instead.
  Files: `python/harness/prompts.py`, `python/harness/market/{gateway.py,tools.py}`.
  Tests: `python/tests/test_market_refusal_trail.py`. docs updated:
  `docs/chart-engine.md`, `docs/harness/market-data.md`.

- **fix(chart): a chart may NAME its series, and a mark's points are read the
  way a model writes them.**
  A real run of "regress AAPL's daily close over 12 months" produced no chart
  at all, and the run's own record says why - in the model's words: "The chart
  did not render. The scatter-plus-regression block I built failed the
  renderer's schema check on the mark data format, and I've run out of steps
  to resubmit it." Three separate causes, all fixed:
  - **A mark's points are read the way a person writes them.** A mark's `y` /
    `data` now accept a scalar, an `[x, y]` pair (the pair carries its own x)
    or an object with named fields - `{i: 1, close: 188.7}` (a field named
    like an x is the x, one named like a y is the y; when the names say
    nothing, the first two numeric fields are the point, in order). The engine
    splits a pair into its x and its y. A chart that refuses a point over its
    FORMAT is a chart the reader never sees.
  - **A chart may NAME its series instead of carrying it.** A mark (or a whole
    chart block) may set a `dataSource` - `{symbol, market?, interval?,
    start?, end?, field?, name?}` - and the engine fetches that series through
    the SAME market gateway every price comes from, then draws and fits it. A
    chart that spells out 250 prices is a long message, and a long message
    gets truncated: the block stops being valid and the chart is lost with no
    diagnostic. With a named source the model writes ~200 characters and the
    reader gets the real 251-bar series, fitted (R2 = 0.687 on AAPL over
    2025-10-22..2026-10-21). A source that cannot be fetched is a named
    refusal, never a guess. The chart route binds the server bridge to the
    gateway (the bridge is bound per RUN, so a route outside a run had none).
  - **The agent is told not to fetch a market series into its own context.**
    The market tool's text result is truncated by design (a 251-bar series
    arrives as its first 30 and last 10 bars), so a model that tries to fit
    the series itself is fitting a fraction of it. The chart fetches the
    series; the model does not.
  Verified in the real app: the same request now answers with a live chart -
  the points, the fitted line and the legend "Series fit (R2 = 0.687)" - in
  14 steps and a 1 KB block (was 24 steps and a 3.8 KB block that was lost).
  Files: `python/harness/charts/{scene.py,source.py,tools.py,spec.py}`,
  `python/harness/routers/charts.py`, `python/harness/service.py`,
  `src/lib/response/{contract.ts,normalize.ts,chart-spec.ts}`,
  `src/lib/harness/charts.ts`, `python/harness/prompts.py`. Tests:
  `python/tests/test_chart_{pairs,source}.py`,
  `src/lib/response/chart-{pairs,point-shapes,source}.test.ts`. docs updated:
  `docs/chart-engine.md`, `docs/harness/market-data.md`.
