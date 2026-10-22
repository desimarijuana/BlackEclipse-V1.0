"use client";

// The lab's staged candidates: what the loop measured about ITSELF, and the
// one click that queues a candidate for the loop's verification. The card never
// activates anything - the operator still verifies, then activates.

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n/use-t";
import {
  listEvolutionSurfaceLabCandidatesBrowser,
  queueEvolutionSurfaceLabCandidateBrowser,
} from "@/lib/harness/evolution-browser";
import type { EvolutionSurfaceLabCandidate } from "@/lib/harness/evolution-client";
import { cn } from "@/lib/utils";

export interface RslLabCardProps {
  className?: string;
}

export function RslLabCard({ className }: RslLabCardProps) {
  const t = useT();
  const [candidates, setCandidates] = useState<EvolutionSurfaceLabCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const result = await listEvolutionSurfaceLabCandidatesBrowser({ limit: 5 });
      setCandidates(result.candidates ?? []);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const queue = useCallback(async (id: string) => {
    setBusyId(id);
    try {
      await queueEvolutionSurfaceLabCandidateBrowser(id);
      await load();
    } catch {
      setFailed(true);
    } finally {
      setBusyId(null);
    }
  }, [load]);

  return (
    <div className={cn("glass-card-subtle rounded-lg border border-border/40 p-3", className)}>
      <div className="text-[12px] font-medium text-foreground">{t("evolution.lab.title")}</div>
      <div className="text-[11px] text-muted-foreground">{t("evolution.lab.subtitle")}</div>

      {loading ? (
        <div className="mt-2 text-[11px] text-muted-foreground">{t("evolution.weekly.loading")}</div>
      ) : failed ? (
        <div className="mt-2 text-[11px] text-destructive">{t("evolution.weekly.failed")}</div>
      ) : candidates.length === 0 ? (
        <div className="mt-2 text-[11px] text-muted-foreground/80">{t("evolution.lab.empty")}</div>
      ) : (
        <ul className="mt-2 space-y-1">
          {candidates.map((candidate) => (
            <li
              key={candidate.id}
              className="flex items-start justify-between gap-2 text-[11px] text-muted-foreground"
            >
              <span className="min-w-0 flex-1">{candidate.problemStatement}</span>
              {candidate.status === "inert" ? (
                <button
                  type="button"
                  onClick={() => void queue(candidate.id)}
                  disabled={busyId === candidate.id}
                  className="shrink-0 rounded-lg border border-border/40 px-2 py-0.5 text-foreground hover:bg-accent disabled:opacity-50"
                >
                  {busyId === candidate.id
                    ? t("evolution.lab.queueing")
                    : t("evolution.lab.queue")}
                </button>
              ) : (
                <span className="shrink-0 text-foreground/80">
                  {t("evolution.lab.queued")}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default RslLabCard;
