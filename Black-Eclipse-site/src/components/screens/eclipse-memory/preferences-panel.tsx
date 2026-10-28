"use client";

// Personal Memory → Preferences. Kept as its own panel so the Eclipse Memory
// control-room shell stays under the source-size ratchet. The server owns all
// authority; this component only renders the read model and posts operator
// actions.

import { useCallback, useEffect, useState } from "react";
import { Brain, Database, Loader2, Sparkles, Trash2 } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import {
  archiveMemory, acceptSuggestion, dismissSuggestion, learnPreferences,
  memoryPreferences,
} from "@/lib/harness/eclipse-memory-browser";
import type { PreferenceSummary } from "@/lib/harness/eclipse-memory-types";
import {
  EmptyBox, ErrorBox, Header, Muted, OriginBadge, Section, Spinner, TypeBadge,
} from "./memory-ui";

const DIMENSION_LABELS: Record<string, string> = {
  answer_format: "Answer format",
  answer_length: "Answer length",
  tone: "Tone",
  research_depth: "Research depth",
};

function dimensionLabel(dimension: string | null | undefined): string {
  if (!dimension) return "preference";
  return DIMENSION_LABELS[dimension] ?? dimension.replace(/_/g, " ");
}

function confidenceLabel(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

function evidenceOf(suggestion: { structuredData?: Record<string, unknown> | null }): Record<string, unknown> {
  return (suggestion.structuredData ?? {}) as Record<string, unknown>;
}

export function Preferences({ isOperator }: { isOperator: boolean }) {
  const [summary, setSummary] = useState<PreferenceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setSummary(await memoryPreferences()); }
    catch (err) { setError(err instanceof Error ? err.message : "failed to load preferences"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try { await fn(); setToast(message); await load(); }
    catch (err) { setToast(err instanceof Error ? err.message : "action failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 4500); }
  };

  const scan = async () => {
    setBusy(true);
    try {
      const result = await learnPreferences();
      const created = result.created?.length ?? 0;
      setToast(created > 0
        ? `Found ${created} new preference ${created === 1 ? "inference" : "inferences"}.`
        : "No new evidence crossed the threshold yet.");
      await load();
    } catch (err) { setToast(err instanceof Error ? err.message : "scan failed"); }
    finally { setBusy(false); setTimeout(() => setToast(null), 5000); }
  };

  if (loading) return <Spinner />;
  if (error) return <ErrorBox message={error} />;
  if (!summary) return <EmptyBox title="Preferences unavailable" hint="The memory runtime did not return a read model." />;

  const pending = summary.suggestions;
  const active = summary.active;
  const observations = summary.observations;
  const thresholds = summary.thresholds;

  return (
    <div className="animate-fade-in-up">
      <Header
        title="Personal Preferences"
        hint="Learned from repeated behaviour across sessions, never from a single request. An inference is inert until you accept it. Dismissing one suppresses it; explicit preferences always win."
      />

      <div className="mb-3 grid grid-cols-2 gap-2 md:grid-cols-4">
        {[
          { label: "Learning mode", value: summary.mode },
          { label: "Observations", value: String(summary.observationCount) },
          { label: "Pending", value: String(pending.length) },
          { label: "Remembered", value: String(active.length) },
        ].map((item) => (
          <div key={item.label} className="rounded-2xl border border-white/10 glass-card p-3">
            <p className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{item.label}</p>
            <p className="mt-1 text-[15px] font-semibold capitalize text-foreground">{item.value}</p>
          </div>
        ))}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 glass-card p-3">
        <p className="text-[10px] text-muted-foreground">
          Proposes at {thresholds.minObservations} observations across {thresholds.minDistinctRuns} runs,
          {" "}{Math.round(thresholds.minConsistency * 100)}% consistency, {Math.round(thresholds.confidence * 100)}% confidence.
          Dismissals cool off for {thresholds.suppressionDays} days.
        </p>
        <div className="ml-auto flex gap-2">
          <Button size="sm" variant="outline" className="cursor-pointer rounded-xl" onClick={() => void load()} disabled={busy}>
            Refresh
          </Button>
          <Button size="sm" className="cursor-pointer rounded-xl" onClick={() => void scan()} disabled={!isOperator || busy}>
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
            Scan evidence
          </Button>
        </div>
      </div>

      {toast && <p className="mb-3 text-[11px] text-primary">{toast}</p>}

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Section title={`Pending inferences (${pending.length})`} icon={Sparkles}>
          {pending.length === 0 ? (
            <EmptyBox
              title="Nothing to confirm"
              hint="A preference is proposed only after the same signal repeats across several runs. Keep working normally; evidence accumulates in the background."
            />
          ) : (
            <div className="space-y-2">
              {pending.map((suggestion) => {
                const evidence = evidenceOf(suggestion);
                const dimension = String(evidence.dimension ?? suggestion.subject ?? "");
                const runs = Number(evidence.distinctRuns ?? 0);
                const count = Number(evidence.observationCount ?? 0);
                return (
                  <div key={suggestion.id} className="rounded-2xl border border-primary/20 bg-primary/[0.04] p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <TypeBadge type="preference" />
                          <span className="text-[10px] font-semibold text-primary">{dimensionLabel(dimension)}</span>
                          <span className="text-[9px] text-muted-foreground">{confidenceLabel(suggestion.confidence)} confidence</span>
                        </div>
                        <p className="mt-1.5 text-[12px] text-foreground/95">{suggestion.content}</p>
                        {suggestion.reason && <p className="mt-1 text-[10px] text-muted-foreground">{suggestion.reason}</p>}
                        <div className="mt-2 flex flex-wrap gap-1.5 text-[9px] text-muted-foreground">
                          <span className="rounded-full border border-border/30 px-2 py-0.5">{runs} runs</span>
                          <span className="rounded-full border border-border/30 px-2 py-0.5">{count} observations</span>
                          {typeof evidence.evidenceText === "string" && evidence.evidenceText ? (
                            <span className="max-w-[220px] truncate rounded-full border border-border/30 px-2 py-0.5">
                              “{evidence.evidenceText}”
                            </span>
                          ) : null}
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-col gap-1.5">
                        <Button
                          size="sm" className="cursor-pointer rounded-xl" disabled={!isOperator || busy}
                          onClick={() => void act(() => acceptSuggestion(suggestion.id), "Preference remembered")}
                        >
                          Remember
                        </Button>
                        <Button
                          size="sm" variant="outline" className="cursor-pointer rounded-xl" disabled={!isOperator || busy}
                          onClick={() => void act(() => dismissSuggestion(suggestion.id), "Inference dismissed")}
                        >
                          Dismiss
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Section>

        <Section title={`Remembered preferences (${active.length})`} icon={Brain}>
          {active.length === 0 ? (
            <EmptyBox title="No learned preferences yet" hint="Accepted inferences and explicitly stated preferences appear here and are injected into future runs." />
          ) : (
            <div className="space-y-2">
              {active.map((memory) => {
                const structured = (memory.structuredData ?? {}) as Record<string, unknown>;
                const dimension = String(structured.dimension ?? memory.subject ?? "");
                return (
                  <div key={memory.id} className="rounded-2xl border border-border/20 bg-background/30 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <TypeBadge type={memory.memoryType} />
                          <span className="text-[10px] font-semibold text-foreground/80">{dimensionLabel(dimension)}</span>
                          <span className="text-[9px] text-muted-foreground">{confidenceLabel(memory.confidence)}</span>
                          <OriginBadge memory={memory} />
                        </div>
                        <p className="mt-1.5 text-[12px] text-foreground/95">{memory.content}</p>
                        <p className="mt-1 text-[9px] text-muted-foreground">
                          {memory.scope}{memory.scopeId ? `:${memory.scopeId}` : ""} · confirmed {String(memory.lastConfirmedAt || memory.updatedAt || "").slice(0, 10)}
                        </p>
                      </div>
                      <Button
                        size="sm" variant="outline" className="shrink-0 cursor-pointer rounded-xl" disabled={!isOperator || busy}
                        onClick={() => void act(() => archiveMemory(memory.id), "Preference forgotten")}
                      >
                        <Trash2 size={12} /> Forget
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Section>
      </div>

      <div className="mt-3">
        <Section title={`Evidence (${observations.length} groups)`} icon={Database}>
          {observations.length === 0 ? (
            <Muted>No behavioural evidence has been observed yet. Ask for a table, a short answer, or a deep dive a few times and it will appear here.</Muted>
          ) : (
            <div className="space-y-2">
              {observations.map((group) => {
                const max = Math.max(thresholds.minObservations, group.observationCount);
                const width = Math.max(6, Math.round((group.observationCount / max) * 100));
                return (
                  <div key={`${group.dimension}:${group.value}`} className="rounded-xl border border-border/20 bg-background/30 p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[11px] text-foreground">
                        <span className="font-semibold">{dimensionLabel(group.dimension)}</span>
                        <span className="text-muted-foreground"> → {group.value}</span>
                      </p>
                      <span className="text-[9px] text-muted-foreground">
                        {group.distinctRuns} runs · {group.observationCount} observations
                      </span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-border/20">
                      <div className="h-full rounded-full bg-primary/70" style={{ width: `${width}%` }} />
                    </div>
                    {group.evidenceText && (
                      <p className="mt-1.5 truncate text-[9px] text-muted-foreground/80">“{group.evidenceText}”</p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <p className="mt-2 text-[9px] text-muted-foreground/80">
            Evidence is a bounded excerpt of the trigger phrase, never the full transcript. Secrets and current financial facts are never inferred.
          </p>
        </Section>
      </div>

      {!isOperator && (
        <p className="mt-3 text-[10px] text-amber-300/90">
          Read-only session — accepting, dismissing or scanning requires operator authorization.
        </p>
      )}
    </div>
  );
}
