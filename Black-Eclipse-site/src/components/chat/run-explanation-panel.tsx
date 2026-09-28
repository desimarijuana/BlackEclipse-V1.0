"use client";

// ── Run explanation (Phase 7) ───────────────────────────────────────────────
// "Why did the agent know/use this?" — a collapsed, read-only view of the run's
// memory/skill observability: which facts were injected, which were excluded and
// why, the profile/prompt-plan segments, and the bundle that expanded.
//
// Derived from canonical retrieval/run events; it changes nothing at runtime and
// redacts secret-shaped content. Loaded on demand (only when expanded).

import { useState } from "react";
import { ChevronDown, ChevronRight, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

interface Explanation {
  memory?: {
    injected?: Array<{ id: string }>;
    excluded?: Array<{ id: string; reason: string; category: string }>;
    budget?: { usedChars?: number; budgetChars?: number };
    selectionReasons?: string[];
  };
  profile?: { snapshotId?: string; entries?: number; charCount?: number; tokenEstimate?: number; excluded?: number } | null;
  promptPlan?: { cacheKey?: string; reusableTokens?: number; segments?: Array<{ id: string; source: string; chars?: number; tokenEstimate?: number }> } | null;
  skills?: { bundleId?: string; resolved?: string[]; missing?: string[]; unavailable?: string[]; provenance?: string } | null;
  note?: string;
}

export function RunExplanationPanel({ runId, compact = false }: { runId: string; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Explanation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && data === null && !loading) {
      setLoading(true); setError(null);
      try {
        const res = await fetch(`/api/harness/runs/${encodeURIComponent(runId)}/explain`);
        if (!res.ok) throw new Error(`explanation unavailable (${res.status})`);
        setData((await res.json()) as Explanation);
      } catch (err) {
        setError(err instanceof Error ? err.message : "failed to load");
      } finally { setLoading(false); }
    }
  };

  const injected = data?.memory?.injected?.length ?? 0;
  const excluded = data?.memory?.excluded?.length ?? 0;

  return (
    <div className={cn("mt-1 rounded-xl border border-border/20 glass-card-subtle", compact ? "p-2" : "p-2.5")}>
      <button type="button" onClick={() => void toggle()}
        className="flex w-full items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground cursor-pointer">
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <Sparkles size={11} className="text-primary" />
        What influenced this run
        {data && <span className="text-muted-foreground/70">· {injected} facts · {excluded} excluded</span>}
      </button>

      {open && (
        <div className="mt-2 space-y-2 text-[10px]">
          {loading && <p className="flex items-center gap-1.5 text-muted-foreground"><Loader2 size={10} className="animate-spin" /> Loading…</p>}
          {error && <p className="text-rose-300">{error}</p>}
          {data && (
            <>
              {injected > 0 && (
                <div>
                  <p className="font-semibold text-foreground">Facts injected ({injected})</p>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {data.memory?.injected?.map((m) => (
                      <span key={m.id} className="rounded-md bg-primary/10 px-1.5 py-0.5 text-[9px] text-primary/90">{m.id.slice(0, 18)}</span>
                    ))}
                  </div>
                </div>
              )}
              {excluded > 0 && (
                <div>
                  <p className="font-semibold text-foreground">Excluded ({excluded})</p>
                  <ul className="mt-0.5 space-y-0.5">
                    {data.memory?.excluded?.slice(0, 8).map((e, i) => (
                      <li key={`${e.id}-${i}`} className="text-muted-foreground">
                        <span className="text-amber-300/90">{e.category}</span>: {e.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {data.memory?.budget && (
                <p className="text-muted-foreground">Budget: {data.memory.budget.usedChars ?? "?"}/{data.memory.budget.budgetChars ?? "?"} chars</p>
              )}
              {data.profile && (
                <p className="text-muted-foreground">Profile: {data.profile.entries ?? 0} entries · {data.profile.charCount ?? 0} chars{data.profile.excluded ? ` · ${data.profile.excluded} excluded` : ""}</p>
              )}
              {data.skills && (
                <p className="text-muted-foreground">
                  Bundle: {data.skills.bundleId ?? "—"} → {(data.skills.resolved ?? []).join(", ") || "none"}
                  {data.skills.missing?.length ? ` · missing ${data.skills.missing.join(", ")}` : ""}
                </p>
              )}
              {data.promptPlan?.segments?.length ? (
                <p className="text-muted-foreground">Prompt segments: {data.promptPlan.segments.map((s) => s.id).join(", ")}</p>
              ) : null}
              {data.note && <p className="text-muted-foreground/70">{data.note}</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
