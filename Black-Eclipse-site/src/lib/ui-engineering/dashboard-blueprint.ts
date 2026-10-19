'use client';

// ── Command Center ↔ blueprint bridge (Phase E) ──────────────────────────────
// The Command Center keeps its arrangement in localStorage; the agent's `ui_*`
// tools read and write blueprints. This bridges them BOTH ways:
//   * dashboard → blueprint (`publishDashboardLayout`), so the agent can see and
//     edit the board the user actually has, and so a dashboard appears as a page;
//   * blueprint → dashboard (`fetchDashboardLayout` + `isOwnPublish`), so an
//     agent edit lands on the live board — the Command Center persists the
//     fetched layout and remounts the workspace when a revision it did NOT
//     publish arrives. The client's own publishes are tracked, so the sync never
//     fights the user's own editing.
// It is best-effort: a publish or sync failure never affects the dashboard.

import type { WorkspaceLayout as KernelLayout } from '@/lib/workspace/types';
import { blueprintLayoutToKernel, kernelLayoutToWire } from '@/lib/ui-engineering/live-page';
import { createPage, getBlueprint, resolveCurrentPage, saveLayout } from '@/lib/harness/ui-client';

const BP_KEY_PREFIX = 'be_dash_bp:';

/** The last blueprint revision THIS client published, per dashboard. */
const publishedRevisions = new Map<string, number>();

function bpKey(dashboardId: string): string {
  return `${BP_KEY_PREFIX}${dashboardId}`;
}

function readBpId(dashboardId: string): string | null {
  try {
    return window.localStorage.getItem(bpKey(dashboardId));
  } catch {
    return null;
  }
}

function writeBpId(dashboardId: string, id: string): void {
  try {
    window.localStorage.setItem(bpKey(dashboardId), id);
  } catch {
    /* storage unavailable — the id is re-resolved next time */
  }
}

async function findBlueprintId(dashboardId: string): Promise<string | null> {
  try {
    const { blueprint } = await resolveCurrentPage({ path: `/dashboard/${dashboardId}` });
    if (blueprint?.id) {
      writeBpId(dashboardId, blueprint.id);
      return blueprint.id;
    }
  } catch {
    /* no mirror yet */
  }
  return null;
}

/** Resolve (creating once) the blueprint id that mirrors a dashboard. */
async function resolveBlueprintId(dashboardId: string, title: string): Promise<string> {
  const existing = readBpId(dashboardId);
  if (existing) return existing;
  const found = await findBlueprintId(dashboardId);
  if (found) return found;
  const { blueprint } = await createPage({
    title,
    kind: 'workspace',
    path: `/dashboard/${dashboardId}`,
    idempotencyKey: `dash-bp:${dashboardId}`,
  });
  writeBpId(dashboardId, blueprint.id);
  return blueprint.id;
}

/**
 * Mirror a dashboard's kernel layout into its blueprint (creating the blueprint
 * on first use). Returns true when the blueprint was updated. Never throws.
 */
export async function publishDashboardLayout(opts: {
  dashboardId: string;
  title: string;
  layout: KernelLayout;
}): Promise<boolean> {
  if (typeof window === 'undefined') return false;
  const wire = kernelLayoutToWire(opts.layout);
  try {
    const id = await resolveBlueprintId(opts.dashboardId, opts.title);
    try {
      const { blueprint } = await getBlueprint(id);
      const { blueprint: saved } = await saveLayout(id, wire, blueprint.revision);
      publishedRevisions.set(opts.dashboardId, saved.revision);
    } catch {
      // A cached id whose blueprint was deleted — drop it and recreate once.
      try {
        window.localStorage.removeItem(bpKey(opts.dashboardId));
      } catch {
        /* ignore */
      }
      const freshId = await resolveBlueprintId(opts.dashboardId, opts.title);
      const { blueprint } = await getBlueprint(freshId);
      const { blueprint: saved } = await saveLayout(freshId, wire, blueprint.revision);
      publishedRevisions.set(opts.dashboardId, saved.revision);
    }
    return true;
  } catch {
    return false;
  }
}

/**
 * Fetch a dashboard's mirrored blueprint layout (the reverse direction). Returns
 * null when there is no mirrored blueprint yet, or the fetch failed. Never throws.
 */
export async function fetchDashboardLayout(
  dashboardId: string,
): Promise<{ revision: number; layout: KernelLayout } | null> {
  if (typeof window === 'undefined') return null;
  const id = readBpId(dashboardId) ?? await findBlueprintId(dashboardId);
  if (!id) return null;
  try {
    const { blueprint } = await getBlueprint(id);
    return { revision: blueprint.revision, layout: blueprintLayoutToKernel(blueprint.layout) };
  } catch {
    return null;
  }
}

/** Whether this client published the given revision (so the sync must skip it). */
export function isOwnPublish(dashboardId: string, revision: number): boolean {
  return publishedRevisions.get(dashboardId) === revision;
}

/**
 * A key-order-insensitive structural key for a kernel layout — the sync's
 * equality test. Two layouts persisted/round-tripped through different code
 * paths must compare equal, or the board would remount on every load.
 */
export function stableLayoutKey(layout: KernelLayout): string {
  const stabilize = (value: unknown): unknown => {
    if (Array.isArray(value)) return value.map(stabilize);
    if (value && typeof value === 'object') {
      return Object.keys(value as Record<string, unknown>)
        .sort()
        .reduce<Record<string, unknown>>((acc, key) => {
          acc[key] = stabilize((value as Record<string, unknown>)[key]);
          return acc;
        }, {});
    }
    return value;
  };
  return JSON.stringify(stabilize(layout));
}

