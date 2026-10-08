'use client';

// ── Agent Workspace — Changes panel ───────────────────────────────────────────
// Live file changes, grouped by kind. A row opens the runtime's diff artifact in
// the shared Viewer (no duplicate editor). Clicking a file reveals its unified
// diff on demand from the persisted tool execution when available.

import { FileText } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n';
import type { FileChange } from '@/lib/agent-workspace/types';
import { changeMark } from '@/lib/agent-workspace/format';

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
          <li key={change.path}>
            <button
              type="button"
              onClick={() => onOpenDiff?.(change)}
              className={cn(
                'flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left text-[12px]',
                onOpenDiff && 'cursor-pointer hover:bg-accent/40',
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
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
