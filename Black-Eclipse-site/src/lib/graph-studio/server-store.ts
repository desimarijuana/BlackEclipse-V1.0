// ── Graph Studio — server-side workflow persistence (Prisma / JDDS) ──────────
// The ONE place Workflow + WorkflowVersion rows are read/written. Workflow
// versions are APPEND-ONLY: saving never updates an existing version row, it
// writes the next integer and moves the workflow's `currentVersion`. The IR is
// re-validated here (via `readWorkflowIR`) before it is trusted or stored, so a
// malformed document cannot enter the catalog.
//
// Server-only: imports Prisma. Never import this from a client component.

import { prisma } from '@/lib/db';
import { contentHash } from './hash';
import { parseWorkflowIR } from './ir';
import { readWorkflowIR } from './migrations';
import type { WorkflowIR } from './types';

export interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  tags: string[];
  owner: string;
  currentVersion: number;
  archived: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface WorkflowRecord extends WorkflowSummary {
  ir: WorkflowIR;
  contentHash: string;
  version: number;
}

export interface VersionSummary {
  version: number;
  contentHash: string;
  note: string | null;
  createdAt: string;
}

function parseTags(raw: string): string[] {
  try {
    const value = JSON.parse(raw);
    return Array.isArray(value) ? value.map(String) : [];
  } catch {
    return [];
  }
}

type WorkflowRow = {
  id: string;
  name: string;
  description: string;
  tags: string;
  owner: string;
  currentVersion: number;
  archived: boolean;
  createdAt: Date;
  updatedAt: Date;
};

function toSummary(row: WorkflowRow): WorkflowSummary {
  return {
    id: row.id,
    name: row.name,
    description: row.description,
    tags: parseTags(row.tags),
    owner: row.owner,
    currentVersion: row.currentVersion,
    archived: row.archived,
    createdAt: row.createdAt.toISOString(),
    updatedAt: row.updatedAt.toISOString(),
  };
}

export async function listWorkflows(options: { owner?: string; includeArchived?: boolean } = {}): Promise<WorkflowSummary[]> {
  const rows = await prisma.workflow.findMany({
    where: {
      ...(options.owner ? { owner: options.owner } : {}),
      ...(options.includeArchived ? {} : { archived: false }),
    },
    orderBy: { updatedAt: 'desc' },
    take: 200,
  });
  return rows.map((r) => toSummary(r as WorkflowRow));
}

export async function createWorkflow(input: {
  name: string;
  description?: string;
  tags?: string[];
  owner?: string;
  ir: WorkflowIR;
}): Promise<WorkflowRecord> {
  const ir = parseWorkflowIR(input.ir);
  const created = await prisma.workflow.create({
    data: {
      name: input.name,
      description: input.description ?? '',
      tags: JSON.stringify(input.tags ?? []),
      owner: input.owner ?? 'guest',
      currentVersion: 1,
    },
  });
  await prisma.workflowVersion.create({
    data: {
      workflowId: created.id,
      version: 1,
      ir: JSON.stringify(ir),
      contentHash: contentHash(ir),
      note: 'Initial version',
    },
  });
  return {
    ...toSummary(created as WorkflowRow),
    ir,
    contentHash: contentHash(ir),
    version: 1,
  };
}

export async function getWorkflow(id: string, version?: number): Promise<WorkflowRecord | null> {
  const workflow = await prisma.workflow.findUnique({ where: { id } });
  if (!workflow) return null;
  const target = version ?? workflow.currentVersion;
  const versionRow = await prisma.workflowVersion.findUnique({
    where: { workflowId_version: { workflowId: id, version: target } },
  });
  if (!versionRow) return null;
  let ir: WorkflowIR;
  try {
    ir = readWorkflowIR(JSON.parse(versionRow.ir));
  } catch {
    // A stored document that no longer validates is surfaced as a corrupt read
    // rather than silently returned.
    throw new Error(`Workflow ${id}@${target} has an unreadable definition.`);
  }
  return {
    ...toSummary(workflow as WorkflowRow),
    ir,
    contentHash: versionRow.contentHash,
    version: versionRow.version,
  };
}

export async function saveWorkflow(
  id: string,
  irInput: unknown,
  note?: string,
): Promise<WorkflowRecord> {
  const ir = readWorkflowIR(irInput);
  const workflow = await prisma.workflow.findUnique({ where: { id } });
  if (!workflow) throw new Error(`Workflow ${id} not found.`);
  const nextVersion = workflow.currentVersion + 1;
  const hash = contentHash(ir);
  await prisma.workflowVersion.create({
    data: { workflowId: id, version: nextVersion, ir: JSON.stringify(ir), contentHash: hash, note: note ?? null },
  });
  const updated = await prisma.workflow.update({
    where: { id },
    data: {
      name: ir.name,
      description: ir.description,
      tags: JSON.stringify(ir.meta.tags),
      currentVersion: nextVersion,
    },
  });
  return { ...toSummary(updated as WorkflowRow), ir, contentHash: hash, version: nextVersion };
}

export async function listVersions(id: string): Promise<VersionSummary[]> {
  const rows = await prisma.workflowVersion.findMany({
    where: { workflowId: id },
    orderBy: { version: 'desc' },
    select: { version: true, contentHash: true, note: true, createdAt: true },
  });
  return rows.map((r) => ({
    version: r.version,
    contentHash: r.contentHash,
    note: r.note,
    createdAt: r.createdAt.toISOString(),
  }));
}

export async function deleteWorkflow(id: string): Promise<boolean> {
  try {
    await prisma.workflow.delete({ where: { id } });
    return true;
  } catch {
    return false;
  }
}
