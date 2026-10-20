// ── Dashboard template/reset (the ONE TS template registry) ──────────────────
// The persona templates and the side rails live in TypeScript. The SDK route
// builds a complete layout here and writes it through the Python dashboard
// layout API, so there is no second copy of the template registry in Python.

import {
  DASHBOARD_TEMPLATES,
  LEGACY_TEMPLATE_IDS,
  resolveTemplateId,
  TEMPLATE_WIDGET_IDS,
} from '@/lib/dashboard/templates';
import {
  ASSET_RAIL,
  LEFT_WIDGET_IDS,
  MARKET_RAIL_WIDGET_IDS,
  buildMarketViewLayout,
} from '@/lib/dashboard/layout';
import { getDefaultBoard } from '@/lib/dashboard/default-board';
import type { WorkspaceLayout } from '@/lib/workspace/types';

export interface DashboardTemplateSummary {
  id: string;
  name: string;
  description: string;
}

/** The widget ids a template layout may reference on the server. */
const TEMPLATE_KNOWN_WIDGET_IDS: readonly string[] = [
  ...TEMPLATE_WIDGET_IDS,
  ...LEFT_WIDGET_IDS,
  ...MARKET_RAIL_WIDGET_IDS,
  ...Object.values(ASSET_RAIL).flat(),
];

function knownIds(extra?: Iterable<string>): Set<string> {
  return new Set([...TEMPLATE_KNOWN_WIDGET_IDS, ...(extra ?? [])]);
}

export function listDashboardTemplates(): DashboardTemplateSummary[] {
  return DASHBOARD_TEMPLATES.map(({ id, name, desc }) => ({ id, name, description: desc }));
}

/**
 * Build a full board: the persona's centre bands plus the left Watchlist and
 * the market's right asset rail. Unknown/legacy ids resolve to the same
 * fallback the dashboard screen uses; a completely unknown id is rejected so a
 * typo cannot silently replace a board with the default.
 */
export function buildDashboardTemplateLayout(
  templateId: string,
  options: { market?: string; knownWidgetIds?: Iterable<string> } = {},
): WorkspaceLayout {
  const raw = (templateId || '').trim();
  const knownTemplate = DASHBOARD_TEMPLATES.some((entry) => entry.id === raw)
    || Object.prototype.hasOwnProperty.call(LEGACY_TEMPLATE_IDS, raw);
  if (!knownTemplate) throw new Error(`unknown dashboard template "${templateId}"`);
  const resolved = resolveTemplateId(raw);
  const template = DASHBOARD_TEMPLATES.find((entry) => entry.id === resolved);
  if (!template) throw new Error(`unknown dashboard template "${templateId}"`);
  const known = knownIds(options.knownWidgetIds);
  const centre = template.build(known);
  return buildMarketViewLayout(options.market ?? 'US', [...known], centre);
}

/**
 * Reset to the shipped default board when one is configured, else to the first
 * persona template. Mirrors `DashboardScreen`'s first-run priority.
 */
export function buildDefaultDashboardLayout(
  options: { market?: string; knownWidgetIds?: Iterable<string> } = {},
): WorkspaceLayout {
  const known = knownIds(options.knownWidgetIds);
  const curated = getDefaultBoard(known);
  if (curated) return buildMarketViewLayout(options.market ?? 'US', [...known], curated);
  return buildDashboardTemplateLayout(DASHBOARD_TEMPLATES[0].id, {
    market: options.market,
    knownWidgetIds: known,
  });
}
