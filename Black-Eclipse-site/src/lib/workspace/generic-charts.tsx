'use client';

// ── Generic chart widgets ────────────────────────────────────────────────────
// `line-chart`, `area-chart`, `bar-chart` and `pie-chart` render whatever the
// allow-listed data-source resolver returns: a time `series` (line/area), or a
// row set reduced to a label column + a numeric column (bar/pie). No data →
// an explicit empty/unavailable state, never a fabricated curve.

import React, { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import { cn } from '@/lib/utils';
import { ChartLine, BarChart3, PieChart } from '@/lib/icons';
import { baseChartOption, useEChart } from '@/components/screens/portfolio/use-echart';
import { useChartPalette } from '@/lib/chart-palette-store';
import type { WidgetPlacement } from '@/lib/workspace/types';
import { useDataSource, type ResolvedSource, type SourceSeries } from '@/lib/workspace/data-source';

function str(v: unknown): string {
  return typeof v === 'string' ? v.trim() : '';
}

function Header({ icon: Icon, title, hint }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  hint?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
      <div className="flex min-w-0 items-center gap-2">
        <Icon size={14} className="shrink-0 text-primary" />
        <h3 className="truncate font-serif text-sm font-semibold text-foreground">{title}</h3>
      </div>
      {hint && <span className="shrink-0 font-mono text-[9px] text-muted-foreground/70">{hint}</span>}
    </div>
  );
}

interface ChartData { labels: string[]; series: SourceSeries[] }

function toChartData(data: ResolvedSource | null | undefined): ChartData | null {
  if (!data) return null;
  if (data.kind === 'series' && data.series?.length) {
    const first = data.series[0];
    const labels = first.dates ?? first.points.map((_, i) => String(i));
    return { labels, series: data.series };
  }
  if (data.kind === 'rows' && data.rows?.length) {
    const columns = data.columns ?? [];
    const labelCol = columns.find((c) => c.align !== 'right') ?? columns[0];
    const numCol = columns.find((c) => c.align === 'right') ?? columns[1] ?? columns[0];
    if (!labelCol || !numCol) return null;
    return {
      labels: data.rows.map((r) => String(r[labelCol.key] ?? '')),
      series: [{ name: numCol.label, points: data.rows.map((r) => Number(String(r[numCol.key] ?? '').replace(/[,\s]/g, '')) || 0) }],
    };
  }
  return null;
}

function useSourceFor(placement: WidgetPlacement, defaultView: string) {
  const cfg = (placement.config ?? {}) as Record<string, unknown>;
  const source = str(cfg.source)
    || (str(cfg.portfolioId) ? `portfolio:${str(cfg.portfolioId)}:${defaultView}` : '');
  const entry = useDataSource(source || undefined);
  return { source, data: entry.data, title: str(cfg.title) };
}

function ChartShell({ icon, title, hint, empty, children }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  hint?: string;
  empty?: { message: string; tone?: 'warn' | 'muted' };
  children?: React.ReactNode;
}) {
  return (
    <div className="flex h-full flex-col p-4">
      <Header icon={icon} title={title} hint={hint} />
      {children ?? (
        <div className="flex flex-1 items-center justify-center text-center">
          <p className={cn('max-w-[30ch] text-xs italic', empty?.tone === 'warn' ? 'text-amber-400/80' : 'text-muted-foreground/70')}>
            {empty?.message ?? 'No data.'}
          </p>
        </div>
      )}
    </div>
  );
}

function LineLike({ placement, area }: { placement: WidgetPlacement; area: boolean }) {
  const { source, data, title } = useSourceFor(placement, 'positions');
  const chart = useMemo(() => toChartData(data), [data]);
  const palette = useChartPalette();

  const ref = useEChart(() => {
    if (!chart || chart.labels.length < 2) return null;
    const colors = [palette.lines.primary, ...palette.lines.series];
    return {
      ...baseChartOption(),
      grid: { left: 8, right: 8, top: 10, bottom: chart.series.length > 1 ? 22 : 0, containLabel: true },
      xAxis: {
        type: 'category', data: chart.labels,
        axisLine: { lineStyle: { color: 'rgba(148,163,184,0.04)' } },
        axisLabel: { color: '#94a3b8', fontSize: 9 },
      },
      yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: 'rgba(148,163,184,0.03)' } }, axisLabel: { color: '#94a3b8', fontSize: 9 } },
      series: chart.series.map((s, i) => ({
        name: s.name, type: 'line', data: s.points, showSymbol: false,
        lineStyle: { width: 2, color: colors[i % colors.length] },
        areaStyle: area ? { color: colors[i % colors.length], opacity: 0.12 } : undefined,
      })),
      legend: chart.series.length > 1 ? { bottom: 0, textStyle: { color: '#94a3b8', fontSize: 9 }, itemWidth: 12 } : undefined,
    } as EChartsOption;
  }, [chart, palette, area]);

  const icon = area ? ChartLine : ChartLine;
  if (!source || data?.kind === 'unavailable') {
    return <ChartShell icon={icon} title={title || 'Chart'} empty={{ message: data?.detail || 'UNAVAILABLE — no data source configured.', tone: 'warn' }} />;
  }
  if (!chart || chart.labels.length < 2) {
    return <ChartShell icon={icon} title={title || 'Chart'} empty={{ message: 'Not enough data points to chart.' }} />;
  }
  return <ChartShell icon={icon} title={title || 'Chart'}><div ref={ref} className="min-h-[160px] flex-1" /></ChartShell>;
}

export function LineChartWidget({ placement }: { placement: WidgetPlacement }) {
  return <LineLike placement={placement} area={false} />;
}
export function AreaChartWidget({ placement }: { placement: WidgetPlacement }) {
  return <LineLike placement={placement} area />;
}

export function BarChartWidget({ placement }: { placement: WidgetPlacement }) {
  const { source, data, title } = useSourceFor(placement, 'allocation');
  const chart = useMemo(() => toChartData(data), [data]);
  const palette = useChartPalette();

  const ref = useEChart(() => {
    if (!chart || chart.labels.length === 0) return null;
    return {
      ...baseChartOption(),
      grid: { left: 8, right: 8, top: 10, bottom: 0, containLabel: true },
      xAxis: { type: 'category', data: chart.labels, axisLabel: { color: '#94a3b8', fontSize: 9, rotate: chart.labels.length > 8 ? 45 : 0 }, axisLine: { lineStyle: { color: 'rgba(148,163,184,0.04)' } } },
      yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: 'rgba(148,163,184,0.03)' } }, axisLabel: { color: '#94a3b8', fontSize: 9 } },
      series: [{ name: chart.series[0]?.name ?? 'Value', type: 'bar', data: chart.series[0]?.points ?? [], itemStyle: { color: palette.lines.primary, borderRadius: [4, 4, 0, 0] } }],
    } as EChartsOption;
  }, [chart, palette]);

  if (!source || data?.kind === 'unavailable') {
    return <ChartShell icon={BarChart3} title={title || 'Bar Chart'} empty={{ message: data?.detail || 'UNAVAILABLE — no data source configured.', tone: 'warn' }} />;
  }
  if (!chart || chart.labels.length === 0) {
    return <ChartShell icon={BarChart3} title={title || 'Bar Chart'} empty={{ message: 'No rows to chart.' }} />;
  }
  return <ChartShell icon={BarChart3} title={title || 'Bar Chart'}><div ref={ref} className="min-h-[160px] flex-1" /></ChartShell>;
}

export function PieChartWidget({ placement }: { placement: WidgetPlacement }) {
  const { source, data, title } = useSourceFor(placement, 'allocation');
  const chart = useMemo(() => toChartData(data), [data]);
  const palette = useChartPalette();

  const ref = useEChart(() => {
    if (!chart || chart.labels.length === 0) return null;
    const points = chart.series[0]?.points ?? [];
    const colors = [palette.lines.primary, ...palette.lines.series, '#fbbf24', '#f472b6', '#a78bfa', '#2dd4bf'];
    return {
      ...baseChartOption(),
      series: [{
        type: 'pie', radius: ['56%', '82%'], center: ['50%', '50%'],
        label: { show: false },
        data: chart.labels.map((label, i) => ({ name: label || `#${i + 1}`, value: Number(points[i] ?? 0), itemStyle: { color: colors[i % colors.length] } })),
      }],
    } as EChartsOption;
  }, [chart, palette]);

  if (!source || data?.kind === 'unavailable') {
    return <ChartShell icon={PieChart} title={title || 'Pie Chart'} empty={{ message: data?.detail || 'UNAVAILABLE — no data source configured.', tone: 'warn' }} />;
  }
  if (!chart || chart.labels.length === 0) {
    return <ChartShell icon={PieChart} title={title || 'Pie Chart'} empty={{ message: 'No rows to chart.' }} />;
  }
  return <ChartShell icon={PieChart} title={title || 'Pie Chart'}><div ref={ref} className="min-h-[160px] flex-1" /></ChartShell>;
}
