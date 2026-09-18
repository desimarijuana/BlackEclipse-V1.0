import { describe, expect, it } from 'vitest';
import { columnHeights, defaultHeightOf, rebalanceColumns, rebalanceLayout } from './pack';
import type { WorkspaceColumn, WorkspaceLayout, WidgetPlacement } from './types';

const wid = (id: string, minHeight?: number, height: number | null = null): WidgetPlacement => ({
  id,
  widgetId: id,
  height,
  minHeight,
});

const col = (id: string, widgets: WidgetPlacement[]): WorkspaceColumn => ({ id, weight: 1, widgets });

const ids = (c: WorkspaceColumn) => c.widgets.map(w => w.id);

describe('defaultHeightOf', () => {
  it('prefers pinned height, then min-height, then the nominal unit', () => {
    expect(defaultHeightOf(wid('a', 200, 500))).toBe(500);
    expect(defaultHeightOf(wid('b', 200))).toBe(200);
    expect(defaultHeightOf(wid('c'))).toBe(280);
  });
});

describe('rebalanceColumns', () => {
  it('is a no-op for a single column', () => {
    const c = col('c1', [wid('a'), wid('b')]);
    rebalanceColumns([c]);
    expect(ids(c)).toEqual(['a', 'b']);
  });

  it('fills the shortest track so no track is stranded short', () => {
    // a=400, b=300, c=300, d=300 across 2 tracks:
    // track0 gets a(400); track1 gets b(300); then c→track1(600); d→track0(700)
    const c0 = col('c0', [wid('a', 400), wid('d', 300)]);
    const c1 = col('c1', [wid('b', 300), wid('c', 300)]);
    const columns = [c0, c1];
    rebalanceColumns(columns);
    const h = columnHeights(columns);
    // Both tracks end within one card-height of each other and nothing is lost.
    expect([...ids(c0), ...ids(c1)].sort()).toEqual(['a', 'b', 'c', 'd']);
    expect(Math.abs(h[0] - h[1])).toBeLessThanOrEqual(400);
  });

  it('balances deterministically for the same input', () => {
    const build = () => {
      const columns = [col('c0', []), col('c1', [])];
      [200, 300, 250, 400, 150, 350].forEach((h, i) => columns[i % 2].widgets.push(wid(`w${i}`, h)));
      rebalanceColumns(columns);
      return columns.map(ids);
    };
    expect(build()).toEqual(build());
  });

  it('preserves column identity, count and weights', () => {
    const c0 = col('c0', [wid('a')]);
    const c1 = col('c1', [wid('b')]);
    const columns = [c0, c1];
    rebalanceColumns(columns);
    expect(columns.map(c => c.id)).toEqual(['c0', 'c1']);
    expect(columns.map(c => c.weight)).toEqual([1, 1]);
  });

  it('loses no cards', () => {
    const columns = [col('c0', []), col('c1', []), col('c2', [])];
    for (let i = 0; i < 11; i++) columns[i % 3].widgets.push(wid(`w${i}`, 100 + i * 10));
    const before = columns.flatMap(ids).sort();
    rebalanceColumns(columns);
    expect(columns.flatMap(ids).sort()).toEqual(before);
  });
});

describe('rebalanceLayout', () => {
  it('rebalances every multi-column section without touching side tracks', () => {
    const layout: WorkspaceLayout = {
      version: 2,
      sections: [
        { id: 's1', zone: 'left', columns: [col('l1', [wid('watch', 380)])] },
        { id: 's2', zone: 'main', columns: [col('m1', [wid('a', 400)]), col('m2', [wid('b', 300)])] },
      ],
    };
    rebalanceLayout(layout);
    expect(ids(layout.sections[0].columns[0])).toEqual(['watch']);
    expect(layout.sections[1].columns.flatMap(c => c.widgets).map(w => w.id).sort()).toEqual(['a', 'b']);
  });
});
