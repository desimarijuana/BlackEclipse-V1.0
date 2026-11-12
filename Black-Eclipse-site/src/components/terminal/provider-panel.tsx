"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "@/lib/icons";
import {
  providerReadiness,
  workspaceGraph,
  type ProviderReadiness,
  type WorkspaceGraph,
} from "@/lib/harness/clients/application-browser";
import { cn } from "@/lib/utils";

/** The provider readiness + workspace graph view.
 *
 *  Shows, without a secret value, which orchestration/infra/cloud tools are
 *  installed AND signed in, with a plain next step per gap. Also shows the
 *  cross-application dependency graph (a monorepo's startup order). Read-only. */
export function ProviderReadinessPanel() {
  const [readiness, setReadiness] = useState<ProviderReadiness | null>(null);
  const [graph, setGraph] = useState<WorkspaceGraph | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const [r, g] = await Promise.all([providerReadiness(), workspaceGraph()]);
      setReadiness(r);
      setGraph(g);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "provider status failed");
    }
  };

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="flex h-full flex-col text-[11px]">
      <div className="mb-1 flex items-center justify-between uppercase tracking-wide text-muted-foreground">
        <span>Providers</span>
        <button type="button" onClick={() => void refresh()} aria-label="Refresh providers" className="hover:text-foreground">
          <RefreshCw size={12} />
        </button>
      </div>
      {error ? <div className="mb-1 text-rose-300">{error}</div> : null}

      {readiness ? (
        <div className="mb-2">
          <div className={cn("mb-1", readiness.ready ? "text-emerald-300" : "text-amber-300")}>
            {readiness.ready ? "Ready" : "Some tools are missing or not signed in"}
          </div>
          <div className="flex flex-col gap-0.5">
            {readiness.providers.map((p) => (
              <div key={p.name} className="flex items-center gap-2">
                <span className={cn("w-2 shrink-0", p.installed ? (p.authenticated === false ? "text-amber-300" : "text-emerald-300") : "text-zinc-500")}>
                  {p.installed ? (p.authenticated === false ? "!" : "●") : "○"}
                </span>
                <span className="w-24 shrink-0 truncate text-zinc-200">{p.name}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {p.installed ? (p.authenticated === false ? "not signed in" : p.version || "installed") : "not installed"}
                </span>
              </div>
            ))}
          </div>
          {readiness.hints.length ? (
            <div className="mt-1 text-[10px] text-muted-foreground">
              {readiness.hints.slice(0, 4).map((hint) => (
                <div key={hint}>- {hint}</div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {graph && graph.nodes.length > 1 ? (
        <div className="mt-auto border-t border-white/5 pt-1.5">
          <span className="uppercase tracking-wide text-muted-foreground">Applications</span>
          <div className="mt-0.5 flex flex-col gap-0.5">
            {graph.nodes.map((node) => (
              <div key={node.id} className="flex items-center gap-2">
                <span className="w-24 shrink-0 truncate text-zinc-200">{node.name}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {node.framework || "project"}
                  {node.dependsOn.length ? ` · needs ${node.dependsOn.join(", ")}` : ""}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-0.5 text-[10px] text-muted-foreground">
            starts: {graph.startupOrder.join(" → ")}
            {graph.hasCycle ? " (a cycle was found and broken)" : ""}
          </div>
        </div>
      ) : null}
    </div>
  );
}
