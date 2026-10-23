'use client';

import { BarChart3 } from '@/lib/icons';
import type { EChartsOption } from 'echarts';
import { SectionShell } from '@/components/screens/company/sections';
import { useEChart, baseChartOption } from '@/components/screens/portfolio/use-echart';
import { useChartPalette } from '@/lib/chart-palette-store';
import { axisLabel } from '@/lib/fundamentals/format';
import { cn } from '@/lib/utils';
import { useStockIntelligence } from '@/lib/stock-intelligence/use-stock-intelligence';
import type { StockChart, StockIntelligenceResponse } from '@/lib/stock-intelligence/types';
import { SourceBadge } from './source-badge';

function fmtAxis(value: number, unit: StockChart['unit']): string {
  if (unit === 'percent') return `${value.toFixed(1)}%`;
  if (unit === 'price') return value >= 100 ? value.toFixed(0) : value.toFixed(2);
  return `${value.toFixed(1)}×`;
}

const LINE_CHART_IDS = new Set<StockChart['id']>([
  'price-trend',
  'drawdown',
  'relative-performance',
]);

function ReadyChart({ chart }: { chart: StockChart }) {
  const palette = useChartPalette();
  const primary = palette.lines.primary;
  const secondary = palette.lines.series[4] ?? '#94a3b8';
  const up = palette.candles.up;
  const down = palette.candles.down;

  const ref = useEChart(() => {
    const isBar = !LINE_CHART_IDS.has(chart.id);
    const series = chart.series.map((entry, index) => {
      if (!isBar) {
        return {
          name: entry.name,
          type: 'line' as const,
          data: entry.values,
          smooth: false,
          symbol: 'none',
          lineStyle: { width: 2, color: index === 0 ? primary : secondary },
          itemStyle: { color: index === 0 ? primary : secondary },
          markLine: index === 0
            ? {
                silent: true,
                symbol: 'none',
                label: { show: false },
                lineStyle: { color: 'rgba(148,163,184,0.25)', type: 'dashed' as const },
                data: [{ yAxis: 0 }],
              }
            : undefined,
        };
      }
      return {
        name: entry.name,
        type: 'bar' as const,
        data: entry.values.map((value) =>
          chart.id === 'earnings-surprise'
            ? {
                value,
                itemStyle: {
                  color: (value ?? 0) >= 0 ? up : down,
                  borderRadius: [3, 3, 0, 0],
                },
              }
            : {
                value,
                itemStyle: { color: primary, borderRadius: [3, 3, 0, 0] },
              },
        ),
        barMaxWidth: 34,
      };
    });

    return {
      ...baseChartOption(),
      grid: { left: 6, right: 8, top: 10, bottom: 0, containLabel: true },
      xAxis: {
        type: 'category',
        data: chart.labels.map(axisLabel),
        boundaryGap: isBar,
        axisLabel: { color: '#94a3b8', fontSize: 9 },
        axisLine: { lineStyle: { color: 'rgba(148,163,184,0.1)' } },
      },
      yAxis: {
        type: 'value',
        scale: true,
        splitLine: { lineStyle: { color: 'rgba(148,163,184,0.05)' } },
        axisLabel: {
          color: '#94a3b8',
          fontSize: 9,
          formatter: (value: number) => fmtAxis(value, chart.unit),
        },
      },
      series: series as EChartsOption['series'],
    } as EChartsOption;
  }, [chart, primary, secondary, up, down]);

  return <div ref={ref} className="h-52 w-full" />;
}

function ChartCard({ chart }: { chart: StockChart }) {
  return (
    <div className="min-w-0 rounded-xl border border-border/30 glass-card-subtle p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-serif text-xs font-bold">{chart.title}</h3>
          <p className="mt-0.5 text-[10px] text-muted-foreground">{chart.subtitle}</p>
        </div>
        <SourceBadge state={chart.provenance.state} sources={chart.provenance.sources} />
      </div>
      {chart.state === 'READY' ? (
        <>
          <ReadyChart chart={chart} />
          {chart.note && <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground/70">{chart.note}</p>}
        </>
      ) : (
        <div className="mt-3 flex min-h-32 items-center justify-center rounded-lg border border-dashed border-border/30 px-3 py-4 text-center">
          <p className="text-[10px] leading-relaxed text-muted-foreground/70">{chart.reason ?? 'Data unavailable.'}</p>
        </div>
      )}
    </div>
  );
}

function PanelBody({ data }: { data: StockIntelligenceResponse }) {
  return (
    <>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
        {data.charts.map((chart) => (
          <ChartCard key={chart.id} chart={chart} />
        ))}
      </div>
      {data.warnings.length > 0 && (
        <p className={cn('text-[10px] leading-relaxed text-muted-foreground/60')}>
          {data.warnings.join(' · ')}
        </p>
      )}
    </>
  );
}

/**
 * Cross-source charts for the stock-detail overlay. Price-derived charts use
 * Yahoo daily closes; fundamentals charts use the provider snapshot. Every card
 * carries its provenance and an explicit unavailable state instead of a blank.
 */
export function StockIntelligencePanel({
  symbol,
  market,
  enabled = true,
}: {
  symbol: string;
  market: string;
  enabled?: boolean;
}) {
  const { data, loading, error } = useStockIntelligence(symbol, market, enabled);

  if (!enabled) return null;

  return (
    <SectionShell
      icon={<BarChart3 size={14} className="text-primary" />}
      title="Market intelligence"
      subtitle="benchmarked return · historical valuation · earnings surprise"
      right={<span className="text-[9px] font-mono text-muted-foreground">sourced</span>}
    >
      {loading && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((key) => (
            <div key={key} className="h-48 animate-pulse rounded-xl border border-border/30 glass-card-subtle" />
          ))}
        </div>
      )}
      {!loading && error && (
        <div className="rounded-xl border border-dashed border-border/30 px-3 py-4 text-center">
          <p className="text-[11px] text-muted-foreground">{error}</p>
        </div>
      )}
      {!loading && !error && data && <PanelBody data={data} />}
    </SectionShell>
  );
}
