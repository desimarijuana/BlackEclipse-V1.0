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
- Produce, alongside the lexical detector: `confirmation_candidate`,
  `conflict_candidate`, `replacement_candidate` (only with explicit replacement
  language), or `unrelated`.

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

## Policy controls

- `semantic_conflict_enabled` (default off; lexical always active).
- `semantic_conflict_threshold` (candidate similarity floor).
- `semantic_conflict_max_candidates`.
- `semantic_conflict_max_index` (index size cap).
- `semantic_conflict_timeout_ms`.
- `semantic_conflict_diagnostics` (whether detector metadata is shown in views).
- Index rebuild / clear actions.

All are bounded and validated; disabling the layer never disables lexical
handling, and lowering a threshold never bypasses privacy or authority rules.

## Known limits

- Lexical detection can still miss a contradiction phrased with entirely
  unfamiliar vocabulary that shares no dimension token (subject identity or
  enough shared normalized content is still required to link two memories).
- Paraphrase coverage depends on the human-reviewed concept table (`CONCEPT_AXES`
  in `normalize.py`); unlisted pairs are misses.
- The optional semantic layer is a *candidate* aid, not a truth oracle: it is
  conservative by design and may miss weak paraphrases. A missed conflict is
  preferred over replacing unrelated memory.
- The default semantic backend (`char-ngram`) is surface-level. A future bundled
  local embedding backend can be registered via `semantic.register_backend`
  without changing the caller or the safety rules.

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

## How a user reviews a possible contradiction

The Memory Control Room shows the existing memory, the proposed one, why they
were related, the detector used, the confidence/similarity, which one is
authoritative, and actions (confirm replacement, keep existing, dismiss
proposal, inspect). An ambiguous conflict is never presented as saved active
truth.
