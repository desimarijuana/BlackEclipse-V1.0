/** Browser-only signal that an RSL verify tick recorded a candidate decision. */
export const EVOLUTION_VERIFIED_EVENT = "eclipse:evolution-verified";

export interface EvolutionVerifiedEventDetail {
  candidateId?: string;
  stateId?: string | null;
  decision?: string;
}

/** Browser-only request to open one candidate in the evidence panel. */
export const EVOLUTION_EVIDENCE_EVENT = "eclipse:evolution-evidence";

export interface EvolutionEvidenceEventDetail {
  candidateId: string;
}
