"use client";

// ── Learning Journey — force-directed graph ─────────────────────────────────
// Renders the derived learning journey (nodes + edges from `learning_graph.py`)
// with ECharts `graph` (force layout). It is a READ-ONLY projection of canonical
// records: no writes, no second store.
//
// Node colour encodes the node `kind`; edge colour encodes the `relation`. Node
// size grows with degree so the most-connected records stand out. Clicking a
// node reports it upward so the screen can show its relations in an inspector.
//
// Modelled on the proven `investor-eye/graph-panel.tsx` (same ECharts instance
// contract, ResizeObserver, full-page expand), so there is one graph idiom in
// the app rather than several.

import { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts";
import { Maximize2 } from "@/lib/icons";
import type { JourneyEdge, JourneyNode, LearningJourney } from "@/lib/harness/skills-types";

// Node kind → colour. Mirrors the badge palette used in the list view.
export const KIND_COLOR: Record<string, string> = {
  memory: "#a78bfa",
  skill: "#34d399",
  skill_version: "#38bdf8",
  learning_candidate: "#fbbf24",
  correction: "#fb7185",
  mistake: "#fb923c",
  promotion: "#34d399",
  execution: "#22d3ee",
  session: "#94a3b8",
};

// Relation → colour (fixed vocabulary from the backend).
export const RELATION_COLOR: Record<string, string> = {
  created_from: "#60a5fa",
  corrected_by: "#fb7185",
  superseded_by: "#a78bfa",
  used_in: "#22d3ee",
  derived_from: "#34d399",
  promoted_from: "#fbbf24",
  evaluated_by: "#38bdf8",
  related_to: "#94a3b8",
};

function kindColor(kind: string): string {
  return KIND_COLOR[kind] ?? "#94a3b8";
}

function relationColor(relation: string): string {
  return RELATION_COLOR[relation] ?? "#94a3b8";
}

function degrees(graph: LearningJourney): Map<string, number> {
  const degree = new Map<string, number>();
  for (const edge of graph.edges) {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  }
  return degree;
}

/**
 * The chart itself at whatever size its container is. Owns its own ECharts
 * instance so the inline and full-page views are the same code at two sizes.
 */
export function LearningGraphChart({
  graph,
  onSelect,
  highlightKind,
  selectedId,
  className,
}: {
  graph: LearningJourney;
  onSelect?: (node: JourneyNode | null) => void;
  highlightKind?: string;
  selectedId?: string | null;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;

  const degree = useMemo(() => degrees(graph), [graph]);

  useEffect(() => {
    if (!ref.current || graph.nodes.length === 0) return;
    const chart = chartRef.current ?? echarts.init(ref.current, undefined, { renderer: "canvas" });
    chartRef.current = chart;

    const option: echarts.EChartsOption = {
      backgroundColor: "transparent",
      tooltip: {
        backgroundColor: "rgba(18,18,20,0.5)",
        borderColor: "rgba(255,255,255,0.12)",
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: "#e5e7eb", fontSize: 11 },
        appendTo: "body",
        extraCssText:
          "backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; " +
          "box-shadow: 0 8px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);",
        formatter: (params: unknown) => {
          const p = params as { dataType?: string; data?: { _node?: JourneyNode; _edge?: JourneyEdge } };
          if (p.dataType === "edge" && p.data?._edge) {
            return `<span style="color:#9ca3af">${p.data._edge.relation}</span>`;
          }
          const n = p.data?._node;
          if (!n) return "";
          return `<b>${escapeHtml(n.label || n.id)}</b><br/><span style="color:#9ca3af">${n.kind} · ${n.status}</span>`;
        },
      },
      series: [
        {
          type: "graph",
          layout: "force",
          roam: true,
          draggable: true,
          // Bounded force settings so a large graph stays responsive.
          force: { repulsion: 130, edgeLength: [50, 140], gravity: 0.08, friction: 0.2 },
          label: {
            show: graph.nodes.length <= 60,
            position: "right",
            color: "#9ca3af",
            fontSize: 9,
            formatter: "{b}",
          },
          emphasis: { focus: "adjacency", label: { show: true, color: "#e5e7eb", fontSize: 10 } },
          lineStyle: { opacity: 0.5, curveness: 0.05 },
          data: graph.nodes.map((n) => {
            const deg = degree.get(n.id) ?? 0;
            const dimmed = highlightKind && n.kind !== highlightKind;
            return {
              id: n.id,
              name: n.label && n.label.length > 24 ? `${n.label.slice(0, 24)}…` : (n.label || n.id),
              symbolSize: Math.min(30, 6 + Math.sqrt(deg) * 4),
              itemStyle: {
                color: kindColor(n.kind),
                opacity: dimmed ? 0.18 : 1,
                borderColor: selectedId === n.id ? "#ffffff" : "transparent",
                borderWidth: selectedId === n.id ? 2 : 0,
              },
              _node: n,
            };
          }) as never,
          links: graph.edges.map((e) => ({
            source: e.source,
            target: e.target,
            lineStyle: {
              color: relationColor(e.relation),
              width: 0.8,
              opacity: highlightKind ? 0.15 : 0.5,
            },
            _edge: e,
          })) as never,
        },
      ],
    };
    chart.setOption(option, { notMerge: true });

    chart.off("click");
    chart.on("click", (params: unknown) => {
      const p = params as { dataType?: string; data?: { _node?: JourneyNode } };
      if (p.dataType === "edge") return;
      selectRef.current?.(p.data?._node ?? null);
    });

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [graph, degree, highlightKind, selectedId]);

  // Dispose on unmount (the component is mounted/unmounted when the graph
  // switches between inline and full-page mode).
  useEffect(() => () => { chartRef.current?.dispose(); chartRef.current = null; }, []);

  return <div ref={ref} className={className} />;
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string)
  );
}

/** Full-page toggle button for the panel header. */
export function FullPageButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px] font-semibold text-muted-foreground hover:text-foreground cursor-pointer"
      title="Open the graph full page (Esc to exit)"
    >
      <Maximize2 size={11} /> Full page
    </button>
  );
}
