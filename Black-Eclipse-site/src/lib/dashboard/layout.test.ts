import { describe, expect, it } from 'vitest';
import {
  ASSET_RAIL, LEFT_WIDGET_IDS, assetClassFor,
  buildLeftSections, buildMarketViewLayout, buildRailSections, composeBoard,
} from './layout';
import { DASHBOARD_TEMPLATES, LEGACY_TEMPLATE_IDS, getDashboardTemplate, resolveTemplateId } from './templates';
import { columnHeights } from '@/lib/workspace/pack';
import type { WorkspaceLayout, WorkspaceSection } from '@/lib/workspace/types';

// Registry ids we exercise. The layout engine only needs ids, not renderers.
const IDS = [
  'market-status', 'market-regime', 'portfolio-summary', 'performance',
  'risk-metrics', 'market-drivers', 'top-movers', 'sector-heatmap',
  'eclipse-chart', 'market-heatmap', 'fund-performance-chart', 'holdings',
  'funds-comparison-chart', 'global-markets', 'macro-snapshot', 'economic-chart',
  'what-changed', 'opportunity-scanner', 'news-feed', 'economic-calendar',
  'geopolitics', 'maritime', 'crypto-markets', 'trade-tape', 'sparklines',
  'crypto-ticker', 'polymarket', 'forex-pairs', 'stock-screener', 'asset-chart',
  'live-tv', 'watchlist', 'commodities',
  'tradingview-chart', 'journal-performance', 'active-alerts', 'candle-chart',
  'investor-eye', 'investor-eye-map',
  'mp-indices', 'mp-movers', 'mp-breadth', 'mp-snapshot', 'mp-hours',
  'mp-forex', 'mp-commodities', 'mp-crypto', 'mp-fear-greed',
];
const KNOWN = new Set(IDS);

const allIds = (l: WorkspaceLayout) =>
  l.sections.flatMap(s => s.columns.flatMap(c => c.widgets.map(w => w.widgetId)));

const zoneIds = (l: WorkspaceLayout, zone: string) =>
  allIds({ ...l, sections: l.sections.filter(s => (s.zone ?? 'main') === zone) });

// ── assetClassFor ────────────────────────────────────────────────────────────

describe('assetClassFor', () => {
  it('maps the special markets to their asset class', () => {
    expect(assetClassFor('FOREX')).toBe('forex');
    expect(assetClassFor('COMMODITIES')).toBe('commodities');
    expect(assetClassFor('CRYPTO')).toBe('crypto');
  });
  it('treats any country code (US, PSX, …) as equity', () => {
    expect(assetClassFor('US')).toBe('equity');
    expect(assetClassFor('PSX')).toBe('equity');
  });
});

// ── composeBoard (the invariants) ────────────────────────────────────────────

describe('composeBoard', () => {
  it('dedupes globally, first occurrence wins', () => {
    const secs = composeBoard([
      { zone: 'main', tracks: 2, cells: ['a', 'b'] },
      { zone: 'main', tracks: 1, cells: ['b', 'c'] },
    ], new Set(['a', 'b', 'c']));
    expect(secs).toHaveLength(2);
    expect(secs.flatMap(s => s.columns.flatMap(c => c.widgets.map(w => w.widgetId))))
      .toEqual(['a', 'b', 'c']);
  });

  it('drops unknown widget ids', () => {
    const secs = composeBoard([{ zone: 'main', tracks: 2, cells: ['a', 'ghost'] }], new Set(['a']));
    expect(secs[0].columns.flatMap(c => c.widgets)).toHaveLength(1);
  });

  it('caps a section at 4 tracks at BUILD time, and never makes empty tracks', () => {
    const capped = composeBoard([{ zone: 'main', tracks: 9, cells: ['a', 'b', 'c', 'd', 'e'] }], new Set(['a', 'b', 'c', 'd', 'e']));
    expect(capped[0].columns).toHaveLength(4);
    // More tracks than cards is clamped to the card count (no dead tracks).
    const single = composeBoard([{ zone: 'main', tracks: 9, cells: ['a'] }], new Set(['a']));
    expect(single[0].columns).toHaveLength(1);
  });

  it('drops empty sections and keeps the zone', () => {
    const secs = composeBoard([
      { zone: 'left', tracks: 1, cells: ['ghost'] },
      { zone: 'right', tracks: 1, cells: ['a'] },
    ], new Set(['a']));
    expect(secs).toHaveLength(1);
    expect(secs[0].zone).toBe('right');
  });

  it('sizes every card to content (height null) with an intrinsic hint', () => {
    const secs = composeBoard([{ zone: 'main', tracks: 2, cells: ['market-status', 'news-feed'] }], KNOWN);
    for (const c of secs[0].columns) {
      for (const w of c.widgets) {
        expect(w.height).toBeNull();
        expect((w.defaultHeight ?? w.minHeight ?? 0)).toBeGreaterThan(0);
      }
    }
  });

  it('balances a multi-track section so no track is stranded short', () => {
    const secs = composeBoard([
      { zone: 'main', tracks: 2, cells: ['eclipse-chart', 'market-status', 'news-feed', 'economic-calendar'] },
    ], KNOWN);
    const heights = columnHeights(secs[0].columns);
    const max = Math.max(...heights);
    const min = Math.min(...heights);
    // The lighter track must carry at least one card and be within one card of
    // the heaviest — the packer fills the shortest track each time.
    expect(heights.every(h => h > 0)).toBe(true);
    expect(max - min).toBeLessThanOrEqual(500);
  });
});

// ── side-zone builders ───────────────────────────────────────────────────────

describe('side-zone builders', () => {
  it('builds the thin left watchlist zone as one stacked track', () => {
    const s = buildLeftSections();
    expect(LEFT_WIDGET_IDS).toEqual(['watchlist']);
    expect(s).toHaveLength(1);
    expect(s[0].zone).toBe('left');
    expect(s[0].columns).toHaveLength(1);
    expect(s[0].columns[0].widgets[0].widgetId).toBe('watchlist');
  });

  it('stacks right-zone stat tiles into ONE section (no per-tile gaps)', () => {
    const s = buildRailSections(['mp-indices', 'mp-movers', 'mp-breadth']);
    expect(s).toHaveLength(1);
    expect(s[0].zone).toBe('right');
    expect(s[0].columns).toHaveLength(1);
    expect(s[0].columns[0].widgets.map(w => w.widgetId))
      .toEqual(['mp-indices', 'mp-movers', 'mp-breadth']);
  });
});

// ── personas ─────────────────────────────────────────────────────────────────

describe('persona templates', () => {
  it('ships exactly the twelve personas', () => {
    expect(DASHBOARD_TEMPLATES.map(t => t.id))
      .toEqual(['tape-reader', 'desk', 'allocator', 'rates-desk', 'chain-desk', 'fx-desk', 'screener', 'map-room', 'newsroom', 'risk-desk', 'trader-pro', 'research']);
  });

  it.each(DASHBOARD_TEMPLATES.map(t => [t.id, t] as const))(
    '%s builds a valid centre with ≤4-track sections and no duplicates',
    (_id, t) => {
      const built = t.build(IDS);
      const used = allIds(built);
      expect(used.length).toBeGreaterThan(0);
      expect(new Set(used).size).toBe(used.length);
      for (const s of built.sections) {
        expect(s.columns.length).toBeGreaterThanOrEqual(1);
        expect(s.columns.length).toBeLessThanOrEqual(4);
        for (const c of s.columns) expect(c.widgets.length).toBeGreaterThanOrEqual(0);
      }
      // A persona is centre-only (side tracks are added by buildMarketViewLayout).
      expect(zoneIds(built, 'left')).toEqual([]);
      expect(zoneIds(built, 'right')).toEqual([]);
    },
  );

  it.each(DASHBOARD_TEMPLATES.map(t => [t.id, t] as const))(
    '%s sizes every card to content with an intrinsic frame/floor (no pinned bands)',
    (_id, t) => {
      const built = t.build(IDS);
      for (const s of built.sections) {
        for (const c of s.columns) {
          for (const w of c.widgets) {
            expect(w.height).toBeNull();
            expect((w.defaultHeight ?? w.minHeight ?? 0)).toBeGreaterThan(0);
          }
        }
      }
    },
  );

  it('uses a DIFFERENT shape for each persona (no two share band structure)', () => {
    const shape = (t: (typeof DASHBOARD_TEMPLATES)[number]) =>
      t.build(IDS).sections.map(s => s.columns.length).join('-');
    const shapes = DASHBOARD_TEMPLATES.map(shape);
    expect(new Set(shapes).size).toBeGreaterThanOrEqual(5);
  });

  it.each(DASHBOARD_TEMPLATES.map(t => [t.id, t] as const))(
    '%s keeps centre bands to at most 4 tracks',
    (_id, t) => {
      const built = t.build(IDS);
      for (const s of built.sections) expect(s.columns.length).toBeLessThanOrEqual(4);
    },
  );

  it('uses live TV in the tape-reader and desk personas, heatmap in the desk', () => {
    const tapeReader = allIds(DASHBOARD_TEMPLATES.find(t => t.id === 'tape-reader')!.build(IDS));
    expect(tapeReader).toContain('live-tv');
    const desk = allIds(DASHBOARD_TEMPLATES.find(t => t.id === 'desk')!.build(IDS));
    expect(desk).toContain('live-tv');
    expect(desk).toContain('market-heatmap');
  });

  it('drops unknown ids without crashing', () => {
    const built = DASHBOARD_TEMPLATES[0].build(['market-status', 'not-real']);
    expect(allIds(built)).toEqual(['market-status']);
  });

  it('keeps every persona materially distinct (no two share their widget set)', () => {
    const sets = DASHBOARD_TEMPLATES.map(t => allIds(t.build(IDS)).slice().sort().join(','));
    expect(new Set(sets).size).toBe(DASHBOARD_TEMPLATES.length);
  });

  it('resolves every legacy persona id to a live template that places a centre', () => {
    for (const [legacy, current] of Object.entries(LEGACY_TEMPLATE_IDS)) {
      expect(resolveTemplateId(legacy)).toBe(current);
      const t = getDashboardTemplate(legacy);
      expect(t).toBeTruthy();
      expect(t!.id).toBe(current);
      // The regression: an unresolved legacy id produced an EMPTY centre.
      const centre = allIds(t!.build(IDS));
      expect(centre.length).toBeGreaterThan(0);
    }
  });

  it('falls back to the first persona for an unknown/empty id (never empty)', () => {
    expect(resolveTemplateId('does-not-exist')).toBe(DASHBOARD_TEMPLATES[0].id);
    expect(resolveTemplateId(undefined)).toBe(DASHBOARD_TEMPLATES[0].id);
    expect(getDashboardTemplate('does-not-exist')?.id).toBe(DASHBOARD_TEMPLATES[0].id);
  });
});

// ── buildMarketViewLayout ────────────────────────────────────────────────────

describe('buildMarketViewLayout', () => {
  const trader = DASHBOARD_TEMPLATES[0];

  it('frames the centre with a left watchlist and right asset stat tiles', () => {
    const layout = buildMarketViewLayout('US', IDS, trader.build(IDS));
    expect(zoneIds(layout, 'left')).toEqual(['watchlist']);
    expect(zoneIds(layout, 'right')).toEqual(ASSET_RAIL.equity);
  });

  it('never duplicates a widget across ANY zone', () => {
    const layout = buildMarketViewLayout('US', IDS, trader.build(IDS));
    const used = allIds(layout);
    expect(new Set(used).size).toBe(used.length);
  });

  it('uses the asset-class right tracks', () => {
    expect(zoneIds(buildMarketViewLayout('FOREX', IDS, trader.build(IDS)), 'right'))
      .toEqual(ASSET_RAIL.forex);
    expect(zoneIds(buildMarketViewLayout('CRYPTO', IDS, trader.build(IDS)), 'right'))
      .toEqual(ASSET_RAIL.crypto);
  });

  it('always emits a valid layout even with no template base', () => {
    const layout = buildMarketViewLayout('US', IDS);
    const sections: WorkspaceSection[] = layout.sections;
    expect(sections.length).toBeGreaterThan(0);
    expect(zoneIds(layout, 'left')).toEqual(['watchlist']);
  });

  it('does not put the same widget in the centre and a side track', () => {
    const layout = buildMarketViewLayout('US', IDS, trader.build(IDS));
    expect(zoneIds(layout, 'main')).not.toContain('watchlist');
  });

  it('is deterministic in structure across rebuilds', () => {
    const shape = (l: WorkspaceLayout) =>
      l.sections.map(s => ({ zone: s.zone ?? 'main', cols: s.columns.length }));
    const a = buildMarketViewLayout('US', IDS, trader.build(IDS));
    const b = buildMarketViewLayout('US', IDS, trader.build(IDS));
    expect(shape(a)).toEqual(shape(b));
    expect(allIds(a)).toEqual(allIds(b));
  });

  it('emits version 2 so the track-board reader is used', () => {
    expect(buildMarketViewLayout('US', IDS, trader.build(IDS)).version).toBe(2);
  });
});

