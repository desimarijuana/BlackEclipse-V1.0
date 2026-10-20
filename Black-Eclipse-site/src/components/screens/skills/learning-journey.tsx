"use client";

// ── Learning Journey (Phase 6 / graph view) ─────────────────────────────────
// A derived, read-only graph of how skills and memories came to exist. Nodes and
// edges are projected from canonical rows — this never writes and never exposes
// secrets. The main view is a force-directed graph; selecting a node opens an
// inspector listing its relations. A full-page mode gives the force layout room.

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { GitBranch, Minimize2, RefreshCcw, X } from "@/lib/icons";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { learningJourney } from "@/lib/harness/skills-browser";
import type { JourneyNode, LearningJourney } from "@/lib/harness/skills-types";
import { formatWhen, LoadingState } from "./skill-ui";
import { FullPageButton, KIND_COLOR, LearningGraphChart } from "./learning-graph";
import { PaginationFooter, usePagination } from "@/components/ui/pagination";
import { RslExperimentsPanel } from "./rsl-experiments-panel";

const KIND_STYLE: Record<string, string> = {
  memory: "border-violet-400/30 bg-violet-400/10 text-violet-300",
  skill: "border-primary/30 bg-primary/10 text-primary",
  skill_version: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  learning_candidate: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  correction: "border-rose-400/30 bg-rose-400/10 text-rose-300",
  mistake: "border-orange-400/30 bg-orange-400/10 text-orange-300",
  promotion: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
  execution: "border-cyan-400/30 bg-cyan-400/10 text-cyan-300",
  session: "border-border/40 text-muted-foreground",
};

export function LearningJourneyPanel() {
  const [graph, setGraph] = useState<LearningJourney | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState("");
  const [expanded, setExpanded] = useState(false);

  const load = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true); else setRefreshing(true);
    setError(null);
    try { setGraph(await learningJourney(kindFilter ? { kind: kindFilter } : {})); }
    catch (err) { setError(err instanceof Error ? err.message : "failed to load"); }
    finally { if (showSpinner) setLoading(false); else setRefreshing(false); }
  }, [kindFilter]);
  useEffect(() => { void load(); }, [load]);
  // Freshness: when the tab/window regains focus, silently refresh so a mutation
  // made elsewhere is reflected without a full app restart.
  useEffect(() => {
    const onFocus = () => { void load(false); };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [load]);

  // Esc closes the full-page graph and page scroll is locked while it is open.
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setExpanded(false); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [expanded]);

  const nodeById = useMemo(() => {
    const map = new Map<string, JourneyNode>();
    graph?.nodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [graph]);

  const selectedNode = selected ? nodeById.get(selected) ?? null : null;

  const visibleEdges = useMemo(() => {
    if (!graph) return [];
    return selected ? graph.edges.filter((e) => e.source === selected || e.target === selected) : graph.edges;
  }, [graph, selected]);

  const relationPager = usePagination(visibleEdges, 25);

  const kinds = useMemo(() => Object.keys(graph?.stats.byKind ?? {}), [graph]);

  if (loading) {
    return <LoadingState label="Loading the learning journey…" hint="First load can start the Python runtime." />;
  }
  if (error) return <div className="rounded-2xl border border-rose-400/30 bg-rose-400/5 p-6 text-center text-sm text-foreground">{error}</div>;
  if (!graph) return null;

  const hasGraph = graph.nodes.length > 0;

  const graphBlock = (fullPage: boolean) => (
    <LearningGraphChart
      graph={graph}
      onSelect={(node) => setSelected(node ? node.id : null)}
      highlightKind={kindFilter || undefined}
      selectedId={selected}
      className={fullPage ? "h-full w-full" : "h-[520px] w-full"}
    />
  );

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
              Last updated {formatWhen(graph.generatedAt)}
              {graph.watermark && graph.watermark !== graph.generatedAt && (
                <> · newest record {formatWhen(graph.watermark)}</>
              )}
              {refreshing ? " · refreshing…" : " · refreshes on focus"}
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {hasGraph && <FullPageButton onClick={() => setExpanded(true)} />}
          <Button size="sm" variant="outline" className="rounded-xl cursor-pointer" disabled={refreshing} onClick={() => void load()}>
            <RefreshCcw size={13} className={"mr-1" + (refreshing ? " animate-spin" : "")} /> Refresh
          </Button>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Kind</span>
        <button onClick={() => setKindFilter("")} className={cn("rounded-lg px-2 py-0.5 text-[10px] font-semibold cursor-pointer", !kindFilter ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent/50")}>all</button>
        {kinds.map((k) => (
          <button key={k} onClick={() => setKindFilter(kindFilter === k ? "" : k)}
            className={cn("inline-flex items-center gap-1.5 rounded-lg px-2 py-0.5 text-[10px] font-semibold cursor-pointer", kindFilter === k ? "bg-primary/15 text-primary" : "text-muted-foreground hover:bg-accent/50")}>
            <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: KIND_COLOR[k] ?? "#94a3b8" }} />
            {k}
          </button>
        ))}
      </div>

      {!hasGraph ? (
        <div className="rounded-2xl border border-border/20 glass-card-subtle p-10 text-center">
          <GitBranch size={26} className="mx-auto text-muted-foreground/60" />
          <p className="mt-3 text-sm font-semibold text-foreground">Nothing learned yet</p>
          <p className="mt-1 text-[11px] text-muted-foreground max-w-sm mx-auto">
            The journey grows as memories are saved, skills are drafted, evaluated and promoted.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1.7fr_1fr]">
          <div className="rounded-2xl border border-white/10 glass-card p-2">
            {graphBlock(false)}
            <div className="flex flex-wrap items-center gap-3 px-2 pb-1 pt-2 text-[9px] text-muted-foreground/70">
              <span>{graph.stats.nodeCount} nodes · {graph.stats.edgeCount} edges{graph.stats.truncated ? " · truncated" : ""}</span>
              <span className="italic">Drag to rearrange · scroll to zoom · click a node for its relations</span>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 glass-card p-4">
            {selectedNode ? (
              <>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className={cn("rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide", KIND_STYLE[selectedNode.kind] ?? "border-border/40 text-muted-foreground")}>{selectedNode.kind}</span>
                  <button onClick={() => setSelected(null)} className="rounded-md p-0.5 text-muted-foreground hover:text-foreground cursor-pointer" title="Clear selection">
                    <X size={12} />
                  </button>
                </div>
                <p className="text-[12px] font-semibold text-foreground break-words">{selectedNode.label || selectedNode.id}</p>
                <dl className="mt-2 space-y-1">
                  <Meta label="status" value={selectedNode.status} />
                  {selectedNode.scope ? <Meta label="scope" value={String(selectedNode.scope)} /> : null}
                  {selectedNode.createdAt ? <Meta label="created" value={formatWhen(selectedNode.createdAt)} /> : null}
                  <Meta label="relations" value={String(visibleEdges.length)} />
                </dl>
                <p className="mt-3 mb-1 text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Relations</p>
                <div className="max-h-[300px] overflow-y-auto space-y-1.5">
                  {visibleEdges.length === 0 ? (
                    <p className="text-[10px] text-muted-foreground">No relations.</p>
                  ) : relationPager.pageItems.map((edge, i) => {
                    const isSource = edge.source === selected;
                    const otherId = isSource ? edge.target : edge.source;
                    return (
                      <button key={`${edge.source}-${edge.target}-${i}`} onClick={() => setSelected(otherId)}
                        className="block w-full text-left text-[10px] text-muted-foreground hover:text-foreground cursor-pointer">
                        <span className="text-primary">{isSource ? edge.relation : `← ${edge.relation}`}</span>{" "}
                        <span className="text-foreground">{nodeById.get(otherId)?.label || otherId}</span>
                      </button>
                    );
                  })}
                </div>
                <PaginationFooter pagination={relationPager} label="relations" />
              </>
            ) : (
              <>
                <p className="text-[10px] uppercase tracking-widest font-bold text-muted-foreground mb-2">
                  All relations ({visibleEdges.length})
                </p>
                <div className="max-h-[520px] overflow-y-auto space-y-1.5">
                  {visibleEdges.length === 0 ? (
                    <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground"><GitBranch size={12} /> No relations.</p>
                  ) : relationPager.pageItems.map((edge, i) => (
                    <div key={`${edge.source}-${edge.target}-${i}`} className="text-[10px] text-muted-foreground">
                      <span className="text-foreground">{nodeById.get(edge.source)?.label || edge.source}</span>
                      <span className="mx-1 text-primary">{edge.relation}</span>
                      <span className="text-foreground">{nodeById.get(edge.target)?.label || edge.target}</span>
                    </div>
                  ))}
                </div>
                <PaginationFooter pagination={relationPager} label="relations" />
              </>
            )}
          </div>
        </div>
      )}

      <RslExperimentsPanel />

      {/* Full-page graph — portaled to <body> so a transformed ancestor cannot
          trap the fixed overlay. */}
      {expanded && hasGraph && typeof document !== "undefined" && createPortal(
        <div className="fixed inset-0 z-[86] flex flex-col bg-background">
          <div className="flex items-center gap-2 border-b border-border/10 px-4 py-2.5">
            <span className="text-[10px] font-bold uppercase tracking-widest text-foreground">Learning journey</span>
            <span className="font-mono text-[9px] text-muted-foreground">
              {graph.stats.nodeCount} nodes · {graph.stats.edgeCount} edges{graph.stats.truncated ? " · truncated" : ""}
            </span>
            <div className="ml-auto flex items-center gap-1.5">
              <span className="hidden flex-wrap items-center gap-2 lg:flex">
                {kinds.map((k) => (
                  <span key={k} className="inline-flex items-center gap-1 text-[9px] font-mono text-muted-foreground">
                    <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: KIND_COLOR[k] ?? "#94a3b8" }} />
                    {k} · {graph.stats.byKind[k]}
                  </span>
                ))}
              </span>
              <button onClick={() => setExpanded(false)} className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-semibold text-muted-foreground hover:text-foreground cursor-pointer" title="Exit full page (Esc)">
                <Minimize2 size={11} /> Exit
                <kbd className="ml-0.5 rounded bg-white/[0.06] px-1 py-0.5 font-mono text-[9px]">Esc</kbd>
              </button>
              <button onClick={() => setExpanded(false)} className="rounded-lg p-1.5 text-muted-foreground hover:text-rose-400 cursor-pointer" aria-label="Close full-page graph">
                <X size={15} />
              </button>
            </div>
          </div>
          <div className="min-h-0 flex-1 p-3">{graphBlock(true)}</div>
          <div className="border-t border-border/10 px-4 py-2 text-[9px] italic text-muted-foreground/60">
            Drag to rearrange, scroll to zoom. Click a node to see its relations.
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-0.5 border-b border-border/10 last:border-0">
      <dt className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground shrink-0">{label}</dt>
      <dd className="text-[10px] text-foreground text-right break-words min-w-0">{value}</dd>
    </div>
  );
}
