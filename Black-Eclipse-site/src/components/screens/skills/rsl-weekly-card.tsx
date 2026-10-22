"use client";

// The weekly summary of the self-improvement loop: what was tried, what
// improved, what it cost and where production is drifting. Read-only.

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n/use-t";
import { getEvolutionRslReportBrowser } from "@/lib/harness/evolution-browser";
import type { EvolutionRslDigest } from "@/lib/harness/evolution-client";
import { cn } from "@/lib/utils";

function _fmt(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  if (typeof value !== "number") return String(value);
  return value.toFixed(digits);
}

export interface RslWeeklyCardProps {
  days?: number;
  className?: string;
}

export function RslWeeklyCard({ days = 7, className }: RslWeeklyCardProps) {
  const t = useT();
  const [digest, setDigest] = useState<EvolutionRslDigest | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const report = await getEvolutionRslReportBrowser({ days });
      setDigest(report.digest ?? null);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  const experiments = digest?.experiments;
  const candidates = digest?.candidates ?? {};
  const candidateTotal = Object.values(candidates).reduce((sum, n) => sum + n, 0);
  const drift = digest?.drift;

  return (
    <div className={cn("glass-card-subtle rounded-lg border border-border/40 p-3", className)}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[12px] font-medium text-foreground">{t("evolution.weekly.title")}</div>
          <div className="text-[11px] text-muted-foreground">
            {t("evolution.weekly.subtitle", { days: String(days) })}
          </div>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="shrink-0 rounded-lg border border-border/40 px-2 py-0.5 text-[11px] text-foreground hover:bg-accent"
        >
          {t("evolution.weekly.refresh")}
        </button>
      </div>

      {loading ? (
        <div className="mt-2 text-[11px] text-muted-foreground">{t("evolution.weekly.loading")}</div>
      ) : failed ? (
        <div className="mt-2 text-[11px] text-destructive">{t("evolution.weekly.failed")}</div>
      ) : !digest ? null : (
        <>
          <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">{t("evolution.weekly.experiments")}</dt>
              <dd className="text-foreground">{_fmt(experiments?.rsl_experiments, 0)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">{t("evolution.weekly.accepted")}</dt>
              <dd className="text-primary">{_fmt(experiments?.rsl_accepted, 0)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">{t("evolution.weekly.rejected")}</dt>
              <dd className="text-foreground">{_fmt(experiments?.rsl_rejected, 0)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">{t("evolution.weekly.unmeasured")}</dt>
              <dd className="text-foreground">{_fmt(experiments?.rsl_unmeasured, 0)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">{t("evolution.weekly.cost")}</dt>
              <dd className="text-foreground">
                {experiments?.cost_usd === null || experiments?.cost_usd === undefined
                  ? "—"
                  : `$${_fmt(experiments.cost_usd, 4)}`}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">{t("evolution.weekly.costPerAccepted")}</dt>
              <dd className="text-foreground">
                {experiments?.cost_per_accepted === null ||
                experiments?.cost_per_accepted === undefined
                  ? "—"
                  : `$${_fmt(experiments.cost_per_accepted, 4)}`}
              </dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">{t("evolution.weekly.candidates")}</dt>
              <dd className="text-foreground">{candidateTotal}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">{t("evolution.weekly.drift")}</dt>
              <dd className="text-foreground">
                {drift?.status === "drift"
                  ? "▼"
                  : drift?.status === "stable"
                    ? "●"
                    : "—"}
              </dd>
            </div>
          </dl>

          <div className="mt-2 text-[11px] text-muted-foreground">
            {t("evolution.weekly.lessons")}
          </div>
          {digest.lessons.length === 0 ? (
            <div className="text-[11px] text-muted-foreground/80">
              {t("evolution.weekly.lessonsEmpty")}
            </div>
          ) : (
            <ul className="mt-0.5 list-disc pl-4 text-[11px] text-muted-foreground">
              {digest.lessons.slice(0, 3).map((lesson) => (
                <li key={lesson.id}>{lesson.cue || lesson.lesson}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

export default RslWeeklyCard;
