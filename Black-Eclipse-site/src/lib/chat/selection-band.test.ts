import { describe, expect, it } from 'vitest';
import { selectionBands, selectionGapFillers, type RectLike } from './selection-band';

const line = (left: number, top: number, right: number, bottom: number): RectLike => ({
  left,
  top,
  right,
  bottom,
});

describe('selectionBands', () => {
  it('merges several inline rects on the same rendered line', () => {
    const bands = selectionBands([
      line(10, 100, 40, 120),
      line(42, 100, 90, 120),
      line(10, 100, 60, 120),
    ]);
    expect(bands).toEqual([{ left: 10, top: 100, right: 90, bottom: 120 }]);
  });

  it('keeps separate lines as separate bands', () => {
    const bands = selectionBands([
      line(10, 100, 90, 120),
      line(10, 130, 90, 150),
    ]);
    expect(bands).toHaveLength(2);
    expect(bands[1].top).toBe(130);
  });

  it('drops zero-area rects from collapsed ranges', () => {
    expect(selectionBands([line(10, 100, 10, 120), line(10, 100, 90, 100)])).toEqual([]);
  });

  it('copies values from DOMRect-like prototype getters', () => {
    // `DOMRect` exposes left/top/right/bottom as prototype getters, so a plain
    // object spread would drop them — the regression this guards.
    class ProtoRect {
      constructor(
        private l: number,
        private t: number,
        private r: number,
        private b: number,
      ) {}
      get left() { return this.l; }
      get top() { return this.t; }
      get right() { return this.r; }
      get bottom() { return this.b; }
    }
    expect(selectionBands([new ProtoRect(10, 100, 90, 120)])).toEqual([
      { left: 10, top: 100, right: 90, bottom: 120 },
    ]);
  });
});

describe('selectionGapFillers', () => {
  it('fills the gap between wrapped lines', () => {
    const fillers = selectionGapFillers([
      line(10, 100, 90, 120),
      line(10, 130, 90, 150),
    ]);
    expect(fillers).toEqual([{ left: 10, top: 120, width: 80, height: 10 }]);
  });

  it('fills the block gap between paragraphs', () => {
    const fillers = selectionGapFillers([
      line(10, 100, 200, 120),
      line(10, 132, 200, 152),
    ]);
    expect(fillers).toEqual([{ left: 10, top: 120, width: 190, height: 12 }]);
  });

  it('fills using the horizontal overlap of the two lines', () => {
    const fillers = selectionGapFillers([
      line(10, 100, 120, 120),
      line(40, 128, 200, 148),
    ]);
    expect(fillers).toEqual([{ left: 40, top: 120, width: 80, height: 8 }]);
  });

  it('does not bridge lines that do not overlap horizontally', () => {
    expect(
      selectionGapFillers([
        line(10, 100, 40, 120),
        line(200, 130, 260, 150),
      ]),
    ).toEqual([]);
  });

  it('ignores a gap taller than a line break', () => {
    expect(
      selectionGapFillers([
        line(10, 100, 90, 120),
        line(10, 400, 90, 420),
      ]),
    ).toEqual([]);
  });

  it('does not fill adjacent lines that already touch', () => {
    expect(selectionGapFillers([line(10, 100, 90, 120), line(10, 120, 90, 140)])).toEqual([]);
  });
});
