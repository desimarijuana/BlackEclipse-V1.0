"use client";

// ── Learning Journey (Phase 6) ──────────────────────────────────────────────
// A derived, read-only timeline/graph of how skills and memories came to exist.
// Nodes and edges are projected from canonical rows — this never writes and
// never exposes secrets. Clicking a node filters the edge list to it.

import { useCallback, useEffect, useMemo, useState } from "react";
import { GitBranch, Loader2, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { learningJourney } from "@/lib/harness/skills-browser";
import type { JourneyNode, LearningJourney } from "@/lib/harness/skills-types";
import { formatWhen } from "./skill-ui";

const KIND_STYLE: Record<string, string> = {
  memory: "border-violet-400/30 bg-violet-400/10 text-violet-300",
  skill: "border-primary/30 bg-primary/10 text-primary",
  skill_version: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  learning_candidate: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  correction: "border-rose-400/30 bg-rose-400/10 text-rose-300",
  mistake: "border-orange-400/30 bg-orange-400/10 text-orange-300",
  promotion: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  session: "border-border/40 text-muted-foreground",
};

export function LearningJourneyPanel() {
  const [graph, setGraph] = useState<LearningJourney | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState("");

  const load = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    setError(null);
    try { setGraph(await learningJourney(kindFilter ? { kind: kindFilter } : {})); }
    catch (err) { setError(err instanceof Error ? err.message : "failed to load"); }
    finally { if (showSpinner) setLoading(false); }
  }, [kindFilter]);
  useEffect(() => { void load(); }, [load]);
  // Freshness: when the tab/window regains focus, silently refresh so a mutation
  // made elsewhere is reflected without a full app restart. The derived graph is
  // cheap and bounded; no second store is introduced.
  useEffect(() => {
    const onFocus = () => { void load(false); };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [load]);

  const nodeById = useMemo(() => {
    const map = new Map<string, JourneyNode>();
    graph?.nodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [graph]);

  const visibleEdges = useMemo(() => {
    if (!graph) return [];
    return selected ? graph.edges.filter((e) => e.source === selected || e.target === selected) : graph.edges;
  }, [graph, selected]);

  if (loading) return <div className="flex items-center justify-center py-16 text-muted-foreground"><Loader2 className="animate-spin mr-2" size={16} /> Loading…</div>;
  if (error) return <div className="rounded-2xl border border-rose-400/30 bg-rose-400/5 p-6 text-center text-sm text-foreground">{error}</div>;
  if (!graph) return null;

  const kinds = Object.keys(graph.stats.byKind);

  return (
    <div className="animate-fade-in-up">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h3 className="font-serif text-sm font-semibold tracking-tight text-foreground">Learning journey</h3>
          <p className="mt-1 text-[11px] text-muted-foreground max-w-2xl leading-relaxed">
            How each skill and memory came to exist — created from, corrected by, superseded by, promoted from.
            Derived from canonical records; read-only, scope-isolated, and never a second source of truth.
          </p>
          {graph.generatedAt && (
            <p className="mt-1 text-[10px] text-muted-foreground/80">
              Last updated {formatWhen(graph.generatedAt)} · refreshes when this tab regains focus
            </p>
          )}
        </div>
        <Button size="sm" variant="outline" className="rounded-xl cursor-pointer shrink-0" onClick={() => void load()}>
          <RefreshCcw size={13} className="mr-1" /> Refresh
        </Button>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Kind</span>
        <button onClick={() => setKindFilter("")} className={cn("rounded-lg px-2 py-0.5 text-[10px] font-semibold cursor-pointer", !kindFilter ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent/50")}>all</button>
        {kinds.map((k) => (
          <button key={k} onClick={() => setKindFilter(k)} className={cn("rounded-lg px-2 py-0.5 text-[10px] font-semibold cursor-pointer", kindFilter === k ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent/50")}>{k}</button>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl border border-white/10 glass-card p-4">
          <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-2">
            Nodes ({graph.stats.nodeCount}){graph.stats.truncated ? " · truncated" : ""}
          </p>
          <div className="max-h-[520px] overflow-y-auto space-y-1">
            {graph.nodes.length === 0 ? <p className="text-[11px] text-muted-foreground">Nothing learned yet.</p> : graph.nodes.map((node) => (
              <button key={node.id} onClick={() => setSelected(selected === node.id ? null : node.id)}
                className={cn("w-full text-left rounded-xl border px-2.5 py-1.5 transition-colors cursor-pointer",
                  selected === node.id ? "border-primary/40 bg-primary/5" : "border-white/10 dark:border-white/5 hover:border-primary/30")}>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className={cn("rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide", KIND_STYLE[node.kind] ?? "border-border/40 text-muted-foreground")}>{node.kind}</span>
                  <span className="text-[9px] text-muted-foreground">{node.status}</span>
                </div>
                <p className="mt-1 text-[11px] text-foreground line-clamp-1">{node.label || node.id}</p>
              </button>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-white/10 glass-card p-4">
          <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-2">
            {selected ? "Relations for selected node" : "All relations"} ({visibleEdges.length})
          </p>
          <div className="max-h-[520px] overflow-y-auto space-y-1.5">
            {visibleEdges.length === 0 ? (
              <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground"><GitBranch size={12} /> No relations.</p>
            ) : (
              visibleEdges.map((edge, i) => (
                <div key={`${edge.source}-${edge.target}-${i}`} className="text-[10px] text-muted-foreground">
                  <span className="text-foreground">{nodeById.get(edge.source)?.label || edge.source}</span>
                  <span className="mx-1 text-primary">{edge.relation}</span>
                  <span className="text-foreground">{nodeById.get(edge.target)?.label || edge.target}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
