'use client';

// ── RiskAckGate — accept the current notice after an upgrade ─────────────────
// New installs accept inside the setup wizard. An install migrated before the
// notice existed never saw it, so this closes that gap in the least intrusive
// way that still records the acceptance:
//
//   * local self-hosted (auth off on loopback): a dismissible bottom banner
//     with a "Review" action. Dismissal is per-session; nothing is recorded
//     until the user actually accepts.
//   * remote / multi-user (hosted): a blocking modal, because consent from
//     every user of a hosted service must be explicit.
//
// It does nothing when setup is incomplete (the wizard owns that flow) and
// nothing when the status read fails (a transient API error must not brick the
// app). The acceptance is versioned server-side.

import { useEffect, useRef, useState } from 'react';
import { Loader2, ShieldCheck, X } from '@/lib/icons';
import {
  RISK_ACK_LABEL,
  RISK_DISCLOSURE_FULL,
  RISK_DISCLOSURE_VERSION,
} from '@/lib/legal/disclosure';

const DISMISS_KEY = `be_risk_ack_dismissed:${RISK_DISCLOSURE_VERSION}`;

interface SetupAckState {
  completed: boolean;
  mode?: string;
  hosted?: boolean;
  riskAck?: { accepted?: boolean };
}

export function RiskAckGate() {
  const [needed, setNeeded] = useState(false);
  const [hosted, setHosted] = useState(false);
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [mode, setMode] = useState<string | undefined>();
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/setup', { cache: 'no-store' })
      .then(async (res) => (res.ok ? ((await res.json()) as SetupAckState) : null))
      .then((data) => {
        if (cancelled || !data) return;
        if (data.completed !== true || data.riskAck?.accepted !== false) return;
        const blocking = data.hosted === true;
        setMode(data.mode);
        setHosted(blocking);
        setNeeded(true);
        if (blocking) {
          setOpen(true);
        } else {
          try {
            setDismissed(sessionStorage.getItem(DISMISS_KEY) === '1');
          } catch {
            setDismissed(false);
          }
        }
      })
      .catch(() => {
        /* status unavailable — never block the app on a transient failure */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    cardRef.current?.focus();
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  if (!needed) return null;

  const accept = async () => {
    if (!checked) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch('/api/legal/risk-ack', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ version: RISK_DISCLOSURE_VERSION, mode }),
      });
      const data = (await res.json()) as { error?: string };
      if (!res.ok) throw new Error(data.error || 'Could not record the acknowledgement.');
      setNeeded(false);
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not record the acknowledgement.');
    } finally {
      setBusy(false);
    }
  };

  const dismissBanner = () => {
    setDismissed(true);
    try {
      sessionStorage.setItem(DISMISS_KEY, '1');
    } catch {
      /* private mode — it stays dismissed for this render */
    }
  };

  if (!open) {
    if (dismissed) return null;
    return (
      <div className="fixed inset-x-0 bottom-4 z-[150] flex justify-center px-4" role="status">
        <div className="glass-card flex w-full max-w-[560px] items-start gap-2.5 rounded-2xl border border-border/40 px-3.5 py-2.5 shadow-lg">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
            <ShieldCheck size={14} />
          </span>
          <div className="min-w-0 flex-1 text-[11px] leading-relaxed text-muted-foreground">
            <span className="font-semibold text-foreground">Risk notice updated.</span>{' '}
            Review how Eclipse&apos;s AI output should be used.
          </div>
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="cursor-pointer rounded-lg border border-border/40 px-2.5 py-1 text-[11px] font-medium text-foreground transition-colors hover:bg-accent/30"
          >
            Review
          </button>
          <button
            type="button"
            onClick={dismissBanner}
            className="flex h-6 w-6 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-accent/30 hover:text-foreground"
            aria-label="Dismiss risk notice reminder"
          >
            <X size={12} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 z-[190] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="risk-ack-title"
    >
      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm" />
      <div
        ref={cardRef}
        tabIndex={-1}
        className="glass-card-strong relative w-full max-w-[560px] overflow-hidden rounded-xl border border-white/15 px-5 pb-4 pt-5 outline-none"
      >
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent opacity-80" />
        {!hosted && (
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="absolute right-3 top-3 flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg text-muted-foreground hover:bg-accent/30 hover:text-foreground"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        )}
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
            <ShieldCheck size={16} />
          </span>
          <div className="min-w-0">
            <h1 id="risk-ack-title" className="font-serif text-[17px] font-semibold leading-snug text-foreground">
              Before you continue
            </h1>
            <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
              Eclipse has updated its risk notice. Please read and accept it once.
            </p>
          </div>
        </div>

        <div className="mt-3 max-h-[38vh] overflow-y-auto rounded-xl border border-white/10 bg-white/[0.02] p-3 text-[11px] leading-relaxed text-muted-foreground/80">
          {RISK_DISCLOSURE_FULL}
        </div>

        <label className="mt-3 flex cursor-pointer items-start gap-2 rounded-xl border border-amber-500/25 bg-amber-500/[0.05] p-2.5">
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
          <p className="mt-2 rounded-lg border border-rose-500/25 bg-rose-500/[0.05] p-2 text-[11px] text-rose-200">
            {error}
          </p>
        )}

        <button
          type="button"
          disabled={!checked || busy}
          onClick={() => void accept()}
          className="mt-3 inline-flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-xl bg-primary px-3 py-2 text-[12px] font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
          Accept and continue
        </button>
        <p className="mt-2 text-center text-[9.5px] leading-relaxed text-muted-foreground/50">
          Version {RISK_DISCLOSURE_VERSION}. This is evidence of a named risk, not a waiver of
          your legal rights.
        </p>
      </div>
    </div>
  );
}
