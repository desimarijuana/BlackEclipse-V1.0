'use client';

// ── ChangeCards — the files an assistant turn changed, with their previews ───
// The "here is exactly what I changed" surface: one card per file carrying its
// path, +N/−M (only when the runtime reported counts) and the unified diff the
// runtime emitted — never a re-derived diff, never a fabricated count.
//
// The text is bounded and secret-scrubbed by the runtime; when it was capped
// the card says so instead of pretending it has the whole change. `DiffLines`
// is the shared body — the same colored rendering the chat's ```diff fences
// use — reused by the Agent Workspace's Changes panel.

import { useState } from 'react';
import { ChevronRight, FileCode2 } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import type { TurnChange } from '@/lib/agent/response-model';

const MARK: Record<TurnChange['change'], string> = {
  added: 'A',
  modified: 'M',
  deleted: 'D',
  renamed: 'R',
};

const MARK_TONE: Record<TurnChange['change'], string> = {
  added: 'text-emerald-400',
  modified: 'text-amber-400',
  deleted: 'text-rose-400',
  renamed: 'text-sky-400',
};

/**
 * The colored body of a unified diff — the ONE renderer shared by the chat
 * cards and the workspace Changes panel. Renders the runtime's text verbatim:
 * only diff-significant prefixes are styled, everything else passes through.
 */
export function DiffLines({ text, className }: { text: string; className?: string }) {
  return (
    <pre className={cn('overflow-x-auto whitespace-pre font-mono text-[11px] leading-[1.55]', className)}>
      {text.split('\n').map((line, i) => (
        <span
          key={i}
          className={cn(
            'block px-2',
            line.startsWith('+') && !line.startsWith('+++') && 'bg-emerald-500/10 text-emerald-300',
            line.startsWith('-') && !line.startsWith('---') && 'bg-rose-500/10 text-rose-300',
            line.startsWith('@@') && 'text-sky-300/80',
            (line.startsWith('+++') || line.startsWith('---')) && 'text-muted-foreground/50',
          )}
        >
          {line || ' '}
        </span>
      ))}
    </pre>
  );
}

function ChangeCard({ change, compact }: { change: TurnChange; compact: boolean }) {
  const t = useT();
  const [open, setOpen] = useState(true);
  const label = change.path.split(/[\\/]/).pop() ?? change.path;

  return (
    <div className="glass-card-subtle w-full overflow-hidden rounded-xl border border-white/10 dark:border-white/5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left transition-colors hover:bg-white/[0.04]"
        title={change.path}
      >
        <span className={cn('w-3 shrink-0 font-mono text-[11px] font-bold', MARK_TONE[change.change])}>
          {MARK[change.change]}
        </span>
        <FileCode2 size={12} className="shrink-0 text-muted-foreground/50" />
        <span className="min-w-0 truncate font-mono text-[11.5px] text-foreground/85">{label}</span>
        {change.change === 'renamed' && change.from && (
          <span className="min-w-0 truncate text-[10.5px] text-muted-foreground/50">
            {t('chat.change.renamedFrom', { path: change.from })}
          </span>
        )}
        <span className="ml-auto flex shrink-0 items-center gap-2">
          {change.edits != null && change.edits > 1 && (
            <span className="text-[10.5px] text-muted-foreground/50">
              {t('chat.change.edits', { count: change.edits })}
            </span>
          )}
          {(change.additions != null || change.deletions != null) && (
            <span className="font-mono text-[10px] tabular-nums">
              {change.additions != null && <span className="text-emerald-400/80">+{change.additions}</span>}
              {change.additions != null && change.deletions != null && ' '}
              {change.deletions != null && <span className="text-rose-400/80">-{change.deletions}</span>}
            </span>
          )}
          <ChevronRight size={11} className={cn('text-muted-foreground/40 transition-transform', open && 'rotate-90')} />
        </span>
      </button>

      {open && change.diff && (
        <div className="border-t border-white/10 dark:border-white/5">
          <div className={cn('overflow-auto', compact ? 'max-h-56' : 'max-h-80')}>
            <DiffLines text={change.diff} />
          </div>
          {change.truncated && (
            <p className="border-t border-white/10 px-2.5 py-1 text-[10.5px] text-amber-300/80 dark:border-white/5">
              {t('chat.change.truncated')}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** All of a turn's changes, in arrival order (one card per file). */
export function ChangeCards({ changes, compact = false }: { changes: TurnChange[]; compact?: boolean }) {
  if (changes.length === 0) return null;
  return (
    <div className="mb-2 w-full space-y-1.5">
      {changes.map((change) => (
        <ChangeCard key={change.path} change={change} compact={compact} />
      ))}
    </div>
  );
}
