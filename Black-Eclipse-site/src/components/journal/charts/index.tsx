'use client';

// ── Journal chart components — reusable ECharts visualizations ───────────────
// Each chart is a thin wrapper over EChartsContainer. They consume analytics
// data via props and never fetch or compute themselves.

import React, { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { EChartsContainer, journalBaseOption, fmtR, fmtMoney } from './echarts-container';
import { cssVarToHex } from '@/lib/chart-colors';
import type { DimensionRow, EquityPoint } from '@/lib/journal/types';

export { EChartsContainer, journalBaseOption, fmtR, fmtMoney, echarts } from './echarts-container';

const UP = '#7aff78';
const DOWN = '#ff3e3e';

/** Shared frosted tooltip style. */
const tooltipStyle = {
  backgroundColor: 'rgba(18,18,20,0.5)', appendTo: 'body',
  borderColor: 'rgba(255, 255, 255, 0.12)',
  borderWidth: 1,
  padding: [10, 12] as [number, number],
  textStyle: { color: '#e5e5e5', fontSize: 11, fontFamily: 'monospace' },
  extraCssText: 'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; box-shadow: 0 8px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);',
};

// ── Equity curve (cumulative R) with drawdown shading ────────────────────────

export function EquityCurveChart({ equity, height = 240, title = 'Equity Curve', hint = 'CUMULATIVE R' }: { equity: EquityPoint[]; height?: number; title?: string; hint?: string }) {
  const primary = useMemo(() => cssVarToHex('--primary', UP), []);
  const option = useMemo<EChartsOption | null>(() => {
    if (equity.length < 2) return null;
    const dates = equity.map((p) => p.date.slice(0, 10));
    return {
      ...journalBaseOption(),
      tooltip: {
        trigger: 'axis',
        ...tooltipStyle,
        formatter: (params: unknown) => {
          const arr = Array.isArray(params) ? params : [params];
          const idx = (arr[0] as { dataIndex: number }).dataIndex;
          const p = equity[idx];
          return `<div style="font-weight:600;margin-bottom:4px">${p.date.slice(0, 10)}</div>Equity: <b style="color:${primary}">${fmtR(p.equity)}</b><br/>Drawdown: <b style="color:${DOWN}">${fmtR(-p.drawdown)}</b>`;
        },
      },
      xAxis: {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#7a7a7a', fontSize: 10, fontFamily: 'monospace' },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { formatter: (v: number) => `${v}R`, color: '#7a7a7a', fontSize: 10, fontFamily: 'monospace' },
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          name: 'Equity (R)',
          type: 'line',
          data: equity.map((p) => p.equity),
          showSymbol: false,
          smooth: 0.3,
          lineStyle: { width: 2.5, color: primary, shadowColor: `${primary}66`, shadowBlur: 8 },
          itemStyle: { color: primary },
          areaStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: `${primary}40` },
                { offset: 1, color: `${primary}00` },
              ],
            },
          },
        },
      ],
    };
  }, [equity, primary]);

  return <EChartsContainer option={option} deps={[equity, primary]} height={height} title={title} hint={hint} empty={equity.length < 2} emptyText="Not enough closed trades to plot an equity curve." />;
}

// ── Horizontal bar: net R by dimension (symbol / setup / session) ────────────

export function DimensionBarChart({ rows, title, hint, height = 220 }: { rows: DimensionRow[]; title: string; hint?: string; height?: number }) {
  const option = useMemo<EChartsOption | null>(() => {
    if (rows.length === 0) return null;
    const sorted = [...rows].sort((a, b) => a.netR - b.netR);
    return {
      ...journalBaseOption(),
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        ...tooltipStyle,
        formatter: (params: unknown) => {
          const arr = Array.isArray(params) ? params : [params];
          const idx = (arr[0] as { dataIndex: number }).dataIndex;
          const r = sorted[idx];
          const tone = r.netR >= 0 ? UP : DOWN;
          return `<div style="font-weight:600;margin-bottom:4px">${r.key}</div>Trades: <b>${r.trades}</b><br/>Win rate: <b>${(r.winRate * 100).toFixed(0)}%</b><br/>Net R: <b style="color:${tone}">${fmtR(r.netR)}</b><br/>Net P&L: <b style="color:${tone}">${fmtMoney(r.netPnl)}</b>`;
        },
      },
      grid: { left: 8, right: 44, top: 8, bottom: 0, containLabel: true },
      xAxis: {
        type: 'value',
        axisLabel: { formatter: (v: number) => `${v}R`, color: '#7a7a7a', fontSize: 10, fontFamily: 'monospace' },
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'category',
        data: sorted.map((r) => r.key),
        axisLabel: { color: '#a3a3a3', fontSize: 10 },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          type: 'bar',
          data: sorted.map((r) => ({
            value: r.netR,
            itemStyle: {
              color: r.netR >= 0 ? UP : DOWN,
              borderRadius: [0, 4, 4, 0],
              shadowColor: r.netR >= 0 ? `${UP}44` : `${DOWN}44`,
              shadowBlur: 6,
            },
          })),
          barWidth: '55%',
          label: {
            show: true,
            position: 'right',
            formatter: (p: { value?: unknown }) => `${Number(p.value ?? 0).toFixed(1)}R`,
            color: '#a3a3a3',
            fontSize: 9,
            fontFamily: 'monospace',
          },
        },
      ],
    };
  }, [rows]);

  return <EChartsContainer option={option} deps={[rows]} height={height} title={title} hint={hint} empty={rows.length === 0} emptyText="No data for this dimension yet." />;
}

// ── R distribution histogram ─────────────────────────────────────────────────

export function RDistributionChart({ rValues, height = 200, title = 'R Distribution', hint = 'TRADE OUTCOMES' }: { rValues: number[]; height?: number; title?: string; hint?: string }) {
  const option = useMemo<EChartsOption | null>(() => {
    if (rValues.length === 0) return null;
    const min = Math.floor(Math.min(...rValues));
    const max = Math.ceil(Math.max(...rValues));
    const bins: { label: string; count: number }[] = [];
    for (let i = min; i <= max; i++) {
      bins.push({ label: `${i}R`, count: 0 });
    }
    for (const v of rValues) {
      const idx = Math.max(0, Math.min(bins.length - 1, Math.floor(v) - min));
      bins[idx].count++;
    }
    return {
      ...journalBaseOption(),
      tooltip: { trigger: 'axis', ...tooltipStyle },
      xAxis: {
        type: 'category',
        data: bins.map((b) => b.label),
        axisLabel: { color: '#7a7a7a', fontSize: 10, fontFamily: 'monospace' },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#7a7a7a', fontSize: 10, fontFamily: 'monospace' },
      },
      series: [
        {
          type: 'bar',
          data: bins.map((b) => ({
            value: b.count,
            itemStyle: {
              color: b.label.startsWith('-') ? DOWN : UP,
              borderRadius: [3, 3, 0, 0],
              shadowColor: b.label.startsWith('-') ? `${DOWN}44` : `${UP}44`,
              shadowBlur: 4,
            },
          })),
          barWidth: '65%',
        },
      ],
    };
  }, [rValues]);

  return <EChartsContainer option={option} deps={[rValues]} height={height} title={title} hint={hint} empty={rValues.length === 0} emptyText="No closed trades to distribute." />;
}

// ── Win/loss distribution (donut) ─────────────────────────────────────────────

export function WinLossChart({ wins, losses, breakevens, height = 200, title = 'Win / Loss', hint = 'OUTCOMES' }: { wins: number; losses: number; breakevens: number; height?: number; title?: string; hint?: string }) {
  const option = useMemo<EChartsOption | null>(() => {
    if (wins + losses + breakevens === 0) return null;
    return {
      ...journalBaseOption(),
      tooltip: { trigger: 'item', ...tooltipStyle, formatter: (p: { name?: string; value?: unknown; percent?: number }) => `${p.name}: <b>${p.value}</b> (${p.percent}%)` },
      series: [
        {
          type: 'pie',
          radius: ['52%', '78%'],
          center: ['50%', '50%'],
          label: { show: false },
          emphasis: { scaleSize: 6 },
          itemStyle: { borderColor: '#0f0f0f', borderWidth: 2 },
          data: [
            { name: 'Wins', value: wins, itemStyle: { color: UP } },
            { name: 'Losses', value: losses, itemStyle: { color: DOWN } },
            { name: 'Breakeven', value: breakevens, itemStyle: { color: '#94a3b8' } },
          ].filter((d) => d.value > 0),
        },
      ],
    } as EChartsOption;
  }, [wins, losses, breakevens]);

  return <EChartsContainer option={option} deps={[wins, losses, breakevens]} height={height} title={title} hint={hint} empty={wins + losses + breakevens === 0} emptyText="No closed trades yet." />;
}

// ── Drawdown chart (equity drawdown from peak, in R) ──────────────────────────

export function DrawdownChart({ equity, height = 200, title = 'Drawdown', hint = 'FROM PEAK' }: { equity: EquityPoint[]; height?: number; title?: string; hint?: string }) {
  const option = useMemo<EChartsOption | null>(() => {
    if (equity.length < 2) return null;
    const dates = equity.map((p) => p.date.slice(0, 10));
    return {
      ...journalBaseOption(),
      tooltip: {
        trigger: 'axis',
        ...tooltipStyle,
        formatter: (params: unknown) => {
          const arr = Array.isArray(params) ? params : [params];
          const idx = (arr[0] as { dataIndex: number }).dataIndex;
          const p = equity[idx];
          return `<div style="font-weight:600;margin-bottom:4px">${p.date.slice(0, 10)}</div>Drawdown: <b style="color:${DOWN}">${fmtR(-p.drawdown)}</b>`;
        },
      },
      xAxis: { type: 'category', data: dates, boundaryGap: false, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace' } },
      yAxis: { type: 'value', scale: true, splitLine: { show: false }, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace', formatter: (v: number) => `${v}R` } },
      series: [
        {
          type: 'line',
          data: equity.map((p) => -p.drawdown),
          showSymbol: false,
          smooth: 0.3,
          lineStyle: { width: 1.5, color: DOWN },
          itemStyle: { color: DOWN },
          areaStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: `${DOWN}40` },
                { offset: 1, color: `${DOWN}00` },
              ],
            },
          },
        },
      ],
    };
  }, [equity]);

  return <EChartsContainer option={option} deps={[equity]} height={height} title={title} hint={hint} empty={equity.length < 2} emptyText="Not enough data to plot drawdown." />;
}

// ── Daily performance (net R per day, bar chart) ───────────────────────────────

export function DailyPerformanceChart({ days, height = 200, title = 'Daily Performance', hint = 'NET R PER DAY' }: { days: { date: string; netR: number }[]; height?: number; title?: string; hint?: string }) {
  const option = useMemo<EChartsOption | null>(() => {
    if (days.length === 0) return null;
    const sorted = [...days].sort((a, b) => a.date.localeCompare(b.date));
    return {
      ...journalBaseOption(),
      tooltip: {
        trigger: 'axis',
        ...tooltipStyle,
        formatter: (params: unknown) => {
          const arr = Array.isArray(params) ? params : [params];
          const idx = (arr[0] as { dataIndex: number }).dataIndex;
          const d = sorted[idx];
          return `<div style="font-weight:600;margin-bottom:4px">${d.date}</div>Net R: <b style="color:${d.netR >= 0 ? UP : DOWN}">${fmtR(d.netR)}</b>`;
        },
      },
      xAxis: { type: 'category', data: sorted.map((d) => d.date.slice(5)), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace' } },
      yAxis: { type: 'value', scale: true, splitLine: { show: false }, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace', formatter: (v: number) => `${v}R` } },
      series: [
        {
          type: 'bar',
          data: sorted.map((d) => ({
            value: d.netR,
            itemStyle: { color: d.netR >= 0 ? UP : DOWN, borderRadius: [2, 2, 0, 0] },
          })),
          barWidth: '60%',
        },
      ],
    };
  }, [days]);

  return <EChartsContainer option={option} deps={[days]} height={height} title={title} hint={hint} empty={days.length === 0} emptyText="No daily data yet." />;
}
