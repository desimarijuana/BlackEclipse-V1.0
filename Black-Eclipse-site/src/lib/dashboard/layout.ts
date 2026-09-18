// ── Dashboard layout composition (pure) ──────────────────────────────────────
// Turns a persona template + the active market into a concrete WorkspaceLayout.
// Pure and framework-free (types + ops only) so it is unit-testable: the widget
// registry stays about widgets, this stays about arrangement.
//
// Composition rules (the "band" grammar, see docs/ARCHITECTURE.md):
//   left zone : the personal Watchlist, STACKED in one section
//   main zone : the persona template (hero → primary → analysis → context)
//   right zone: asset-class stat tiles, STACKED in one section
// A global first-wins dedupe runs across EVERY zone, so a widget never renders
// twice. Each section is capped at 4 columns AT BUILD TIME. Side rails are a
// single STACKED section (not one section per tile) so tiles sit close together
// with no per-section padding/gap — the old one-section-per-widget shape was
// what made the rails look full of dead gaps.

import { newId, type WorkspaceColumn, type WorkspaceLayout, type WorkspaceSection, type WorkspaceZone, type WidgetPlacement } from '@/lib/workspace/types';

/** Asset classes for a market id (equity country, forex, commodities, crypto). */
export type AssetClass = 'equity' | 'forex' | 'commodities' | 'crypto';

export function assetClassFor(market: string): AssetClass {
  if (market === 'FOREX') return 'forex';
  if (market === 'COMMODITIES') return 'commodities';
  if (market === 'CRYPTO') return 'crypto';
  return 'equity';
}

const MAX_COLUMNS = 4;

/**
 * Default band heights (px). Every default placement is pinned to one of these
 * so a widget never stretches into dead space and rows can be authored as
 * matched-height pairs. `auto` (null) is only used for user-added widgets.
 */
export const HEIGHTS = {
  /** One-line tickers / strips. */
  strip: 130,
  /** Small status / KPI tiles. */
  tile: 190,
  /** Standard panel (lists, tables, feeds). */
  panel: 300,
  /** Tall news / live / map panels. */
  tall: 420,
  /** The full-width primary visual (chart, heatmap, map). */
  chart: 460,
  /** Live TV — deliberately large so it is watchable. */
  live: 520,
  /** Auto height — natural content size (user-added widgets only). */
  auto: null,
} as const;

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

/**
 * Build one STACKED section (single column) holding every widget id, each
 * pinned to `height` (default `HEIGHTS.tile`) so stacked rail tiles never
 * stretch.
 */
function stackedSection(zone: WorkspaceZone, widgetIds: string[], height: number | null = HEIGHTS.tile): WorkspaceSection[] {
  if (widgetIds.length === 0) return [];
  return [{
    id: newId('sec'),
    zone,
    columns: [{
      id: newId('col'),
      weight: 1,
      widgets: widgetIds.map(widgetId => ({ id: newId('wid'), widgetId, height })),
    }],
  }];
}

/** Right zone: the asset-class market stat tiles, stacked. */
export function buildRailSections(widgetIds: string[] = MARKET_RAIL_WIDGET_IDS): WorkspaceSection[] {
  return stackedSection('right', widgetIds);
}

/** Left zone: the personal watchlist, stacked. */
export function buildLeftSections(widgetIds: string[] = LEFT_WIDGET_IDS): WorkspaceSection[] {
  return stackedSection('left', widgetIds, HEIGHTS.panel);
}

/**
 * A row spec. `stack: true` puts every cell in ONE column of a single section
 * (used for the side rails); otherwise each cell is its own column.
 * `height` pins a card's pixel height (null = auto/stretch).
 */
export interface LayoutRow {
  zone?: WorkspaceZone;
  stack?: boolean;
  cells: Array<{ widget: string; weight?: number; height?: number | null }>;
}

/** Flatten a built layout back into rows for re-composition. */
export function layoutToRows(layout: WorkspaceLayout): LayoutRow[] {
  return layout.sections.map(section => ({
    zone: section.zone ?? 'main',
    cells: section.columns.flatMap(col =>
      col.widgets.map(w => ({ widget: w.widgetId, weight: col.weight, height: w.height })),
    ),
  }));
}

/** A placement with the cell's pinned height (null = auto). */
function placement(widgetId: string, height?: number | null): WidgetPlacement {
  return { id: newId('wid'), widgetId, height: height ?? null };
}

/**
 * Compose rows into sections: drop unknown ids, dedupe globally (first wins),
 * cap each section at 4 columns, and honour each cell's pinned height. This is
 * the single place the composition invariants are enforced.
 */
export function composeRows(rows: LayoutRow[], known: ReadonlySet<string>): WorkspaceSection[] {
  const seen = new Set<string>();
  const sections: WorkspaceSection[] = [];
  for (const row of rows) {
    const cells = row.cells.filter(cell => {
      if (!known.has(cell.widget) || seen.has(cell.widget)) return false;
      seen.add(cell.widget);
      return true;
    });
    if (cells.length === 0) continue;

    if (row.stack) {
      sections.push({
        id: newId('sec'),
        zone: row.zone ?? 'main',
        columns: [{
          id: newId('col'),
          weight: 1,
          widgets: cells.map(c => placement(c.widget, c.height)),
        }],
      });
      continue;
    }

    const columns: WorkspaceColumn[] = cells.slice(0, MAX_COLUMNS).map(cell => ({
      id: newId('col'),
      weight: cell.weight ?? 1,
      widgets: [placement(cell.widget, cell.height)],
    }));
    sections.push({ id: newId('sec'), zone: row.zone ?? 'main', columns });
  }
  return sections;
}

/**
 * Build the starting layout for a single market view: the persona template's
 * centre, framed by a stacked Watchlist (left) and the market's stacked
 * asset-class stat tiles (right). `templateBase` is the persona layout from
 * `templates.ts`; when absent, only the two rails are produced.
 */
export function buildMarketViewLayout(
  market: string,
  baseWidgetIds: string[],
  templateBase?: WorkspaceLayout,
): WorkspaceLayout {
  const known = new Set(baseWidgetIds);
  const cls = assetClassFor(market);

  const rows: LayoutRow[] = [
    { zone: 'left', stack: true, cells: LEFT_WIDGET_IDS.map(widget => ({ widget, height: HEIGHTS.panel })) },
    ...(templateBase && templateBase.sections.length > 0
      ? layoutToRows(templateBase)
      : []),
    { zone: 'right', stack: true, cells: ASSET_RAIL[cls].map(widget => ({ widget, height: HEIGHTS.tile })) },
  ];

  return { version: 1, sections: composeRows(rows, known) };
}

export { LEFT_WIDGET_IDS, ASSET_RAIL };
