'use client';

// ── Generic, data-source-driven widgets ──────────────────────────────────────
// `data-table` and `metric-card` are the universal primitives: they render
// whatever `src/lib/workspace/data-source.ts` resolves for their `source`
// config. Because they are registry widgets with stable ids, an agent composes
// them onto any page (`ui_add_widget componentId="data-table" config={source}`)
// and they render live — the missing half of the UI-Engineering loop for pages
// that are not the Command Center.
//
// Honesty: a missing/unconfigured/unresolvable source renders an explicit
// UNAVAILABLE state with the reason; a number is only ever shown when the
// resolver returned one.

import React, { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { Table2, Activity, ChevronLeft, ChevronRight } from '@/lib/icons';
import type { WidgetPlacement } from '@/lib/workspace/types';
import type { WidgetDefinition } from '@/lib/workspace/widget-def';
import { useDataSource, type ResolvedSource } from '@/lib/workspace/data-source';
import { LineChartWidget, AreaChartWidget, BarChartWidget, PieChartWidget } from '@/lib/workspace/generic-charts';
import { ListWidget, MarkdownWidget, StatusIndicatorWidget, EmptyStateWidget, ErrorStateWidget } from '@/lib/workspace/generic-content';

const UP = 'text-emerald-400';
const DOWN = 'text-rose-400';

function WidgetHeader({ icon: Icon, title, hint, provenance }: {
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  hint?: string;
  provenance?: ResolvedSource['provenance'];
}) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
      <div className="flex min-w-0 items-center gap-2">
        <Icon size={14} className="shrink-0 text-primary" />
        <h3 className="truncate font-serif text-sm font-semibold text-foreground">{title}</h3>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {hint && <span className="font-mono text-[9px] text-muted-foreground/70">{hint}</span>}
        {provenance && (
          <span className={cn(
            'rounded border px-1 py-0.5 font-mono text-[8px] font-bold uppercase tracking-wide',
            provenance === 'LIVE'
              ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-400'
              : 'border-amber-500/25 bg-amber-500/10 text-amber-400',
          )}>
            {provenance}
          </span>
        )}
      </div>
    </div>
  );
}

function Unavailable({ title, detail, icon }: { title: string; detail?: string; icon: React.ComponentType<{ size?: number; className?: string }> }) {
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={icon} title={title} provenance="UNAVAILABLE" />
      <div className="flex flex-1 items-center justify-center text-center">
        <p className="max-w-[28ch] text-xs italic text-amber-400/80">{detail || 'UNAVAILABLE — no data source configured.'}</p>
      </div>
    </div>
  );
}

function str(v: unknown): string {
  return typeof v === 'string' ? v.trim() : '';
}

/**
 * Turn a widget instance's config into one source string. Explicit `source`
 * wins; a `metric` that already looks like a source is used as-is; otherwise a
 * `portfolioId` (plus an optional view and metric field) builds a portfolio
 * source. Unknown shapes return undefined → the widget renders UNAVAILABLE.
 */
function sourceOf(
  config: Record<string, unknown> | null | undefined,
  opts: { defaultView: string; defaultField?: string },
): string | undefined {
  const cfg = config ?? {};
  const explicitSource = str(cfg.source);
  if (explicitSource) return explicitSource;

  const metric = str(cfg.metric);
  if (metric.includes(':')) return metric;

  const portfolioId = str(cfg.portfolioId);
  if (!portfolioId) return undefined;
  const view = str(cfg.view) || opts.defaultView;
  const field = metric || opts.defaultField;
  return field ? `portfolio:${portfolioId}:${view}.${field}` : `portfolio:${portfolioId}:${view}`;
}

function formatValue(value: string | number | null | undefined, format: unknown): string {
  if (value == null) return '—';
  const fmt = typeof format === 'string' ? format : 'number';
  const num = typeof value === 'number' ? value : Number(String(value).replace(/[,\s]/g, ''));
  if (!Number.isFinite(num)) return String(value);
  if (fmt === 'currency') return num.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
  if (fmt === 'percent') return `${num.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
  return num.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

// ── data-table ───────────────────────────────────────────────────────────────

export function DataTableWidget({ placement }: { placement: WidgetPlacement }) {
  const cfg = (placement.config ?? {}) as Record<string, unknown>;
  const source = sourceOf(cfg, { defaultView: 'positions' });
  const entry = useDataSource(source);
  const data = entry.data;
  const dense = cfg.dense === true;
  const pageSize = Math.max(1, Math.min(500, Number(cfg.pageSize) || 25));
  const [page, setPage] = useState(0);

  const title = typeof cfg.title === 'string' && cfg.title.trim()
    ? cfg.title.trim()
    : source ? `Data · ${source.split(':').slice(1).join(':')}` : 'Data Table';

  const rows = data?.rows ?? [];
  const columns = data?.columns ?? [];
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const visible = useMemo(() => rows.slice(safePage * pageSize, safePage * pageSize + pageSize), [rows, safePage, pageSize]);

  if (!source || data?.kind === 'unavailable') {
    return <Unavailable title={title} detail={data?.detail} icon={Table2} />;
  }
  if (data?.kind !== 'rows') {
    return <Unavailable title={title} detail="this source is not tabular" icon={Table2} />;
  }

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={Table2} title={title} hint={rows.length ? `${rows.length} rows` : undefined} provenance={data.provenance} />
      {rows.length === 0 ? (
        <div className="flex flex-1 items-center justify-center py-8 text-center">
          <p className="text-xs italic text-muted-foreground/70">No rows.</p>
        </div>
      ) : (
        <>
          <div className="flex-1 overflow-auto custom-scrollbar rounded-xl glass-card-subtle shadow-inner shadow-black/20">
            <table className="w-full border-separate border-spacing-0 text-left text-xs">
              <thead className="sticky top-0 z-10">
                <tr className="glass-card-subtle">
                  {columns.map((col) => (
                    <th
                      key={col.key}
                      className={cn(
                        'border-b border-white/10 px-3 text-[9px] font-mono font-semibold uppercase tracking-widest text-muted-foreground/80 whitespace-nowrap',
                        dense ? 'py-1.5' : 'py-2.5',
                        col.align === 'right' ? 'text-right' : 'text-left',
                      )}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="font-mono">
                {visible.map((row, i) => (
                  <tr key={i} className="transition-colors hover:bg-white/[0.05]">
                    {columns.map((col) => (
                      <td
                        key={col.key}
                        className={cn(
                          'border-b border-white/5 px-3 tabular-nums text-muted-foreground whitespace-nowrap',
                          dense ? 'py-1.5' : 'py-2.5',
                          col.align === 'right' ? 'text-right' : 'text-left',
                        )}
                      >
                        {row[col.key] == null ? '—' : String(row[col.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pageCount > 1 && (
            <div className="mt-2 flex shrink-0 items-center justify-end gap-2 font-mono text-[10px] text-muted-foreground">
              <button type="button" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={safePage === 0} className="rounded p-1 hover:text-primary disabled:opacity-30">
                <ChevronLeft size={12} />
              </button>
              <span>{safePage + 1} / {pageCount}</span>
              <button type="button" onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))} disabled={safePage >= pageCount - 1} className="rounded p-1 hover:text-primary disabled:opacity-30">
                <ChevronRight size={12} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── metric-card ──────────────────────────────────────────────────────────────

export function MetricCardWidget({ placement }: { placement: WidgetPlacement }) {
  const cfg = (placement.config ?? {}) as Record<string, unknown>;
  const source = sourceOf(cfg, { defaultView: 'summary', defaultField: 'totalValue' });
  const entry = useDataSource(source);
  const data = entry.data;

  const label = typeof cfg.label === 'string' && cfg.label.trim()
    ? cfg.label.trim()
    : data?.label ? data.label : (source?.split(':').pop() ?? 'Metric');
  const title = typeof cfg.title === 'string' && cfg.title.trim() ? cfg.title.trim() : 'Metric';

  if (!source || data?.kind === 'unavailable') {
    return <Unavailable title={title} detail={data?.detail} icon={Activity} />;
  }
  if (data?.kind !== 'value') {
    return <Unavailable title={title} detail="this source is not a single metric" icon={Activity} />;
  }

  const display = formatValue(data.value, cfg.format);
  const numeric = typeof data.value === 'number' ? data.value : Number(String(data.value).replace(/[,\s]/g, ''));
  const tone = Number.isFinite(numeric) && numeric !== 0 ? (numeric > 0 ? UP : DOWN) : 'text-foreground';

  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader icon={Activity} title={title} provenance={data.provenance} />
      <div className="flex flex-1 flex-col justify-center rounded-xl glass-card-subtle p-4">
        <p className="truncate text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{label}</p>
        <p className={cn('mt-1.5 truncate font-mono text-2xl font-bold', tone)}>{display}</p>
        {source && <p className="mt-1 truncate font-mono text-[9px] text-muted-foreground/60">{source}</p>}
      </div>
    </div>
  );
}

// ── Registry definitions ─────────────────────────────────────────────────────
// These ids MUST match the Python runtime catalog so an agent can compose them
// by the same name it discovers via `ui_get_component_catalog`.

export const SOURCE_WIDGETS: WidgetDefinition[] = [
  {
    id: 'data-table',
    category: 'tables',
    label: 'Data Table',
    desc: 'A table over any resolvable source (e.g. portfolio:<id>:positions).',
    icon: 'table',
    sizes: ['large', 'full'],
    defaultHeight: 360,
    catalogDataSources: ['any', 'portfolio'],
    defaultConfig: { pageSize: 25, dense: false },
    configFields: [
      { key: 'source', label: 'Data source', type: 'text', placeholder: 'portfolio:pf_…:positions' },
      { key: 'portfolioId', label: 'Portfolio id', type: 'text', placeholder: 'pf_… (shorthand for a positions table)' },
      { key: 'pageSize', label: 'Page size', type: 'number', min: 1, max: 500, default: 25 },
      { key: 'dense', label: 'Dense rows', type: 'boolean' },
    ],
    render: (placement) => <DataTableWidget placement={placement} />,
  },
  {
    id: 'metric-card',
    category: 'metrics',
    label: 'Metric Card',
    desc: 'A single metric from a source (e.g. portfolio:<id>:summary.totalValue).',
    icon: 'activity',
    sizes: ['small', 'medium'],
    defaultHeight: 140,
    catalogDataSources: ['any', 'portfolio'],
    configFields: [
      { key: 'label', label: 'Label', type: 'text' },
      { key: 'metric', label: 'Metric / source', type: 'text', placeholder: 'portfolio:pf_…:summary.totalValue' },
      { key: 'portfolioId', label: 'Portfolio id', type: 'text', placeholder: 'pf_… (with metric = field name)' },
      {
        key: 'format', label: 'Format', type: 'select',
        options: [{ value: 'number', label: 'Number' }, { value: 'percent', label: 'Percent' }, { value: 'currency', label: 'Currency' }],
      },
    ],
    render: (placement) => <MetricCardWidget placement={placement} />,
  },
  chartDef('line-chart', 'Line Chart', 'A time series over a source (e.g. market:price:AAPL).', 'line-chart', ['large', 'full'], (p) => <LineChartWidget placement={p} />),
  chartDef('area-chart', 'Area Chart', 'A filled time series over a source.', 'line-chart', ['large', 'full'], (p) => <AreaChartWidget placement={p} />),
  chartDef('bar-chart', 'Bar Chart', 'A categorical bar chart over a source.', 'bar-chart', ['large', 'full'], (p) => <BarChartWidget placement={p} />),
  chartDef('pie-chart', 'Pie Chart', 'A proportional pie over a source (e.g. portfolio:<id>:allocation).', 'pie', ['medium', 'large'], (p) => <PieChartWidget placement={p} />),
  {
    id: 'list',
    category: 'tables',
    label: 'List',
    desc: 'A compact card list over any row source.',
    icon: 'layers',
    sizes: ['medium', 'large'],
    defaultHeight: 340,
    catalogDataSources: ['any', 'portfolio'],
    configFields: [
      { key: 'source', label: 'Data source', type: 'text', placeholder: 'portfolio:pf_…:positions' },
      { key: 'portfolioId', label: 'Portfolio id', type: 'text', placeholder: 'pf_… (shorthand for positions)' },
    ],
    render: (placement) => <ListWidget placement={placement} />,
  },
  contentDef('markdown', 'Markdown', 'Rendered Markdown content (a safe subset).', 'file-text', ['medium', 'large', 'full'],
    [{ key: 'title', label: 'Title', type: 'text' }, { key: 'text', label: 'Markdown', type: 'text' }],
    (p) => <MarkdownWidget placement={p} />),
  contentDef('status-indicator', 'Status Indicator', 'A single coloured status pill.', 'heart', ['small'],
    [
      { key: 'label', label: 'Label', type: 'text' },
      {
        key: 'status', label: 'Status', type: 'select',
        options: [{ value: 'ok', label: 'OK' }, { value: 'warning', label: 'Warning' }, { value: 'error', label: 'Error' }, { value: 'unknown', label: 'Unknown' }],
      },
    ],
    (p) => <StatusIndicatorWidget placement={p} />),
  contentDef('empty-state', 'Empty State', 'A deliberate empty placeholder.', 'layers', ['small', 'medium'],
    [{ key: 'title', label: 'Title', type: 'text' }, { key: 'message', label: 'Message', type: 'text' }],
    (p) => <EmptyStateWidget placement={p} />),
  contentDef('error-state', 'Error State', 'A recoverable error placeholder.', 'activity', ['small', 'medium'],
    [{ key: 'title', label: 'Title', type: 'text' }, { key: 'message', label: 'Message', type: 'text' }],
    (p) => <ErrorStateWidget placement={p} />),
];

function chartDef(
  id: string, label: string, desc: string, icon: string,
  sizes: WidgetDefinition['sizes'], body: (p: WidgetPlacement) => React.ReactNode,
): WidgetDefinition {
  return {
    id, category: 'markets', label, desc, icon, sizes,
    defaultHeight: 320,
    catalogDataSources: ['any', 'portfolio'],
    configFields: [
      { key: 'source', label: 'Data source', type: 'text', placeholder: 'market:price:AAPL' },
      { key: 'portfolioId', label: 'Portfolio id', type: 'text', placeholder: 'pf_… (shorthand; view depends on the chart)' },
    ],
    render: body,
  };
}

function contentDef(
  id: string, label: string, desc: string, icon: string,
  sizes: WidgetDefinition['sizes'], configFields: WidgetDefinition['configFields'],
  body: (p: WidgetPlacement) => React.ReactNode,
): WidgetDefinition {
  return { id, category: 'tools', label, desc, icon, sizes, configFields, render: body };
}
