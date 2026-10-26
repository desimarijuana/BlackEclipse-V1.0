'use client';

// ── ParallelAgentsDialog — click a fan-out card to see each agent working ───
// A portaled frosted dialog (the card lives inside the transcript, which is an
// animated/backdrop-root subtree, so a nested popup would render flat). Each row
// carries the full sub-question, the live activity, the runtime's step counter
// and a short activity timeline — the "what is this agent doing?" view.

import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Bot, Clock, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { DelegationChildView, DelegationView } from '@/lib/agent/response-model';

function humanizeAgent(agentId?: string): string {
  if (!agentId) return 'Eclipse Agent';
  return agentId
    .replace(/[-_]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function percentOf(child: DelegationChildView): number | null {
  if (!child.maxSteps || child.maxSteps <= 0 || child.step == null) return null;
  return Math.max(0, Math.min(100, Math.round((child.step / child.maxSteps) * 100)));
}

function statusLabel(child: DelegationChildView): string {
  switch (child.status) {
    case 'completed': return 'Done';
    case 'failed': return child.reason || "Couldn't finish";
    case 'refused': return child.reason || 'Skipped';
    case 'timed_out': return child.reason || 'Ran out of time';
    case 'cancelled': return child.reason || 'Stopped';
    default: return child.activity || 'Starting';
  }
}

// One Eclipse agent working in parallel — the same Bot glyph as the ChatBot nav
// item, not a distinct generated face.
function Face({ size = 36 }: { size?: number }) {
  return <Bot size={Math.round(size * 0.5)} aria-hidden />;
}

/** The dialog's inner content — pure, so it can be rendered/tested without a portal. */
export function DelegationDetails({ delegation }: { delegation: DelegationView }) {
  const done = delegation.children.filter((c) => c.status !== 'running').length;
  return (
    <div className="flex flex-col gap-3">
      <header className="flex items-start gap-2 pr-8">
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <h2 className="truncate text-[15px] font-semibold text-foreground">
              {delegation.strategy === 'best_of'
                ? `Best of ${delegation.children.length || '…'}`
                : `${delegation.children.length || '…'} agents working`}
            </h2>
            {delegation.title && (
              <span className="truncate text-[13px] text-muted-foreground">· {delegation.title}</span>
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {done} of {delegation.children.length} done · live agent detail
          </p>
        </div>
      </header>

      <div className="space-y-2">
        {delegation.children.map((child) => {
          const percent = percentOf(child);
          const recent = [...(child.recent ?? [])].reverse();
          const winner = delegation.winner === child.childIndex;
          return (
            <section
              key={child.childIndex}
              className="rounded-xl border border-white/5 bg-white/[0.025] p-3"
              aria-label={`${humanizeAgent(child.agentId)}: ${statusLabel(child)}`}
            >
              <div className="flex items-start gap-3">
                <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white/5 ring-1 ring-white/10">
                  <Face size={28} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <span className="text-[13px] font-medium text-foreground/90">
                      {child.model || humanizeAgent(child.agentId)}
                    </span>
                    <span className="truncate text-[12px] text-muted-foreground">
                      · {child.approach || child.goal || `Part ${child.childIndex + 1}`}
                    </span>
                    {winner && (
                      <span className="rounded-full bg-emerald-400/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300 ring-1 ring-emerald-400/20">
                        Best
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                    <span>{statusLabel(child)}</span>
                    {child.maxSteps != null && (
                      <span className="inline-flex items-center gap-1">
                        <Clock size={10} aria-hidden /> step {child.step ?? 0} of {child.maxSteps}
                      </span>
                    )}
                    {percent != null && <span>{percent}%</span>}
                    {typeof child.tokens === 'number' && child.tokens > 0 && (
                      <span>{child.tokens.toLocaleString()} tokens</span>
                    )}
                  </div>

                  {child.goal && child.approach && (
                    <p className="mt-1.5 text-[12px] leading-relaxed text-foreground/75">
                      {child.goal}
                    </p>
                  )}

                  <div
                    className="mt-2 h-1 overflow-hidden rounded-full bg-white/10"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={percent ?? undefined}
                  >
                    <div
                      className={cn(
                        'h-full rounded-full transition-all duration-500',
                        child.status === 'failed' || child.status === 'refused'
                          ? 'bg-red-400/70'
                          : child.status === 'completed' ? 'bg-emerald-400/80' : 'bg-primary/80',
                        percent == null && child.status === 'running' && 'animate-pulse',
                      )}
                      style={{ width: percent != null ? `${percent}%` : child.status === 'running' ? '28%' : '0%' }}
                    />
                  </div>

                  {recent.length > 0 && (
                    <div className="mt-2.5">
                      <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground/60">
                        What it did
                      </div>
                      <ol className="space-y-0.5">
                        {recent.map((line, index) => (
                          <li key={`${index}-${line}`} className="flex gap-2 text-[11px] text-muted-foreground">
                            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary/60" aria-hidden />
                            <span className="min-w-0 truncate">{line}</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {child.runId && (
                    <div className="mt-2 truncate font-mono text-[10px] text-muted-foreground/45">
                      {child.runId}
                    </div>
                  )}
                </div>
              </div>
            </section>
          );
        })}
      </div>

      {delegation.droppedClaims ? (
        <p className="text-[11px] text-muted-foreground/70">
          {delegation.droppedClaims} statement{delegation.droppedClaims === 1 ? '' : 's'} could not be
          confirmed, so {delegation.droppedClaims === 1 ? "it isn't" : "they aren't"} repeated as fact.
        </p>
      ) : null}
    </div>
  );
}

export function ParallelAgentsDialog({
  delegation,
  onClose,
}: {
  delegation: DelegationView;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  if (typeof document === 'undefined') return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/55 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Parallel agents"
        className="glass-card-strong relative max-h-[82vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/10 p-4 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close agent details"
          className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground transition-colors hover:bg-white/10 hover:text-foreground"
        >
          <X size={16} />
        </button>
        <DelegationDetails delegation={delegation} />
      </div>
    </div>,
    document.body,
  );
}
