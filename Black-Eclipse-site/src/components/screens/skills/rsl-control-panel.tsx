"use client";

// Production controls for the RSL conductor: mode/lifecycle/budget visibility,
// an operator-triggered tick, and a staging form for code proposals. Everything
// goes through the operator-gated Next.js proxy; nothing applies automatically.

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n/use-t";
import {
  getEvolutionRslStatusBrowser,
  proposeEvolutionCandidateBrowser,
  tickEvolutionRslBrowser,
} from "@/lib/harness/evolution-browser";
import type {
  EvolutionCandidate,
  EvolutionRslStatus,
  EvolutionRslTickResult,
} from "@/lib/harness/evolution-client";
import { cn } from "@/lib/utils";

const SAMPLE_OPS = JSON.stringify(
  [
    {
      op: "create",
      path: "python/harness/rsl_fixture.py",
      content: "VALUE = 1\n",
      reason: "operator-staged proposal",
    },
  ],
  null,
  2,
);

export function RslControlPanel() {
  const t = useT();
  const [status, setStatus] = useState<EvolutionRslStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [ticking, setTicking] = useState(false);
  const [tickResult, setTickResult] = useState<EvolutionRslTickResult | null>(null);
  const [tickError, setTickError] = useState<string | null>(null);

  const [candidateId, setCandidateId] = useState("");
  const [targetPath, setTargetPath] = useState("");
  const [ops, setOps] = useState(SAMPLE_OPS);
  const [proposing, setProposing] = useState(false);
  const [proposal, setProposal] = useState<EvolutionCandidate | null>(null);
  const [proposalError, setProposalError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    setStatusError(null);
    try {
      setStatus(await getEvolutionRslStatusBrowser());
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "RSL status failed");
    }
  }, []);
  useEffect(() => { void loadStatus(); }, [loadStatus]);

  const tick = useCallback(async () => {
    setTicking(true);
    setTickError(null);
    setTickResult(null);
    try {
      setTickResult(await tickEvolutionRslBrowser());
      await loadStatus();
    } catch (err) {
      setTickError(err instanceof Error ? err.message : "RSL tick failed");
    } finally {
      setTicking(false);
    }
  }, [loadStatus]);

  const stageProposal = useCallback(async () => {
    setProposing(true);
    setProposalError(null);
    setProposal(null);
    try {
      let parsed: unknown;
      try {
        parsed = JSON.parse(ops);
      } catch {
        throw new Error(t("evolution.propose.invalidJson"));
      }
      if (!Array.isArray(parsed) || parsed.length === 0) {
        throw new Error(t("evolution.propose.invalidJson"));
      }
      const result = await proposeEvolutionCandidateBrowser(candidateId.trim(), {
        targetPath: targetPath.trim() || null,
        ops: parsed as Array<Record<string, unknown>>,
      });
      setProposal(result.candidate);
    } catch (err) {
      setProposalError(err instanceof Error ? err.message : "proposal failed");
    } finally {
      setProposing(false);
    }
  }, [candidateId, ops, t, targetPath]);

  const inputClass =
    "w-full rounded-lg border border-border/50 bg-background/40 px-2.5 py-1.5 text-[11px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/40";

  return (
    <section className="glass-card-subtle p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-xs font-semibold text-foreground">{t("evolution.rsl.title")}</h4>
          <p className="mt-1 text-[10px] text-muted-foreground">{t("evolution.rsl.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void loadStatus()}
            className="rounded-lg border border-border/50 px-2 py-1 text-[10px] text-muted-foreground transition hover:text-foreground"
          >
            {t("evolution.rsl.refresh")}
          </button>
          <button
            type="button"
            onClick={() => void tick()}
            disabled={ticking || status?.mode === "off"}
            className="rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] text-primary transition hover:bg-primary/15 disabled:opacity-50"
          >
            {ticking ? t("evolution.rsl.ticking") : t("evolution.rsl.tick")}
          </button>
        </div>
      </div>

      {statusError && (
        <p className="mt-2 rounded-lg border border-rose-400/30 bg-rose-400/5 px-2 py-1 text-[10px] text-rose-300">
          {statusError}
        </p>
      )}
      {status ? (
        <div className="mt-2 grid gap-1 text-[10px] text-muted-foreground sm:grid-cols-3">
          <span className={cn(
            "font-medium",
            status.mode === "off" ? "text-amber-300" : "text-emerald-300",
          )}>
            {t("evolution.rsl.mode", { mode: status.mode })}
          </span>
          <span>
            {t("evolution.rsl.lifecycle", {
              state: status.running ? "running" : "stopped",
              busy: status.busy ? "busy" : "idle",
            })}
          </span>
          <span>
            {t("evolution.rsl.budget", {
              used: status.startedToday,
              max: status.maxExperimentsPerDay,
              remaining: status.remainingToday,
            })}
          </span>
          <span>{t("evolution.rsl.k", { k: status.k })}</span>
          {status.tickSeconds != null && (
            <span>{t("evolution.rsl.tickSeconds", { seconds: status.tickSeconds })}</span>
          )}
        </div>
      ) : (
        !statusError && <p className="mt-2 text-[10px] text-muted-foreground">{t("evolution.rsl.loading")}</p>
      )}
      {status?.mode === "off" && (
        <p className="mt-2 rounded-lg border border-amber-400/30 bg-amber-400/5 px-2 py-1 text-[10px] text-amber-300">
          {t("evolution.rsl.offHint")}
        </p>
      )}
      {tickError && <p className="mt-2 text-[10px] text-rose-300">{tickError}</p>}
      {tickResult && (
        <p className="mt-2 text-[10px] text-muted-foreground">
          {t("evolution.rsl.tickResult", {
            mode: tickResult.mode,
            count: tickResult.processed?.length ?? 0,
            decision: tickResult.decision ?? "none",
          })}
        </p>
      )}

      <div className="mt-4 border-t border-border/40 pt-3">
        <h5 className="text-xs font-semibold text-foreground">{t("evolution.propose.title")}</h5>
        <p className="mt-1 text-[10px] text-muted-foreground">{t("evolution.propose.subtitle")}</p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <input
            className={inputClass}
            placeholder={t("evolution.propose.candidate")}
            value={candidateId}
            onChange={(event) => setCandidateId(event.target.value)}
          />
          <input
            className={inputClass}
            placeholder={t("evolution.propose.target")}
            value={targetPath}
            onChange={(event) => setTargetPath(event.target.value)}
          />
          <textarea
            className={`${inputClass} font-mono sm:col-span-2`}
            rows={6}
            aria-label={t("evolution.propose.ops")}
            value={ops}
            onChange={(event) => setOps(event.target.value)}
          />
        </div>
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={() => void stageProposal()}
            disabled={proposing || !candidateId.trim() || !ops.trim()}
            className="rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] text-primary transition hover:bg-primary/15 disabled:opacity-50"
          >
            {proposing ? t("evolution.propose.staging") : t("evolution.propose.stage")}
          </button>
          {proposal && (
            <span className="text-[10px] text-emerald-300">
              {t("evolution.propose.staged", { id: proposal.id })}
            </span>
          )}
          {proposalError && <span className="text-[10px] text-rose-300">{proposalError}</span>}
        </div>
      </div>
    </section>
  );
}
