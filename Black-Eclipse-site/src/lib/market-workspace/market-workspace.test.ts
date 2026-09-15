// ── Market Workspace kernel tests ────────────────────────────────────────────
// Pure layout ops + validation + AI analysis + instrument formatting. These run
// without a DOM (immer producers are used directly for the mutating ops).

import { describe, it, expect } from 'vitest';
import { produce } from 'immer';
import {
  addPanel, applyGridPreset, autoArrange, cloneLayout, duplicatePanel,
  findFreeSlot, firstFreeRow, normalizeLayout, placePanel, recomputeRows,
  removePanel, setPanelRect, setPanelSymbol, togglePanelAi,
} from './ops';
import {
  GRID_COLUMNS, MAX_ROWS, clampRect, gridPreset, newPanelId, presetRect,
  rectsOverlap, type MarketWorkspaceLayout,
} from './types';
import { WORKSPACE_PRESETS, defaultWorkspaceLayout, getWorkspacePreset } from './presets';
import { analyzeForAi } from './ai-analysis';
import { formatPercent, instrumentMeta, marketSession, formatInstrumentPrice } from './instruments';
import type { PriceBar } from '@/lib/chart/types';

function empty(): MarketWorkspaceLayout {
  return { version: 1, layoutId: 'custom', rows: 4, panels: [] };
}

describe('grid presets', () => {
  it('tiles a 3-col preset on the 12-unit grid', () => {
    expect(presetRect(0, 3)).toMatchObject({ col: 0, colSpan: 4 });
    expect(presetRect(1, 3)).toMatchObject({ col: 4, colSpan: 4 });
    expect(presetRect(2, 3)).toMatchObject({ col: 8, colSpan: 4 });
    expect(presetRect(3, 3)).toMatchObject({ col: 0, row: 1 });
  });

  it('clamps rects into the grid', () => {
    const r = clampRect({ col: 11, row: 0, colSpan: 4, rowSpan: 2 });
    expect(r.col + r.colSpan).toBeLessThanOrEqual(GRID_COLUMNS);
    expect(r.rowSpan).toBeGreaterThanOrEqual(1);
  });

  it('detects overlap', () => {
    expect(rectsOverlap({ col: 0, row: 0, colSpan: 6, rowSpan: 1 }, { col: 4, row: 0, colSpan: 6, rowSpan: 1 })).toBe(true);
    expect(rectsOverlap({ col: 0, row: 0, colSpan: 4, rowSpan: 1 }, { col: 4, row: 0, colSpan: 4, rowSpan: 1 })).toBe(false);
  });

  it('falls back to a sane preset for unknown ids', () => {
    expect(gridPreset('nope')).toEqual({ columns: 3, rows: 2 });
  });
});

describe('layout ops', () => {
  it('adds panels without overlap and grows rows', () => {
    const layout = produce(empty(), (d) => {
      addPanel(d, 'chart');
      addPanel(d, 'watchlist');
      addPanel(d, 'news');
    });
    expect(layout.panels).toHaveLength(3);
    for (let i = 0; i < layout.panels.length; i++) {
      for (let j = i + 1; j < layout.panels.length; j++) {
        expect(rectsOverlap(layout.panels[i].rect, layout.panels[j].rect)).toBe(false);
      }
    }
  });

  it('compacts a panel below occupied cells', () => {
    const layout = produce(empty(), (d) => {
      addPanel(d, 'chart');
      addPanel(d, 'chart');
    });
    const target = firstFreeRow(layout.panels, { col: 0, row: 0, colSpan: 12, rowSpan: 1 });
    expect(target).toBeGreaterThanOrEqual(1);
  });

  it('re-tiles on applyGridPreset', () => {
    const layout = produce(empty(), (d) => {
      addPanel(d, 'chart'); addPanel(d, 'chart'); addPanel(d, 'chart'); addPanel(d, 'chart');
      applyGridPreset(d, '2x2');
    });
    expect(layout.layoutId).toBe('2x2');
    expect(layout.panels[0].rect.colSpan).toBe(6);
    expect(layout.panels[3].rect).toMatchObject({ col: 6, row: 1 });
  });

  it('auto-arranges into a sensible column count', () => {
    const layout = produce(empty(), (d) => {
      for (let i = 0; i < 9; i++) addPanel(d, 'chart');
      autoArrange(d);
    });
    expect(layout.panels[0].rect.colSpan).toBe(4); // 3 per row
  });

  it('duplicates a panel with a new id', () => {
    const layout = produce(empty(), (d) => {
      const p = addPanel(d, 'chart');
      duplicatePanel(d, p.id);
    });
    expect(layout.panels).toHaveLength(2);
    expect(layout.panels[0].id).not.toBe(layout.panels[1].id);
  });

  it('removes a panel', () => {
    const layout = produce(empty(), (d) => {
      const p = addPanel(d, 'chart');
      addPanel(d, 'news');
      removePanel(d, p.id);
    });
    expect(layout.panels).toHaveLength(1);
    expect(layout.panels[0].type).toBe('news');
  });

  it('updates symbol on both the panel and its chart', () => {
    const layout = produce(empty(), (d) => {
      const p = addPanel(d, 'chart');
      setPanelSymbol(d, p.id, 'msft', 'US');
    });
    expect(layout.panels[0].symbol).toBe('MSFT');
    expect(layout.panels[0].chart?.symbol).toBe('MSFT');
  });

  it('toggles the AI drawer', () => {
    const layout = produce(empty(), (d) => {
      const p = addPanel(d, 'chart');
      togglePanelAi(d, p.id);
    });
    expect(layout.panels[0].aiOpen).toBe(true);
  });

  it('gives a new custom-workspace panel a usable half-width, two-row size', () => {
    const layout = produce(empty(), (d) => { addPanel(d, 'chart'); });
    expect(layout.panels[0].rect.colSpan).toBe(GRID_COLUMNS / 2);
    expect(layout.panels[0].rect.rowSpan).toBe(2);
  });

  it('never adds a new custom panel as a 1-unit sliver', () => {
    const layout = produce(empty(), (d) => {
      for (let i = 0; i < 6; i++) addPanel(d, 'chart');
    });
    for (const p of layout.panels) {
      expect(p.rect.colSpan).toBeGreaterThanOrEqual(GRID_COLUMNS / 2);
      expect(p.rect.colSpan).toBeLessThanOrEqual(GRID_COLUMNS);
    }
  });

  it('fills the first free slot instead of always starting at column 0', () => {
    const layout = produce(empty(), (d) => {
      addPanel(d, 'chart');
      addPanel(d, 'chart');
    });
    expect(layout.panels[0].rect).toMatchObject({ col: 0, row: 0 });
    expect(layout.panels[1].rect).toMatchObject({ col: 6, row: 0 });
  });

  it('sizes new preset panels to their logical column count', () => {
    const layout = produce({ version: 1, layoutId: '3x2', rows: 2, panels: [] } as MarketWorkspaceLayout, (d) => {
      addPanel(d, 'chart');
    });
    expect(layout.panels[0].rect.colSpan).toBe(4);
    expect(layout.panels[0].rect.rowSpan).toBe(1);
  });
});

describe('row fitting (no phantom scroll space)', () => {
  it('shrinks rows to content after removing a panel', () => {
    const layout = produce(empty(), (d) => {
      const a = addPanel(d, 'chart');
      addPanel(d, 'chart');
      addPanel(d, 'chart');
      // Two half-width panels per row → 3 panels span rows 0 and 1.
      removePanel(d, a.id);
    });
    const maxRow = layout.panels.reduce((m, p) => Math.max(m, p.rect.row + p.rect.rowSpan), 0);
    expect(layout.rows).toBe(maxRow);
  });

  it('never leaves rows below the last panel', () => {
    const layout = produce(empty(), (d) => {
      for (let i = 0; i < 3; i++) addPanel(d, 'chart');
    });
    const maxRow = layout.panels.reduce((m, p) => Math.max(m, p.rect.row + p.rect.rowSpan), 0);
    expect(layout.rows).toBe(maxRow);
  });

  it('recomputeRows clamps to at least 1 and at most MAX_ROWS', () => {
    const layout = produce(empty(), (d) => {
      addPanel(d, 'chart');
      d.panels[0].rect.row = 999;
      recomputeRows(d);
    });
    expect(layout.rows).toBeGreaterThanOrEqual(1);
    expect(layout.rows).toBeLessThanOrEqual(MAX_ROWS);
  });
});

describe('placePanel (interactive drag)', () => {
  it('keeps the moved panel exactly where it was dropped', () => {
    const layout = produce(empty(), (d) => {
      const p = addPanel(d, 'chart');
      placePanel(d, p.id, 6, 3);
    });
    expect(layout.panels[0].rect.col).toBe(6);
    expect(layout.panels[0].rect.row).toBe(3);
  });

  it('pushes overlapped panels down instead of snapping the moved one back', () => {
    const layout = produce(empty(), (d) => {
      const a = addPanel(d, 'chart'); // row 0
      addPanel(d, 'chart');           // row 0 right / row 2
      // Drop A onto where the other panels already sit.
      placePanel(d, a.id, 6, 0);
    });
    const [a, b] = layout.panels;
    expect(a.rect).toMatchObject({ col: 6, row: 0 });
    expect(rectsOverlap(a.rect, b.rect)).toBe(false);
  });

  it('grows the grid when dropped near the bottom', () => {
    const layout = produce(empty(), (d) => {
      const p = addPanel(d, 'chart');
      placePanel(d, p.id, 0, 5);
    });
    // The panel stays at row 5 and the grid grows to cover its full span.
    expect(layout.panels[0].rect.row).toBe(5);
    expect(layout.rows).toBe(5 + layout.panels[0].rect.rowSpan);
  });
});

describe('setPanelRect (interactive resize)', () => {
  it('resizes the panel and grows rows to fit', () => {
    const layout = produce(empty(), (d) => {
      const p = addPanel(d, 'chart');
      setPanelRect(d, p.id, { col: 0, row: 0, colSpan: 12, rowSpan: 3 });
    });
    expect(layout.panels[0].rect).toMatchObject({ colSpan: 12, rowSpan: 3 });
    expect(layout.rows).toBe(3);
  });

  it('pushes down a panel that the resize would overlap', () => {
    const layout = produce(empty(), (d) => {
      const a = addPanel(d, 'chart');
      addPanel(d, 'chart'); // second panel sits right of A
      setPanelRect(d, a.id, { col: 0, row: 0, colSpan: 12, rowSpan: 1 });
    });
    expect(rectsOverlap(layout.panels[0].rect, layout.panels[1].rect)).toBe(false);
  });
});

describe('findFreeSlot', () => {
  it('packs left-to-right on the first row', () => {
    const placed = [{ id: 'a', type: 'chart' as const, rect: { col: 0, row: 0, colSpan: 6, rowSpan: 1 } }];
    expect(findFreeSlot(placed, 6, 1)).toEqual({ col: 6, row: 0 });
  });

  it('drops to the next row when the current row is full', () => {
    const placed = [
      { id: 'a', type: 'chart' as const, rect: { col: 0, row: 0, colSpan: 6, rowSpan: 1 } },
      { id: 'b', type: 'chart' as const, rect: { col: 6, row: 0, colSpan: 6, rowSpan: 1 } },
    ];
    expect(findFreeSlot(placed, 6, 1)).toEqual({ col: 0, row: 1 });
  });

  it('returns a fresh row when nothing fits in the existing rows', () => {
    const placed = [{ id: 'a', type: 'chart' as const, rect: { col: 0, row: 0, colSpan: 12, rowSpan: 2 } }];
    expect(findFreeSlot(placed, 12, 1)).toEqual({ col: 0, row: 2 });
  });
});

describe('normalizeLayout', () => {
  it('rejects garbage', () => {
    expect(normalizeLayout(null)).toBeNull();
    expect(normalizeLayout({})).toBeNull();
    expect(normalizeLayout({ panels: 'nope' })).toBeNull();
    expect(normalizeLayout({ panels: [] })).toBeNull();
  });

  it('drops malformed panels and de-duplicates ids', () => {
    const raw = {
      version: 1,
      layoutId: 'custom',
      rows: 4,
      panels: [
        { id: 'a', type: 'chart', rect: { col: 0, row: 0, colSpan: 4, rowSpan: 1 } },
        { id: 'a', type: 'chart', rect: { col: 0, row: 0, colSpan: 4, rowSpan: 1 } },
        { id: 'b', type: 'chart' }, // no rect → dropped
      ],
    };
    const layout = normalizeLayout(raw);
    expect(layout?.panels).toHaveLength(1);
  });

  it('re-flows overlapping stored panels', () => {
    const raw = {
      version: 1,
      layoutId: 'custom',
      rows: 4,
      panels: [
        { id: 'a', type: 'chart', rect: { col: 0, row: 0, colSpan: 12, rowSpan: 1 } },
        { id: 'b', type: 'chart', rect: { col: 0, row: 0, colSpan: 12, rowSpan: 1 } },
      ],
    };
    const layout = normalizeLayout(raw)!;
    expect(rectsOverlap(layout.panels[0].rect, layout.panels[1].rect)).toBe(false);
  });
});

describe('presets', () => {
  it('every preset builds a valid, non-overlapping layout', () => {
    for (const preset of WORKSPACE_PRESETS) {
      const layout = preset.build();
      expect(layout.panels.length).toBeGreaterThan(0);
      for (let i = 0; i < layout.panels.length; i++) {
        for (let j = i + 1; j < layout.panels.length; j++) {
          expect(rectsOverlap(layout.panels[i].rect, layout.panels[j].rect)).toBe(false);
        }
      }
    }
  });

  it('defaults to the trading preset', () => {
    expect(getWorkspacePreset('trading')).toBeDefined();
    expect(defaultWorkspaceLayout().panels.length).toBeGreaterThan(0);
  });

  it('clones deeply (mutating a clone never touches the source)', () => {
    const a = defaultWorkspaceLayout();
    const b = cloneLayout(a);
    b.panels[0].rect.col = 999;
    expect(a.panels[0].rect.col).not.toBe(999);
  });
});

describe('instrument metadata', () => {
  it('formats US, India, Pakistan and crypto appropriately', () => {
    expect(instrumentMeta('AAPL', 'US').currency).toBe('$');
    expect(instrumentMeta('RELIANCE', 'IN').currency).toBe('₹');
    expect(instrumentMeta('OGDC', 'PK').currency).toBe('PKR');
    expect(instrumentMeta('BTC', 'CRYPTO').currency).toBe('$');
  });

  it('resolves exchange + timezone from the market', () => {
    expect(instrumentMeta('AAPL', 'US').exchange).toContain('NYSE');
    expect(instrumentMeta('OGDC', 'PK').timezone).toBe('Asia/Karachi');
    expect(instrumentMeta('BTC', 'CRYPTO').isCrypto).toBe(true);
  });

  it('formats price with the market currency', () => {
    expect(formatInstrumentPrice(instrumentMeta('OGDC', 'PK'), 412.5)).toBe('PKR 412.50');
    expect(formatInstrumentPrice(instrumentMeta('AAPL', 'US'), 245.32)).toBe('$245.32');
    expect(formatInstrumentPrice(instrumentMeta('RELIANCE', 'IN'), 1842.5)).toBe('₹1,842.50');
  });

  it('formats percentages with a sign', () => {
    expect(formatPercent(1.34)).toBe('+1.34%');
    expect(formatPercent(-0.42)).toBe('-0.42%');
  });

  it('crypto is always open', () => {
    expect(marketSession(instrumentMeta('BTC', 'CRYPTO'))).toBe('open');
  });
});

describe('AI analysis', () => {
  function bars(closes: number[]): PriceBar[] {
    return closes.map((c, i) => ({
      date: `2025-01-${String((i % 28) + 1).padStart(2, '0')}`,
      time: i * 86400000,
      open: c, high: c * 1.01, low: c * 0.99, close: c, volume: 1_000_000 + i * 1000,
    }));
  }

  it('returns null without enough history', () => {
    expect(analyzeForAi('AAPL', bars([1, 2, 3]))).toBeNull();
  });

  it('reads a rising series as bullish', () => {
    const series = Array.from({ length: 80 }, (_, i) => 100 + i);
    const view = analyzeForAi('AAPL', bars(series))!;
    expect(view.trend).toBe('Bullish');
    expect(view.summary.length).toBeGreaterThan(20);
    expect(view.levels.length).toBeGreaterThan(0);
  });

  it('reads a falling series as bearish', () => {
    const series = Array.from({ length: 80 }, (_, i) => 200 - i);
    const view = analyzeForAi('AAPL', bars(series))!;
    expect(view.trend).toBe('Bearish');
  });

  it('produces a risk level from measured volatility', () => {
    const series = Array.from({ length: 80 }, (_, i) => 100 + (i % 2 === 0 ? 5 : -5));
    const view = analyzeForAi('AAPL', bars(series))!;
    expect(['Low', 'Medium', 'High']).toContain(view.risk);
  });
});

describe('newPanelId', () => {
  it('is unique', () => {
    const ids = new Set(Array.from({ length: 200 }, () => newPanelId('chart')));
    expect(ids.size).toBe(200);
  });
  it('respects the row ceiling constant', () => {
    expect(MAX_ROWS).toBeGreaterThanOrEqual(8);
  });
});
