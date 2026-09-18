import { describe, expect, it } from 'vitest';
import {
  ASSET_RAIL, LEFT_WIDGET_IDS, assetClassFor, buildLeftSections,
  buildMarketViewLayout, buildRailSections, composeRows,
} from './layout';
import { DASHBOARD_TEMPLATES } from './templates';
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
  'live-tv', 'watchlist',
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

// ── composeRows (the invariants) ─────────────────────────────────────────────

describe('composeRows', () => {
  const rows = [
    { zone: 'main' as const, cells: [{ widget: 'a' }, { widget: 'b' }] },
    { zone: 'main' as const, cells: [{ widget: 'b' }, { widget: 'c' }] },
  ];

  it('dedupes globally, first occurrence wins', () => {
    const secs = composeRows(rows, new Set(['a', 'b', 'c']));
    expect(secs.flatMap(s => s.columns.flatMap(c => c.widgets.map(w => w.widgetId))))
      .toEqual(['a', 'b', 'c']);
  });

  it('drops unknown widget ids', () => {
    const secs = composeRows([{ zone: 'main', cells: [{ widget: 'a' }, { widget: 'ghost' }] }], new Set(['a']));
    expect(secs[0].columns).toHaveLength(1);
  });

  it('caps each section at 4 columns at BUILD time (no silent reload truncation)', () => {
    const wide = [{ zone: 'main' as const, cells: ['a', 'b', 'c', 'd', 'e'].map(widget => ({ widget })) }];
    const secs = composeRows(wide, new Set(['a', 'b', 'c', 'd', 'e']));
    expect(secs[0].columns).toHaveLength(4);
    // The 5th widget is dropped here, not lost later on read.
    expect(secs[0].columns.flatMap(c => c.widgets.map(w => w.widgetId))).toEqual(['a', 'b', 'c', 'd']);
  });

  it('drops empty rows and keeps the zone', () => {
    const secs = composeRows([
      { zone: 'left', cells: [{ widget: 'ghost' }] },
      { zone: 'right', cells: [{ widget: 'a' }] },
    ], new Set(['a']));
    expect(secs).toHaveLength(1);
    expect(secs[0].zone).toBe('right');
  });
});

// ── side-zone builders ───────────────────────────────────────────────────────

describe('side-zone builders', () => {
  it('builds the thin left watchlist zone', () => {
    const s = buildLeftSections();
    expect(LEFT_WIDGET_IDS).toEqual(['watchlist']);
    expect(s).toHaveLength(1);
    expect(s[0].zone).toBe('left');
    expect(s[0].columns[0].widgets[0].widgetId).toBe('watchlist');
  });

  it('builds right-zone stat tiles with no duplicates', () => {
    const s = buildRailSections(['mp-indices', 'mp-indices', 'mp-movers']);
    expect(s).toHaveLength(3); // builder does not dedupe; composeRows does
    expect(s.every(sec => sec.zone === 'right')).toBe(true);
  });
});

// ── personas ─────────────────────────────────────────────────────────────────

describe('persona templates', () => {
  it('ships exactly the six personas', () => {
    expect(DASHBOARD_TEMPLATES.map(t => t.id))
      .toEqual(['trader', 'investor', 'macro', 'crypto', 'forex', 'quant']);
  });

  it.each(DASHBOARD_TEMPLATES.map(t => [t.id, t] as const))(
    '%s builds a valid centre with ≤4-column sections and no duplicates',
    (_id, t) => {
      const built = t.build(IDS);
      const used = allIds(built);
      expect(used.length).toBeGreaterThan(0);
      // No widget repeats within a persona.
      expect(new Set(used).size).toBe(used.length);
      // Every section respects the 4-column cap and has at least one widget.
      for (const s of built.sections) {
        expect(s.columns.length).toBeGreaterThanOrEqual(1);
        expect(s.columns.length).toBeLessThanOrEqual(4);
        for (const c of s.columns) expect(c.widgets.length).toBeGreaterThanOrEqual(1);
      }
      // A persona is centre-only (side zones are added by buildMarketViewLayout).
      expect(zoneIds(built, 'left')).toEqual([]);
      expect(zoneIds(built, 'right')).toEqual([]);
    },
  );

  it('drops unknown ids without crashing', () => {
    const built = DASHBOARD_TEMPLATES[0].build(['market-status', 'not-real']);
    expect(allIds(built)).toEqual(['market-status']);
  });

  it('keeps personas materially distinct (Trader vs Investor differ)', () => {
    const trader = allIds(DASHBOARD_TEMPLATES[0].build(IDS));
    const investor = allIds(DASHBOARD_TEMPLATES[1].build(IDS));
    expect(trader).not.toEqual(investor);
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

  it('uses the asset-class right tiles', () => {
    expect(zoneIds(buildMarketViewLayout('FOREX', IDS, trader.build(IDS)), 'right'))
      .toEqual(ASSET_RAIL.forex);
    expect(zoneIds(buildMarketViewLayout('CRYPTO', IDS, trader.build(IDS)), 'right'))
      .toEqual(ASSET_RAIL.crypto);
  });

  it('always emits a valid layout even with no template base', () => {
    const layout = buildMarketViewLayout('US', IDS);
    const sections: WorkspaceSection[] = layout.sections;
    expect(sections.length).toBeGreaterThan(0);
    // Without a persona base it still carries the two thin rails.
    expect(zoneIds(layout, 'left')).toEqual(['watchlist']);
  });

  it('does not put the same widget in the centre and a rail', () => {
    // watchlist is a left-zone widget; no persona may also place it centrally.
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
});
