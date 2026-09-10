'use client';

// ── Market Structure Registry (Phase 5) ──────────────────────────────────────
// Maps BlackEclipse-native structure objects to ECharts overlay configs
// (markLine / markArea / markPoint). Each structure type is a first-class,
// queryable object rendered as a distinct visual on the main pane.

import type { MarketStructureResult } from '@/lib/chart/types';

/** Which structure layers are enabled. */
export interface StructureLayers {
  swings: boolean;
  bos: boolean;
  choch: boolean;
  orderBlocks: boolean;
  fvgs: boolean;
  liquidity: boolean;
  sessions: boolean;
  openingRanges: boolean;
}

export const DEFAULT_STRUCTURE_LAYERS: StructureLayers = {
  swings: false,
  bos: false,
  choch: false,
  orderBlocks: false,
  fvgs: false,
  liquidity: false,
  sessions: false,
  openingRanges: false,
};

const UP = '#7aff78';
const DOWN = '#ff3e3e';
const BLUE = '#60a5fa';
const AMBER = '#fbbf24';
const PINK = '#f472b6';

/** Build all mark overlays for the enabled structure layers. */
export function structureToMarks(result: MarketStructureResult, layers: StructureLayers): {
  markLine: unknown[];
  markArea: unknown[];
  markPoint: unknown[];
} {
  const markLine: unknown[] = [];
  const markArea: unknown[] = [];
  const markPoint: unknown[] = [];

  if (layers.swings) {
    for (const s of result.swings) {
      markPoint.push({
        coord: [s.index, s.price],
        symbol: s.type === 'high' ? 'triangle' : 'triangle',
        symbolRotate: s.type === 'high' ? 0 : 180,
        symbolSize: 6,
        itemStyle: { color: s.type === 'high' ? DOWN : UP },
      });
    }
  }

  if (layers.bos) {
    for (const b of result.bos) {
      markLine.push({
        xAxis: b.index,
        lineStyle: { color: b.direction === 'bullish' ? UP : DOWN, width: 1.5, type: 'dashed' },
        label: { show: true, position: 'end', color: b.direction === 'bullish' ? UP : DOWN, fontSize: 8, fontFamily: 'monospace', formatter: 'BOS' },
      });
    }
  }

  if (layers.choch) {
    for (const c of result.choch) {
      markLine.push({
        xAxis: c.index,
        lineStyle: { color: AMBER, width: 2, type: 'solid' },
        label: { show: true, position: 'end', color: AMBER, fontSize: 8, fontFamily: 'monospace', formatter: 'CHOCH' },
      });
    }
  }

  if (layers.orderBlocks) {
    for (const ob of result.orderBlocks) {
      markArea.push([
        {
          xAxis: ob.startIndex, yAxis: ob.high,
          itemStyle: { color: ob.direction === 'bullish' ? UP + '14' : DOWN + '14', borderColor: ob.direction === 'bullish' ? UP : DOWN, borderWidth: 1 },
          label: { show: true, position: 'insideTop', color: ob.direction === 'bullish' ? UP : DOWN, fontSize: 8, fontFamily: 'monospace', formatter: 'OB' },
        },
        { xAxis: ob.endIndex, yAxis: ob.low },
      ]);
    }
  }

  if (layers.fvgs) {
    for (const f of result.fvgs) {
      markArea.push([
        {
          xAxis: f.startIndex, yAxis: f.top,
          itemStyle: { color: f.direction === 'bullish' ? BLUE + '18' : PINK + '18', borderColor: f.direction === 'bullish' ? BLUE : PINK, borderWidth: 1 },
          label: { show: true, position: 'insideTop', color: f.direction === 'bullish' ? BLUE : PINK, fontSize: 8, fontFamily: 'monospace', formatter: 'FVG' },
        },
        { xAxis: f.endIndex, yAxis: f.bottom },
      ]);
    }
  }

  if (layers.liquidity) {
    for (const l of result.liquidity) {
      markLine.push({
        yAxis: l.price,
        lineStyle: { color: PINK, width: 1, type: 'dotted' },
        label: { show: true, position: 'end', color: PINK, fontSize: 8, fontFamily: 'monospace', formatter: l.type.includes('high') ? 'EQ-H' : 'EQ-L' },
      });
    }
  }

  if (layers.sessions) {
    for (const s of result.sessions) {
      markLine.push({
        yAxis: s.high,
        lineStyle: { color: 'rgba(160,160,160,0.5)', width: 1, type: 'dashed' },
        label: { show: true, position: 'end', color: 'rgba(160,160,160,0.7)', fontSize: 8, fontFamily: 'monospace', formatter: 'S-H' },
      });
      markLine.push({
        yAxis: s.low,
        lineStyle: { color: 'rgba(160,160,160,0.5)', width: 1, type: 'dashed' },
        label: { show: true, position: 'end', color: 'rgba(160,160,160,0.7)', fontSize: 8, fontFamily: 'monospace', formatter: 'S-L' },
      });
    }
  }

  if (layers.openingRanges) {
    for (const r of result.openingRanges) {
      markArea.push([
        {
          xAxis: r.rangeIndex, yAxis: r.high,
          itemStyle: { color: 'rgba(251,191,36,0.10)', borderColor: AMBER, borderWidth: 1 },
          label: { show: true, position: 'insideTop', color: AMBER, fontSize: 8, fontFamily: 'monospace', formatter: 'OR' },
        },
        { xAxis: r.rangeIndex + 3, yAxis: r.low },
      ]);
    }
  }

  return { markLine, markArea, markPoint };
}
