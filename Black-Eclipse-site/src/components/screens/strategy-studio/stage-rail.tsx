'use client';

// ── Stage rail ──────────────────────────────────────────────────────────────
// Five honest stages: an idea is not a strategy, a backtest is not proof, and
// paper is not live. The rail always shows where the workspace is and what the
// next step is, so the screen never looks finished when it is not.

import React from 'react';
import { Check } from '@/lib/icons';
import { cn } from '@/lib/utils';

export type StudioStage = 'idea' | 'spec' | 'test' | 'prove' | 'track';

/** The one place the rail's "current stage" is decided. */
export function computeStudioStage(input: {
  paper: boolean;
  proved: boolean;
  result: boolean;
  specValid: boolean;
}): StudioStage {
  if (input.paper) return 'track';
  if (input.proved) return 'prove';
  if (input.result) return 'test';
  if (input.specValid) return 'spec';
  return 'idea';
}

/** The stages that have been satisfied (the rail draws a check for each). */
export function computeCompleted(input: {
  hasPrompt: boolean;
  specValid: boolean;
  result: boolean;
  proved: boolean;
  paper: boolean;
}): StudioStage[] {
  const done: StudioStage[] = [];
  if (input.hasPrompt) done.push('idea');
  if (input.specValid) done.push('spec');
  if (input.result) done.push('test');
  if (input.proved) done.push('prove');
  if (input.paper) done.push('track');
  return done;
}

export const STUDIO_STAGES: Array<{ id: StudioStage; label: string; hint: string }> = [
  { id: 'idea', label: 'Idea', hint: 'Describe the thesis' },
  { id: 'spec', label: 'Spec', hint: 'Draft, then validate' },
  { id: 'test', label: 'Test', hint: 'Run the backtest' },
  { id: 'prove', label: 'Prove', hint: 'Robustness and edge grade' },
  { id: 'track', label: 'Track', hint: 'Paper shadow run' },
];

export function StageRail({ current, completed }: { current: StudioStage; completed: StudioStage[] }) {
  const done = new Set(completed);
  return (
    <nav className="glass-card-subtle flex flex-wrap items-center gap-1 rounded-2xl px-3 py-2" aria-label="Studio stages">
      {STUDIO_STAGES.map((stage, index) => {
        const active = stage.id === current;
        const complete = done.has(stage.id) && !active;
        return (
          <React.Fragment key={stage.id}>
            {index > 0 ? <span className="px-0.5 text-[10px] text-muted-foreground/40">→</span> : null}
            <span
              aria-current={active ? 'step' : undefined}
              title={stage.hint}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] transition',
                active && 'bg-primary/15 text-foreground ring-1 ring-primary/30',
                complete && 'text-emerald-400/90',
                !active && !complete && 'text-muted-foreground',
              )}
            >
              <span
                className={cn(
                  'flex h-4 w-4 items-center justify-center rounded-full border font-mono text-[9px]',
                  active && 'border-primary/50 text-primary',
                  complete && 'border-emerald-500/40 text-emerald-400',
                  !active && !complete && 'border-white/15',
                )}
              >
                {complete ? <Check className="h-2.5 w-2.5" /> : index + 1}
              </span>
              {stage.label}
            </span>
          </React.Fragment>
        );
      })}
      <span className="ml-auto hidden font-mono text-[9px] text-muted-foreground/60 sm:block">
        paper only · live routing disabled
      </span>
    </nav>
  );
}
