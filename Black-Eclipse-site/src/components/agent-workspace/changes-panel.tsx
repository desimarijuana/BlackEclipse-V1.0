'use client';

// ── Agent Workspace — Changes panel ───────────────────────────────────────────
// Live file changes, grouped by kind. A row carrying the runtime's bounded
// preview expands inline to show the change (the shared DiffLines rendering the
// chat cards use); a row without one opens the runtime's diff artifact in the
// shared Viewer. No duplicate editor, no re-derived diff.

import { useState } from 'react';
import { ChevronRight, FileText } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { FileChange } from '@/lib/agent-workspace/types';
import { changeMark } from '@/lib/agent-workspace/format';
import { DiffLines } from '@/components/chat/change-cards';

const TONE: Record<FileChange['change'], string> = {
  added: 'text-emerald-400',
  modified: 'text-amber-400',
  deleted: 'text-rose-400',
  renamed: 'text-sky-400',
};

export function ChangesPanel({
  changes,
  onOpenDiff,
}: {
  changes: FileChange[];
  onOpenDiff?: (change: FileChange) => void;
}) {
  const t = useT();
  if (changes.length === 0) {
    return <p className="px-1 py-3 text-[12px] text-muted-foreground/50">{t('workspace.empty')}</p>;
  }
  return (
    <div className="space-y-1">
      <p className="px-0.5 text-[11px] text-muted-foreground/60 tabular-nums">
        {changes.length} {t('workspace.filesChanged')}
      </p>
      <ul className="space-y-0.5">
        {changes.map((change) => (
          <ChangeRow key={change.path} change={change} onOpenDiff={onOpenDiff} />
        ))}
      </ul>
    </div>
  );
}

function ChangeRow({
  change,
  onOpenDiff,
}: {
  change: FileChange;
  onOpenDiff?: (change: FileChange) => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const expandable = Boolean(change.diff);
  const handleClick = () => {
    if (expandable) setOpen((v) => !v);
    else onOpenDiff?.(change);
  };
  return (
    <li>
      <button
        type="button"
        onClick={handleClick}
        aria-expanded={expandable ? open : undefined}
        className={cn(
          'flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left text-[12px]',
          (expandable || onOpenDiff) && 'cursor-pointer hover:bg-accent/40',
        )}
        title={change.path}
      >
        <span className={cn('w-3 shrink-0 font-mono text-[11px] font-bold', TONE[change.change])}>
          {changeMark(change.change)}
        </span>
        <FileText size={11} className="shrink-0 text-muted-foreground/40" />
        <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-foreground/80">{change.path}</span>
        {(change.additions != null || change.deletions != null) && (
          <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/50">
            {change.additions != null && <span className="text-emerald-400/70">+{change.additions}</span>}
            {change.additions != null && change.deletions != null && ' '}
            {change.deletions != null && <span className="text-rose-400/70">-{change.deletions}</span>}
          </span>
        )}
        {expandable ? (
          <ChevronRight
            size={11}
            className={cn('shrink-0 text-muted-foreground/40 transition-transform', open && 'rotate-90')}
          />
        ) : null}
      </button>
      {open && change.diff && (
        <div className="ml-6 mt-0.5 space-y-0.5 pb-1">
          <div className="max-h-56 overflow-auto rounded-lg border border-white/10 dark:border-white/5">
            <DiffLines text={change.diff} />
          </div>
          {change.truncated && (
            <p className="text-[10.5px] text-amber-300/80">{t('chat.change.truncated')}</p>
          )}
        </div>
      )}
    </li>
  );
}
