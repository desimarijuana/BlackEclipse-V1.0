'use client';

// ── Trade Replay — candlestick chart of the market around a trade ────────────
// Shows the price series with the trade's entry, stop, target and exit marked
// as horizontal lines. Uses ECharts candlestick.

import React, { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { useEChart } from '@/components/screens/portfolio/use-echart';
import { fmtR } from './charts/echarts-container';
import { useChartPalette } from '@/lib/chart-palette-store';

export interface ReplayBar {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume?: number | null;
}

export interface ReplayTrade {
  symbol: string;
  direction: 'LONG' | 'SHORT';
  entry: number;
  exit: number;
  stopLoss: number | null;
  takeProfit: number | null;
  entryTime: string;
  exitTime: string;
  rMultiple: number;
  mfe: number | null;
  mae: number | null;
}

interface TradeReplayChartProps {
  series: ReplayBar[];
  trade: ReplayTrade;
  height?: number;
}

export function TradeReplayChart({ series, trade, height = 320 }: TradeReplayChartProps) {
  const palette = useChartPalette();
  const { up: UP, down: DOWN } = palette.candles;
  const entryColor = palette.lines.primary;
  const option = useMemo<EChartsOption | null>(() => {
    if (series.length < 2) return null;
    const dates = series.map((b) => b.date);
    const candles = series.map((b) => [b.open ?? b.close, b.close, b.low ?? b.close, b.high ?? b.close]);

    // Mark lines: entry, stop, target, exit.
    const markLines: { name: string; yAxis: number; color: string; type?: 'dashed' }[] = [];
    if (trade.entry) markLines.push({ name: 'Entry', yAxis: trade.entry, color: entryColor });
    if (trade.stopLoss) markLines.push({ name: 'Stop', yAxis: trade.stopLoss, color: DOWN, type: 'dashed' });
    if (trade.takeProfit) markLines.push({ name: 'Target', yAxis: trade.takeProfit, color: UP, type: 'dashed' });
    if (trade.exit) markLines.push({ name: 'Exit', yAxis: trade.exit, color: '#fbbf24' });

    return {
      backgroundColor: 'transparent',
      grid: { left: 8, right: 8, top: 16, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        backgroundColor: 'rgba(18,18,20,0.5)', appendTo: 'body',
        borderColor: 'rgba(255,255,255,0.12)',
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: '#e5e5e5', fontSize: 11, fontFamily: 'monospace' },
        extraCssText:
          'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; box-shadow: 0 8px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);',
        formatter: (params: unknown) => {
          const arr = Array.isArray(params) ? params : [params];
          const p = arr[0] as { axisValue: string; data: number[] };
          if (!p) return '';
          const [o, c, l, h] = p.data;
          const fmt = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 4 });
          return `<b>${p.axisValue}</b><br/>O: ${fmt(o)}<br/>C: ${fmt(c)}<br/>L: ${fmt(l)}<br/>H: ${fmt(h)}`;
        },
      },
      xAxis: {
        type: 'category',
        data: dates,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace' },
        boundaryGap: true,
      },
      yAxis: {
        type: 'value',
        scale: true,
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace' },
      },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 12, bottom: 0, borderColor: 'transparent' }],
      series: [
        {
          type: 'candlestick',
          data: candles,
          itemStyle: {
            color: UP,
            color0: DOWN,
            borderColor: UP,
            borderColor0: DOWN,
          },
          markLine: {
            symbol: 'none',
            label: { color: '#a3a3a3', fontSize: 9, fontFamily: 'monospace', position: 'insideEndTop' },
            lineStyle: { width: 1 },
            data: markLines.map((m) => ({
              name: m.name,
              yAxis: m.yAxis,
              lineStyle: { color: m.color, type: m.type ?? 'solid' },
              label: { formatter: m.name },
            })),
          },
        },
      ],
    } as EChartsOption;
  }, [series, trade, UP, DOWN, entryColor]);

  const ref = useEChart(() => option, [option]);

  return (
    <div className="flex flex-col">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <span className="font-serif text-sm font-semibold text-foreground">{trade.symbol}</span>
        <span className={trade.direction === 'LONG' ? 'text-emerald-400' : 'text-rose-400'}>{trade.direction}</span>
        <span className="font-mono text-[10px] text-muted-foreground">R: <b className={trade.rMultiple >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{fmtR(trade.rMultiple)}</b></span>
        {trade.mfe != null && <span className="font-mono text-[10px] text-muted-foreground">MFE: <b className="text-emerald-400">{fmtR(trade.mfe)}</b></span>}
        {trade.mae != null && <span className="font-mono text-[10px] text-muted-foreground">MAE: <b className="text-rose-400">{fmtR(trade.mae)}</b></span>}
      </div>
      <div ref={ref} style={{ width: '100%', height }} />
      <div className="mt-2 flex flex-wrap gap-3 text-[9px] font-mono text-muted-foreground/70">
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-sky-400" /> Entry</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-rose-400" /> Stop</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-emerald-400" /> Target</span>
        <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-amber-400" /> Exit</span>
      </div>
    </div>
  );
}
