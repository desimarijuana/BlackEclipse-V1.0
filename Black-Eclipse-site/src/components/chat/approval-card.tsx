'use client';

// ── ApprovalCard — the blocking "this task requires approval" prompt ────────
// Shown while a run is paused on an effectful step (MCP write/action, external
// action, or an `ask`-classified command). Three choices, in the same vocabulary
// the operator already knows:
//
//   Allow once   — approve this single step (the runtime's single-use approval).
//   Always allow — remember the program/tool in this workspace so it stops
//                  asking; creates an explicit, revocable standing grant.
//   Cancel       — refuse this step.
//
// "Always allow" is offered ONLY when the runtime marked the action grantable
// (`grantPattern`). It is never offered for a high-risk action.
//
// Portaled to <body> and positioned above the host composer: the app shell is a
// frosted-glass backdrop root, so a nested glass surface would render flat.

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ShieldAlert, ShieldCheck, ShieldPlus, Loader2, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { PendingApproval } from '@/lib/agent/response-model';

export interface ApprovalCardProps {
  approval: PendingApproval;
  /** The element the card floats above (the composer container). */
  anchor: HTMLElement | null;
  /**
   * Answer the card. `remember` requests a standing grant for the action the
   * runtime marked grantable. Resolves the paused run on the runtime side.
   */
  onDecide: (approve: boolean, remember?: boolean) => void | Promise<void>;
}

// No yellow anywhere: risk reads on the app's own scale — emerald (low/accent),
// neutral border (medium), rose (high).
const RISK_STYLE: Record<string, string> = {
  high: 'border-rose-500/40 text-rose-300',
  medium: 'border-border/50 text-muted-foreground',
  low: 'border-emerald-500/40 text-emerald-300',
};

export function ApprovalCard({ approval, anchor, onDecide }: ApprovalCardProps) {
  const [mounted, setMounted] = useState(false);
  const [busy, setBusy] = useState<'approve' | 'always' | 'deny' | null>(null);
  const [rect, setRect] = useState<{ left: number; top: number; width: number } | null>(null);
  const [typed, setTyped] = useState('');
  const challenge = approval.challenge;
  const [secondsLeft, setSecondsLeft] = useState(challenge?.coolingOffSeconds ?? 0);

  useEffect(() => {
    setMounted(true);
  }, []);

  // A money confirmation may require a cooling-off period before the approve
  // control becomes usable. The timer is display-only; the runtime re-checks the
  // elapsed time when it consumes the approval, so a fast click cannot bypass it.
  useEffect(() => {
    setSecondsLeft(challenge?.coolingOffSeconds ?? 0);
    if (!challenge?.coolingOffSeconds) return;
    const timer = setInterval(() => {
      setSecondsLeft((value) => (value > 0 ? value - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [challenge?.coolingOffSeconds]);

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

  const decide = async (choice: 'approve' | 'always' | 'deny') => {
    if (busy) return;
    setBusy(choice);
    try {
      await onDecide(choice !== 'deny', choice === 'always');
    } finally {
      // The card is normally unmounted by the caller on resolve; keep the busy
      // state if it lingers so a double-click cannot submit twice.
      setBusy(null);
    }
  };

  const risk = approval.risk?.toLowerCase();
  const riskStyle = risk ? RISK_STYLE[risk] ?? 'border-border/40 text-muted-foreground' : null;
  const highRisk = risk === 'high';
  const canRemember = Boolean(approval.grantPattern) && !highRisk;
  const needsPhrase = Boolean(
    challenge?.requiresTypedConfirmation && challenge?.confirmPhrase,
  );
  const phraseOk = !needsPhrase || typed.trim() === challenge?.confirmPhrase;
  const canApprove = busy === null && secondsLeft <= 0 && phraseOk;

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
        maxHeight: Math.max(200, rect.top - 16),
        overflowY: 'auto',
        transform: 'translate(-50%, -100%)',
      }}
      className="z-50 animate-fade-in"
    >
      <div className="glass-card-strong rounded-2xl border border-border/50 px-4 py-3.5 shadow-2xl">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-primary/30 bg-primary/10 text-primary">
            <ShieldAlert size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <p className="text-[10px] font-bold uppercase tracking-wide text-primary">
                Approval needed
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
            {challenge?.reasons && challenge.reasons.length > 0 && (
              <ul className="mt-2 space-y-1">
                {challenge.reasons.slice(0, 5).map((reason) => (
                  <li key={reason} className="flex gap-1.5 text-[11px] leading-relaxed text-foreground/75">
                    <span className="mt-[3px] h-1 w-1 shrink-0 rounded-full bg-primary" />
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            )}
            {challenge?.escalateTo && (
              <p className="mt-2 text-[11px] text-rose-300">
                Check in with {challenge.escalateTo} before continuing.
              </p>
            )}
            {secondsLeft > 0 && (
              <p className="mt-2 text-[11px] font-medium text-muted-foreground">
                Cooling-off: {secondsLeft}s before you can confirm.
              </p>
            )}
            {needsPhrase && (
              <label className="mt-2 block text-[11px] text-muted-foreground">
                Type <span className="font-mono text-foreground">{challenge?.confirmPhrase}</span> to confirm
                <input
                  value={typed}
                  onChange={(event) => setTyped(event.target.value)}
                  spellCheck={false}
                  autoComplete="off"
                  className="mt-1 w-full rounded-lg border border-border/40 bg-transparent px-2 py-1.5 text-xs text-foreground focus:border-primary/40 focus:outline-none"
                />
              </label>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => void decide('approve')}
                disabled={!canApprove}
                title={secondsLeft > 0 ? 'Wait for the cooling-off period' : undefined}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy === 'approve' ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
                {challenge ? 'Confirm' : 'Allow once'}
              </button>
              {canRemember && (
                <button
                  type="button"
                  onClick={() => void decide('always')}
                  disabled={busy !== null}
                  title={approval.grantLabel ?? undefined}
                  className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-primary/40 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"
                >
                  {busy === 'always' ? <Loader2 size={13} className="animate-spin" /> : <ShieldPlus size={13} />}
                  {approval.grantLabel ?? 'Always allow'}
                </button>
              )}
              <button
                type="button"
                onClick={() => void decide('deny')}
                disabled={busy !== null}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-border/40 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent/30 hover:text-foreground disabled:opacity-50"
              >
                {busy === 'deny' ? <Loader2 size={13} className="animate-spin" /> : <X size={13} />}
                Cancel
              </button>
              <span className="ml-auto text-[10px] text-muted-foreground">
                {canRemember ? 'Always allow is revocable in Settings.' : 'Allowing runs exactly this one step.'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
