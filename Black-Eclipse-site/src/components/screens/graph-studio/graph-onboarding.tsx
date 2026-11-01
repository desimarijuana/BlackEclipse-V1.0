'use client';

// ── First-run tour ────────────────────────────────────────────────────────────
// Three cards, once per browser. It exists because the canvas is readable only
// after someone has told you the two conventions (labels describe ports; round =
// value, square = branch). Dismissing it writes a localStorage flag; the same
// information stays available in the canvas `?` panel, so nothing is lost.
//
// Deliberately NOT a spotlight/coach-mark library: no dependency, no focus trap,
// no state machine. It must never block editing — the card is `pointer-events-auto`
// only on itself.

import { useEffect, useState } from 'react';
import { X } from '@/lib/icons';
import { cn } from '@/lib/utils';

const STORAGE_KEY = 'be_graph_tour_v1';

const STEPS: Array<{ title: string; body: string }> = [
  {
    title: 'A node is one step',
    body: 'The subtitle says what the step does. Double-click it for the full form, its ports and a worked example.',
  },
  {
    title: 'Connectors are labelled',
    body: 'Round handles carry values; square handles are branches (run control). The label beside each one is the port name — "If true", "Items", "Done".',
  },
  {
    title: 'Run it safely',
    body: 'Start workflow performs a TEST run: it reads and computes, but never writes a file, trades, or uses the network.',
  },
];

export function GraphOnboarding() {
  const [visible, setVisible] = useState(false);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    try {
      if (window.localStorage.getItem(STORAGE_KEY) !== 'done') setVisible(true);
    } catch {
      // Storage can be unavailable (private mode); the tour is optional.
    }
  }, []);

  const finish = () => {
    try {
      window.localStorage.setItem(STORAGE_KEY, 'done');
    } catch {
      // Ignore: the tour simply shows again next session.
    }
    setVisible(false);
  };

  if (!visible) return null;
  const step = STEPS[index];
  const last = index === STEPS.length - 1;

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-3 z-20 flex justify-center px-3">
      <div className="glass-card pointer-events-auto w-full max-w-[430px] rounded-xl p-3">
        <div className="mb-1.5 flex items-center gap-2">
          <span className="text-[9.5px] font-semibold uppercase tracking-wider text-muted-foreground">
            Quick tour · {index + 1}/{STEPS.length}
          </span>
          <span className="ml-auto flex items-center gap-1">
            {STEPS.map((_, dot) => (
              <span
                key={dot}
                className={cn(
                  'h-1.5 w-1.5 rounded-full',
                  dot === index ? 'bg-primary' : 'bg-muted-foreground/30',
                )}
              />
            ))}
          </span>
          <button
            type="button"
            onClick={finish}
            title="Close the tour"
            aria-label="Close the tour"
            className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/10 hover:text-foreground"
          >
            <X size={12} />
          </button>
        </div>
        <p className="text-[12.5px] font-semibold text-foreground">{step.title}</p>
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{step.body}</p>
        <div className="mt-2.5 flex items-center gap-2">
          <button
            type="button"
            onClick={finish}
            className="text-[10.5px] text-muted-foreground transition-colors hover:text-foreground"
          >
            Skip
          </button>
          <span className="ml-auto flex items-center gap-1.5">
            {index > 0 && (
              <button
                type="button"
                onClick={() => setIndex((value) => Math.max(0, value - 1))}
                className="rounded-md border border-white/10 px-2 py-1 text-[10.5px] text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground"
              >
                Back
              </button>
            )}
            <button
              type="button"
              onClick={() => (last ? finish() : setIndex((value) => value + 1))}
              className="rounded-md border border-primary/40 bg-primary/15 px-2.5 py-1 text-[10.5px] font-medium text-primary transition-colors hover:bg-primary/25"
            >
              {last ? 'Got it' : 'Next'}
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}
