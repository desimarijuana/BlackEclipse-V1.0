'use client';

// ── ClarificationCard — the blocking "Eclipse has a question" prompt ──────────
// Shown while a run is paused on a `clarify` tool call. Unlike ApprovalCard this
// is NOT a permission decision: the operator picks one of the agent's options,
// types a free-text answer, or lets Eclipse decide. The answer resolves the
// paused run on the runtime side; no effect is authorized by it.
//
// Portaled to <body> and positioned above the host composer, matching the
// approval card (the app shell is a frosted-glass backdrop root, so a nested
// glass surface would render flat).

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { HelpCircle, Loader2, ArrowRight, Sparkles } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { PendingClarification } from '@/lib/agent/response-model';

export interface ClarificationCardProps {
  clarification: PendingClarification;
  /** The element the card floats above (the composer container). */
  anchor: HTMLElement | null;
  /** Send the chosen option label, the typed answer, or "" for "decide for me". */
  onAnswer: (answer: string) => void | Promise<void>;
}

export function ClarificationCard({ clarification, anchor, onAnswer }: ClarificationCardProps) {
  const [mounted, setMounted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState('');
  const [rect, setRect] = useState<{ left: number; top: number; width: number } | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

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

  const submit = async (value: string) => {
    if (busy) return;
    setBusy(true);
    try {
      await onAnswer(value);
    } finally {
      setBusy(false);
    }
  };

  return createPortal(
    <div
      role="alertdialog"
      aria-modal="false"
      aria-label="Eclipse has a question"
      style={{
        position: 'fixed',
        left: rect.left,
        top: rect.top - 10,
        width: Math.min(rect.width, 720),
        maxHeight: Math.max(220, rect.top - 16),
        overflowY: 'auto',
        transform: 'translate(-50%, -100%)',
      }}
      className="z-50 animate-fade-in"
    >
      <div className="glass-card-strong rounded-2xl border border-border/50 px-4 py-3.5 shadow-2xl">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-primary/30 bg-primary/10 text-primary">
            <HelpCircle size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <p className="text-[10px] font-bold uppercase tracking-wide text-primary">
                Eclipse has a question
              </p>
              <span className="rounded-md border border-border/40 px-1.5 py-0.5 text-[9px] font-mono uppercase text-muted-foreground">
                input needed
              </span>
            </div>
            <p className="mt-1 text-sm font-semibold text-foreground">{clarification.question}</p>
            {clarification.context && (
              <p className="mt-0.5 text-[12px] leading-relaxed text-foreground/80">
                {clarification.context}
              </p>
            )}

            {clarification.options.length > 0 && (
              <div className="mt-3 flex flex-col gap-1.5">
                {clarification.options.map((option) => {
                  const recommended = clarification.recommended === option;
                  return (
                    <button
                      key={option}
                      type="button"
                      disabled={busy}
                      onClick={() => void submit(option)}
                      className={cn(
                        'flex w-full cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-left text-xs font-medium transition-colors disabled:opacity-50',
                        recommended
                          ? 'border-primary/40 bg-primary/10 text-primary hover:bg-primary/15'
                          : 'border-border/40 text-foreground/90 hover:bg-accent/30',
                      )}
                    >
                      <span className="min-w-0 flex-1">{option}</span>
                      {recommended && (
                        <span className="shrink-0 rounded-md border border-primary/30 px-1.5 py-0.5 text-[9px] font-bold uppercase">
                          Recommended
                        </span>
                      )}
                      {busy ? (
                        <Loader2 size={13} className="shrink-0 animate-spin" />
                      ) : (
                        <ArrowRight size={13} className="shrink-0 opacity-60" />
                      )}
                    </button>
                  );
                })}
              </div>
            )}

            {clarification.allowCustom && (
              <form
                className="mt-2.5 flex items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  const value = typed.trim();
                  if (value) void submit(value);
                }}
              >
                <textarea
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  rows={2}
                  placeholder="Or type your answer…"
                  disabled={busy}
                  className="min-h-[38px] w-full resize-none rounded-xl border border-border/40 bg-background/40 px-3 py-2 text-xs text-foreground outline-none placeholder:text-muted-foreground focus:border-primary/40"
                />
                <button
                  type="submit"
                  disabled={busy || !typed.trim()}
                  className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-xl bg-primary px-3 py-2 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                >
                  {busy ? <Loader2 size={13} className="animate-spin" /> : <ArrowRight size={13} />}
                  Send
                </button>
              </form>
            )}

            <div className="mt-2.5 flex items-center gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => void submit('')}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-border/40 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent/30 hover:text-foreground disabled:opacity-50"
              >
                <Sparkles size={13} />
                Let Eclipse decide
              </button>
              <span className="ml-auto text-[10px] text-muted-foreground">
                Your answer continues this run; it does not approve any action.
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
