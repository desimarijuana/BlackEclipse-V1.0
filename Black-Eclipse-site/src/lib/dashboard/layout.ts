// ── Dashboard layout composition (pure) ──────────────────────────────────────
// Turns a persona template + the active market into a concrete WorkspaceLayout.
// Pure and framework-free (types + ops only) so it is unit-testable: the widget
// registry stays about widgets, this stays about arrangement.
//
// Composition rules (the "band" grammar, see docs/ARCHITECTURE.md):
//   left zone : the personal Watchlist (thin, one widget)
//   main zone : the persona template (hero → primary → analysis → context)
//   right zone: asset-class market stat tiles (mp-*), thin
// A global first-wins dedupe runs across EVERY zone, so a widget never renders
// twice. Each section is capped at 4 columns AT BUILD TIME, so the layout the
// user sees is exactly the layout that is persisted (normalizeLayout also caps
// at 4 on read, which used to silently drop the 5th column on reload).

import { newId, type WorkspaceColumn, type WorkspaceLayout, type WorkspaceSection, type WorkspaceZone } from '@/lib/workspace/types';

/** Asset classes for a market id (equity country, forex, commodities, crypto). */
export type AssetClass = 'equity' | 'forex' | 'commodities' | 'crypto';

export function assetClassFor(market: string): AssetClass {
  if (market === 'FOREX') return 'forex';
  if (market === 'COMMODITIES') return 'commodities';
  if (market === 'CRYPTO') return 'crypto';
  return 'equity';
}

const MAX_COLUMNS = 4;

/** Left zone: the personal watchlist only. Never duplicated in the centre. */
const LEFT_WIDGET_IDS = ['watchlist'];

/**
 * Right zone (asset-class stats). FOREX / COMMODITIES have no JDDS overview
 * group, so overview-driven tiles (movers, breadth) are omitted there.
 */
const ASSET_RAIL: Record<AssetClass, string[]> = {
  equity: ['mp-indices', 'mp-movers', 'mp-breadth', 'mp-snapshot'],
  forex: ['mp-forex', 'mp-snapshot', 'mp-hours'],
  commodities: ['mp-commodities', 'mp-snapshot', 'mp-hours'],
  crypto: ['mp-crypto', 'mp-movers', 'mp-fear-greed', 'mp-breadth'],
};

/** Widget ids that ship in the default right zone (kept for compatibility). */
export const MARKET_RAIL_WIDGET_IDS = [
  'mp-fear-greed', 'mp-breadth', 'mp-movers', 'mp-snapshot', 'mp-hours',
];

/** Build a section per widget id (one widget per column), in the given zone. */
function sectionsFor(zone: WorkspaceZone, widgetIds: string[]): WorkspaceSection[] {
  return widgetIds.map(widgetId => ({
    id: newId('sec'),
    zone,
    columns: [{ id: newId('col'), weight: 1, widgets: [{ id: newId('wid'), widgetId, height: null }] }],
  }));
}

/** Right zone: the asset-class market stat tiles. */
export function buildRailSections(widgetIds: string[] = MARKET_RAIL_WIDGET_IDS): WorkspaceSection[] {
  return sectionsFor('right', widgetIds);
}

/** Left zone: the personal watchlist column. */
export function buildLeftSections(widgetIds: string[] = LEFT_WIDGET_IDS): WorkspaceSection[] {
  return sectionsFor('left', widgetIds);
}

/** A section spec: widget ids placed one-per-column, with optional weights. */
export interface LayoutRow {
  zone?: WorkspaceZone;
  cells: Array<{ widget: string; weight?: number }>;
}

/** Flatten a built layout back into rows (one cell per widget) for re-composition. */
export function layoutToRows(layout: WorkspaceLayout): LayoutRow[] {
  return layout.sections.map(section => ({
    zone: section.zone ?? 'main',
    cells: section.columns.flatMap(col =>
      col.widgets.map(w => ({ widget: w.widgetId, weight: col.weight })),
    ),
  }));
}

/**
 * Compose rows into sections: drop unknown ids, dedupe globally (first wins),
 * and cap each section at 4 columns. This is the single place the composition
 * invariants are enforced.
 */
export function composeRows(rows: LayoutRow[], known: ReadonlySet<string>): WorkspaceSection[] {
  const seen = new Set<string>();
  const sections: WorkspaceSection[] = [];
  for (const row of rows) {
    const columns: WorkspaceColumn[] = [];
    for (const cell of row.cells) {
      if (!known.has(cell.widget) || seen.has(cell.widget)) continue;
      seen.add(cell.widget);
      columns.push({
        id: newId('col'),
        weight: cell.weight ?? 1,
        widgets: [{ id: newId('wid'), widgetId: cell.widget, height: null }],
      });
      if (columns.length >= MAX_COLUMNS) break;
    }
    if (columns.length > 0) {
      sections.push({ id: newId('sec'), zone: row.zone ?? 'main', columns });
    }
  }
  return sections;
}

/**
 * Build the starting layout for a single market view: the persona template's
 * centre, framed by a thin Watchlist (left) and the market's asset-class stat
 * tiles (right). `templateBase` is the persona layout from `templates.ts`; when
 * absent, the caller's default body is used.
 */
export function buildMarketViewLayout(
  market: string,
  baseWidgetIds: string[],
  templateBase?: WorkspaceLayout,
): WorkspaceLayout {
  const known = new Set(baseWidgetIds);
  const cls = assetClassFor(market);

  const rows: LayoutRow[] = [
    { zone: 'left', cells: LEFT_WIDGET_IDS.map(widget => ({ widget })) },
    ...(templateBase && templateBase.sections.length > 0
      ? layoutToRows(templateBase)
      : []),
    { zone: 'right', cells: ASSET_RAIL[cls].map(widget => ({ widget })) },
  ];

  return { version: 1, sections: composeRows(rows, known) };
}

export { LEFT_WIDGET_IDS, ASSET_RAIL };
