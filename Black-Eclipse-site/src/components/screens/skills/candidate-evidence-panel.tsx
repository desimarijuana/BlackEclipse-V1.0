"use client";

// One candidate's recorded evidence: the candidate row, its attempts and every
// experiment that names it. Read-only; the experiment list reuses the same
// critical-regression block as the main panel.

import { useCallback, useEffect, useRef, useState } from "react";
import { useT } from "@/lib/i18n/use-t";
import { evolutionCandidateEvidenceBrowser } from "@/lib/harness/clients/evolution-browser";
import {
  EVOLUTION_EVIDENCE_EVENT,
  EVOLUTION_VERIFIED_EVENT,
  type EvolutionEvidenceEventDetail,
} from "@/lib/harness/evolution-events";
import type { EvolutionCandidateEvidence } from "@/lib/harness/clients/evolution-client";
import { cn } from "@/lib/utils";
import { ExperimentList } from "./experiment-list";

export function evidenceSectionClass(highlighted: boolean): string {
  return cn(
    "mt-4 scroll-mt-4 border-t border-border/40 pt-3 transition-shadow",
    highlighted && "rounded-xl ring-2 ring-sky-400/40",
  );
}

export function CandidateEvidencePanel({
  initialCandidateId,
  scope,
}: {
  initialCandidateId?: string;
  scope?: string;
}) {
  const t = useT();
  const sectionRef = useRef<HTMLElement | null>(null);
  const highlightTimer = useRef<number | null>(null);
  const [highlighted, setHighlighted] = useState(false);
  const [candidateId, setCandidateId] = useState("");
  const [evidence, setEvidence] = useState<EvolutionCandidateEvidence | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");

  const loadById = useCallback(async (id: string) => {
    const value = id.trim();
    if (!value) return;
    setLoading(true);
    setError(null);
    setEvidence(null);
    try {
      setEvidence(await evolutionCandidateEvidenceBrowser(value));
      try {
        window.localStorage.setItem("eclipse.rsl.evidence.candidateId", value);
      } catch {
        // Storage is optional; the panel still works without it.
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("evolution.evidence.error"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    let stored = "";
    try {
      stored = window.localStorage.getItem("eclipse.rsl.evidence.candidateId") ?? "";
    } catch {
      stored = "";
    }
    const target = initialCandidateId || stored;
    if (!target) return;
    setCandidateId(target);
    void loadById(target);
  }, [initialCandidateId, loadById]);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<EvolutionEvidenceEventDetail>).detail;
      const id = detail?.candidateId?.trim();
      if (!id) return;
      setCandidateId(id);
      void loadById(id);
      sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      setHighlighted(true);
      if (highlightTimer.current != null) {
        window.clearTimeout(highlightTimer.current);
      }
      highlightTimer.current = window.setTimeout(() => {
        setHighlighted(false);
        highlightTimer.current = null;
      }, 1800);
    };
    window.addEventListener(EVOLUTION_EVIDENCE_EVENT, handler);
    return () => {
      window.removeEventListener(EVOLUTION_EVIDENCE_EVENT, handler);
      if (highlightTimer.current != null) {
        window.clearTimeout(highlightTimer.current);
        highlightTimer.current = null;
      }
    };
  }, [loadById]);

  const clearEvidence = useCallback(() => {
    setCandidateId("");
    setEvidence(null);
    setError(null);
    setCopied("idle");
    setHighlighted(false);
    try {
      window.localStorage.removeItem("eclipse.rsl.evidence.candidateId");
    } catch {
      // Storage is optional; clearing the visible state is enough.
    }
  }, []);

  const refreshEvidence = useCallback(async () => {
    if (!evidence) return;
    setRefreshing(true);
    setError(null);
    try {
      setEvidence(await evolutionCandidateEvidenceBrowser(evidence.candidate.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("evolution.evidence.error"));
    } finally {
      setRefreshing(false);
    }
  }, [evidence, t]);

  useEffect(() => {
    const handler = () => { void refreshEvidence(); };
    window.addEventListener(EVOLUTION_VERIFIED_EVENT, handler);
    return () => window.removeEventListener(EVOLUTION_VERIFIED_EVENT, handler);
  }, [refreshEvidence]);

  const copyId = useCallback(async () => {
    if (!evidence) return;
    try {
      await navigator.clipboard.writeText(evidence.candidate.id);
      setCopied("copied");
    } catch {
      setCopied("failed");
    }
    window.setTimeout(() => setCopied("idle"), 1500);
  }, [evidence]);

  const load = useCallback(() => loadById(candidateId), [candidateId, loadById]);

  const inputClass =
    "w-full rounded-lg border border-border/50 bg-background/40 px-2.5 py-1.5 text-[11px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/40";
  const visibleExperiments = evidence
    ? (scope && scope !== "all"
      ? evidence.experiments.filter((experiment) => String(
        (experiment.metadata ?? {}).scope ?? "global",
      ) === scope)
      : evidence.experiments)
    : [];

  return (
    <section ref={sectionRef} className={evidenceSectionClass(highlighted)}>
      <div>
        <h4 className="text-xs font-semibold text-foreground">{t("evolution.evidence.title")}</h4>
        <p className="mt-1 text-[10px] text-muted-foreground">{t("evolution.evidence.subtitle")}</p>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          className={`${inputClass} max-w-xs`}
          placeholder={t("evolution.evidence.candidate")}
          value={candidateId}
          onChange={(event) => setCandidateId(event.target.value)}
        />
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading || !candidateId.trim()}
          className="rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] text-primary transition hover:bg-primary/15 disabled:opacity-50"
        >
          {loading ? t("evolution.evidence.loading") : t("evolution.evidence.load")}
        </button>
        <button
          type="button"
          onClick={() => void refreshEvidence()}
          disabled={!evidence || refreshing}
          className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-2.5 py-1 text-[11px] text-sky-300 transition hover:bg-sky-400/15 disabled:opacity-50"
        >
          {refreshing ? t("evolution.evidence.refreshing") : t("evolution.evidence.refresh")}
        </button>
        <button
          type="button"
          onClick={clearEvidence}
          className="rounded-lg border border-border/50 px-2.5 py-1 text-[11px] text-muted-foreground transition hover:text-foreground"
        >
          {t("evolution.evidence.clear")}
        </button>
      </div>
      {error && (
        <p className="mt-2 rounded-lg border border-rose-400/30 bg-rose-400/5 px-2 py-1 text-[10px] text-rose-300">
          {error}
        </p>
      )}
      {evidence && (
        <div className="mt-3 space-y-2">
          <div className="rounded-lg border border-border/40 bg-background/30 p-2 text-[10px]">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[11px] font-medium text-foreground">
                {evidence.candidate.id}
                {evidence.candidate.subjectType ? ` · ${evidence.candidate.subjectType}` : ""}
                {" · "}
                {evidence.candidate.status}
                {evidence.candidate.scope ? ` | ${evidence.candidate.scope}` : ""}
              </p>
              <button
                type="button"
                onClick={() => void copyId()}
                className="rounded-lg border border-border/50 px-2 py-0.5 text-[9.5px] text-muted-foreground transition hover:text-foreground"
              >
                {copied === "copied"
                  ? t("evolution.evidence.copied")
                  : copied === "failed"
                    ? t("evolution.evidence.copyFailed")
                    : t("evolution.evidence.copy")}
              </button>
            </div>
            <p className="mt-0.5 text-muted-foreground">
              {evidence.candidate.problemStatement}
            </p>
            {evidence.candidate.targetPath && (
              <p className="mt-0.5 font-mono text-muted-foreground">
                {evidence.candidate.targetPath}
              </p>
            )}
          </div>
          <div>
            <p className="text-[10px] font-medium text-muted-foreground">
              {t("evolution.evidence.attempts", { count: evidence.attempts.length })}
            </p>
            {evidence.attempts.length === 0 ? (
              <p className="text-[10px] text-muted-foreground">{t("evolution.evidence.noAttempts")}</p>
            ) : (
              <ul className="mt-1 space-y-1">
                {evidence.attempts.slice(0, 8).map((attempt) => (
                  <li key={attempt.id} className="rounded-lg border border-border/30 px-2 py-1 text-[10px] text-muted-foreground">
                    {attempt.outcome} · {attempt.outcomeReason ?? attempt.targetPath}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <p className="text-[10px] font-medium text-muted-foreground">
              {t("evolution.evidence.experiments", { count: visibleExperiments.length })}
              {scope && scope !== "all" ? ` · ${scope}` : ""}
            </p>
            {visibleExperiments.length === 0 ? (
              <p className="text-[10px] text-muted-foreground">{t("evolution.evidence.noExperiments")}</p>
            ) : (
              <ExperimentList experiments={visibleExperiments} t={t} />
            )}
          </div>
        </div>
      )}
    </section>
  );
}
