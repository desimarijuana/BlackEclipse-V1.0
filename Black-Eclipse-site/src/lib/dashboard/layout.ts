// ── Dashboard layout composition (pure) ──────────────────────────────────────
// Turns a persona template + the active market into a concrete WorkspaceLayout.
// Pure and framework-free (types + ops only) so it is unit-testable: the widget
// registry stays about widgets, this stays about arrangement.
//
// Track-board grammar (replaces the retired row-band grammar):
//   left zone : the personal Watchlist, one stacked track
//   main zone : one or more centre bands, each 1–4 tracks
//   right zone: asset-class stat tiles, one stacked track
// The masonry packer (workspace/pack.ts) balances each band's cards into the
// shortest track. A global first-wins dedupe runs across EVERY zone, so a
// widget never renders twice.
//
// SIZING has two modes (see WidgetPlacement):
//   FRAME  (`defaultHeight`) — the widget's content fills the card and/or
//          scrolls internally (charts, maps, live video, tables, feeds). The
//          card gets that height as a frame and its body stretches to fill.
//   GROW   (`minHeight`)     — compact tiles that size to content with a floor.
// Frame heights are deliberately VARIED per widget so bands pack into distinct,
// non-uniform shapes rather than a monotone grid.

import { newId, type WorkspaceColumn, type WorkspaceLayout, type WorkspaceSection, type WorkspaceZone, type WidgetPlacement } from '@/lib/workspace/types';
import { rebalanceColumns } from '@/lib/workspace/pack';

/** Asset classes for a market id (equity country, forex, commodities, crypto). */
export type AssetClass = 'equity' | 'forex' | 'commodities' | 'crypto';

export function assetClassFor(market: string): AssetClass {
  if (market === 'FOREX') return 'forex';
  if (market === 'COMMODITIES') return 'commodities';
  if (market === 'CRYPTO') return 'crypto';
  return 'equity';
}

/** Default centre track count when a band does not specify one. */
export const CENTRE_TRACKS = 3;

/**
 * FRAME heights (px): widgets whose content fills the card and must have a
 * definite box — charts, maps, live video, scrollable tables/feeds. The card
 * becomes a fixed frame and the widget body stretches into it.
 */
export const WIDGET_FRAME_HEIGHT: Record<string, number> = {
  // Charts / maps / media
  'eclipse-chart': 460,
  'tradingview-chart': 460,
  'asset-chart': 400,
  'candle-chart': 440,
  'economic-chart': 400,
  'fund-performance-chart': 420,
  'funds-comparison-chart': 360,
  'market-heatmap': 440,
  'live-tv': 460,
  'investor-eye': 420,
  'investor-eye-map': 460,
  // Tables / feeds / scrolling lists
  'news-feed': 380,
  'news-category': 380,
  'holdings': 380,
  'stock-screener': 420,
  'economic-calendar': 340,
  'earnings-calendar': 340,
  'trade-tape': 320,
  'active-alerts': 300,
  'journal-performance': 300,
  'geopolitics': 360,
  'maritime': 360,
  'agent-activity': 300,
  'recent-research': 300,
  'ai-insights': 300,
};

/**
 * GROW floors (px): compact tiles that size to their content with a floor.
 * These read best side-by-side because they never force a tall row.
 */
export const WIDGET_MIN_HEIGHT: Record<string, number> = {
  'market-status': 150,
  'market-regime': 260,
  'crypto-ticker': 130,
  'sparklines': 170,
  'quote-strip': 130,
  'top-movers': 280,
  'sector-heatmap': 280,
  'what-changed': 280,
  'opportunity-scanner': 300,
  'market-drivers': 280,
  'global-markets': 300,
  'macro-snapshot': 260,
  'commodities': 260,
  'forex-pairs': 260,
  'crypto-markets': 260,
  'polymarket': 300,
  'portfolio-summary': 280,
  'performance': 300,
  'risk-metrics': 220,
  'mp-fear-greed': 120,
  'mp-breadth': 150,
  'mp-movers': 260,
  'mp-snapshot': 240,
  'mp-hours': 220,
  'mp-indices': 240,
  'mp-forex': 240,
  'mp-crypto': 240,
  'mp-commodities': 240,
  'mp-country-watch': 280,
};

/** Floor for any widget id without an explicit hint. */
export const WIDGET_MIN_DEFAULT = 260;

/** Resolve a widget's intrinsic size hints by id. */
export function placementSizing(widgetId: string): { defaultHeight?: number; minHeight?: number } {
  const frame = WIDGET_FRAME_HEIGHT[widgetId];
  if (frame != null) return { defaultHeight: frame };
  return { minHeight: WIDGET_MIN_HEIGHT[widgetId] ?? WIDGET_MIN_DEFAULT };
}

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

/** A placement with its intrinsic sizing (height stays null = auto). */
function placement(widgetId: string, override?: Partial<Pick<WidgetPlacement, 'height' | 'defaultHeight' | 'minHeight'>>): WidgetPlacement {
  const sizing = placementSizing(widgetId);
  return { id: newId('wid'), widgetId, height: null, ...sizing, ...override };
}

/**
 * Build one STACKED section (single column) holding every widget id, each
 * sized to its intrinsic hints so stacked side tiles never stretch.
 */
function stackedSection(zone: WorkspaceZone, widgetIds: string[], override?: Partial<Pick<WidgetPlacement, 'height' | 'defaultHeight' | 'minHeight'>>): WorkspaceSection[] {
  if (widgetIds.length === 0) return [];
  return [{
    id: newId('sec'),
    zone,
    columns: [{
      id: newId('col'),
      weight: 1,
      widgets: widgetIds.map(widgetId => placement(widgetId, override)),
    }],
  }];
}

/** Right zone: the asset-class market stat tiles, stacked. */
export function buildRailSections(widgetIds: string[] = MARKET_RAIL_WIDGET_IDS): WorkspaceSection[] {
  return stackedSection('right', widgetIds);
}

/** Left zone: the personal watchlist, stacked at a generous frame. */
export function buildLeftSections(widgetIds: string[] = LEFT_WIDGET_IDS): WorkspaceSection[] {
  return stackedSection('left', widgetIds, { defaultHeight: 520 });
}

/**
 * One band cell: a widget id, or an object overriding its intrinsic height so a
 * persona can express intentional asymmetry (e.g. a taller hero chart).
 */
export type BoardCell = string | { id: string; h?: number; min?: number; frame?: boolean };

/**
 * A track-board band: one section, `tracks` columns, holding `cells` in
 * document order. The packer balances the cards across the tracks.
 */
export interface BoardSpec {
  zone?: WorkspaceZone;
  tracks?: number;
  cells: BoardCell[];
}

function cellToPlacement(cell: BoardCell): WidgetPlacement {
  if (typeof cell === 'string') return placement(cell);
  const { id, h, min, frame } = cell;
  if (h != null) return placement(id, frame === false ? { minHeight: h } : { defaultHeight: h });
  if (min != null) return placement(id, { minHeight: min });
  return placement(id);
}

/**
 * Compose specs into sections: drop unknown ids, dedupe globally (first wins),
 * cap each section at 4 tracks, and balance each section's cards with the
 * masonry packer so no track is left with dead space. This is the single place
 * the composition invariants are enforced.
 */
export function composeBoard(specs: BoardSpec[], known: ReadonlySet<string>): WorkspaceSection[] {
  const seen = new Set<string>();
  const sections: WorkspaceSection[] = [];
  for (const spec of specs) {
    const cells = spec.cells.filter(cell => {
      const id = typeof cell === 'string' ? cell : cell.id;
      if (!known.has(id) || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
    if (cells.length === 0) continue;

    // Never create more tracks than cards: an empty track is exactly the dead
    // space this grammar exists to remove.
    const tracks = Math.max(1, Math.min(4, Math.round(spec.tracks ?? 1), cells.length));
    const columns: WorkspaceColumn[] = Array.from({ length: tracks }, () => ({
      id: newId('col'),
      weight: 1,
      widgets: [],
    }));
    // Seed cards across tracks so the packer has something to balance; it then
    // re-distributes by estimated height.
    cells.forEach((cell, i) => columns[i % tracks].widgets.push(cellToPlacement(cell)));
    rebalanceColumns(columns);
    sections.push({ id: newId('sec'), zone: spec.zone ?? 'main', columns });
  }
  return sections;
}

/**
 * Build the starting layout for a single market view: the persona template's
 * centre, framed by a stacked Watchlist (left) and the market's stacked
 * asset-class stat tiles (right). `templateBase` is the persona layout from
 * `templates.ts`; when absent, only the two side tracks are produced.
 */
export function buildMarketViewLayout(
  market: string,
  baseWidgetIds: string[],
  templateBase?: WorkspaceLayout,
): WorkspaceLayout {
  const known = new Set(baseWidgetIds);
  const cls = assetClassFor(market);

  const centreSpecs: BoardSpec[] = templateBase
    ? templateBase.sections.map(s => ({
        zone: 'main' as WorkspaceZone,
        tracks: s.columns.length,
        cells: s.columns.flatMap(c => c.widgets.map(w => ({
          id: w.widgetId,
          ...(w.defaultHeight != null ? { h: w.defaultHeight } : {}),
          ...(w.minHeight != null ? { min: w.minHeight } : {}),
        }))),
      }))
    : [];

  const specs: BoardSpec[] = [
    { zone: 'left', tracks: 1, cells: LEFT_WIDGET_IDS },
    ...centreSpecs,
    { zone: 'right', tracks: 1, cells: ASSET_RAIL[cls] },
  ];

  return { version: 2, sections: composeBoard(specs, known) };
}

export { LEFT_WIDGET_IDS, ASSET_RAIL };
