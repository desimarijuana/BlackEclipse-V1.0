"use client";

// ── Risk & AI settings ───────────────────────────────────────────────────────
// The permanent, low-noise home for the company's position and the accepted
// risk-notice version. It is deliberately not a banner: the user finds it in
// Settings, and every trading/AI surface links back to the same words.

import { useCallback, useEffect, useState } from "react";
import { Bot, Check, Loader2, ShieldCheck } from "@/lib/icons";
import {
  AI_OUTPUT_FULL,
  RESPONSIBILITY_STATEMENT,
  RISK_ACK_LABEL,
  RISK_DISCLOSURE_FULL,
  RISK_DISCLOSURE_VERSION,
} from "@/lib/legal/disclosure";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Panel, SectionHeader, SubSection } from "./settings-ui";

interface RiskStatus {
  requiredVersion: string;
  acceptedVersion?: string;
  acceptedAt?: string;
  accepted: boolean;
}

function formatDate(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function RiskAiSettingsPanel() {
  const [status, setStatus] = useState<RiskStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/legal/risk-ack", { cache: "no-store" });
      if (!res.ok) throw new Error("Could not read the risk acknowledgement.");
      setStatus((await res.json()) as RiskStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read the risk acknowledgement.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const accept = async () => {
    if (!checked) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/legal/risk-ack", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ version: RISK_DISCLOSURE_VERSION }),
      });
      const data = (await res.json()) as { error?: string };
      if (!res.ok) throw new Error(data.error || "Could not record the acknowledgement.");
      setReviewOpen(false);
      setChecked(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the acknowledgement.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-6">
      <SectionHeader
        icon={ShieldCheck}
        title="Risk & AI"
        description="What Eclipse is, what it is not, and the risk notice you have accepted. The same words are used at first run and before live trading."
      />

      <SubSection
        icon={ShieldCheck}
        title="The position"
        description="This is the sentence every surface must agree with."
      >
        <Panel className="p-5">
          <p className="text-[13px] leading-relaxed text-foreground">
            {RESPONSIBILITY_STATEMENT}
          </p>
        </Panel>
      </SubSection>

      <SubSection
        icon={Bot}
        title="AI agent"
        description="The assistant is useful, not infallible. You remain the decision-maker."
      >
        <Panel className="p-5">
          <p className="text-[13px] leading-relaxed text-foreground">{AI_OUTPUT_FULL}</p>
          <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
            Output can be incomplete, outdated, or wrong even when it sounds confident. Verify
            prices, orders, and positions with your broker before acting.
          </p>
        </Panel>
      </SubSection>

      <SubSection
        icon={Check}
        title="Risk notice"
        description="The acceptance is versioned; a material change asks again."
      >
        <Panel className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs font-semibold text-foreground">
                {loading ? "Checking acceptance…" : status?.accepted ? "Accepted" : "Not accepted for this version"}
              </p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {loading
                  ? "Reading the local record."
                  : status?.accepted
                    ? `Version ${status.acceptedVersion ?? RISK_DISCLOSURE_VERSION}${
                        status.acceptedAt ? ` · ${formatDate(status.acceptedAt)}` : ""
                      }`
                    : `Current version ${RISK_DISCLOSURE_VERSION}. Review and accept once.`}
              </p>
            </div>
            <button
              type="button"
              onClick={() => {
                setChecked(false);
                setError(null);
                setReviewOpen(true);
              }}
              className="shrink-0 cursor-pointer rounded-xl border border-primary/40 bg-primary/10 px-3 py-1.5 text-[11px] font-medium text-primary transition-colors hover:bg-primary/15"
            >
              Review notice
            </button>
          </div>
          {error && <p className="mt-2 text-[11px] text-rose-300">{error}</p>}
        </Panel>
      </SubSection>

      <Dialog open={reviewOpen} onOpenChange={setReviewOpen}>
        <DialogContent className="max-w-[560px] gap-0 rounded-xl border border-white/15 glass-card-strong p-0">
          <div className="flex items-start gap-3 px-5 pb-3 pt-5">
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
              <ShieldCheck size={16} />
            </span>
            <div className="min-w-0">
              <DialogTitle className="font-serif text-[17px] font-semibold leading-snug text-foreground">
                Risk notice
              </DialogTitle>
              <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
                Read and accept the current notice. Version {RISK_DISCLOSURE_VERSION}.
              </p>
            </div>
          </div>

          <div className="mx-5 max-h-[38vh] overflow-y-auto rounded-xl border border-white/10 bg-white/[0.02] p-3 text-[11px] leading-relaxed text-muted-foreground/80">
            {RISK_DISCLOSURE_FULL}
          </div>

          <label className="mx-5 mt-3 flex cursor-pointer items-start gap-2 rounded-xl border border-amber-500/25 bg-amber-500/[0.05] p-2.5">
            <input
              type="checkbox"
              className="mt-0.5 accent-primary"
              checked={checked}
              onChange={(event) => setChecked(event.target.checked)}
            />
            <span className="text-[11px] leading-relaxed text-muted-foreground">
              {RISK_ACK_LABEL}
            </span>
          </label>

          {error && (
            <p className="mx-5 mt-2 rounded-lg border border-rose-500/25 bg-rose-500/[0.05] p-2 text-[11px] text-rose-200">
              {error}
            </p>
          )}

          <div className="flex items-center justify-end gap-2 px-5 pb-5 pt-3">
            <button
              type="button"
              onClick={() => setReviewOpen(false)}
              className="cursor-pointer rounded-xl border border-border/40 px-3 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-accent/30 hover:text-foreground"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!checked || busy}
              onClick={() => void accept()}
              className="inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-xl bg-primary px-3 py-1.5 text-[11px] font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              Accept
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
