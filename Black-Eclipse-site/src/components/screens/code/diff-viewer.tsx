'use client';

// ── Diff viewer (Phase 5) ───────────────────────────────────────────────────
// The change, described in everyday words, with the raw text and digest behind a
// "details" affordance. It never leads with a diff hunk or a tree digest.

import { useState } from 'react';
import { ChevronRight } from '@/lib/icons';
import { useT } from '@/lib/i18n/use-t';
import { cn } from '@/lib/utils';
import { splitUnifiedDiff } from '@/lib/code/diff-sections';

export interface DiffViewerProps {
  files: string[];
  unified?: string;
  digest?: string | null;
}

export function DiffViewer({ files, unified, digest }: DiffViewerProps) {
  const t = useT();
  const [showDetails, setShowDetails] = useState(false);
  const sections = splitUnifiedDiff(unified ?? '');
  return (
    <div className="glass-card-subtle rounded-xl border border-border/40 p-3 text-[12px]">
      <ul className="space-y-0.5">
        {files.map((name) => (
          <li key={name} className="text-muted-foreground">{t('code.task.changeEditedFile', { name })}</li>
        ))}
      </ul>
      <button
        type="button"
        onClick={() => setShowDetails((v) => !v)}
        className="mt-2 flex items-center gap-1 text-[11px] text-muted-foreground/60"
      >
        <ChevronRight size={11} className={cn('transition-transform', showDetails && 'rotate-90')} />
        {t('code.proof.details')}
      </button>
      {showDetails && (
        <div className="mt-1 space-y-1">
          {sections.length > 0 ? sections.map((section) => (
            <details key={section.path} className="rounded-lg bg-background/40">
              <summary className="cursor-pointer px-2 py-1 font-mono text-[10.5px] text-muted-foreground/80">
                {section.path}
              </summary>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap px-2 pb-2 font-mono text-[10.5px] text-muted-foreground/70">
                {section.text}
              </pre>
            </details>
          )) : (
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-background/40 p-2 font-mono text-[10.5px] text-muted-foreground/70">
              {unified || '—'}
            </pre>
          )}
          {digest ? (
            <div className="font-mono text-[10px] text-muted-foreground/50">{digest}</div>
          ) : null}
        </div>
      )}
    </div>
  );
}
