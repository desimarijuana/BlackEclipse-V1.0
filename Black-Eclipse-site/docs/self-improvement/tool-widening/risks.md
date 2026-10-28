# Residual risks and deliberate omissions

This file assumes the change described in `design.md`: a pure safety-case
builder, a strengthened frozen target denylist, and tests. No runtime grant is
implemented.

## Residual risks after this change

### R1. The safety case is only as honest as its inputs

`widening.py` receives counts, run ids, timestamps and replay results from its
caller. It can check that the fields are present, distinct, disjoint and above
thresholds. It **cannot** prove that a run id exists, that a run actually
completed, or that a timestamp is real. A caller that fabricates the evidence
can produce an `eligible: true` package.

Mitigation: the seam that supplies evidence must resolve each run id against the
evaluation store and stamp the timestamps. This change does not build that seam.
Until it does, the package is a *format*, not a proof. The human-review block
must say so.

### R2. Human-review items are not enforced

The package records `humanReview` items (is this the narrowest tool? is the
deny path representative? is the blast radius acceptable?). Nothing forces the
operator to read them. A polished package can create automation bias.

Mitigation: the future UI must require an explicit acknowledgement per review
item, not a single Approve button. Deliberately not built here.

### R3. The builder is not wired into any route or UI

The operator cannot yet see the package in the product. The core is testable and
safe, but the user-facing cost reduction (the point of Option B) is not delivered
by this change alone.

Mitigation: a later `POST /evolution/widening-cases` plus a capability-studio
card. It was omitted to keep the blast radius at zero runtime behaviour.

### R4. The frozen target denylist is still not total

This change adds `self_improvement/**`, `capabilities/**`, `grants.py` and
`recovery/envelope.py`. It does **not** protect every file that could influence
authority, for example:

- `python/harness/tools.py` (the registry and the tool contract),
- `python/harness/surface.py` (the one tool-surface resolver),
- `python/harness/agents.py` (agent presets and allowlists),
- `python/harness/persistence.py` (the run store),
- `python/harness/service.py` / `graph.py` (boot and the tool loop).

A code patch to those is L0 and requires a human (`autonomy.py:206-207`), but
the RSL *target* guard does not refuse it structurally. Adding every authority
file to the glob list is a separate hardening task because it narrows the set of
legitimate RSL subjects; it should be done deliberately, with a review of what
self-improvement is still allowed to change.

### R5. Financial-action detection is partly name-based

The tool is refused if its metadata says `permission != "read"`, or its name
contains a known financial marker. A tool registered as `read` with an innocuous
name could still perform an external action. The metadata gate is the primary
control; the name gate is a second barrier, not a proof.

Mitigation: Option D (capability contracts) and an independent runtime effect
gate. Deliberately not built here.

### R6. `decide()` still trusts the caller's risk string

The L2 refusal is only as good as `classify_snapshot_risk` being called. The
operator route can pass `risk` directly. This change does not add a
defence-in-depth re-classification inside `decide()`.

Mitigation: a future `decide()` should accept the base/candidate snapshots and
recompute the risk itself, or the route should refuse a caller-supplied risk for
surface changes. Not changed here to avoid touching the autonomy path.

### R7. No grant, therefore no grant revocation

The requirement "revocation works" is satisfied at the proposal level: a case
can be withdrawn, and an expired/withdrawn case is not live. There is **no
runtime grant** to revoke. If a future Option C is built, revocation must be
implemented at the surface resolver and tested there; this module's
`withdraw`/`is_live` semantics are not a substitute.

### R8. The denylist strengthening may surprise the RSL loop

`python/harness/self_improvement/**` is now a frozen target. A legitimate RSL
code patch that tries to improve the loop's own machinery will be refused. That
is intended (constraint 5), but it changes the loop's reachable subject set and
should be communicated to operators.

### R9. Tests are unit-level over a pure function

The tests prove the refusal logic and the denylist hardening. They do not prove
the eventual route, the UI, the run-id provenance seam, or the runtime effect
gate. The integration tests listed as "future work" in `design.md` are not
present.

### R10. The package's `eligible` flag can be misread

`eligible: true` means "the safety case is complete enough to ask a human". It
does **not** mean the tool is safe, authorized or active. Every result also
carries `granted: false`, `requiresOperator: true`, `autoApply: false` and
`selfRenewable: false`, but a UI could still render eligibility as a green light.

Mitigation: the UI must present the result as "ready for review", never "ready to
enable".

## Deliberately not built

| Not built | Why |
|---|---|
| Autonomous widening (Option A) | 89% reported lifetime rejection; tool additions are unmeasurable; financial blast radius; audit expects a human owner. |
| A widening grant store with expiry (Option C) | Requires runtime wiring at the surface resolver; premature before the evidence seam and tool contracts exist. |
| A new capability kind for tools | The capability builder deliberately hands effectful kinds to their existing owner (`builder.py:193-207`); adding a second builder would violate "reuse before rebuild". |
| Relaxing `validate_snapshot` to admit tool additions | That is the measurement prerequisite, and it is a security-sensitive change. It must be paired with an independent evaluator, not smuggled in with a proposal formatter. |
| A route/UI for the package | Keeps runtime and API blast radius at zero in this change. |
| Tool contract enforcement (Option D) | Long-term foundation; needs tool-by-tool metadata and a call-time checker. |
| Financial-action tools | Out of scope by constraint 6. |
| Self-renewal or automatic re-issue | Explicitly forbidden by constraint 5 and this design. |
| Editing `jdds.db` or any seed data | No relationship to this change. |
