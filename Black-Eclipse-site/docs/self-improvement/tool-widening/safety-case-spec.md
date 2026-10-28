# Safety-case specification: widening an agent's tool set by one read/compute tool

This is a checkable specification. Every requirement is written so it can fail,
and every failure has a stable reason code. The implementation in
`python/harness/self_improvement/widening.py` enforces the machine-checkable
subset and records the rest as human-review items. **The function never grants
anything.** It returns a package with `granted: false`, `requiresOperator: true`
and `selfRenewable: false`.

## 0. Subject and scope

A *widening case* is a proposal to add **exactly one** tool name to an agent's
declared `toolNames` for **one scope** (one agent or `global`), for a bounded
period.

In scope: read and compute tools whose declared metadata says
`permission == "read"`, `risk in {"none", "low"}`, `effect in {"", "read"}`.

Out of scope, structurally:

- any financial-action tool (order placement, cancellation, transfer,
  withdrawal, deposit, trade execution, broker connection);
- any tool that can modify instructions, permissions, policy, guards, grants,
  the autonomy envelope, the capability builder, MCP approvals, or this module;
- any effectful tool (`write` / `external_action`) regardless of how narrow it
  looks;
- any tool on the frozen exclusion list (below);
- more than one tool per case (two tools require two cases, so a reviewer can
  reject one without rejecting the other).

The tool's metadata is a mandatory input. Missing or contradictory metadata is
a refusal, never a default.

## 1. Frozen exclusion list

These are structural, not configurable, and cannot be overridden by a caller:

| Class | Match | Why |
|---|---|---|
| Financial actions | name contains `place_order`, `submit_order`, `cancel_order`, `modify_order`, `transfer`, `withdraw`, `deposit`, `execute_trade`, `trade_execute`, `send_payment`, `fund_transfer` | Out of scope entirely. |
| Mechanism tools | name starts with `capability_`, `skill_`, `grant_`, `autonomy_`, `rsl_`, `mcp_`, `plugin_install`, `code_`, `command_`, `shell_`, `terminal_`, `execution_`, `fabric_`, `approval_`, `policy_`, `security_` | Widening must never widen itself or the authority layer. |
| Effectful metadata | `permission != "read"` or `effect not in {"", "read"}` | Least privilege. |
| High risk | `risk not in {"none", "low"}` | Least privilege. |

The same frozen principle applies to the RSL **target** denylist: a code change
that would edit this module, the autonomy gate, the capability builder, the
grant store or the recovery envelope must be refused by
`assert_landable_target` (`python/harness/self_improvement/security.py`).

**Failure mode if absent:** the loop could propose a tool that places an order,
or a tool that edits the gate that approves the proposal. Both are
non-recoverable in the financial sense.

## 2. Demonstrated need

All of the following must be true.

| ID | Requirement | Threshold | Failure mode |
|---|---|---|---|
| N1 | A named failure signature is present and non-empty. | `len > 0` | The proposal is a preference, not a fix (`WIDENING_NEED_UNNAMED`). |
| N2 | The failure recurred. | `occurrences >= 3` | One-off anomaly becomes permanent capability (`WIDENING_NEED_TOO_FEW_OCCURRENCES`). |
| N3 | The failure spans distinct sessions. | `distinctSessions >= 3` | One bad session over-fits the tool set (`WIDENING_NEED_TOO_FEW_SESSIONS`). |
| N4 | The failure spans distinct tasks. | `distinctTasks >= 2` | A single task shape is mistaken for a class (`WIDENING_NEED_TOO_FEW_TASKS`). |
| N5 | The current tool set demonstrably cannot serve it. | A non-empty `existingToolsCannotServe` statement, plus an empty (or below-threshold) capability-index match list. | The tool is redundant; the real fix is guidance or routing (`WIDENING_NEED_NOT_DEMONSTRATED`). |
| N6 | The evidence set is identified. | Non-empty `evidenceRunIds`. | The claim is unauditable (`WIDENING_EVIDENCE_IDS_MISSING`). |

`existingToolsCannotServe` is **human judgement** in its prose, but the
machine-checkable part is the recorded absence of a matching capability. The
case must carry the query and the result, not just the conclusion.

## 3. Demonstrated safety

### 3.1 Holdout discipline

| ID | Requirement | Threshold | Failure mode |
|---|---|---|---|
| S1 | Derivation runs and validation runs are disjoint. | Empty intersection | The loop selects the runs that flatter the proposal (`WIDENING_EVIDENCE_NOT_DISJOINT`). |
| S2 | There is a holdout set. | `validationRunIds >= 2` | The proposal is selected and validated on the same data (`WIDENING_TOO_FEW_VALIDATION_RUNS`). |
| S3 | Derivation and validation task sets are disjoint. | Empty intersection | The same task shape can be counted twice (`WIDENING_TASKS_NOT_DISJOINT`). |
| S4 | All evidence predates the proposal. | `max(completedAt) <= proposedAt` | Back-filled or post-hoc runs launder the result (`WIDENING_EVIDENCE_POSTDATES_PROPOSAL`). |

S4 is checkable at the seam that supplies timestamps, not by a pure function
that receives only ids. The implementation records the timestamps and requires
the caller to pass them; the pure function checks ordering.

### 3.2 Replay of historical runs where the tool would have fired

| ID | Requirement | Threshold | Failure mode |
|---|---|---|---|
| S5 | Enough historical runs were replayed. | `replay.runs >= 5` | Anecdote replaces evidence (`WIDENING_REPLAY_TOO_FEW_RUNS`). |
| S6 | The tool would actually have fired. | `toolWouldHaveFired >= 1` | A tool that never fires passes trivially; this is the "refuse to act" gaming path (`WIDENING_REPLAY_TOOL_NEVER_FIRED`). |
| S7 | Every firing passed its task. | `passed >= toolWouldHaveFired` | The tool fires and makes answers worse (`WIDENING_REPLAY_FAILED`). |
| S8 | No critical regression. | `criticalRegressions == 0` | The fix trades a small win for a safety loss (`WIDENING_CRITICAL_REGRESSION`). |
| S9 | A negative control exists. | `notNeededControlsPassed >= 2` | The tool changes answers even when it should not fire; it is not scoped (`WIDENING_NEGATIVE_CONTROL_FAILED`). |
| S10 | Evidence is fresh. | `evidenceFreshness == "fresh"` and age <= 14 days | Stale evidence describes a system that no longer exists (`WIDENING_EVIDENCE_STALE`). |

### 3.3 Deny path

The added tool must be shown to refuse an input outside its declared purpose.

| ID | Requirement | Threshold | Failure mode |
|---|---|---|---|
| S11 | A deny-path test exists. | `denyPathTested == true` | The tool is unbounded in practice (`WIDENING_DENY_PATH_UNTESTED`). |
| S12 | The deny-path test refused. | `denyPathRefused == true` and the refusal is a typed error, not an empty answer | Out-of-scope input is silently accepted (`WIDENING_DENY_PATH_FAILED`). |

The deny-path test must name the out-of-scope input and the observed refusal
code. "It did not crash" is not a deny path.

### 3.4 Conclusion stability

| ID | Requirement | Threshold | Failure mode |
|---|---|---|---|
| S13 | Prior conclusions are recorded before replay. | `conclusionDigestsBefore` non-empty | No baseline, so drift is invisible (`WIDENING_CONCLUSION_EVIDENCE_MISSING`). |
| S14 | Conclusions after replay are recorded. | `conclusionDigestsAfter` non-empty | The comparison cannot be made (`WIDENING_CONCLUSION_EVIDENCE_MISSING`). |
| S15 | New access does not silently change prior conclusions. | Sorted before == sorted after, or every difference is explicitly listed in `expectedConclusionChanges` and is not a financial claim | The tool changes earlier answers without anyone noticing (`WIDENING_CONCLUSIONS_CHANGED`). |

The digest is over the **conclusion**, not the prose. A formatting change does
not count. A changed number, rating, recommendation or classification does.

### 3.5 Blast radius

| ID | Requirement | Threshold | Failure mode |
|---|---|---|---|
| B1 | One tool only. | `len(addedTools) == 1` | Scope creep (`WIDENING_TOO_MANY_TOOLS`). |
| B2 | The tool is registered. | Present in the live registry | The proposal references a phantom (`WIDENING_TOOL_UNKNOWN`). |
| B3 | The tool is not already present. | Not in `baseTools` | No-op proposal wastes review (`WIDENING_TOOL_ALREADY_PRESENT`). |
| B4 | Metadata is complete and read-only. | `permission == "read"`, `effect in {"", "read"}`, `risk in {"none","low"}` | Effectful tool enters a read lane (`WIDENING_TOOL_OUT_OF_SCOPE`). |
| B5 | Scope is the narrowest. | `workspace` scope by default; `global` requires a separate operator decision | A local need becomes every agent's capability (`WIDENING_SCOPE_NOT_NARROWEST`). |
| B6 | A call budget is declared. | `maxCallsPerDay > 0` and bounded | The tool can be used without limit (`WIDENING_NO_CALL_BUDGET`). |

## 4. Machine-checkable versus human judgement

**Machine-checkable by the pure function:**

- N1–N4, N6
- S1–S2, S3, S5–S8, S10–S15
- B1–B4, B6
- every frozen exclusion in §1
- the presence and type of every evidence field

**Machine-checkable at the seam, with timestamps supplied by it:**

- S4 (all evidence predates the proposal)
- S9 (negative controls are actual runs, not assertions)
- B2 (the registry is the authority)
- B5 (scope is compared to the current agent configuration)

**Human judgement, recorded as explicit review items:**

- N5: whether the existing tools genuinely cannot serve the need.
- Whether the named failure and the replay failures are the same class.
- Whether the chosen tool is the narrowest available.
- Whether the deny-path input covers the realistic dangerous cases.
- Whether a conclusion change is acceptable and non-financial.
- Whether the blast radius (data, cost, latency, downstream readers) is
  acceptable for this workspace.

The package must show these as `humanReview` items with the evidence attached.
It must never mark them "passed" mechanically.

## 5. Anti-gaming rules

| Attack | Rule that stops it |
|---|---|
| Pick the runs that flatter the proposal | S1, S2, S3: disjoint derivation/validation, disjoint task sets. |
| Cherry-pick within the window | `excludedRunIds` must be empty or every exclusion must be listed with a reason and surfaced to the reviewer (`WIDENING_CHERRY_PICK`). |
| Satisfy the metric by refusing to act | S6: `toolWouldHaveFired >= 1`; S7: every firing must pass. |
| Satisfy the metric by always firing | S9: negative controls must pass without firing. |
| Inflate the sample with near-duplicate runs | Distinct `runId` values; duplicate ids are refused (`WIDENING_DUPLICATE_EVIDENCE`). |
| Use runs generated after the proposal | S4: timestamps must predate `proposedAt`. |
| Hide a changed conclusion in a different task | S15 compares the whole replay set, not only the firing runs. |
| Widen via prompt/guidance instead of `toolNames` | This specification is about `toolNames`; a `toolGuidance` change that tells the model to call an unlisted tool is **not** a widening and must not be counted as satisfying it. The tool must be in `toolNames` and registered. |
| Renew without new evidence | `selfRenewable: false`; a renewal is a fresh case with its own evidence window (`renewalRequiresNewEvidence: true`). |
| Grant more than was asked | `maxAddedTools: 1`; the package's `addedTools` is exact. |

## 6. Minimum sample sizes and insufficient evidence

- Fewer than 3 occurrences of the failure: **refuse** (`WIDENING_NEED_TOO_FEW_OCCURRENCES`).
- Fewer than 3 distinct sessions: **refuse**.
- Fewer than 2 distinct tasks: **refuse**.
- Fewer than 5 replay runs: **refuse**.
- Fewer than 2 validation runs: **refuse**.
- Fewer than 2 negative controls: **refuse**.
- Any missing evidence field: **refuse**; never substitute a default.
- Evidence older than 14 days: **refuse**.

There is no "unknown = allow" path. Unknown is a refusal reason
(`WIDENING_EVIDENCE_UNKNOWN`).

## 7. Ratification, expiry and revocation

The package is not a grant. If an operator ratifies it, the existing operator
surfaces own the actual change (agent preset / surface activation / capability
activation). The package must carry:

| Field | Requirement |
|---|---|
| `proposedBy` | The run or actor that assembled the case. |
| `proposedAt` | Timestamp. |
| `evidenceCutoff` | The newest evidence timestamp accepted. |
| `addedTools` | Exactly one name. |
| `scope` | Agent id or `global`. |
| `proposedTtlDays` | 14 days maximum. |
| `expiresAt` | `null` until ratification; if set later, it is absolute. |
| `selfRenewable` | `false`. |
| `revocation` | `{"path": "operator surface that removes the tool", "audited": true}`. |
| `autoApply` | `false`. |

A ratified widening must be removable without a code change (edit the agent
preset or deactivate the capability), and the removal must be auditable. A
ratified widening that cannot be revoked is not ratifiable.

**Failure mode if expiry is absent:** a temporary experiment becomes the
permanent default. The existing `StandingGrant` store has no expiry column
(`python/harness/grants.py:40-53`), which is why this specification does not
reuse it for widening.

## 8. Refusal contract

Every refusal names all failed requirements, not the first one. The package
returns:

```json
{
  "status": "refused",
  "eligible": false,
  "granted": false,
  "requiresOperator": true,
  "selfRenewable": false,
  "reasons": ["WIDENING_NEED_TOO_FEW_SESSIONS", "..."],
  "missing": ["..."],
  "humanReview": ["..."],
  "proposedTtlDays": 14,
  "expiresAt": null
}
```

An `eligible: true` result still has `granted: false` and
`requiresOperator: true`. Eligibility means "the safety case is complete enough
to ask a human", not "the tool is authorized".

## 9. What this specification deliberately cannot prove

- That the named failure is the *real* cause. That is a human judgement.
- That the replay corpus is representative of production. It bounds the claim,
  it does not eliminate distribution shift.
- That the tool's implementation has no side channel (network, clock, file
  access). That must be enforced by the tool's own contract and the runtime's
  effect gate.
- That a ratifying human understood the case. The audit trail records who and
  when; it cannot record comprehension.

These residual gaps are listed again in `risks.md`.
