'use client';

// ── Runtime catalog sync (host registry → Python catalog) ─────────────────────
// The Python UI runtime needs to know the REAL dashboard widget ids to let the
// agent Compose with them. Rather than hand-maintain a second copy in Python,
// the browser (which already loads the widget registry) pushes the adapted specs
// into the runtime ONCE; the runtime persists them on agent-memory.db, so they
// survive restarts. Idempotent: `register_component` upserts by id.
//
// The second sync ships the app's FIXED screen inventory (tabs + sub-tabs +
// deep links) derived from `src/lib/app-surfaces.ts`, so the agent can answer
// "where is X in the app?" and never treats a saved dashboard as the app's
// screen list. Idempotent: `replace_surfaces` upserts the whole batch.

import { appSurfaces } from '@/lib/app-surfaces';
import { dashboardComponentSpecs } from '@/lib/ui-engineering/registry-catalog';
import { registerComponents, registerSurfaces } from '@/lib/harness/ui-client';

let synced = false;
let surfacesSynced = false;

export interface SyncResult { total: number; registered: number; failed: number }

/** Push the dashboard widget specs into the runtime catalog. Safe to call often. */
export async function syncCoreCatalog(force = false): Promise<SyncResult> {
  if (synced && !force) return { total: 0, registered: 0, failed: 0 };
  let specs;
  try {
    specs = dashboardComponentSpecs();
  } catch {
    return { total: 0, registered: 0, failed: 0 };
  }
  if (specs.length === 0) return { total: 0, registered: 0, failed: 0 };
  // ONE batched request instead of one POST per spec. The app shell mounts on
  // every full page load, so the old per-spec loop fired ~80 sequential
  // browser→Next→Python round-trips each load and saturated the runtime; the
  // runtime upserts idempotently either way, so batching is behaviour-preserving.
  try {
    const res = await registerComponents(specs);
    const registered = res.registered ?? 0;
    if (registered > 0) synced = true;
    return { total: res.total ?? specs.length, registered, failed: res.failed?.length ?? 0 };
  } catch {
    return { total: specs.length, registered: 0, failed: specs.length };
  }
}

/** Push the app's screen inventory into the runtime. Safe to call often. */
export async function syncAppSurfaces(force = false): Promise<SyncResult> {
  if (surfacesSynced && !force) return { total: 0, registered: 0, failed: 0 };
  let surfaces;
  try {
    surfaces = appSurfaces();
  } catch {
    return { total: 0, registered: 0, failed: 0 };
  }
  if (surfaces.length === 0) return { total: 0, registered: 0, failed: 0 };
  try {
    const res = await registerSurfaces(surfaces);
    const registered = res.registered ?? 0;
    if (registered > 0) surfacesSynced = true;
    const total = res.total ?? surfaces.length;
    return { total, registered, failed: Math.max(0, total - registered) };
  } catch {
    return { total: surfaces.length, registered: 0, failed: surfaces.length };
  }
}
