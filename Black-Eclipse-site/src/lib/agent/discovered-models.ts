// ── Discovered-models cache ──────────────────────────────────────────────────
// A "Discover installed models" probe registers the models a live provider
// (Ollama, LM Studio, a router) actually serves into the Python runtime's
// in-process registry. That registry is rebuilt on every runtime restart and the
// client list resets on remount, so without this cache the operator has to click
// "Discover" again and again just to see their own installed models.
//
// This is a durable, non-secret snapshot of the model IDs found by the last
// probe, stored in `SystemConfig` (the same config store the rest of the app
// uses). It is a CONVENIENCE list, never an allowlist: the runtime remains the
// authority and any model id can still be typed by hand. It lives on the server
// so every surface (Settings › AI and the chat composer) reads one copy, and it
// survives a page reload and a runtime restart.

import { prisma } from '@/lib/db';

export const DISCOVERED_MODELS_CONFIG_KEY = 'discovered_models_v1';

export interface DiscoveredSnapshot {
  /** Runtime provider id → model ids returned by the last successful probe. */
  providers: Record<string, string[]>;
  /**
   * Runtime provider id → the model ids the provider ACTUALLY serves. This is
   * the subset of `providers` the live probe genuinely found; the static
   * catalog's declared placeholders (e.g. Ollama's `llama3.1`) are excluded.
   *
   * The distinction matters: a keyless local server's declared default may not
   * be installed at all, so choosing a default from `providers` can pick a
   * model the server will 404 on. `served` is the set that is safe to default
   * to. Absent for snapshots written before this field existed — callers treat
   * a missing entry as "unknown" and re-probe.
   */
  served: Record<string, string[]>;
  updatedAt: string;
}

const EMPTY: DiscoveredSnapshot = { providers: {}, served: {}, updatedAt: new Date(0).toISOString() };

function sanitize(map: Record<string, unknown> | undefined): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const [id, ids] of Object.entries(map ?? {})) {
    if (Array.isArray(ids)) out[id] = ids.filter((m): m is string => typeof m === 'string' && m.length > 0);
  }
  return out;
}

export async function readDiscoveredModels(): Promise<DiscoveredSnapshot> {
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key: DISCOVERED_MODELS_CONFIG_KEY } });
    if (!row?.value) return EMPTY;
    const parsed = JSON.parse(row.value) as Partial<DiscoveredSnapshot>;
    return {
      providers: sanitize(parsed.providers),
      served: sanitize(parsed.served),
      updatedAt: parsed.updatedAt ?? EMPTY.updatedAt,
    };
  } catch {
    return EMPTY;
  }
}

/**
 * Merge the models a probe found for one provider into the durable snapshot.
 * Merges (never replaces) so discovering provider B does not erase provider A,
 * and a later probe that returns fewer models cannot drop already-known ones.
 *
 * `servedIds` (optional) is the subset the provider genuinely serves. It is
 * merged the same way. When a probe cannot distinguish served models it is
 * omitted, and any previously-known served set is left untouched.
 */
export async function recordDiscoveredModels(
  providerId: string,
  modelIds: string[],
  servedIds?: string[],
): Promise<DiscoveredSnapshot> {
  const current = await readDiscoveredModels();
  const merged = new Set([...(current.providers[providerId] ?? []), ...modelIds.filter(Boolean)]);
  // `served` is REPLACED by each successful probe (not merged): it must reflect
  // what the server serves NOW, or a model since removed would keep being
  // chosen as the default and 404. When the probe omits `servedIds`, the
  // previously-known set is preserved.
  const served =
    servedIds === undefined ? current.served[providerId] : Array.from(new Set(servedIds.filter(Boolean)));
  const next: DiscoveredSnapshot = {
    providers: { ...current.providers, [providerId]: [...merged] },
    served: { ...current.served, [providerId]: served ?? [] },
    updatedAt: new Date().toISOString(),
  };
  const value = JSON.stringify(next);
  await prisma.systemConfig.upsert({
    where: { key: DISCOVERED_MODELS_CONFIG_KEY },
    update: { value },
    create: { key: DISCOVERED_MODELS_CONFIG_KEY, value },
  });
  return next;
}
