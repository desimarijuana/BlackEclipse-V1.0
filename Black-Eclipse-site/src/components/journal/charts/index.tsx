'use client';

// ── Journal chart components — reusable ECharts visualizations ───────────────
// Each chart is a thin wrapper over EChartsContainer. They consume analytics
// data via props and never fetch or compute themselves.

import React, { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { EChartsContainer, journalBaseOption, fmtR, fmtMoney } from './echarts-container';
import { useChartPalette } from '@/lib/chart-palette-store';
import type { DimensionRow, EquityPoint } from '@/lib/journal/types';

export { EChartsContainer, journalBaseOption, fmtR, fmtMoney, echarts } from './echarts-container';

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

export function EquityCurveChart({ equity, height = 240, title = 'Equity Curve', hint, currency = false }: { equity: EquityPoint[]; height?: number; title?: string; hint?: string; currency?: boolean }) {
  const palette = useChartPalette();
  const resolvedHint = hint ?? (currency ? 'ACCOUNT BALANCE' : 'CUMULATIVE R');
  const option = useMemo<EChartsOption | null>(() => {
    const sym = '\u0024';
    const fmt = currency ? (v: number) => `${sym}${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : fmtR;
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
          return `<div style="font-weight:600;margin-bottom:4px">${p.date.slice(0, 10)}</div>Equity: <b style="color:${palette.lines.primary}">${fmt(p.equity)}</b><br/>Drawdown: <b style="color:${palette.candles.down}">${fmt(-p.drawdown)}</b>`;
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
        axisLabel: { formatter: (v: number) => (currency ? fmt(v) : `${v}R`), color: '#7a7a7a', fontSize: 10, fontFamily: 'monospace' },
        splitLine: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          name: currency ? 'Equity (balance)' : 'Equity (R)',
          type: 'line',
          data: equity.map((p) => p.equity),
          showSymbol: false,
          smooth: 0.3,
          lineStyle: { width: 2.5, color: palette.lines.primary, shadowColor: `${palette.lines.primary}66`, shadowBlur: 8 },
          itemStyle: { color: palette.lines.primary },
          areaStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: `${palette.lines.primary}40` },
                { offset: 1, color: `${palette.lines.primary}00` },
              ],
            },
          },
        },
      ],
    };
  }, [equity, palette, currency]);

  return <EChartsContainer option={option} deps={[equity, palette, currency]} height={height} title={title} hint={resolvedHint} empty={equity.length < 2} emptyText="Not enough closed trades to plot an equity curve." />;
}

// ── Horizontal bar: net R by dimension (symbol / setup / session) ────────────

export function DimensionBarChart({ rows, title, hint, height = 220, basis = 'R' }: { rows: DimensionRow[]; title: string; hint?: string; height?: number; basis?: 'R' | 'pnl' }) {
  const palette = useChartPalette();
  const valueOf = (r: DimensionRow) => (basis === 'pnl' ? r.netPnl : r.netR);
  const label = (v: number) => (basis === 'pnl' ? fmtMoney(v) : fmtR(v));
  const option = useMemo<EChartsOption | null>(() => {
    if (rows.length === 0) return null;
    const sorted = [...rows].sort((a, b) => (basis === 'pnl' ? a.netPnl - b.netPnl : a.netR - b.netR));
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
          const tone = (basis === 'pnl' ? r.netPnl : r.netR) >= 0 ? palette.candles.up : palette.candles.down;
          return `<div style="font-weight:600;margin-bottom:4px">${r.key}</div>Trades: <b>${r.trades}</b><br/>Win rate: <b>${(r.winRate * 100).toFixed(0)}%</b><br/>Net ${basis === 'pnl' ? 'P&L' : 'R'}: <b style="color:${tone}">${label(basis === 'pnl' ? r.netPnl : r.netR)}</b><br/>Net P&L: <b style="color:${tone}">${fmtMoney(r.netPnl)}</b>`;
        },
      },
      grid: { left: 8, right: 44, top: 8, bottom: 0, containLabel: true },
      xAxis: {
        type: 'value',
        axisLabel: { formatter: (v: number) => (basis === 'pnl' ? fmtMoney(v) : `${v}R`), color: '#7a7a7a', fontSize: 10, fontFamily: 'monospace' },
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
          data: sorted.map((r) => {
            const v = valueOf(r);
            return {
              value: v,
              itemStyle: {
                color: v >= 0 ? palette.candles.up : palette.candles.down,
                borderRadius: [0, 4, 4, 0],
                shadowColor: v >= 0 ? `${palette.candles.up}44` : `${palette.candles.down}44`,
                shadowBlur: 6,
              },
            };
          }),
          barWidth: '55%',
          label: {
            show: true,
            position: 'right',
            formatter: (p: { value?: unknown }) => label(Number(p.value ?? 0)),
            color: '#a3a3a3',
            fontSize: 9,
            fontFamily: 'monospace',
          },
        },
      ],
    };
  }, [rows, palette, basis]);

  return <EChartsContainer option={option} deps={[rows, palette, basis]} height={height} title={title} hint={hint} empty={rows.length === 0} emptyText="No data for this dimension yet." />;
}

// ── R distribution histogram ─────────────────────────────────────────────────

export function RDistributionChart({ rValues, height = 200, title = 'R Distribution', hint = 'TRADE OUTCOMES' }: { rValues: number[]; height?: number; title?: string; hint?: string }) {
  const palette = useChartPalette();
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
              color: b.label.startsWith('-') ? palette.candles.down : palette.candles.up,
              borderRadius: [3, 3, 0, 0],
              shadowColor: b.label.startsWith('-') ? `${palette.candles.down}44` : `${palette.candles.up}44`,
              shadowBlur: 4,
            },
          })),
          barWidth: '65%',
        },
      ],
    };
  }, [rValues, palette]);

  return <EChartsContainer option={option} deps={[rValues, palette]} height={height} title={title} hint={hint} empty={rValues.length === 0} emptyText="No closed trades to distribute." />;
}

// ── Win/loss distribution (donut) ─────────────────────────────────────────────

export function WinLossChart({ wins, losses, breakevens, height = 200, title = 'Win / Loss', hint = 'OUTCOMES' }: { wins: number; losses: number; breakevens: number; height?: number; title?: string; hint?: string }) {
  const palette = useChartPalette();
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
            { name: 'Wins', value: wins, itemStyle: { color: palette.candles.up } },
            { name: 'Losses', value: losses, itemStyle: { color: palette.candles.down } },
            { name: 'Breakeven', value: breakevens, itemStyle: { color: palette.candles.neutral } },
          ].filter((d) => d.value > 0),
        },
      ],
    } as EChartsOption;
  }, [wins, losses, breakevens, palette]);

  return <EChartsContainer option={option} deps={[wins, losses, breakevens, palette]} height={height} title={title} hint={hint} empty={wins + losses + breakevens === 0} emptyText="No closed trades yet." />;
}

// ── Drawdown chart (equity drawdown from peak, in R) ──────────────────────────

export function DrawdownChart({ equity, height = 200, title = 'Drawdown', hint = 'FROM PEAK' }: { equity: EquityPoint[]; height?: number; title?: string; hint?: string }) {
  const palette = useChartPalette();
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
          return `<div style="font-weight:600;margin-bottom:4px">${p.date.slice(0, 10)}</div>Drawdown: <b style="color:${palette.candles.down}">${fmtR(-p.drawdown)}</b>`;
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
          lineStyle: { width: 1.5, color: palette.candles.down },
          itemStyle: { color: palette.candles.down },
          areaStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: `${palette.candles.down}40` },
                { offset: 1, color: `${palette.candles.down}00` },
              ],
            },
          },
        },
      ],
    };
  }, [equity, palette]);

  return <EChartsContainer option={option} deps={[equity, palette]} height={height} title={title} hint={hint} empty={equity.length < 2} emptyText="Not enough data to plot drawdown." />;
}

// ── Daily performance (net R per day, bar chart) ───────────────────────────────

export function DailyPerformanceChart({ days, height = 200, title = 'Daily Performance', hint, basis = 'R' }: { days: { date: string; netR: number; netPnl?: number }[]; height?: number; title?: string; hint?: string; basis?: 'R' | 'pnl' }) {
  const palette = useChartPalette();
  const valueOf = (d: { netR: number; netPnl?: number }) => (basis === 'pnl' ? d.netPnl ?? 0 : d.netR);
  const label = (v: number) => (basis === 'pnl' ? fmtMoney(v) : fmtR(v));
  const resolvedHint = hint ?? (basis === 'pnl' ? 'NET P&L PER DAY' : 'NET R PER DAY');
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
          const v = valueOf(d);
          return `<div style="font-weight:600;margin-bottom:4px">${d.date}</div>${basis === 'pnl' ? 'Net P&L' : 'Net R'}: <b style="color:${v >= 0 ? palette.candles.up : palette.candles.down}">${label(v)}</b>`;
        },
      },
      xAxis: { type: 'category', data: sorted.map((d) => d.date.slice(5)), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace' } },
      yAxis: { type: 'value', scale: true, splitLine: { show: false }, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace', formatter: (v: number) => (basis === 'pnl' ? fmtMoney(v) : `${v}R`) } },
      series: [
        {
          type: 'bar',
          data: sorted.map((d) => {
            const v = valueOf(d);
            return {
              value: v,
              itemStyle: { color: v >= 0 ? palette.candles.up : palette.candles.down, borderRadius: [2, 2, 0, 0] },
            };
          }),
          barWidth: '60%',
        },
      ],
    };
  }, [days, palette, basis]);

  return <EChartsContainer option={option} deps={[days, palette, basis]} height={height} title={title} hint={resolvedHint} empty={days.length === 0} emptyText="No daily data yet." />;
}

// ── Generic scatter (MAE/MFE efficiency, confidence vs outcome) ──────────────

export interface ScatterPoint { x: number; y: number; label?: string }

export function ScatterChart({
  points, xLabel, yLabel, title, hint, xFormatter, yFormatter, tooltipFormatter, height = 220,
}: {
  points: ScatterPoint[];
  xLabel: string;
  yLabel: string;
  title?: string;
  hint?: string;
  xFormatter?: (v: number) => string;
  yFormatter?: (v: number) => string;
  tooltipFormatter?: (p: ScatterPoint) => string;
  height?: number;
}) {
  const palette = useChartPalette();
  const option = useMemo<EChartsOption | null>(() => {
    if (points.length === 0) return null;
    const xfmt = xFormatter ?? ((v: number) => String(v));
    const yfmt = yFormatter ?? ((v: number) => String(v));
    return {
      ...journalBaseOption(),
      tooltip: {
        trigger: 'item',
        ...tooltipStyle,
        formatter: (params: unknown) => {
          const d = (Array.isArray(params) ? params[0] : params) as { data: { value: [number, number]; point: ScatterPoint } };
          const pt = d.data.point;
          return tooltipFormatter
            ? tooltipFormatter(pt)
            : `${xLabel}: <b>${xfmt(pt.x)}</b><br/>${yLabel}: <b>${yfmt(pt.y)}</b>`;
        },
      },
      xAxis: {
        type: 'value', scale: true, name: xLabel,
        nameLocation: 'middle', nameGap: 24,
        nameTextStyle: { color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } },
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { formatter: (v: number) => xfmt(v), color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace' },
      },
      yAxis: {
        type: 'value', scale: true, name: yLabel,
        nameTextStyle: { color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } },
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { formatter: (v: number) => yfmt(v), color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace' },
      },
      series: [
        {
          type: 'scatter',
          symbolSize: 9,
          data: points.map((pt) => ({
            value: [pt.x, pt.y],
            point: pt,
            itemStyle: { color: pt.y >= 0 ? palette.candles.up : palette.candles.down, opacity: 0.75 },
          })),
        },
      ],
    };
  }, [points, palette, xLabel, yLabel, xFormatter, yFormatter, tooltipFormatter]);

  return <EChartsContainer option={option} deps={[points, palette]} height={height} title={title} hint={hint} empty={points.length === 0} emptyText="Not enough data to plot this view." />;
}

// ── Rolling performance (trailing window) ─────────────────────────────────────

export function RollingMetricsChart({ rolling, height = 220, title = 'Rolling Performance', hint = 'TRAILING 20 TRADES' }: { rolling: { date: string; winRate: number; expectancyR: number; netR: number }[]; height?: number; title?: string; hint?: string }) {
  const palette = useChartPalette();
  const option = useMemo<EChartsOption | null>(() => {
    if (rolling.length === 0) return null;
    const dates = rolling.map((p) => p.date.slice(0, 10));
    return {
      ...journalBaseOption(),
      tooltip: {
        trigger: 'axis',
        ...tooltipStyle,
        formatter: (params: unknown) => {
          const arr = Array.isArray(params) ? params : [params];
          const idx = (arr[0] as { dataIndex: number }).dataIndex;
          const p = rolling[idx];
          return `<div style="font-weight:600;margin-bottom:4px">${p.date.slice(0, 10)}</div>Win rate: <b>${(p.winRate * 100).toFixed(0)}%</b><br/>Expectancy: <b style="color:${p.expectancyR >= 0 ? palette.candles.up : palette.candles.down}">${fmtR(p.expectancyR)}</b><br/>Net R (window): <b>${fmtR(p.netR)}</b>`;
        },
      },
      xAxis: { type: 'category', data: dates, boundaryGap: false, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace' } },
      yAxis: { type: 'value', scale: true, splitLine: { show: false }, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#7a7a7a', fontSize: 9, fontFamily: 'monospace', formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
      series: [
        {
          name: 'Win rate',
          type: 'line',
          data: rolling.map((p) => p.winRate),
          showSymbol: false,
          smooth: 0.3,
          lineStyle: { width: 2, color: palette.lines.primary },
          itemStyle: { color: palette.lines.primary },
        },
      ],
    };
  }, [rolling, palette]);

  return <EChartsContainer option={option} deps={[rolling, palette]} height={height} title={title} hint={hint} empty={rolling.length === 0} emptyText="Need at least 20 closed trades for a rolling view." />;
}
