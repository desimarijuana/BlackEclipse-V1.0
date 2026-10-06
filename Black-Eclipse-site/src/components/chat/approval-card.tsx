'use client';

// ── ApprovalCard — the blocking "this task requires approval" prompt ────────
// Shown while a run is paused on an effectful step (MCP write/action, external
// action, or an `ask`-classified command). Approve resumes the paused run in
// place; Deny refuses that step. The decision is still the runtime's single-use,
// digest-bound approval — this component only reports the operator's answer.
//
// Portaled to <body> and positioned above the host composer: the app shell is a
// frosted-glass backdrop root, so a nested glass surface would render flat.

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ShieldAlert, ShieldCheck, Loader2 } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { PendingApproval } from '@/lib/agent/response-model';

export interface ApprovalCardProps {
  approval: PendingApproval;
  /** The element the card floats above (the composer container). */
  anchor: HTMLElement | null;
  /** Answer the card. Resolves the paused run on the runtime side. */
  onDecide: (approve: boolean) => void | Promise<void>;
}

const RISK_STYLE: Record<string, string> = {
  high: 'border-rose-500/40 text-rose-300',
  medium: 'border-amber-500/40 text-amber-300',
  low: 'border-emerald-500/40 text-emerald-300',
};

export function ApprovalCard({ approval, anchor, onDecide }: ApprovalCardProps) {
  const [mounted, setMounted] = useState(false);
  const [busy, setBusy] = useState<'approve' | 'deny' | null>(null);
  const [rect, setRect] = useState<{ left: number; top: number; width: number } | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Track the anchor's box so the card stays glued just above the composer
  // through resize/scroll (the composer can move when the window changes).
  useEffect(() => {
    if (!anchor) return;
    const update = () => {
      const r = anchor.getBoundingClientRect();
      setRect({ left: r.left + r.width / 2, top: r.top, width: r.width });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(anchor);
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [anchor]);

  if (!mounted || !rect) return null;

  const decide = async (approve: boolean) => {
    if (busy) return;
    setBusy(approve ? 'approve' : 'deny');
    try {
      await onDecide(approve);
    } finally {
      // The card is normally unmounted by the caller on resolve; keep the busy
      // state if it lingers so a double-click cannot submit twice.
      setBusy(null);
    }
  };

  const risk = approval.risk?.toLowerCase();
  const riskStyle = risk ? RISK_STYLE[risk] ?? 'border-border/40 text-muted-foreground' : null;

  return createPortal(
    <div
      role="alertdialog"
      aria-modal="false"
      aria-label="Approval required"
      style={{
        position: 'fixed',
        left: rect.left,
        top: rect.top - 10,
        width: Math.min(rect.width, 720),
        transform: 'translate(-50%, -100%)',
      }}
      className="z-50 animate-fade-in"
    >
      <div className="glass-card-strong rounded-2xl border border-border/50 px-4 py-3.5 shadow-2xl">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-300">
            <ShieldAlert size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <p className="text-[10px] font-bold uppercase tracking-wide text-amber-300">
                This task requires approval
              </p>
              <span className="rounded-md border border-border/40 px-1.5 py-0.5 text-[9px] font-mono uppercase text-muted-foreground">
                {approval.kind}
              </span>
              {approval.effect && (
                <span className="rounded-md border border-border/40 px-1.5 py-0.5 text-[9px] font-mono uppercase text-muted-foreground">
                  {approval.effect}
                </span>
              )}
              {riskStyle && (
                <span className={cn('rounded-md border px-1.5 py-0.5 text-[9px] font-bold uppercase', riskStyle)}>
                  {risk} risk
                </span>
              )}
            </div>
            <p className="mt-1 text-sm font-semibold text-foreground">{approval.title}</p>
            {approval.summary && (
              <p className="mt-0.5 text-[12px] leading-relaxed text-foreground/80">{approval.summary}</p>
            )}
            <div className="mt-3 flex items-center gap-2">
              <button
                type="button"
                onClick={() => void decide(true)}
                disabled={busy !== null}
                className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50 cursor-pointer"
              >
                {busy === 'approve' ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
                Approve
              </button>
              <button
                type="button"
                onClick={() => void decide(false)}
                disabled={busy !== null}
                className="inline-flex items-center gap-1.5 rounded-xl border border-rose-500/30 px-3 py-1.5 text-xs font-medium text-rose-300 transition-colors hover:bg-rose-500/10 disabled:opacity-50 cursor-pointer"
              >
                {busy === 'deny' ? <Loader2 size={13} className="animate-spin" /> : null}
                Deny
              </button>
              <span className="ml-auto text-[10px] text-muted-foreground">
                Approving runs exactly this one step.
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
