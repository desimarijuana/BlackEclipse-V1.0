// ── Investment Thesis contracts (Workstream K) ───────────────────────────────
// A thesis is a persisted, versioned investment hypothesis with supporting and
// contradicting evidence. These are the shared shapes for the store, the API
// and the UI. JSON columns are parsed into arrays here so no caller handles
// raw JSON strings.

export type ThesisStatus = "active" | "weakening" | "broken" | "closed";
export type EvidenceStance = "supporting" | "contradicting";

export const THESIS_STATUSES: ThesisStatus[] = ["active", "weakening", "broken", "closed"];

export interface ThesisEvidenceRecord {
  id: string;
  stance: EvidenceStance;
  summary: string;
  sourceUrl: string | null;
  sourceType: string | null;
  publishedAt: string | null;
  retrievedAt: string;
}

export interface ThesisRevisionRecord {
  id: string;
  version: number;
  note: string | null;
  snapshot: ThesisSnapshot;
  createdAt: string;
}

export interface ThesisSnapshot {
  title: string;
  hypothesis: string;
  status: ThesisStatus;
  assumptions: string[];
  catalysts: string[];
  risks: string[];
  metrics: string[];
  reviewDate: string | null;
  version: number;
}

export interface ThesisRecord extends ThesisSnapshot {
  id: string;
  symbol: string;
  marketId: string;
  companyName: string | null;
  sourceArtifacts: string[];
  createdAt: string;
  updatedAt: string;
  evidence: ThesisEvidenceRecord[];
}

export interface ThesisInput {
  symbol: string;
  marketId: string;
  companyName?: string | null;
  title: string;
  hypothesis: string;
  status?: ThesisStatus;
  assumptions?: string[];
  catalysts?: string[];
  risks?: string[];
  metrics?: string[];
  reviewDate?: string | null;
  sourceArtifacts?: string[];
}

export interface ThesisUpdate {
  title?: string;
  hypothesis?: string;
  status?: ThesisStatus;
  assumptions?: string[];
  catalysts?: string[];
  risks?: string[];
  metrics?: string[];
  reviewDate?: string | null;
  note?: string;
}
