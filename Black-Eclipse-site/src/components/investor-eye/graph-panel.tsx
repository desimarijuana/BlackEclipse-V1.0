'use client';

// ── Investor Eye — Relationship Graph panel (Phase 2.10, spec §41) ───────────
// Renders the stored relationship graph with ECharts `graph` (force layout).
// Relational, not a graph database (ADR-011) — the pure `graph.ts` builder has
// already turned edges into nodes/links before this component sees them.
//
// Edge colour encodes the relation class, so an INFERRED link is visibly
// different from an OBSERVED one. A country node click pivots back to the map.

import { useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts';
import { useTopic } from '@/lib/workspace/data-hub';
import { IE_GRAPH_TOPIC } from '@/lib/investor-eye/topics';
import type { GraphLink, GraphNode, RelationshipGraph, RelationClass } from '@/lib/investor-eye/types';
import { cn } from '@/lib/utils';

const CLASS_COLOR: Record<RelationClass, string> = {
  OBSERVED: '#34d399',
  HISTORICAL: '#a78bfa',
  INFERRED: '#fbbf24',
  'AI-INTERPRETED': '#e879f9',
};

const KIND_COLOR: Record<string, string> = {
  country: '#60a5fa',
  company: '#38bdf8',
  commodity: '#fbbf24',
  sector: '#a78bfa',
  market: '#34d399',
  event: '#f87171',
  security: '#f472b6',
};

export function GraphPanel({ onSelectCountry }: { onSelectCountry?: (iso2: string) => void }) {
  const topic = useTopic<RelationshipGraph>(IE_GRAPH_TOPIC);
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const graph = topic.data;

  const stats = useMemo(() => {
    if (!graph) return null;
    const byClass = new Map<RelationClass, number>();
    for (const l of graph.links) byClass.set(l.relationClass, (byClass.get(l.relationClass) ?? 0) + 1);
    const byKind = new Map<string, number>();
    for (const n of graph.nodes) byKind.set(n.kind, (byKind.get(n.kind) ?? 0) + 1);
    return { byClass: [...byClass.entries()].sort((a, b) => b[1] - a[1]), byKind: [...byKind.entries()].sort((a, b) => b[1] - a[1]) };
  }, [graph]);

  // Stable click bridge so the handler never goes stale.
  const selectRef = useRef(onSelectCountry);
  selectRef.current = onSelectCountry;

  useEffect(() => {
    if (!ref.current || !graph || graph.nodes.length === 0) return;
    const chart = chartRef.current ?? echarts.init(ref.current, undefined, { renderer: 'canvas' });
    chartRef.current = chart;

    const option: echarts.EChartsOption = {
      backgroundColor: 'transparent',
      tooltip: {
        backgroundColor: 'rgba(18,18,20,0.5)',
        borderColor: 'rgba(255,255,255,0.12)',
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: '#e5e7eb', fontSize: 11 },
        appendTo: 'body',
        extraCssText:
          'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; ' +
          'box-shadow: 0 8px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);',
        // Node labels are hidden at density, so the tooltip carries the full
        // name, kind and degree.
        formatter: (params: unknown) => {
          const p = params as { dataType?: string; data?: { _node?: GraphNode; _link?: GraphLink } };
          if (p.dataType === 'edge' && p.data?._link) {
            const l = p.data._link;
            return `${l.relations.join(' / ')} <span style="color:#9ca3af">(${l.relationClass.toLowerCase()})</span>`;
          }
          const n = p.data?._node;
          if (!n) return '';
          return `<b>${n.name}</b><br/><span style="color:#9ca3af">${n.kind} · degree ${n.degree}</span>`;
        },
      },
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          // Bounded force settings: the graph must stay responsive.
          force: { repulsion: 120, edgeLength: [40, 120], gravity: 0.08, friction: 0.2 },
          // Labels only for the most-connected nodes at normal density; above
          // that they overlap into noise, so they appear on hover instead.
          label: {
            show: graph.nodes.length <= 40,
            position: 'right',
            color: '#9ca3af',
            fontSize: 9,
            // Only the name — the default formatter would append node values.
            formatter: '{b}',
          },
          emphasis: {
            focus: 'adjacency',
            label: { show: true, color: '#e5e7eb', fontSize: 10 },
          },
          lineStyle: { opacity: 0.5, curveness: 0.05 },
          data: graph.nodes.map((n: GraphNode) => ({
            id: n.id,
            // Truncate so a long company name cannot dominate the chart.
            name: n.name.length > 22 ? `${n.name.slice(0, 22)}…` : n.name,
            symbolSize: Math.min(28, 5 + Math.sqrt(n.degree) * 4),
            itemStyle: { color: KIND_COLOR[n.kind] ?? '#94a3b8' },
            // Keep the payload so clicks can pivot to the map.
            _node: n,
          })) as never,
          links: graph.links.map((l: GraphLink) => ({
            source: l.source,
            target: l.target,
            lineStyle: { color: CLASS_COLOR[l.relationClass], width: Math.min(3, 0.6 + l.weight) },
            _link: l,
          })) as never,
        },
      ],
    };
    chart.setOption(option);

    chart.off('click');
    chart.on('click', (params: unknown) => {
      const p = params as { dataType?: string; data?: { _node?: GraphNode } };
      const node = p.data?._node;
      if (node?.kind === 'country' && node.iso2) selectRef.current?.(node.iso2);
    });

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [graph]);

  useEffect(() => () => { chartRef.current?.dispose(); chartRef.current = null; }, []);

  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5 px-3 py-2.5">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
          Relationship Graph
        </span>
        {graph && (
          <span className="text-[9px] font-mono text-muted-foreground/60">
            {graph.nodes.length}n · {graph.links.length}e
          </span>
        )}
      </div>

      {topic.source === 'UNAVAILABLE' && (
        <div className="text-[10px] italic text-muted-foreground/70">Graph unavailable.</div>
      )}

      {topic.source !== 'UNAVAILABLE' && graph && graph.nodes.length === 0 && (
        <div className="text-[10px] italic text-muted-foreground/70">
          No relationships derived yet — they are built from ingested events.
        </div>
      )}

      {graph && graph.nodes.length > 0 && (
        <>
          <div ref={ref} className="h-56 w-full" />
          <div className="mt-1.5 flex flex-wrap gap-1">
            {stats?.byKind.map(([kind, count]) => (
              <span key={kind} className="glass-card-subtle rounded border border-white/10 px-1.5 py-0.5 text-[9px] font-mono text-muted-foreground">
                <span
                  className="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle"
                  style={{ backgroundColor: KIND_COLOR[kind] ?? '#94a3b8' }}
                />
                {kind} · {count}
              </span>
            ))}
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {stats?.byClass.map(([cls, count]) => (
              <span key={cls} className={cn('rounded border px-1.5 py-0.5 text-[9px] font-mono')} style={{ borderColor: `${CLASS_COLOR[cls]}55`, color: CLASS_COLOR[cls] }}>
                {cls.toLowerCase()} · {count}
              </span>
            ))}
          </div>
          {graph.totals.truncated && (
            <div className="mt-1 text-[9px] italic text-muted-foreground/60">
              Showing the {graph.nodes.length} most-connected of {graph.totals.nodes} nodes.
            </div>
          )}
          <div className="mt-1 text-[9px] italic text-muted-foreground/60">
            Edges are co-mentions in real source records unless marked otherwise. Click a country to
            pivot the map.
          </div>
        </>
      )}
    </div>
  );
}
