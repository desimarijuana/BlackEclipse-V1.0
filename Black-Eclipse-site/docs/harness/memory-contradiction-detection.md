---
title: Harness — Memory Contradiction Detection (lexical + optional semantic)
status: Current
last-verified: 2026-09-25
---

# Memory Contradiction Detection

How Black Eclipse decides whether a new durable statement contradicts an existing
one, and what the optional local semantic layer is allowed to do. Local,
single-user product: `userId`/`scopeId` are labels, not account identities.

## Lexical vs semantic

- **Lexical (always on).** `eclipse_memory/conflicts.py` compares same
  memory-type, same scope + owner memories on the same dimension using subject
  identity (`same_dimension`, subject equality or `normalize.SUBJECT_ALIASES`),
  controlled normalized tokens (`normalize.canonical_tokens`), known
  opposing-polarity pairs, and explicit replacement language. Deterministic,
  explainable, no model, no network. This is the safety and authority layer.
- **Semantic (optional, local, off by default).** A bounded candidate layer that
  can only *find possible related memories* to hand back to the same lexical +
  authority decision. It never decides on its own; it never supersedes, activates,
  archives, or deletes. It requires an operator-enabled policy setting and an
  available local backend; otherwise behavior falls back to lexical-only.

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

## What semantic similarity may do

- Identify same-dimension candidates that deterministic filtering already
  authorized (same scope + owner, same memory type, same dimension, active).
- Classify each above-threshold candidate, deterministically, as one of
  `confirmation_candidate`, `conflict_candidate`, `replacement_candidate`,
  `unrelated_candidate` (or `unavailable`). Only `conflict_candidate` and
  `replacement_candidate` are ACTIONABLE: they may lead the service to store the
  new record inert (`proposed`) for review. A `confirmation_candidate` is
  diagnostic only — similarity never confirms or activates a memory.

## What it is forbidden to do

- Authorize access or bypass scope, status, memory-type, subject, privacy, or
  authority checks.
- Supersede, activate, archive, or delete any memory by itself.
- Let an automatic statement override an explicit one.
- Activate a proposed memory.
- Turn a current financial fact into durable memory.

## Local-only / zero-config

No hosted accounts, no cloud, no mandatory network call. The semantic backend is
selected from what is already installed locally; when nothing suitable is present
the layer reports itself unavailable and detection stays lexical. No model is
downloaded at runtime without explicit operator action.

### Backends

- `char-ngram` (default): dependency-free character n-gram cosine similarity,
  local, deterministic, bounded. **Honest limitation:** the dedicated semantic
  evaluation shows it scores genuinely unfamiliar paraphrases at ~0.0–0.38, so at
  any safe threshold it finds essentially no candidate a deterministic lexical
  rule would miss. It is therefore a bounded fallback, not a source of measured
  improvement.
- `local-embedding` (optional, off unless configured): a sentence-transformer
  loaded ONLY from an explicit local directory
  (`BLACK_ECLIPSE_MEMORY_EMBEDDING_MODEL`). It never downloads a model, never
  contacts a network, and its absence is not an error — `auto` falls back to
  `char-ngram`.
- `none`: forces lexical-only.
- `auto`: the strongest *available* backend, else `char-ngram`.

No raw embeddings or memory text are stored; only numeric similarity scores and
bounded candidate ids/kinds cross into diagnostics.

## Deterministic decision layer

The final disposition is deterministic and explainable. It combines the lexical
decision, normalized subject identity, the typed semantic candidate,
similarity, authority, scope, memory type and replacement language. Each outcome
states why: confirmed, proposed, superseded, ignored, rejected, or unavailable.

A crucial safety fix: a same-dimension **value substitution** ("reports as PDF"
vs "reports as Excel", "quarterly" vs "monthly", "24-hour" vs "12-hour") is
NEVER silently confirmed. `conflicts._value_changed` requires both statements to
carry a distinctive canonical token the other lacks (reviewed synonym folds are
excluded), and such a case is proposed for review (or superseded when an explicit
statement overrides an automatic one) — never treated as a restatement that would
discard the new value.


## Policy controls

- `semantic_conflict_enabled` (default off; lexical always active).
- `semantic_conflict_backend` (default `char-ngram`; `auto`/`local-embedding`/
  `none` also accepted, all local).
- `semantic_conflict_threshold` (candidate similarity floor).
- `semantic_conflict_max_candidates`.
- `semantic_conflict_max_index` (index size cap).
- `semantic_conflict_timeout_ms`.
- `semantic_conflict_diagnostics` (whether detector metadata is shown in views).
- `semantic_recall_tiebreak` (default off; optional retrieval reorder of
  memories that already carry a lexical signal — never widens the eligible set).
- Index rebuild / clear action: `POST /eclipse-memory/semantic/rebuild`
  (operator-gated; honest that v1 holds no persistent index).

All are bounded and validated; disabling the layer never disables lexical
handling, and lowering a threshold never bypasses privacy or authority rules.

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
- The optional semantic layer is a *candidate* aid, not a truth oracle: it is
  conservative by design and may miss weak paraphrases. A missed conflict is
  preferred over replacing unrelated memory.
- The default semantic backend (`char-ngram`) is surface-level and is NOT shown
  by the dedicated evaluation to add measurable recall at a safe threshold. A
  stronger local embedding backend can be configured
  (`BLACK_ECLIPSE_MEMORY_EMBEDDING_MODEL` + `semantic_conflict_backend`) without
  changing the caller or the safety rules, but it stays optional and off.

## Measurements

`python -m harness.eclipse_memory.eval.contradictions_cli` runs the labeled set
(`contradictions_v1.json`, 28 cases) through the REAL detector and prints a
threshold gate. Recorded on the Phase 2 normalization change:

| Metric | Baseline (lexical, 0.462 recall) | After normalization |
|---|---|---|
| contradiction recall | 0.462 | **1.000** |
| false-conflict rate | 0.111 | **0.000** |
| confirmation accuracy | 0.333 | **1.000** |
| unrelated-memory safety | 1.000 | **1.000** |
| scope isolation | 1.000 | **1.000** |
| authority correctness | 1.000 | **1.000** |
| unauthorized supersessions | 0 | **0** |

The deterministic normalization (reviewed concept axes + polarity/negation +
temporary-instruction exclusion + subject-identity authority) closed the entire
measured paraphrase/confirmation gap, so the optional semantic layer was kept
**off by default** and remains a bounded, local fallback rather than a
requirement.

### Dedicated semantic evaluation

`python -m harness.eclipse_memory.eval.semantic_cli` runs a separate labeled set
(`semantic_v1.json`, 20 cases) built specifically from cases lexical matching did
not solve, through the REAL write pipeline (via the production authorization
gate) in both lexical-only and semantic-enabled modes, and prints a release gate.

**Phase 0 finding (pre-fix, lexical-only):** the value-substitution cases
("reports as PDF" vs "reports as Excel", "quarterly" vs "monthly", "24-hour" vs
"12-hour") were silently **confirmed**, discarding the new value — a real safety
bug, not just a recall miss. The 24-hour/12-hour numeric tokens were also dropped
by the length filter, the `short`→`sell` synonym collision mis-folded a
confirmation, and the financial-fact guard missed "trading at 190".

**After the deterministic fix (both modes):**

| Metric | Value |
|---|---|
| contradiction recall | 1.000 |
| false-conflict rate | 0.000 |
| confirmation accuracy | 1.000 |
| scope leakage | 0 |
| unauthorized supersessions | 0 |
| automatic-over-explicit | 0 |
| secret stored | 0 |
| financial fact stored | 0 |

**Honest conclusion:** the measured improvement came from deterministic
normalization + the value-substitution safety fix, NOT from semantic similarity.
The default `char-ngram` backend scores genuinely unfamiliar paraphrases at
~0.0–0.38, so it finds no candidate above a safe threshold. Semantic matching is
kept optional, off by default, local, bounded, explainable and fail-safe; a
stronger local embedding backend can be configured explicitly but is not
required and is not part of the default install.


## How a user reviews a possible contradiction

The Memory Control Room shows the existing memory, the proposed one, why they
were related, the detector used, the confidence/similarity, which one is
authoritative, and actions (confirm replacement, keep existing, dismiss
proposal, inspect). An ambiguous conflict is never presented as saved active
truth.
