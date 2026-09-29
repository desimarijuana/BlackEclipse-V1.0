---
title: Harness — Memory Contradiction Detection (lexical, deterministic)
status: Current
last-verified: 2026-09-29
---

# Memory Contradiction Detection

How Black Eclipse decides whether a new durable statement contradicts an existing
one. Local, single-user product: `userId`/`scopeId` are labels, not account
identities.

> **Update (2026-09-29):** the optional local semantic candidate layer was
> **removed** on the evidence it recorded — deterministic normalization closed the
> entire measured gap, and the dependency-free backend scored genuine paraphrases
> at ~0.0–0.38 (no candidate above a safe threshold). Detection is now lexical
> only. See "Why the semantic layer was removed" below.

## Detection

- **Lexical (the only path).** `eclipse_memory/conflicts.py` compares same
  memory-type, same scope + owner memories on the same dimension using subject
  identity (`same_dimension`, subject equality or `normalize.SUBJECT_ALIASES`),
  controlled normalized tokens (`normalize.canonical_tokens`), known
  opposing-polarity pairs, and explicit replacement language. Deterministic,
  explainable, no model, no network. This is the safety and authority layer.
- There is no second detector. The `GET /eclipse-memory/semantic-status` and
  `POST /eclipse-memory/semantic/rebuild` routes remain as honest **tombstones**
  (they report the retirement), so an older client gets a truthful answer rather
  than a 404.

## Baseline (lexical only) — `contradictions_v1.json`

Measured by `python -m harness.eclipse_memory.eval.contradictions_cli` before the
Phase 2 normalization work:

| Metric | Baseline |
|---|---|
| contradiction recall | 0.462 |
| false-conflict rate | 0.111 |
| confirmation accuracy | 0.333 |
| unrelated-memory safety | 1.000 |
| scope isolation | 1.000 |
| authority correctness | 1.000 |
| unauthorized supersessions | 0 |

The baseline's misses are **paraphrased conflicts** (e.g. "keep it punchy" vs
"full deep-dive") and **paraphrased confirmations** that share no lexical token
and are not in the small opposing-pair table; the one false conflict is a
temporary instruction ("for this task …") treated as durable.

## What the detector may do

- Identify same-dimension candidates that deterministic filtering already
  authorized (same scope + owner, same memory type, same dimension, active).
- Classify an above-threshold candidate as a conflict or a replacement, which may
  lead the service to store the new record inert (`proposed`) for review.
- A same-meaning restatement is confirmed; it never activates a memory on
  similarity alone.

## What it is forbidden to do

- Authorize access or bypass scope, status, memory-type, subject, privacy, or
  authority checks.
- Supersede, activate, archive, or delete any memory by itself.
- Let an automatic statement override an explicit one.
- Activate a proposed memory.
- Turn a current financial fact into durable memory.

## Local-only / zero-config

No hosted accounts, no cloud, no mandatory network call. Detection is pure,
dependency-free Python: no model, no download, no index, no embeddings. No raw
embeddings or memory text are stored by the detector.

## Deterministic decision layer

The final disposition is deterministic and explainable. It combines the lexical
decision, normalized subject identity, authority, scope, memory type and
replacement language. Each outcome states why: confirmed, proposed, superseded,
ignored, rejected, or unavailable.

A crucial safety fix: a same-dimension **value substitution** ("reports as PDF"
vs "reports as Excel", "quarterly" vs "monthly", "24-hour" vs "12-hour") is
NEVER silently confirmed. `conflicts._value_changed` requires both statements to
carry a distinctive canonical token the other lacks (reviewed synonym folds are
excluded), and such a case is proposed for review (or superseded when an explicit
statement overrides an automatic one) — never treated as a restatement that would
discard the new value.


## Policy controls

- Retrieval/capture/recall policy (`capture_policy`, `recall_policy`) still applies
  and can only tighten. There are **no** conflict-detector policy keys anymore —
  the semantic layer's seven keys were removed with it.

The retired `GET /eclipse-memory/semantic-status` and
`POST /eclipse-memory/semantic/rebuild` routes return honest tombstones.

## Why the semantic layer was removed (2026-09-29)

The layer was deleted, not merely left off. Its own evaluation recorded that the
dependency-free `char-ngram` backend scores genuine paraphrases at ~0.0–0.38, so
at any safe threshold it found essentially no candidate a deterministic lexical
rule would miss; the deterministic normalization + value-substitution fix closed
the entire measured gap. It carried ~433 LOC, seven policy keys, typed candidate
machinery, a retrieval tie-break, a rebuild route, its own eval set and a UI
surface — all for a feature deliberately never enabled. That is review surface and
refactor cost for no measured return. The deterministic path and the labeled
contradiction evaluation remain; the semantic-specific eval and backend are gone.
Its value-substitution safety cases were **repurposed** as lexical regression
cases in `contradictions_v1.json` (kinds `numeric-value`/`paraphrase-conflict`),
because they guard a real, previously-shipped safety bug.

## Operational status

`GET /eclipse-memory/semantic-status` reports the mode (`lexical`,
`lexical+semantic`, `lexical+semantic-unavailable`), backend + version,
availability, the bounded controls, per-backend health, and bounded counters
(proposals, actionable candidates, confirmed-after-review, kept/dismissed,
replacement proposals). No content is exposed.


## Known limits

- Lexical detection can still miss a contradiction phrased with entirely
  unfamiliar vocabulary that shares no dimension token (subject identity or
  enough shared normalized content is still required to link two memories).
- Paraphrase coverage depends on the human-reviewed concept table (`CONCEPT_AXES`
  in `normalize.py`); unlisted pairs are misses.
- A missed conflict is preferred over replacing unrelated memory.

## Measurements

`python -m harness.eclipse_memory.eval.contradictions_cli` runs the labeled set
(`contradictions_v1.json`, 49 cases after the semantic layer's safety cases were
folded in) through the REAL detector and prints a threshold gate.

| Metric | Baseline (lexical, 0.462 recall) | After normalization | After semantic removal |
|---|---|---|---|
| contradiction recall | 0.462 | 1.000 | **1.000** |
| false-conflict rate | 0.111 | 0.000 | **0.000** |
| confirmation accuracy | 0.333 | 1.000 | **1.000** |
| scope isolation | 1.000 | 1.000 | **1.000** |
| forbidden hits | — | 0 | **0** |
| authority correctness | 1.000 | 1.000 | **1.000** |
| unauthorized supersessions | 0 | 0 | **0** |

The deterministic normalization (reviewed concept axes + polarity/negation +
temporary-instruction exclusion + subject-identity authority) closed the entire
measured paraphrase/confirmation gap. Because of that, the optional semantic
layer added no measurable recall at a safe threshold; it was **removed** rather
than left off. Its value-substitution safety cases were repurposed as lexical
regression cases (kinds `numeric-value`/`paraphrase-conflict`) — they guard a
real, previously-shipped bug where a changed value was silently confirmed.

### Measurement honesty (real usage)

A perfect score on a self-authored labeled set is a smell, not evidence: it
proves the detector implements its rules, not that the rules match reality. The
complement is `GET /eclipse-memory/usage-report` (`eclipse_memory/usage_report.py`),
a bounded, read-only report over ACTUAL persisted rows: durable-write outcomes,
real conflict resolutions (accepted/dismissed/pending) and the dismissed rate as a
false-positive proxy, plus likely-missed conflicts (multiple active same-subject
records) for human review. Early numbers are small and reported as such; empty
data yields an honest empty report, never a zero-filled fake. It never exposes
memory text.


## How a user reviews a possible contradiction

The Memory Control Room shows the existing memory, the proposed one, why they
were related, the detector used, the confidence/similarity, which one is
authoritative, and actions (confirm replacement, keep existing, dismiss
proposal, inspect). An ambiguous conflict is never presented as saved active
truth.
