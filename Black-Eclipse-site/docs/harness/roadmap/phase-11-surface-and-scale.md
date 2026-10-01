---
title: "Phase 11 — Surface and Scale"
status: Done
phase: 11
depends_on: [6, 10]
unlocks: []
last-verified: 2026-10-01
---

# Phase 11 — Surface and Scale

|||
|---|---|
| **Depends on** | Phase 6 (the job model and the `DeliveryAdapter` protocol) and Phase 10 (self-modification gated before more surfaces exist) |
| **Unlocks** | — (the last capability phase before the Phase-12 standing gate) |
| **Estimated work** | 8–14 h of agent time |
| **Deliverable type** | 2 new delivery adapters + a backend interface + scope-awareness across surfaces + runbooks + `doctor.js` probes |
| **New ADRs** | ADR-H113 |
| **Prompt to copy** | [§11 below](#11-implementation-prompt-copy-this-to-opencode) |

**ADR numbering.** This phase takes **ADR-H113**. The harness series in
`docs/harness/decisions.md` ends at ADR-H92; the roadmap's provisional
`ADR-H102` for this subject is superseded by the contiguous allocation H103–H114
across Phases 0, 2, 4, 5, 6, 7, 8, 9 and 10. The ADR text uses the repo's shape —
`## ADR-H113 — Title` followed by **Decision.** / **Why.** / **Consequences.**,
never "Impact".

## Contents

- [1. Goal](#1-goal)
- [2. Why this phase exists (what is already defined and unused)](#2-why-this-phase-exists-what-is-already-defined-and-unused)
- [3. In scope](#3-in-scope)
- [4. Who can use it (the non-expert obligation)](#4-who-can-use-it-the-non-expert-obligation)
- [5. Non-goals (do not do these)](#5-non-goals-do-not-do-these)
- [6. Exact contracts to create](#6-exact-contracts-to-create)
  - [6.1 The messaging adapter — the third `DeliveryAdapter`](#61-the-messaging-adapter--the-third-deliveryadapter)
  - [6.2 The saved report artifact — `.black-eclipse/artifacts/<runId>/`](#62-the-saved-report-artifact--black-eclipseartifactsrunid)
  - [6.3 The per-target outcome record](#63-the-per-target-outcome-record)
  - [6.4 Scope awareness for every new surface](#64-scope-awareness-for-every-new-surface)
  - [6.5 The execution backend — `SandboxBackend` (local / container / remote)](#65-the-execution-backend--sandboxbackend-local--container--remote)
  - [6.6 Packaging — zero-config stays intact (`scripts/doctor.js`)](#66-packaging--zero-config-stays-intact-scriptsdoctorjs)
  - [6.7 Operational runbooks](#67-operational-runbooks)
  - [6.8 Plain language](#68-plain-language)
- [7. Work items (ordered)](#7-work-items-ordered)
- [8. Deliverables](#8-deliverables)
- [9. Acceptance gates](#9-acceptance-gates)
- [10. Definition of done](#10-definition-of-done)
- [11. Implementation prompt (copy this to OpenCode)](#11-implementation-prompt-copy-this-to-opencode)

## 1. Goal

Make every surface the harness now has behave the same way, and make the
harness's own claims about itself remain true as it grows:

1. **More ways out.** A job's result can reach the user where they actually are —
   in the app, as a saved report, or as a message — through **one** adapter
   interface.
2. **Scope-aware everywhere.** Every new surface (jobs, code tasks, artifacts,
   code workspaces) carries the same scope labels the existing routes already
   carry, and an isolation test proves one scope cannot read another's work.
3. **An execution backend that can move.** The command broker gains a documented
   `SandboxBackend` interface with three implementations — local OS, container,
   remote — each declaring its guarantees, and the honest-failure rule unchanged.
4. **Zero-config still works.** A fresh clone runs `npm install && npm run dev`
   with no manual steps; a missing backend degrades to a clear refusal.
5. **A runbook per surface**, so adding a job or a kit is a documented procedure
   rather than tribal knowledge.

## 2. Why this phase exists (what is already defined and unused)

Phase 6 built the shape and left it deliberately unfinished. Verified:

| Already exists | What it defines | What is missing |
|---|---|---|
| `python/harness/jobs/delivery.py` | `DeliveryAdapter` Protocol (`name`, `deliver(job, run_id, summary) -> DeliveryOutcome`) | one implementation ships as `in_app` + `artifact` per the phase file; the phase file itself names **messaging as Phase 11** |
| `src/lib/alerts/notifier.ts` | the TS notification surface | nothing consumes it for a job's delivery outcome |
| `research/receipt.py` | a bounded `ResearchReceipt` | no on-disk artifact path for a job's report |
| `python/harness/deps.py` | `identity_boundary`, `deployment_exposure`, `require_operator`, `actor_for` | the newer surfaces do not yet carry scope labels through |
| `python/tests/test_identity_tenancy_boundary.py` | the honest boundary: `authentication=False`, `multiUserSafe=False`, `tenancy="single-user-local"`, `scopeFiltering="caller-supplied-labels"` | no isolation test for jobs / code tasks / artifacts |

Three concrete gaps:

1. **The delivery interface has one shape and few implementations.** A job that
   runs at 07:30 and produces a good report still only lands where the app can put
   it. The user asked for a message; the interface exists and nothing answers it.
2. **The honesty boundary is stated but not tested per surface.** The app correctly
   says it is **not** multi-user safe. That statement is only worth something if
   the new surfaces are also *scope-aware and tested* — otherwise "not multi-user
   safe" quietly becomes "not even scope-aware", which is worse.
3. **The broker is welded to the local OS.** `code/sandbox.py` is one bounded
   execution primitive on this machine. Nothing documents what a *different*
   backend would have to guarantee, so nobody can add one without guessing.

**Explicitly additive.** This phase **adds adapters and a backend interface**; it
does not refactor the job model (README §3.1 — one runtime, and Phase 6's ADR
owns the model). If a change to `jobs/model.py` looks necessary, the correct
outcome is an honest partial report naming it, not a redesign.

## 3. In scope

1. A messaging `DeliveryAdapter` whose user-facing copy comes from i18n keys.
2. The saved-report artifact under `.black-eclipse/artifacts/<runId>/`, reusing
   the receipt rendering.
3. Per-target delivery outcomes recorded on the job run row — one row per
   configured target, never one rolled-up boolean.
4. Scope awareness (`userId` / `scopeId`) on jobs, code tasks, artifacts and code
   workspaces, plus a cross-tenant isolation test mirroring
   `python/tests/test_identity_tenancy_boundary.py`.
5. `SandboxBackend` — a documented interface with `local` / `container` / `remote`
   implementations, each declaring its guarantees.
6. `scripts/doctor.js` probes for the new runtime dependencies, with a repair path
   and a clear refusal when a backend is missing.
7. Operational runbooks: how to add a job, how to add a kit, how to inspect a
   failed code task.

## 4. Who can use it (the non-expert obligation)

This is the phase where the harness stops being something you *open* and becomes
something that *reaches you* — so the audience rule is tested harder than anywhere
else: **a message must read like a colleague's message, not like a system log.**

1. **The destination is a human choice, in human words.** The user picks
   *"In the app"*, *"Save it as a report"*, or *"Send it to my phone"* — never
   `in_app` / `artifact` / `messaging`. The adapter name is data behind "details".
2. **A delivered message names the finance job**, never the mechanism: *"Your
   overnight market brief is ready — 3 things changed."* Never a run id, a job id,
   a skill id, a duration in milliseconds or a delivery outcome code.
3. **A delivery failure is a plain sentence with a next step.** *"I finished the
   brief but could not reach your phone. It is saved in the app — open it there, or
   try sending again."* The machine reason (`DELIVERY_FAILED`, a transport error)
   lives behind the same "details" affordance as every other refusal.
4. **A missing backend refuses, it never improvises.** When a job needs a kind of
   execution that is not available, the user reads *"This job needs a way to run
   its work that is not set up on this machine. I did not run it."* — and the
   harness does **not** fall back to a less safe path (README §3.5).
5. **Nothing claims multi-user safety.** The app states what it is: local,
   single-user, scope labels are caller-supplied filters and never authentication.
   A scope-separated view never becomes a security claim in the UI.
6. **Every new user-facing string is an i18n key** in `src/lib/i18n/` —
   `dictionaries/en.ts` holds the canonical keys, `dictionaries/index.ts` the
   translations, `translate.ts` the lookup, `use-t.ts` the hook. This matters here
   more than usual: a message sent to a person's phone in a language they did not
   choose is the most visible possible translation failure. Nothing is hardcoded
   in a component or in the Python that composes the message text — the runtime
   sends a **key plus parameters**, and the surface renders it.
7. **A mechanism denylist exists as data**, not as reviewer taste:
   `policy.PLAIN_LANGUAGE_DENYLIST` in `python/harness/code/policy.py` contains
   `sandbox`, `worktree`, `workspace`, `allowlist`, `autonomy`, `digest`, `argv`,
   `cwd`, `stderr`, `stdout`, `patch`, `diff`, `manifest`, `operator`,
   `policy engine`, `tool registry`, `exit code`, `verification ledger`, `repo`,
   `repository`, `commit`, `branch`, `head`. The gate over it is **G7** in §9.
8. **Who receives what, and in what words:**

| Who | What reaches them | What they never meet |
|---|---|---|
| Analyst / journalist | "Your filing watch found 2 new filings" with a link into the app | the adapter name, the run id |
| Portfolio manager / advisor | "Overnight brief is ready — 3 things changed" | the delivery outcome code |
| Trader / risk officer | "The risk check could not run — here is what to fix" | the backend name, a container image |
| Accountant / controller | a saved report artifact with its receipt | `receipt` as a word; the artifact path |
| Student / teacher | one sentence explaining what was checked | the trace ids |
| Small-business owner | a message that says whether anything needs attention | `SANDBOX_UNAVAILABLE` |
| Software engineer in finance | the full per-target outcomes, the backend's declared guarantees, the run trace | nothing, on request |

## 5. Non-goals (do not do these)

- **No refactor of the job model.** Phase 6 defined `DeliveryAdapter`; this phase
  adds implementations and nothing else. `jobs/model.py` changes only to carry a
  scope label, and only additively.
- **No cloud multi-tenancy, no accounts, no auth provider.** The app remains
  single-user local; this phase makes the *scope labels* consistent and tested, and
  changes no honesty claim.
- **No weakening of the sandbox rule.** A missing/unsupported backend refuses; it
  **never** degrades to unsandboxed execution. `SANDBOX_UNAVAILABLE` stays a
  first-class, user-visible refusal.
- **No new scheduler, no distributed execution.** One process, one broker.
- **No new required dependency for a fresh clone.** A container backend is
  optional and detected, never installed implicitly.
- **No message body that carries data the user did not ask to receive.** A
  message carries the job's own summary, rendered from a key; it is never a
  free-form channel for model prose.
- **No secrets in a message or an artifact.** The secret posture is unchanged.
- Do not commit, push, or open a PR. Do not commit `jdds.db`.

## 6. Exact contracts to create

### 6.1 The messaging adapter — the third `DeliveryAdapter`

Phase 6's protocol is reused unchanged:

```python
class DeliveryAdapter(Protocol):
    name: str
    async def deliver(self, job: JobDefinition, run_id: str,
                      summary: DeliverySummary) -> DeliveryOutcome: ...
```

This phase adds `messaging`:

```python
class MessagingDelivery:
    """Send the job's summary to the user's chosen destination.

    The body is a TEMPLATE KEY plus parameters — never composed prose and never a
    hardcoded string here. The surface resolves the key through src/lib/i18n/ so a
    message is translatable and the jargon gate can see every word of it.
    """
    name = "messaging"

    async def deliver(self, job, run_id, summary) -> DeliveryOutcome:
        # templateKey  e.g. "jobs.delivery.message.brief_ready"
        # params       {"jobName": job.name, "changeCount": n}
        # refuses (never improvises) when no destination is configured:
        #   DeliveryOutcome(ok=False, reasonCode="NO_DESTINATION")
        ...
```

**Configuration is a user choice, stored as data.** `JobDelivery` gains an
optional `destination` (a label the user picked), additively and old-row-safe — a
job saved before this phase delivers exactly as it did.

`src/lib/alerts/notifier.ts` is the existing TS surface that actually shows the
notification; the adapter hands it a key + params, not a sentence.

### 6.2 The saved report artifact — `.black-eclipse/artifacts/<runId>/`

The `artifact` adapter writes the run's report where the app already keeps things
it owns:

```
.black-eclipse/artifacts/<runId>/
  report.md          the rendered answer, as the user saw it
  receipt.json       the bounded ResearchReceipt, when the run produced one
  meta.json          { jobId, jobName, runId, producedAt, scopeId, templateKeys }
```

Rules:

- **Path is derived, never accepted.** `runId` is a server-assigned id; the path is
  built from it, and the result is confined with the same path policy the code
  capability uses. A caller-supplied path is refused.
- **Reuse the receipt rendering.** `research/receipt.py` already owns the shape;
  the artifact writes what that module produces rather than inventing a second
  report format.
- **No new store.** The artifact is a file on disk; nothing is added to
  `agent-memory.db` for it. The run row already exists.
- **Artifacts are scope-labelled** (§6.4) and an artifact is never readable by a
  different scope.

### 6.3 The per-target outcome record

A job with three configured targets must not report one boolean. `DeliveryOutcome`
is recorded **per target**:

| Field | Meaning |
|---|---|
| `target` | the user's chosen destination label |
| `adapter` | `in_app` / `artifact` / `messaging` |
| `ok` | whether this target succeeded |
| `reasonCode` | a structured code (`NO_DESTINATION`, `DELIVERY_FAILED`, `REFUSED`) — never a bare string |
| `detail` | non-secret, bounded, "details"-affordance text |

A delivery failure **never fails the job run**; it is reported on the run row —
the rule Phase 6 already set, now applied per target.

### 6.4 Scope awareness for every new surface

`python/harness/deps.py` already exposes `identity_boundary`,
`deployment_exposure` and `actor_for`. The seam is stated honestly:

```
authentication            False   — no auth; loopback/operator token only
tenancyIsolation          not enforced by the runtime
operatorAuthorization     require_operator (transport/loopback/token proof)
scopeFiltering            caller-supplied labels
multiUserSafe             False
tenancy                   "single-user-local"
```

This phase makes the four new surfaces carry the same labels the older routes
carry — **as filters, never as authorization**:

| Surface | Scope label | Rule |
|---|---|---|
| Jobs | `scopeId` on `HarnessJob` | a job's runs are listed per scope; a body-supplied scope never authorizes |
| Code tasks | `scopeId` on the task | a code task is visible to its scope only |
| Artifacts | `scopeId` on the artifact's `meta.json` **and** on the run row | a read of another scope's artifact is refused |
| Code workspaces | `scopeId` on the workspace binding | a workspace is not enumerable across scopes |

**The rule that must not drift:** `require_operator` stays the *only* thing that
authorizes a mutation. A `scopeId` in a request body is a filter label — it can
narrow what is returned and it can **never** widen what is permitted. This is
exactly the property `python/tests/test_identity_tenancy_boundary.py` already
asserts for the older routes, and the new test **mirrors** it rather than
restating it differently.

### 6.5 The execution backend — `SandboxBackend` (local / container / remote)

The command broker gains a documented interface. Nothing about the *policy* changes
— the class table, the protected paths and the approval rules are the same
wherever the command runs.

```python
class SandboxBackend(Protocol):
    """Where a command actually runs. Each backend DECLARES its guarantees so the
    user-facing answer can be honest about what was and was not contained."""
    name: str
    guarantees: SandboxGuarantees     # filesystem isolation, network, cpu/mem, wall clock
    available: bool                   # probed, never assumed
    def describe(self) -> dict[str, Any]: ...
    async def run(self, spec: CommandSpec) -> CommandResult: ...
```

| Backend | Guarantees it declares | Availability |
|---|---|---|
| `local` | process-level bounds only: no network by policy, workspace-confined paths, wall-clock and output caps | always (the zero-config default) |
| `container` | a real filesystem boundary, an explicit network flag, cpu/memory limits | optional; detected via `doctor.js` |
| `remote` | whatever the endpoint advertises, **and nothing more** | optional; off unless explicitly configured |

**The honest-failure rule, restated because it is the point of this section:**

- an unavailable backend is reported as unavailable; a job that requires it
  **refuses with `SANDBOX_UNAVAILABLE`**;
- it **never** degrades to `local`, and it never degrades to running unsandboxed
  (README §3.5);
- the backend's `guarantees` are what the refusal and the run explanation quote —
  the app never claims a guarantee it cannot name.

`code/sandbox.py` keeps its current behaviour as the `local` backend. This phase
adds the interface and the declaration, not a new execution path.

### 6.6 Packaging — zero-config stays intact (`scripts/doctor.js`)

`scripts/doctor.js` already probes Node, dependencies, the Prisma client, the DB
and the Python bridge, and repairs what it can. This phase adds probes for the new
runtime dependencies:

| Probe | Repair | When it cannot repair |
|---|---|---|
| vendored python present | `npm run setup:python` | prints the exact command and exits non-zero |
| container backend usable | nothing automatic — **detected, never installed** | reports "not available"; jobs needing it refuse |
| artifact directory writable | create `.black-eclipse/artifacts/` | reports honestly and names the path |
| remote backend configured | nothing automatic | reports "not configured" |

**The acceptance condition is unchanged and is a gate:** a fresh clone satisfies
`npm install && npm run dev` with **no manual steps**. A container runtime is never
required for the default path — it is an upgrade, and its absence is a *refusal*,
not a failure to start.

### 6.7 Operational runbooks

New documents under `docs/harness/`, one per surface, written for the person who
has to do the thing at 09:00 on a Monday:

| Runbook | Answers |
|---|---|
| `docs/harness/runbook-add-a-job.md` | how a job is added (template, cadence, target, delivery), what to check when it does not fire, how to read a breaker state |
| `docs/harness/runbook-add-a-kit.md` | how a Phase-9 kit is added (file layout, acceptance test, how it is discovered) |
| `docs/harness/runbook-failed-code-task.md` | how to inspect a failed code task: where the trace is, what the verification ledger says, what "not checked yet" means, and the three recovery actions |

Each runbook is linked from `docs/NAVIGATION.md` through its trigger table — the
repo's existing rule — and each names the **plain** thing the user sees before the
machine thing.

### 6.8 Plain language

Everything this phase adds is user-visible: destination names, message templates,
delivery refusals, artifact titles, backend refusals and the runbook headings. All
of it is i18n keys, and all of it is covered by §9 **G7** against
`policy.PLAIN_LANGUAGE_DENYLIST`. The message body is the highest-risk surface in
the whole roadmap — it leaves the app and lands in a person's inbox — so it gets
the strictest reading: a template may contain a job name and a count, and nothing
else that the user did not choose to receive.

## 7. Work items (ordered)

1. `docs/harness/roadmap/progress/phase-11-progress.md` with §9's gates as
   unchecked boxes.
2. Read `python/harness/jobs/delivery.py`, `jobs/model.py`, `jobs/store.py`,
   `src/lib/alerts/notifier.ts`, `research/receipt.py`, `deps.py`,
   `python/tests/test_identity_tenancy_boundary.py`, `code/sandbox.py`,
   `scripts/doctor.js` in full. Record the exact evidence for §2's table.
3. The `messaging` adapter + its key/params template contract (§6.1).
4. The `artifact` adapter + the derived path and receipt reuse (§6.2).
5. Per-target outcomes on the job run row (§6.3), old-row-safe.
6. Scope labels on the four surfaces + `python/tests/test_surface_tenancy_isolation.py`
   mirroring the existing tenancy test (§6.4).
7. `SandboxBackend` + the three declarations (§6.5); wire the existing
   `code/sandbox.py` in as `local` and prove nothing about policy changed.
8. `doctor.js` probes (§6.6) + a test that a missing backend degrades to a
   refusal, never to an uncontained run.
9. The three runbooks (§6.7) + `NAVIGATION.md` rows.
10. Front door: `src/app/api/jobs/**` destination routes and the UI
    (`src/components/screens/jobs/**`, frosted-glass conventions).
11. ADR-H113 (Decision / Why / Consequences); `docs/CHANGELOG.md` dated entry;
    `docs/NAVIGATION.md` rows.
12. Tests: `python/tests/test_delivery_adapters.py`,
    `test_surface_tenancy_isolation.py`, `test_sandbox_backends.py`.

## 8. Deliverables

| File | Change |
|---|---|
| `python/harness/jobs/delivery.py` | `messaging` + `artifact` adapters; `DeliveryOutcome` per target |
| `python/harness/jobs/model.py` | additive `destination` on `JobDelivery`; additive `scopeId` |
| `python/harness/jobs/store.py` | per-target outcome rows / JSON; old-row-safe |
| `python/harness/code/backends.py` | new — `SandboxBackend` + `local` / `container` / `remote` declarations |
| `python/harness/code/sandbox.py` | registered as the `local` backend (behaviour unchanged) |
| `python/harness/routers/jobs.py`, `routers/code.py` | scope-aware reads; destination routes |
| `python/tests/test_delivery_adapters.py` | new |
| `python/tests/test_surface_tenancy_isolation.py` | new — mirrors `test_identity_tenancy_boundary.py` |
| `python/tests/test_sandbox_backends.py` | new — the honest-failure rule |
| `scripts/doctor.js` | probes for the new runtime dependencies |
| `src/app/api/jobs/**`, `src/components/screens/jobs/**`, `src/lib/alerts/notifier.ts` | destination UI + notification render |
| `src/lib/i18n/dictionaries/en.ts`, `dictionaries/index.ts` | the message + destination key set |
| `docs/harness/runbook-{add-a-job,add-a-kit,failed-code-task}.md` | new |
| `docs/harness/decisions.md` | ADR-H113 |
| `docs/harness/roadmap/progress/phase-11-progress.md` | new |

## 9. Acceptance gates

```bash
# G1 — every configured delivery target receives the job, with a PER-TARGET
#      recorded outcome (in_app, artifact, messaging) — no rolled-up boolean
./scripts/vendor/python/python.exe -m pytest python/tests/test_delivery_adapters.py -v

# G2 — cross-tenant isolation: one scope cannot read another scope's job, code
#      task, artifact or workspace
./scripts/vendor/python/python.exe -m pytest python/tests/test_surface_tenancy_isolation.py -v

# G3 — the honest-failure rule: an unavailable backend refuses with
#      SANDBOX_UNAVAILABLE and NEVER degrades to an uncontained run
./scripts/vendor/python/python.exe -m pytest python/tests/test_sandbox_backends.py -v

# G4 — doctor reports the runtime dependencies honestly
node scripts/doctor.js
# expected: reports vendored python / container backend / artifact dir / remote
#           backend with their real state; a missing backend prints "not available"
#           and does not claim the app is broken

# G5 — a fresh clone still runs with no manual steps
rm -rf node_modules .next && npm install && npm run dev
# expected: dev server starts; no backend installation is requested

# G6 — the suite + the release gate
npm run test && npm run check:all

# G7 — plain-language gate (§4): destination names, message templates, delivery
#      refusals, artifact titles and backend refusals
npx vitest run src/lib/i18n/plain-language.test.ts
./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q
# every new string is an i18n key and contains no term from
# policy.PLAIN_LANGUAGE_DENYLIST; a message body carries a key + params, never a
# hardcoded sentence and never a machine value
```

| Gate | Assertion |
|---|---|
| G1 | A scheduled job configured with all three targets records one outcome **per target**; the `in_app` and `artifact` outcomes are `ok`; a failing `messaging` target records `ok=false` with `reasonCode="DELIVERY_FAILED"` **without** failing the run; `.black-eclipse/artifacts/<runId>/report.md`, `receipt.json` and `meta.json` exist and the path was derived from `runId`. |
| G1b | A job with no destination configured refuses with `reasonCode="NO_DESTINATION"` — it never sends to a default the user did not choose. |
| G2 | For each of the four surfaces, a read with a different `scopeId` returns nothing and is refused/emptied; a **request-body** `scopeId` grants no access to a mutation (the property `test_identity_tenancy_boundary.py` already asserts for older routes); the identity boundary still reports `authentication=False` and `multiUserSafe=False`. |
| G3 | A job requiring the `container` backend on a machine without one refuses with `SANDBOX_UNAVAILABLE`; no execution happens; the refusal names the backend and its guarantees. The same holds for `remote` when unconfigured. |
| G3b | The `local` backend's declared guarantees are exactly the ones enforced today — asserted by comparing the declaration against the existing policy constants, so an upgrade cannot silently restate a weaker guarantee as a stronger one. |
| G4 | `node scripts/doctor.js` reports the four new probes with their **real** state; a missing container backend reads "not available" and the run continues; a missing vendored interpreter prints the exact repair command and exits non-zero. |
| G5 | A fresh clone completes `npm install && npm run dev` with no manual step and no backend installation; the app starts on the default `local` backend. |
| G6 | Full suite + `check:all` green. |
| G7 | Plain language: every new destination / message / delivery / artifact / backend string is an i18n key and contains no term from `policy.PLAIN_LANGUAGE_DENYLIST`; each refusal is ONE plain sentence plus a next step with the machine reason behind "details"; no message body contains a run id, job id, duration in ms or a delivery code. |

## 10. Definition of done

- Every gate run, raw output pasted, observed counts recorded.
- `DeliveryOutcome` is recorded **per target**; no code path collapses them to one
  boolean.
- The messaging adapter receives a **key + parameters**; grep its call sites and
  confirm no sentence is composed in Python or hardcoded in a component.
- `jobs/model.py` grew only additively; a job saved before this phase still
  delivers exactly as it did.
- A missing backend produces a refusal, never a fallback — grep for any
  `except: backend = "local"`-shaped degradation and confirm none exists.
- `scripts/doctor.js` reports honestly: no probe claims a dependency that is not
  present, and none blocks the default path.
- The three runbooks exist and are linked from `NAVIGATION.md`.
- `deployment_exposure` / `identity_boundary` are unchanged; the app still claims
  no multi-user safety.
- ADR-H113 written; `docs/CHANGELOG.md` entry appended; `NAVIGATION.md` updated.
- `status:` flipped here and in the index.

## 11. Implementation prompt (copy this to OpenCode)

```text
Task: Phase 11 — Surface and Scale (Eclipse-as-a-Harness roadmap).

Read first, in full:
- docs/harness/roadmap/phase-11-surface-and-scale.md  (this phase, verbatim)
- docs/harness/roadmap/README.md  (invariants §3 — especially 3.5 zero-config /
  honest refusal and 3.1 one runtime; §4 work in flight)
- python/harness/jobs/delivery.py  ← the DeliveryAdapter protocol you IMPLEMENT,
  never redefine. Phase 6 owns it.
- python/harness/jobs/model.py, python/harness/jobs/store.py
- python/harness/deps.py  (identity_boundary, deployment_exposure, actor_for,
  require_operator) and python/tests/test_identity_tenancy_boundary.py  ← the
  boundary test you MIRROR for the new surfaces
- python/harness/code/sandbox.py, python/harness/code/policy.py  ← the execution
  primitive and the policy constants a backend declaration must match
- python/harness/research/receipt.py  ← the receipt rendering the artifact reuses
- src/lib/alerts/notifier.ts, src/lib/i18n/{dictories/en.ts,dictionaries/index.ts,
  translate.ts,use-t.ts}, scripts/doctor.js, scripts/check-all.js

Goal: more ways for a job's result to reach the user through ONE adapter
interface; scope-awareness across every new surface with an isolation test;
a documented SandboxBackend interface (local / container / remote) with declared
guarantees; zero-config intact; a runbook per surface.

In scope:
1. jobs/delivery.py — ADD the 'messaging' adapter (template KEY + params, resolved
   through src/lib/i18n/; refuses with reasonCode='NO_DESTINATION' when no
   destination is set) and make the 'artifact' adapter write
   .black-eclipse/artifacts/<runId>/{report.md,receipt.json,meta.json} with a path
   DERIVED from the server-assigned runId and confined by policy. Reuse
   research/receipt.py's rendering — do not invent a second report format.
2. Record DeliveryOutcome PER TARGET (target, adapter, ok, reasonCode, detail).
   A delivery failure never fails the job run. No rolled-up boolean anywhere.
3. jobs/model.py — additive only: an optional user-chosen `destination` on
   JobDelivery and an additive `scopeId`. Old rows must load and behave exactly
   as before.
4. Scope-awareness on jobs, code tasks, artifacts and code workspaces. require_operator
   remains the ONLY authorization for a mutation; a body-supplied scopeId is a
   FILTER and can never widen permission. Add
   python/tests/test_surface_tenancy_isolation.py mirroring
   test_identity_tenancy_boundary.py — authentication=False, multiUserSafe=False,
   tenancy='single-user-local', scopeFiltering='caller-supplied-labels'.
5. New python/harness/code/backends.py — a SandboxBackend Protocol (name,
   guarantees, available, describe(), run()) with 'local' / 'container' /
   'remote'. Register the existing code/sandbox.py as 'local' with its CURRENT
   behaviour unchanged. The honest-failure rule is absolute: an unavailable
   backend refuses with SANDBOX_UNAVAILABLE and NEVER degrades to local and never
   to an uncontained run. Each backend's `guarantees` must be quotable in the
   refusal.
6. scripts/doctor.js — probe vendored python, the container backend, the artifact
   directory and the remote backend; repair only what is safe to repair (never
   install a container runtime implicitly); report the real state honestly.
7. Runbooks: docs/harness/runbook-add-a-job.md, runbook-add-a-kit.md,
   runbook-failed-code-task.md; link each from docs/NAVIGATION.md's trigger table.
8. Front door: destination picker in src/components/screens/jobs/** ("In the app",
   "Save it as a report", "Send it to my phone"), src/app/api/jobs/** routes, and
   src/lib/alerts/notifier.ts consuming a key + params.
9. All new user-facing copy is an i18n KEY in src/lib/i18n/ — never hardcoded in a
   component and never composed as a sentence in Python. A message body names the
   finance job and nothing else; no run id, no job id, no duration in ms, no
   delivery code.
10. Tests: test_delivery_adapters.py, test_surface_tenancy_isolation.py,
    test_sandbox_backends.py.
11. ADR-H113 in docs/harness/decisions.md using the repo's shape —
    '## ADR-H113 — Title' then **Decision.** / **Why.** / **Consequences.**
    (NOT "Impact"). Plus a dated docs/CHANGELOG.md entry and NAVIGATION.md rows.

Non-goals (do NOT do these):
- Do NOT refactor or redefine the Phase-6 job model / DeliveryAdapter protocol.
  Add adapters; do not redesign.
- No cloud multi-tenancy, no accounts, no auth provider, and no change to the
  honesty claims in deps.py.
- NEVER degrade to unsandboxed execution; SANDBOX_UNAVAILABLE is a first-class
  user-visible refusal.
- No new REQUIRED dependency for a fresh clone; a container runtime is optional
  and detected, never installed.
- No secrets in a message or an artifact.
- Never commit, push, or open a PR. Do not commit jdds.db.

Acceptance gates — run each and paste the RAW output into
docs/harness/roadmap/progress/phase-11-progress.md:
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_delivery_adapters.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_surface_tenancy_isolation.py -v
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_sandbox_backends.py -v
  node scripts/doctor.js
  rm -rf node_modules .next && npm install && npm run dev
  npm run test && npm run check:all
  npx vitest run src/lib/i18n/plain-language.test.ts
  ./scripts/vendor/python/python.exe -m pytest python/tests/test_plain_language.py -q

Finish by stating: "docs updated: <files>" or "no doc change — <reason>".
```

---

**Next:** [Phase 12 — Evaluation harness, safety cases and the standing gate](./phase-12-evaluation-gate.md)
