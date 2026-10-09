// ── Thesis store (Workstream K) — server-side Prisma access ──────────────────
// The ONE place the Thesis tables are read/written. Every update appends an
// immutable ThesisRevision snapshot BEFORE applying the change, so the original
// hypothesis can always be reconstructed and is never silently rewritten.

import { prisma } from "@/lib/db";
import type {
  EvidenceStance,
  ThesisEvidenceRecord,
  ThesisInput,
  ThesisRecord,
  ThesisRevisionRecord,
  ThesisStatus,
  ThesisUpdate,
} from "./types";

type JsonArray = string[];
const parseArr = (raw: string | null | undefined): JsonArray => {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
};
const stringifyArr = (v: unknown): string =>
  JSON.stringify(Array.isArray(v) ? v.map((x) => String(x).trim()).filter(Boolean) : []);

/* eslint-disable @typescript-eslint/no-explicit-any */
function toEvidence(e: any): ThesisEvidenceRecord {
  return {
    id: e.id,
    stance: e.stance as EvidenceStance,
    summary: e.summary,
    sourceUrl: e.sourceUrl ?? null,
    sourceType: e.sourceType ?? null,
    publishedAt: e.publishedAt ? e.publishedAt.toISOString() : null,
    retrievedAt: e.retrievedAt.toISOString(),
  };
}

function toRecord(t: any, evidence: any[]): ThesisRecord {
  return {
    id: t.id,
    symbol: t.symbol,
    marketId: t.marketId,
    companyName: t.companyName ?? null,
    title: t.title,
    hypothesis: t.hypothesis,
    status: t.status as ThesisStatus,
    assumptions: parseArr(t.assumptions),
    catalysts: parseArr(t.catalysts),
    risks: parseArr(t.risks),
    metrics: parseArr(t.metrics),
    reviewDate: t.reviewDate ? t.reviewDate.toISOString() : null,
    version: t.version,
    sourceArtifacts: parseArr(t.sourceArtifacts),
    createdAt: t.createdAt.toISOString(),
    updatedAt: t.updatedAt.toISOString(),
    evidence: evidence.map(toEvidence),
  };
}

function snapshotOf(t: any, version: number): ThesisRevisionRecord["snapshot"] {
  return {
    title: t.title,
    hypothesis: t.hypothesis,
    status: t.status as ThesisStatus,
    assumptions: parseArr(t.assumptions),
    catalysts: parseArr(t.catalysts),
    risks: parseArr(t.risks),
    metrics: parseArr(t.metrics),
    reviewDate: t.reviewDate ? t.reviewDate.toISOString() : null,
    version,
  };
}
/* eslint-enable @typescript-eslint/no-explicit-any */

const evidenceOrder = { createdAt: "desc" as const };

export async function listTheses(filter: { symbol?: string; status?: string } = {}) {
  const rows = await prisma.thesis.findMany({
    where: {
      ...(filter.symbol ? { symbol: filter.symbol.toUpperCase() } : {}),
      ...(filter.status ? { status: filter.status } : {}),
    },
    orderBy: { updatedAt: "desc" },
    include: { evidence: { orderBy: evidenceOrder } },
  });
  return rows.map((t) => toRecord(t, t.evidence));
}

export async function getThesis(id: string): Promise<ThesisRecord | null> {
  const t = await prisma.thesis.findUnique({
    where: { id },
    include: { evidence: { orderBy: evidenceOrder } },
  });
  return t ? toRecord(t, t.evidence) : null;
}

export async function createThesis(input: ThesisInput): Promise<ThesisRecord> {
  const t = await prisma.thesis.create({
    data: {
      symbol: input.symbol.trim().toUpperCase(),
      marketId: input.marketId.trim().toUpperCase(),
      companyName: input.companyName ?? null,
      title: input.title.trim(),
      hypothesis: input.hypothesis.trim(),
      status: input.status ?? "active",
      assumptions: stringifyArr(input.assumptions),
      catalysts: stringifyArr(input.catalysts),
      risks: stringifyArr(input.risks),
      metrics: stringifyArr(input.metrics),
      reviewDate: input.reviewDate ? new Date(input.reviewDate) : null,
      sourceArtifacts: stringifyArr(input.sourceArtifacts),
      version: 1,
    },
  });
  // Record the original hypothesis as revision 1 so the origin is always kept.
  await prisma.thesisRevision.create({
    data: { thesisId: t.id, version: 1, snapshot: JSON.stringify(snapshotOf(t, 1)), note: "Initial thesis" },
  });
  return (await getThesis(t.id))!;
}

/**
 * Apply an update. A revision is appended FIRST (capturing the PRIOR version),
 * then the row is bumped. This preserves history and makes the change auditable.
 */
export async function updateThesis(id: string, patch: ThesisUpdate): Promise<ThesisRecord | null> {
  const existing = await prisma.thesis.findUnique({ where: { id } });
  if (!existing) return null;
  const nextVersion = existing.version + 1;
  await prisma.thesisRevision.create({
    data: {
      thesisId: id,
      version: existing.version,
      snapshot: JSON.stringify(snapshotOf(existing, existing.version)),
      note: patch.note ?? null,
    },
  });
  await prisma.thesis.update({
    where: { id },
    data: {
      ...(patch.title !== undefined ? { title: patch.title } : {}),
      ...(patch.hypothesis !== undefined ? { hypothesis: patch.hypothesis } : {}),
      ...(patch.status !== undefined ? { status: patch.status } : {}),
      ...(patch.assumptions !== undefined ? { assumptions: stringifyArr(patch.assumptions) } : {}),
      ...(patch.catalysts !== undefined ? { catalysts: stringifyArr(patch.catalysts) } : {}),
      ...(patch.risks !== undefined ? { risks: stringifyArr(patch.risks) } : {}),
      ...(patch.metrics !== undefined ? { metrics: stringifyArr(patch.metrics) } : {}),
      ...(patch.reviewDate !== undefined
        ? { reviewDate: patch.reviewDate ? new Date(patch.reviewDate) : null }
        : {}),
      version: nextVersion,
    },
  });
  return getThesis(id);
}

export async function deleteThesis(id: string): Promise<boolean> {
  const found = await prisma.thesis.findUnique({ where: { id }, select: { id: true } });
  if (!found) return false;
  await prisma.thesis.delete({ where: { id } });
  return true;
}

export async function addEvidence(
  thesisId: string,
  ev: {
    stance: EvidenceStance;
    summary: string;
    sourceUrl?: string | null;
    sourceType?: string | null;
    publishedAt?: string | null;
  },
): Promise<ThesisEvidenceRecord | null> {
  const thesis = await prisma.thesis.findUnique({ where: { id: thesisId }, select: { id: true } });
  if (!thesis) return null;
  const row = await prisma.thesisEvidence.create({
    data: {
      thesisId,
      stance: ev.stance,
      summary: ev.summary.trim(),
      sourceUrl: ev.sourceUrl ?? null,
      sourceType: ev.sourceType ?? null,
      publishedAt: ev.publishedAt ? new Date(ev.publishedAt) : null,
    },
  });
  return toEvidence(row);
}

export async function listRevisions(thesisId: string): Promise<ThesisRevisionRecord[]> {
  const rows = await prisma.thesisRevision.findMany({
    where: { thesisId },
    orderBy: { version: "desc" },
  });
  return rows.map((r) => ({
    id: r.id,
    version: r.version,
    note: r.note ?? null,
    snapshot: JSON.parse(r.snapshot),
    createdAt: r.createdAt.toISOString(),
  }));
}
