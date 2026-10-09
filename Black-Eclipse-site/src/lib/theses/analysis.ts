// ── Thesis analysis (Workstream K) — deterministic, no model ─────────────────
// When new evidence arrives we must decide whether it supports or weakens the
// thesis's stated assumptions WITHOUT silently rewriting the thesis. This module
// is a deterministic textual-overlap matcher + a simple health summary. It never
// invents a verdict beyond what the recorded evidence states: an assumption with
// no matching evidence is `unmentioned`, not `supported`.

import type {
  EvidenceStance,
  ThesisEvidenceRecord,
  ThesisRecord,
  ThesisStatus,
} from "./types";

export type AssumptionVerdict = "supported" | "weakened" | "contradicted" | "unmentioned";

export interface AssumptionImpact {
  assumption: string;
  supporting: number;
  contradicting: number;
  verdict: AssumptionVerdict;
}

export interface ThesisHealth {
  supporting: number;
  contradicting: number;
  /** supporting - contradicting, ranging from -N to +N. */
  netScore: number;
  coverage: "no-evidence" | "poorly-supported" | "mixed" | "well-supported";
  /** A status SUGGESTION — never auto-applied to the persisted thesis. */
  suggestedStatus: ThesisStatus;
}

const STOPWORDS = new Set([
  "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is",
  "are", "be", "will", "its", "it", "by", "as", "at", "from", "that", "this",
]);

/** Lowercased significant tokens (len >= 3, stopwords removed). */
export function tokens(text: string): string[] {
  return (text || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length >= 3 && !STOPWORDS.has(t));
}

/** Count overlap between an assumption's tokens and an evidence summary. */
export function overlapCount(assumption: string, summary: string): number {
  const a = new Set(tokens(assumption));
  if (a.size === 0) return 0;
  let hits = 0;
  for (const t of new Set(tokens(summary))) if (a.has(t)) hits++;
  return hits;
}

/**
 * Match each assumption against the recorded evidence and classify it. An
 * evidence piece counts toward an assumption when it shares at least one
 * significant token with it — deliberately conservative, so unrelated evidence
 * does not get attributed to an assumption it never addressed.
 */
export function assessAssumptionImpacts(
  assumptions: string[],
  evidence: ThesisEvidenceRecord[],
): AssumptionImpact[] {
  return assumptions.map((assumption) => {
    let supporting = 0;
    let contradicting = 0;
    for (const ev of evidence) {
      if (overlapCount(assumption, ev.summary) === 0) continue;
      if (ev.stance === "supporting") supporting++;
      else contradicting++;
    }
    let verdict: AssumptionVerdict = "unmentioned";
    if (contradicting > supporting) verdict = "contradicted";
    else if (contradicting > 0) verdict = "weakened";
    else if (supporting > 0) verdict = "supported";
    return { assumption, supporting, contradicting, verdict };
  });
}

/** Roll the evidence up into a health summary + a status SUGGESTION. */
export function summarizeThesis(record: Pick<ThesisRecord, "evidence">): ThesisHealth {
  let supporting = 0;
  let contradicting = 0;
  for (const ev of record.evidence) {
    if (ev.stance === "supporting") supporting++;
    else contradicting++;
  }
  const netScore = supporting - contradicting;
  const total = supporting + contradicting;
  let coverage: ThesisHealth["coverage"];
  if (total === 0) coverage = "no-evidence";
  else if (netScore > 0) coverage = "well-supported";
  else if (netScore === 0) coverage = "mixed";
  else coverage = "poorly-supported";

  let suggestedStatus: ThesisStatus = "active";
  if (total > 0 && contradicting > supporting * 2) suggestedStatus = "broken";
  else if (contradicting > supporting) suggestedStatus = "weakening";

  return { supporting, contradicting, netScore, coverage, suggestedStatus };
}

/** True when a stance string is a valid recorded stance. */
export function isStance(v: unknown): v is EvidenceStance {
  return v === "supporting" || v === "contradicting";
}
