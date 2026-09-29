"use client";

// ── Run explanation (Phase 7) ───────────────────────────────────────────────
// "Why did the agent know/use this?" — a collapsed, read-only view of the run's
// memory/skill observability: which facts were injected, which were excluded and
// why, the profile/prompt-plan segments, and the bundle that expanded.
//
// Derived from canonical retrieval/run events; it changes nothing at runtime and
// redacts secret-shaped content. Loaded on demand (only when expanded).

import { useState } from "react";
import { ChevronDown, ChevronRight, Loader2, Search } from "lucide-react";
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

/** Coarse category → short, plain-English heading. */
const CATEGORY_LABELS: Record<string, string> = {
  scope: "Out of scope",
  status: "Not active",
  expiry: "Expired",
  permissions: "Not permitted",
  relevance: "Not relevant",
  budget: "Over budget",
  trust: "Low trust",
  drift: "Quarantined",
  other: "Other",
};

/** Raw exclusion reason → plain-English sentence. Falls back to the original. */
function friendlyReason(reason: string): string {
  const text = (reason || "").toLowerCase();
  if (text === "user scope not attributable") return "Personal memory, but no signed-in user to attribute it to";
  if (text === "another user's scope") return "Belongs to a different user";
  if (text === "recall denied by policy") return "Recall is turned off for this memory type";
  if (text === "proposed (needs review)") return "Suggested memory, still awaiting your review";
  if (text === "expired") return "Past its retention date";
  if (text === "low confidence, unverified") return "Low confidence and never verified";
  if (text === "no lexical relevance to query") return "Not related to this question";
  if (text === "rank limit") return "Further down the ranking than the limit allows";
  if (text === "over context budget") return "Would push the memory context over budget";
  if (text.startsWith("status=")) return `Replaced or retired (${reason.slice("status=".length)})`;
  if (text.startsWith("scope ") && text.endsWith(" not authorized")) return "Scope not authorized for this run";
  return reason || "Filtered out";
}

/** Group exclusions by category, counting identical reasons within each. */
function groupExclusions(excluded: Array<{ id: string; reason: string; category: string }>) {
  const groups = new Map<string, Map<string, number>>();
  for (const e of excluded) {
    const cat = e.category || "other";
    if (!groups.has(cat)) groups.set(cat, new Map());
    const reasons = groups.get(cat)!;
    reasons.set(e.reason, (reasons.get(e.reason) ?? 0) + 1);
  }
  return [...groups.entries()].map(([category, reasons]) => ({
    category,
    label: CATEGORY_LABELS[category] ?? category,
    total: [...reasons.values()].reduce((a, b) => a + b, 0),
    reasons: [...reasons.entries()].sort((a, b) => b[1] - a[1]),
  }));
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
  const groups = data?.memory?.excluded ? groupExclusions(data.memory.excluded) : [];

  const usedChars = data?.memory?.budget?.usedChars;
  const budgetChars = data?.memory?.budget?.budgetChars;
  const budgetPct = usedChars != null && budgetChars ? Math.min(100, Math.round((usedChars / budgetChars) * 100)) : null;

  return (
    <div className={cn("mt-1 w-full rounded-xl border border-border/20 glass-card-subtle", compact ? "p-2" : "p-2.5")}>
      <button type="button" onClick={() => void toggle()}
        className="flex w-full items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground cursor-pointer">
        {open ? <ChevronDown size={11} className="shrink-0" /> : <ChevronRight size={11} className="shrink-0" />}
        <Search size={11} className="shrink-0 text-primary" />
        What influenced this run
        {data && (
          <span className="text-muted-foreground/70">
            · {injected} {injected === 1 ? "memory" : "memories"} used{excluded > 0 ? `, ${excluded} filtered out` : ""}
          </span>
        )}
      </button>

      {open && (
        <div className="mt-2.5 space-y-3 text-[10px]">
          {loading && <p className="flex items-center gap-1.5 text-muted-foreground"><Loader2 size={10} className="animate-spin" /> Loading…</p>}
          {error && <p className="text-rose-300">{error}</p>}
          {data && (
            <>
              {/* Stat tiles — the headline numbers, at a glance. */}
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg border border-primary/15 bg-primary/[0.06] px-2.5 py-2">
                  <p className="text-[15px] font-semibold leading-none text-primary">{injected}</p>
                  <p className="mt-1 text-[9px] uppercase tracking-wide text-muted-foreground">Used in this answer</p>
                </div>
                <div className="rounded-lg border border-border/20 bg-foreground/[0.03] px-2.5 py-2">
                  <p className="text-[15px] font-semibold leading-none text-foreground/80">{excluded}</p>
                  <p className="mt-1 text-[9px] uppercase tracking-wide text-muted-foreground">Filtered out</p>
                </div>
              </div>

              {injected > 0 && (
                <div>
                  <p className="font-semibold text-foreground">Memories the agent had available</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {data.memory?.injected?.map((m) => (
                      <span key={m.id} className="rounded-md bg-primary/10 px-1.5 py-0.5 text-[9px] text-primary/90" title={m.id}>{m.id.slice(0, 18)}</span>
                    ))}
                  </div>
                </div>
              )}

              {groups.length > 0 && (
                <div>
                  <p className="font-semibold text-foreground">Why {excluded} {excluded === 1 ? "memory was" : "memories were"} filtered out</p>
                  <div className="mt-1 space-y-1.5">
                    {groups.map((g) => (
                      <div key={g.category}>
                        <p className="flex items-center gap-1.5 text-[9px] uppercase tracking-wide text-amber-300/90">
                          {g.label}
                          <span className="rounded-full bg-amber-400/10 px-1.5 text-[9px] text-amber-200/80">{g.total}</span>
                        </p>
                        <ul className="mt-0.5 space-y-0.5 text-muted-foreground">
                          {g.reasons.map(([reason, count]) => (
                            <li key={reason} className="flex items-start gap-1.5">
                              <span className="mt-[3px] h-1 w-1 shrink-0 rounded-full bg-muted-foreground/40" />
                              <span className="flex-1">{friendlyReason(reason)}</span>
                              {count > 1 && <span className="shrink-0 text-muted-foreground/60">×{count}</span>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {budgetPct != null && (
                <div>
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-foreground">Memory budget</p>
                    <p className="text-muted-foreground">
                      {(usedChars ?? 0).toLocaleString()} / {(budgetChars ?? 0).toLocaleString()} chars · {budgetPct}%
                    </p>
                  </div>
                  <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-foreground/[0.06]">
                    <div className="h-full rounded-full bg-primary/60" style={{ width: `${budgetPct}%` }} />
                  </div>
                  <p className="mt-1 text-muted-foreground/70">
                    Caps how much remembered context can enter one prompt; everything past it is filtered out.
                  </p>
                </div>
              )}

              {(data.profile || data.skills || data.promptPlan?.segments?.length) && (
                <div className="space-y-1 border-t border-border/20 pt-2">
                  <p className="font-semibold text-foreground">Also shaping the prompt</p>
                  {data.profile && (
                    <p className="text-muted-foreground">
                      Profile: {data.profile.entries ?? 0} {data.profile.entries === 1 ? "fact" : "facts"} · {(data.profile.charCount ?? 0).toLocaleString()} chars
                      {data.profile.excluded ? ` · ${data.profile.excluded} filtered` : ""}
                    </p>
                  )}
                  {data.skills && (
                    <p className="text-muted-foreground">
                      Skills: {(data.skills.resolved ?? []).join(", ") || "none resolved"}
                      {data.skills.missing?.length ? ` · missing ${data.skills.missing.join(", ")}` : ""}
                    </p>
                  )}
                  {data.promptPlan?.segments?.length ? (
                    <p className="text-muted-foreground">Prompt sections: {data.promptPlan.segments.map((s) => s.id).join(", ")}</p>
                  ) : null}
                </div>
              )}

              <p className="border-t border-border/20 pt-2 text-muted-foreground/60">
                {data.note ?? "Derived from this run's retrieval and run events; read-only."}
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
