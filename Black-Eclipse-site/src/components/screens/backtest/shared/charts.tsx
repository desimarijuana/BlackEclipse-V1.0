'use client';

// ── Shared quant charts ─────────────────────────────────────────────────────
// Equity and drawdown are drawn identically on the Backtest bench and in the
// Strategy Studio. They live here once so the two screens cannot drift.

import React from 'react';
import type { EChartsOption } from 'echarts';
import { useEChart, baseChartOption } from '@/components/screens/portfolio/use-echart';
import type { BacktestResult } from '@/lib/backtest/backtest-client';

export function EquityChart({ result, height = 260 }: { result: BacktestResult; height?: number }) {
  const curve = result.equityCurve;
  const ref = useEChart((): EChartsOption => {
    const option = baseChartOption();
    const x = curve.map((point) => point.ts ?? String(point.index));
    return {
      ...option,
      grid: { left: 56, right: 16, top: 24, bottom: 40 },
      xAxis: { type: 'category', data: x, axisLabel: { color: '#9ca3af', fontSize: 10 }, boundaryGap: false },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: '#9ca3af', fontSize: 10 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      },
      series: [
        {
          name: 'Equity',
          type: 'line',
          showSymbol: false,
          smooth: false,
          data: curve.map((point) => point.equity),
          lineStyle: { color: '#22d3ee', width: 2 },
          itemStyle: { color: '#22d3ee' },
          areaStyle: { color: 'rgba(34,211,238,0.12)' },
        },
      ],
    } as EChartsOption;
  }, [curve]);
  return <div ref={ref} style={{ height }} className="w-full" />;
}

export function DrawdownChart({ result, height = 200 }: { result: BacktestResult; height?: number }) {
  const curve = result.drawdownCurve;
  const ref = useEChart((): EChartsOption => {
    const option = baseChartOption();
    const x = curve.map((point) => point.ts ?? String(point.index));
    return {
      ...option,
      grid: { left: 56, right: 16, top: 20, bottom: 40 },
      xAxis: { type: 'category', data: x, axisLabel: { color: '#9ca3af', fontSize: 10 }, boundaryGap: false },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#9ca3af', fontSize: 10, formatter: '{value}%' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
      },
      series: [
        {
          name: 'Drawdown',
          type: 'line',
          showSymbol: false,
          data: curve.map((point) => point.drawdown),
          lineStyle: { color: '#f87171', width: 1.5 },
          itemStyle: { color: '#f87171' },
          areaStyle: { color: 'rgba(248,113,113,0.15)' },
        },
      ],
    } as EChartsOption;
  }, [curve]);
  return <div ref={ref} style={{ height }} className="w-full" />;
}
