// ── Agent Workspace — context-usage math (pure) ──────────────────────────────
// Turns the live workspace slices (context counts, telemetry tokens, prompt-plan
// sources, the run's model) into the numbers a context gauge renders. Kept pure,
// dependency-free and unit-tested. Honesty rule: when a value cannot be derived
// we return null / [] so the UI shows "Not available" — never a fabricated 0%.

import type { CatalogProvider } from '@/lib/agent/model-catalog';
import type { ContextSource } from './types';

/**
 * Resolve the context window for the run's model, in tokens.
 *
 * Priority: the provider's per-model window (the most specific declaration), then
 * the provider default. Returns null when neither is declared — the caller shows
 * "Not available" rather than guessing a window.
 */
export function resolveContextWindow(
  catalog: Record<string, CatalogProvider>,
  provider: string | undefined,
  model: string | undefined,
): number | null {
  const p = provider ? catalog[provider] : undefined;
  if (!p) return null;
  const perModel = model && p.modelWindows ? p.modelWindows[model] : null;
  if (perModel != null) return perModel;
  return p.contextWindow ?? null;
}

/**
 * Used ÷ window as a 0–100 percentage, clamped. Returns null when the window is
 * unknown (or non-positive), so a missing limit never renders as a full bar.
 */
export function usagePercent(
  used: number | undefined,
  window: number | null | undefined,
  windowKnown = true,
): number | null {
  if (!windowKnown) return null;
  if (used == null || !Number.isFinite(used) || used < 0) return null;
  if (window == null || !Number.isFinite(window) || window <= 0) return null;
  return Math.min(100, Math.max(0, (used / window) * 100));
}

export interface BreakdownSegment {
  id: string;
  /** Human label for the legend (the source name, else the id). */
  label: string;
  tokens: number;
  /** Share of the window (or of the reported total when the window is unknown). */
  percent: number;
  /** A Tailwind background class for the bar segment + legend dot. */
  color: string;
}

// A closed, legible palette — reused cyclically so N sources stay distinguishable.
const SOURCE_COLORS = [
  'bg-sky-400',
  'bg-emerald-400',
  'bg-amber-400',
  'bg-fuchsia-400',
  'bg-rose-400',
  'bg-violet-400',
  'bg-teal-400',
  'bg-orange-400',
] as const;

export function sourceColor(index: number): string {
  return SOURCE_COLORS[((index % SOURCE_COLORS.length) + SOURCE_COLORS.length) % SOURCE_COLORS.length];
}

/**
 * Build the segmented bar / legend from the prompt-plan sources. Segment widths
 * are relative to the window so the bar reflects real occupancy; when the window
 * is unknown they fall back to the share of the reported source total, so the
 * bar still shows composition (the caller must not print a usage % in that case).
 */
export function buildBreakdown(sources: ContextSource[], window: number | null): BreakdownSegment[] {
  const known = sources.filter((s) => s.tokens != null && s.tokens > 0);
  if (known.length === 0) return [];
  const total = known.reduce((n, s) => n + (s.tokens ?? 0), 0);
  const denom = window != null && window > 0 ? window : total;
  if (denom <= 0) return [];
  return known.map((s, i) => ({
    id: s.id,
    label: s.source ?? s.id,
    tokens: s.tokens ?? 0,
    percent: ((s.tokens ?? 0) / denom) * 100,
    color: sourceColor(i),
  }));
}
