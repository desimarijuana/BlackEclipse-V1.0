# Diagnosis: is the evidence discarded, and who pays?

**Verdict: partially confirmed, but for a different and more serious reason than
the brief states. The human is indeed doing research from scratch. The loop is
not holding a discarded safety case; in the tool-addition case it cannot build
one at all.**

## What is true

1. **The autonomy layer classifies tool addition as L2 and refuses it.**
   `classify_snapshot_risk` sets L2 when the candidate has a tool the base does
   not (`python/harness/self_improvement/autonomy.py:75-79`), and `decide`
   refuses L2 with `risk_L2_requires_human`
   (`python/harness/self_improvement/autonomy.py:206-211`).

2. **The runtime computes measurable evidence before that decision.**
   `auto_apply_surface` reads the stored base and candidate, computes paired
   per-task rates with `paired_bootstrap`, runs regression detection, and passes
   the result into `decide_autonomy`
   (`python/harness/self_improvement/loop.py:318-346`). On refusal it returns
   the risk, the paired result and the decision to the caller
   (`loop.py:347-354`); the route returns that JSON to the operator
   (`python/harness/routers/evolution_autonomy.py:71-84`). It does not persist a
   proposal package. So when this path is reached, the evidence is computed,
   returned once, and then only exists in the HTTP response.

3. **The human does not receive a ready-made case.** There is no record type,
   route or file that packages "tool X, on this failure, with this replay
   evidence, this blast radius, this expiry and this revocation path" for
   ratification. The capability builder has a manifest, verification report and
   capability record for **recipes**
   (`python/harness/capabilities/builder.py:262-319`), but that is a different
   subject: a generated read-only recipe, not a widened tool allowlist. The
   surface-experiment UI shows a diff (`python/harness/routers/evolution.py:537-559`)
   but not a safety case.

4. **The operator gate is real and layered.** The pure recipe path auto-activates
   only when `effect == "read"`, `kind in PURE_KINDS` and `scope == "workspace"`
   (`builder.py:289-299`). Effectful kinds are handed off to their existing owner
   (`builder.py:193-207`); activation of an effectful/global capability requires
   `operator=True` (`builder.py:322-341`). `StandingGrant` is operator-only,
   scoped and revocable (`python/harness/grants.py:1-23`, `grants.py:134-137`).
   None of this is a self-grant path.

## What the brief gets wrong

**The evidence is not merely discarded; it is uncomputable for a tool addition
through the supported path.**

`validate_snapshot` refuses a candidate whose `toolNames` contains anything not
in the base:

- `python/harness/evaluation/candidate_invoker.py:76-81`:
  `extra_tools = sorted(set(candidate.toolNames) - set(base.toolNames))` →
  `SNAPSHOT_TOOL_NOT_IN_BASE`.
- The verifier applies the same check before running anything
  (`python/harness/self_improvement/verifier.py:287-293`).
- The operator surface-experiment route applies it before the candidate is
  stored (`python/harness/routers/evolution.py:1099-1102`).

So a tool-addition candidate cannot be created, cannot be benchmarked, and
cannot reach `auto_apply_surface` unless someone writes the row directly into
the store. The paired-bootstrap code in `loop.py:318-346` is therefore dead for
this class in normal operation. Any design that says "surface the evidence the
loop already computed" would surface nothing.

**The loop does not invent tool additions.** `propose_many` validates
caller-supplied operations and explicitly "never invents a patch"
(`python/harness/self_improvement/proposer.py:191-223`). The surface lab varies
`toolGuidance` and copies `toolNames` unchanged
(`python/harness/self_improvement/surface_lab.py:91`, `surface_lab.py:105`,
`surface_lab.py:122`, `surface_lab.py:139`, `surface_lab.py:152`,
`surface_lab.py:480-487`). So "the loop knows what it learned" is true for
lessons/guidance, but not for the actual added tool. The tool is chosen by a
human or an agent-authored experiment, not by the self-improvement loop.

## The cost, stated more precisely than the brief

The brief says the cost is that "the human is not ratifying a prepared safety
case — they are doing the research from scratch." That is correct, but the
reason is not a short circuit at `decide`. The reason is that the system has no
**subject** for a tool-widening safety case:

- `HarnessSnapshot.toolNames` is just a tuple of names; it carries no
  preconditions, no blast-radius declaration, no deny-path test, no expiry, and
  no evidence provenance (`python/harness/self_improvement/models.py:44-70`).
- `validate_snapshot` is an all-or-nothing base-allowlist check, not a contract
  on the added tool (`candidate_invoker.py:61-99`).
- The capability manifest has `effect`, `permissions`, `imports`, `tests` and
  `acceptance` for recipes (`python/harness/capabilities/manifest.py:45-106`),
  but tools are handed off, not built and never measured by the capability
  builder (`builder.py:193-207`).

Therefore, the ten-second operator approval the brief wants cannot be produced
from current records. The operator must still answer: *which* tool, *why* this
failure, *what* it would have done on historical runs, *what* it refuses, *how
long* it lasts, and *how to undo it*. None of those answers exists as a
first-class record.

## What the observed rejection rate changes

The running instance reports 57 learning candidates, 2 accepted and 52 rejected
(~89% lifetime rejection), with one recent replay timeout and one
"front-door reachability check, not a reusable recovery". That is not code
evidence, but it is highly relevant: **the loop's proposal judgement is the
weakest link, not the operator's throughput.** A design that lowers the
operator's review cost is useful. A design that lowers the evidence bar because
the loop is "confident" would be selecting on the loop's worst behaviour.

## Bottom line

- The brief's safety observation is right: the human gate is the feature.
- The brief's mechanism is wrong: tool additions are refused before
  measurement, not after.
- The actual defect is a **missing evidence contract and a missing ratification
  artifact**, plus a **frozen denylist that (before this change) did not cover
  the self-improvement and capability machinery and could be overridden by a
  caller**. The patch adds those protected paths (current list:
  `python/harness/self_improvement/security.py:18-41`) and removes the override
  parameter (current signature: `security.py:68-94`).

That is the gap the design and patch address.
