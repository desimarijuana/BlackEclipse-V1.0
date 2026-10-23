"use client";

// The corpus card: task counts, oracle coverage, manifest integrity and a
// rotation PREVIEW. Applying a rotation stays a deliberate CLI action.

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n/use-t";
import {
  getEvolutionCorpusStatusBrowser,
  getEvolutionRotationPreviewBrowser,
} from "@/lib/harness/evolution-browser";
import type {
  EvolutionCorpusStatus,
  EvolutionRotationPreview,
} from "@/lib/harness/evolution-client";
import { cn } from "@/lib/utils";

export function currentQuarter(now = new Date()): string {
  return `${now.getUTCFullYear()}Q${Math.floor(now.getUTCMonth() / 3) + 1}`;
}

function splitOrder(split: string): number {
  const order = ["validation", "optimization", "held_out", "release"];
  const index = order.indexOf(split);
  return index === -1 ? order.length : index;
}

export interface RslCorpusCardViewProps {
  status: EvolutionCorpusStatus | null;
  error: string | null;
  quarter: string;
  count: number;
  preview: EvolutionRotationPreview | null;
  previewing: boolean;
  previewError: string | null;
  onRefresh: () => void;
  onQuarterChange: (value: string) => void;
  onCountChange: (value: number) => void;
  onPreview: () => void;
  className?: string;
}

export function RslCorpusCardView({
  status,
  error,
  quarter,
  count,
  preview,
  previewing,
  previewError,
  onRefresh,
  onQuarterChange,
  onCountChange,
  onPreview,
  className,
}: RslCorpusCardViewProps) {
  const t = useT();
  const manifest = status?.manifest;
  const splits = manifest
    ? Object.entries(manifest.bySplit).sort(
        ([left], [right]) => splitOrder(left) - splitOrder(right),
      )
    : [];

  return (
    <section
      className={cn("glass-card-subtle p-3", className)}
      data-testid="rsl-corpus-card"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h5 className="text-xs font-semibold text-foreground">
            {t("evolution.corpus.title")}
          </h5>
          <p className="mt-1 text-[10px] text-muted-foreground">
            {t("evolution.corpus.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="rounded-lg border border-border/50 px-2 py-1 text-[10px] text-muted-foreground transition hover:text-foreground"
        >
          {t("evolution.corpus.refresh")}
        </button>
      </div>

      {error && (
        <p className="mt-2 rounded-lg border border-rose-400/30 bg-rose-400/5 px-2 py-1 text-[10px] text-rose-300">
          {t("evolution.corpus.error")}: {error}
        </p>
      )}
      {!status && !error && (
        <p className="mt-2 text-[10px] text-muted-foreground">
          {t("evolution.corpus.loading")}
        </p>
      )}

      {manifest && status && (
        <>
          <div className="mt-2 flex flex-wrap items-center gap-1 text-[10px]">
            <span className="text-muted-foreground">
              {t("evolution.corpus.tasks", {
                count: manifest.taskCount,
                datasets: manifest.datasetCount,
              })}
            </span>
            {splits.map(([split, splitCount]) => (
              <span
                key={split}
                className="rounded border border-border/40 bg-background/30 px-1.5 py-0.5 text-muted-foreground"
              >
                {t("evolution.corpus.split", { split, count: splitCount })}
              </span>
            ))}
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground">
            {t("evolution.corpus.oracle", {
              covered: manifest.oracleCount,
              total: manifest.taskCount,
              percent: (manifest.oracleCoverage * 100).toFixed(1),
            })}
            {" · "}
            {t("evolution.corpus.exempt", {
              count: manifest.oracleExemptCount,
            })}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px]">
            <span
              className={
                status.verification.ok ? "text-emerald-300" : "text-rose-300"
              }
            >
              {status.verification.ok
                ? t("evolution.corpus.verified")
                : t("evolution.corpus.unverified", {
                    count: status.verification.mismatches.length,
                  })}
            </span>
            <span className={status.audit.ok ? "text-emerald-300" : "text-rose-300"}>
              {status.audit.ok
                ? t("evolution.corpus.auditOk")
                : t("evolution.corpus.auditFail", {
                    count: status.audit.errorCount,
                  })}
            </span>
          </div>
        </>
      )}

      <div className="mt-3 border-t border-border/40 pt-2">
        <div className="flex flex-wrap items-center gap-2 text-[10px]">
          <label className="flex items-center gap-1 text-muted-foreground">
            {t("evolution.corpus.quarter")}
            <input
              value={quarter}
              onChange={(event) => onQuarterChange(event.target.value)}
              className="w-20 rounded border border-border/50 bg-background/40 px-1.5 py-1 text-[10px] text-foreground"
            />
          </label>
          <label className="flex items-center gap-1 text-muted-foreground">
            {t("evolution.corpus.count")}
            <input
              type="number"
              min={1}
              max={50}
              value={count}
              onChange={(event) =>
                onCountChange(Math.min(50, Math.max(1, Number(event.target.value) || 1)))
              }
              className="w-12 rounded border border-border/50 bg-background/40 px-1.5 py-1 text-[10px] text-foreground"
            />
          </label>
          <button
            type="button"
            onClick={onPreview}
            disabled={previewing || !quarter.trim()}
            className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-2 py-1 text-[10px] text-sky-300 transition hover:bg-sky-400/15 disabled:opacity-50"
          >
            {previewing
              ? t("evolution.corpus.previewing")
              : t("evolution.corpus.preview")}
          </button>
        </div>

        {previewError && (
          <p className="mt-2 text-[10px] text-rose-300">
            {t("evolution.corpus.previewError")}: {previewError}
          </p>
        )}
        {preview && (
          <div className="mt-2 space-y-0.5 text-[10px] text-muted-foreground">
            {preview.plan.ok ? (
              <>
                <p>
                  {t("evolution.corpus.plan", {
                    count: preview.plan.count ?? 0,
                    returned: preview.plan.returned ?? 0,
                  })}
                </p>
                {preview.plan.moves.slice(0, 12).map((move) => (
                  <p key={`${move.datasetFile}:${move.taskId}`} className="truncate">
                    {move.taskId} · {move.from} → {move.to}
                  </p>
                ))}
                {preview.plan.moves.length > 12 && (
                  <p>{t("evolution.corpus.moreMoves", {
                    count: preview.plan.moves.length - 12,
                  })}</p>
                )}
              </>
            ) : (
              <p>
                {t("evolution.corpus.notApplicable", {
                  reason: preview.plan.reason ?? "unknown",
                })}
              </p>
            )}
            <p className="text-[9px]">{t("evolution.corpus.previewOnly")}</p>
          </div>
        )}
      </div>
    </section>
  );
}

export function RslCorpusCard({ className }: { className?: string }) {
  const [status, setStatus] = useState<EvolutionCorpusStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [quarter, setQuarter] = useState(currentQuarter);
  const [count, setCount] = useState(4);
  const [preview, setPreview] = useState<EvolutionRotationPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setStatus(await getEvolutionCorpusStatusBrowser());
    } catch (err) {
      setError(err instanceof Error ? err.message : "corpus status failed");
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const requestPreview = useCallback(async () => {
    setPreviewing(true);
    setPreviewError(null);
    try {
      setPreview(
        await getEvolutionRotationPreviewBrowser({
          quarter: quarter.trim(),
          count,
        }),
      );
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : "rotation preview failed");
    } finally {
      setPreviewing(false);
    }
  }, [count, quarter]);

  return (
    <RslCorpusCardView
      status={status}
      error={error}
      quarter={quarter}
      count={count}
      preview={preview}
      previewing={previewing}
      previewError={previewError}
      onRefresh={() => void load()}
      onQuarterChange={setQuarter}
      onCountChange={setCount}
      onPreview={() => void requestPreview()}
      className={className}
    />
  );
}
