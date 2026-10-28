# Corrections to the brief

Every claim below was checked against the repository at the time of writing.
Where the code disagrees with the brief, the code wins.

## Claim-by-claim

### 1. "The denylist constant includes the field that carries tool names (`toolNames`)."

**True.** `_NEVER_AUTO_FIELDS` is a `frozenset` that contains `"toolNames"`,
along with `modelProvider`, `modelName`, `temperature` and `skillDraftIds`
(`python/harness/self_improvement/autonomy.py:37-43`).

Naming correction: this is **not a target-path denylist**. It is the set of
surface fields that can never be automatic. The target-path denylist is
`RSL_DENY_GLOBS` in `python/harness/self_improvement/security.py:18-41`.

### 2. "`classify_snapshot_risk` maps the 'tool added' change class to L2."

**True.** A tool present in the candidate but not the base sets `risk = L2` and
adds the reason `tool_added` (`python/harness/self_improvement/autonomy.py:75-79`).
The result is also forced to L2 if the changed-field set intersects
`_NEVER_AUTO_FIELDS` (`autonomy.py:100-102`).

### 3. "`decide()` refuses L2 unconditionally — no evidence, threshold or quality score can make that branch return 'allow'."

**True.** `decide()` appends `risk_L2_requires_human` for L2 and returns
`allowed: not reasons` (`python/harness/self_improvement/autonomy.py:206-211`,
`autonomy.py:239-248`). No evidence argument participates in the risk branch.

Important nuance the brief misses: **`decide()` trusts its `risk` argument.** It
does not re-classify the candidate. The L2 refusal is only as strong as the
caller's classification. `auto_apply_surface` does call
`classify_snapshot_risk` before deciding (`python/harness/self_improvement/loop.py:318`,
`loop.py:337-346`), but the operator route can pass a risk string directly
(`python/harness/routers/evolution_autonomy.py:47-69`). A defence-in-depth
design should not assume every caller classifies correctly.

### 4. "`PURE_KINDS` is something like `{"recipe", "report_template"}`, and any other kind requires `operator=True`."

**Mostly true, but the gate is in the wrong function.** `PURE_KINDS` is exactly
`frozenset({"recipe", "report_template"})`
(`python/harness/capabilities/manifest.py:23`).

However, `build()` does **not** take an `operator` argument. A non-pure kind is
routed to a typed hand-off and returns `handoff_required`; it is not built at
all (`python/harness/capabilities/builder.py:186-207`). The `operator=True`
requirement lives in `activate()` for effectful/global manifests
(`builder.py:322-341`), in `promote()` (`builder.py:445-464`) and in
`rollback()` (`builder.py:362-395`). So the correct statement is: *the builder
hands effectful kinds to their existing owner; activation of anything outside
the pure read set requires an operator.*

### 5. "Whether anything else in the tree already has a notion of a scoped/graded grant."

**It does — three of them, none of which reaches tool-surface widening.**

- `StandingGrant` is an operator-created, `(kind, scope, pattern)`-scoped,
  revocable "always allow" record (`python/harness/grants.py:1-23`,
  `grants.py:40-53`, `grants.py:134-137`). It removes a prompt; it does not
  change a tool allowlist. It has **no expiry column** (`grants.py:40-53`).
- `AutonomyEnvelope` is time-boxed, revocable, risk-ceilinged and
  action-class-scoped; an unparseable expiry fails closed
  (`python/harness/recovery/envelope.py:115-138`, `envelope.py:140-194`).
- A2A envelopes carry a `ttl` and an `is_expired()` check
  (`python/harness/a2a/model.py:308-313`).

So the gap is not "no scoped-grant vocabulary exists". The gap is: **there is
no path that converts measured evidence into a scoped tool-surface grant, and
no expiry/revocation record for a widened tool set.**

## Corrections the brief did not ask for but that change the design

### A. The loop cannot measure a tool addition at all through the normal path.

This is the most important correction. `validate_snapshot()` refuses any tool
in the candidate that is not already in the base allowlist, with
`SNAPSHOT_TOOL_NOT_IN_BASE`
(`python/harness/evaluation/candidate_invoker.py:61-99`, especially
`candidate_invoker.py:76-81`). The verifier calls the same check
(`python/harness/self_improvement/verifier.py:287-293`), and the operator surface
experiment route validates before the candidate is even stored
(`python/harness/routers/evolution.py:1099-1102`).

Consequence: the brief's statement that the loop "computes the evidence that
the fix works" for the tool-addition class is **not true end to end**. The
paired-evidence code in `auto_apply_surface` would run if a stored surface
candidate already contained a tool addition
(`python/harness/self_improvement/loop.py:318-354`), but the normal creation and
verification paths structurally prevent such a candidate from existing. The
evidence is not "computed and discarded"; it is **uncomputable through the
supported candidate path**. A design that only persists existing evidence would
therefore persist nothing.

### B. The self-improvement loop does not invent tool additions.

`propose_many` is explicitly operator/agent-supplied operations; it "never
invents a patch, never calls a model and never persists"
(`python/harness/self_improvement/proposer.py:191-223`, `proposer.py:216-233`).
The surface lab varies `toolGuidance` while copying `toolNames` unchanged
(`python/harness/self_improvement/surface_lab.py:91`, `surface_lab.py:105`,
`surface_lab.py:122`, `surface_lab.py:139`, `surface_lab.py:152`,
`surface_lab.py:425-436`, `surface_lab.py:480-487`). So a tool-widening
proposal today comes from a human or an agent-authored surface experiment, not
from the loop's own search.

### C. The frozen target denylist is incomplete and is overridable.

**Before this change**, `RSL_DENY_GLOBS` protected `evaluation/**`,
`security/**`, code policy, tests, `.env` and `jdds.db`. It did **not** protect:

- `python/harness/self_improvement/**` — the autonomy gate, the risk
  classifier, the proposer and the verifier,
- `python/harness/capabilities/**` — the capability builder and manifest,
- `python/harness/grants.py`,
- `python/harness/recovery/envelope.py`.

**Before this change**, `assert_landable_target()` also accepted an optional
`deny_globs` parameter that replaced the frozen list for that call. No current
caller passed it, but the API made the "frozen" list configurable. Both facts
violate the brief's constraints 4 and 5 as written.

The patch in this change adds the four missing protected paths (the current list
is `security.py:18-41`) and removes the override parameter (the current
signature is `security.py:68-94`). A caller can no longer narrow the denylist.

### D. `_NEVER_AUTO_FIELDS` is a field set, not a subject denylist.

Already stated above. Recorded because the brief calls it "a denylist constant"
and that ambiguity matters when reasoning about what is structurally
unreachable.

## Claims marked UNVERIFIED

- The ~89% lifetime rejection rate, the 57-candidate / 2-accepted / 52-rejected
  split, the 562 learning reviews and the 18 memory records are from the running
  instance's self-report supplied with this task. They are not asserted by any
  file read here. Treat them as **reported, not code-verified**.
- No claim is made here about the production frequency of tool-widening
  proposals. The code path that would create one is refused before storage, so
  production counts cannot be inferred from the code alone.
