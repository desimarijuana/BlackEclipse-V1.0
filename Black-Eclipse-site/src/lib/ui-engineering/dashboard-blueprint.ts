'use client';

// ── Command Center → blueprint mirror (Phase E) ──────────────────────────────
// The Command Center keeps its arrangement in localStorage; the agent's `ui_*`
// tools read and write blueprints. This bridges them ONE WAY (dashboard →
// blueprint) so the agent can see and edit the board the user actually has,
// and so a dashboard appears as a page. It is best-effort: a publish failure
// never affects the dashboard. The reverse (agent edit → dashboard) is a
// deliberate follow-up (see docs/harness/capability-extension-plan.md).

import type { WorkspaceLayout as KernelLayout } from '@/lib/workspace/types';
import { kernelLayoutToWire } from '@/lib/ui-engineering/live-page';
import { createPage, getBlueprint, saveLayout } from '@/lib/harness/ui-client';

const BP_KEY_PREFIX = 'be_dash_bp:';

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

/** Resolve (creating once) the blueprint id that mirrors a dashboard. */
async function resolveBlueprintId(dashboardId: string, title: string): Promise<string> {
  const existing = readBpId(dashboardId);
  if (existing) return existing;
  // `idempotencyKey` makes a concurrent/retried create return the same page.
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
      await saveLayout(id, wire, blueprint.revision);
    } catch {
      // A cached id whose blueprint was deleted — drop it and recreate once.
      try {
        window.localStorage.removeItem(bpKey(opts.dashboardId));
      } catch {
        /* ignore */
      }
      const freshId = await resolveBlueprintId(opts.dashboardId, opts.title);
      const { blueprint } = await getBlueprint(freshId);
      await saveLayout(freshId, wire, blueprint.revision);
    }
    return true;
  } catch {
    return false;
  }
}
