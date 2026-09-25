'use client';

// ── Memory-action panel ─────────────────────────────────────────────────────
// A compact, always-visible line under an assistant turn that makes the
// memory/skill outcome of the run observable from the originating chat:
//   * what was remembered/forgotten/corrected (with inspect + undo),
//   * a refusal or a confirmation request (honest, never a silent save),
//   * learning eligibility + a link to the Learning Queue.
//
// Presentation only — all logic lives in `lib/chat/memory-action.ts`.

import { useState } from 'react';
import { Brain, Check, Info, ListChecks, Loader2, RotateCcw, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils';
import { buildMemoryRunView } from '@/lib/chat/memory-action';
import { learnFromRun } from '@/lib/harness/skills-browser';

const ACTION_META: Record<string, { icon: typeof Check; tone: string; label: string }> = {
  saved: { icon: Check, tone: 'text-emerald-400', label: 'Remembered' },
  forgotten: { icon: RotateCcw, tone: 'text-muted-foreground', label: 'Forgotten' },
  corrected: { icon: Check, tone: 'text-sky-400', label: 'Corrected' },
  refused: { icon: ShieldAlert, tone: 'text-amber-500', label: 'Not saved' },
  needs_confirmation: { icon: Info, tone: 'text-amber-500', label: 'Confirmation needed' },
  needs_clarification: { icon: Info, tone: 'text-amber-500', label: 'Which memory?' },
  needs_review: { icon: ShieldAlert, tone: 'text-amber-500', label: 'Conflicts — needs review' },
  memory_full: { icon: ShieldAlert, tone: 'text-amber-500', label: 'Memory is full' },
  suggested: { icon: Info, tone: 'text-sky-400', label: 'Not saved — suggestion' },
  skill_requested: { icon: ListChecks, tone: 'text-primary', label: 'Ready to learn' },
};

export function MemoryActionPanel({
  memory,
  runId,
  compact = false,
}: {
  memory: unknown;
  runId?: string;
  compact?: boolean;
}) {
  const [learnState, setLearnState] = useState<'idle' | 'busy' | 'done' | 'error'>('idle');
  const [learnMessage, setLearnMessage] = useState<string | null>(null);
  const view = buildMemoryRunView(memory);
  if (!view) return null;
  const { action, eligibility } = view;
  // Show the panel only when the run took a memory action or produced a genuine
  // learning outcome (an automatic candidate, an explicit skill draft, or an
  // explicit skill request that could not be captured). Ordinary informational
  // replies — and merely "eligible" runs — stay uncluttered: eligibility is
  // still recorded on the run and readable via /api/learning/eligibility/:runId.
  const hasLearningOutcome = Boolean(
    eligibility &&
      (eligibility.autoCaptured ||
        eligibility.skillDraftReady ||
        eligibility.skillRequested),
  );
  if (!action && !hasLearningOutcome) return null;

  const handleLearn = async () => {
    if (!runId || learnState === 'busy') return;
    setLearnState('busy');
    try {
      const result = await learnFromRun(runId, 'turn this into a skill');
      if (result.ok && (result.created?.length ?? 0) > 0) {
        setLearnState('done');
        setLearnMessage(`Captured ${result.created.length} learning candidate(s)`);
      } else if (result.duplicates?.length) {
        setLearnState('done');
        setLearnMessage('Already captured — see the Learning Queue');
      } else {
        setLearnState('error');
        setLearnMessage(result.error ?? 'No candidate could be created from this run');
      }
    } catch (err) {
      setLearnState('error');
      setLearnMessage(err instanceof Error ? err.message : 'learning capture failed');
    }
  };

  return (
    <div
      className={cn(
        'mt-2 flex w-full flex-col gap-1 rounded-2xl border border-white/10 px-3 py-2 dark:border-white/8 glass-card-subtle',
        compact ? 'text-[11px]' : 'text-xs',
      )}
    >
      {action && (() => {
        const meta = ACTION_META[action.kind] ?? ACTION_META.saved;
        const Icon = meta.icon;
        return (
          <div className="flex flex-wrap items-center gap-2">
            <Icon className={cn('h-3.5 w-3.5 shrink-0', meta.tone)} />
            <span className={cn('font-semibold', meta.tone)}>{action.headline}</span>
            {(action.memoryType || action.scope) && (
              <span className="text-muted-foreground/80">
                {[action.memoryType, action.scope, action.subject].filter(Boolean).join(' · ')}
              </span>
            )}
            {action.preview && (
              <span className="w-full text-muted-foreground/90">{action.preview}</span>
            )}
            {action.reason && (
              <span className="w-full text-muted-foreground/70">{action.reason}</span>
            )}
            {action.inspectPath && (
              <a
                href={action.inspectPath}
                className="text-primary underline-offset-2 hover:underline"
                target="_blank"
                rel="noreferrer"
              >
                Inspect
              </a>
            )}
            {action.undoPath && (
              <a
                href={action.undoPath}
                className="text-muted-foreground underline-offset-2 hover:underline"
                target="_blank"
                rel="noreferrer"
              >
                Undo
              </a>
            )}
            {action.kind === 'suggested' && (
              <a
                href={action.suggestionPath ?? '/api/eclipse-memory/suggestions'}
                className="text-primary underline-offset-2 hover:underline"
                target="_blank"
                rel="noreferrer"
              >
                Review suggestion
              </a>
            )}
          </div>
        );
      })()}

      {eligibility && (() => {
        // A quiet outcome line. No button is shown for an ordinary, merely
        // "eligible" run — only a genuine automatic capture or an explicit
        // skill draft/request produces a learning line, so the user is never
        // asked to learn after every run.
        const captured = eligibility.autoCaptured || eligibility.skillDraftReady;
        return (
          <div className="flex flex-wrap items-center gap-2 text-muted-foreground/80">
            {captured ? (
              <Brain className="h-3.5 w-3.5 shrink-0 text-primary/80" />
            ) : (
              <ListChecks className="h-3.5 w-3.5 shrink-0 text-primary/80" />
            )}
            <span>
              {eligibility.skillDraftReady
                ? `Draft skill created for review — ${eligibility.reason}`
                : eligibility.autoCaptured
                  ? `Automatically captured as a learning candidate${eligibility.candidatesCreated > 1 ? ` (${eligibility.candidatesCreated})` : ''} — ${eligibility.reason}`
                  : `Skill request noted — ${eligibility.reason}`}
            </span>
            {captured ? (
              <a
                href={eligibility.learnQueuePath}
                className="text-primary underline-offset-2 hover:underline"
                target="_blank"
                rel="noreferrer"
              >
                Review in Learning Queue
              </a>
            ) : runId && (
              <button
                type="button"
                onClick={handleLearn}
                disabled={learnState === 'busy' || learnState === 'done'}
                className={cn(
                  'inline-flex items-center gap-1 rounded-lg border border-white/10 px-2 py-0.5 transition-colors hover:bg-white/5',
                  'text-primary disabled:opacity-60',
                )}
              >
                {learnState === 'busy' && <Loader2 className="h-3 w-3 animate-spin" />}
                {learnState === 'done' ? 'Learned' : 'Create skill draft'}
              </button>
            )}
            {learnMessage && <span className="w-full text-muted-foreground/70">{learnMessage}</span>}
          </div>
        );
      })()}
    </div>
  );
}
