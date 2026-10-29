'use client';

// ── Spec card — the one place a strategy is authored ────────────────────────
// Two views over the SAME text: a no-code builder and the JSON editor. The JSON
// is authoritative; the builder writes a new JSON string back. Validation
// issues are listed here with copyable paths.

import React, { useState } from 'react';
import type { StrategyRecord } from '@/lib/backtest/backtest-client';
import { SpecBuilder } from './spec-builder';
import { Copy, Loader2, Play } from '@/lib/icons';
import { cn } from '@/lib/utils';

export interface Issue {
  code: string;
  message: string;
  path?: string;
  severity?: string;
}

function Issues({ issues, onCopy }: { issues: Issue[]; onCopy: (path: string) => void }) {
  if (!issues.length) return null;
  return (
    <ul className="space-y-1">
      {issues.map((issue, index) => (
        <li
          key={`${issue.code}-${index}`}
          className={cn(
            'rounded-lg border px-2.5 py-1.5 text-[11px]',
            issue.severity === 'warning'
              ? 'border-amber-500/25 bg-amber-500/10 text-amber-200'
              : 'border-rose-500/25 bg-rose-500/10 text-rose-200',
          )}
        >
          <span className="font-mono text-[10px]">{issue.code}</span>
          {issue.path ? (
            <button
              type="button"
              onClick={() => onCopy(issue.path!)}
              title="Copy this spec path"
              className="ml-1 inline-flex items-center gap-0.5 rounded font-mono text-[10px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            >
              {issue.path}
              <Copy className="h-2.5 w-2.5" />
            </button>
          ) : null}
          <span className="block">{issue.message}</span>
        </li>
      ))}
    </ul>
  );
}

export function SpecCard({
  editor,
  onEditor,
  spec,
  identityId,
  saved,
  issues,
  copiedPath,
  onCopyPath,
  onValidate,
  onSaveAndRun,
  busy,
  saving,
  running,
  progress,
}: {
  editor: string;
  onEditor: (text: string) => void;
  spec: Record<string, unknown> | null;
  identityId: string;
  saved: StrategyRecord | null;
  issues: Issue[];
  copiedPath: string | null;
  onCopyPath: (path: string) => void;
  onValidate: () => void;
  onSaveAndRun: () => void;
  busy: boolean;
  saving: boolean;
  running: boolean;
  progress: { stage: string; percent: number } | null;
}) {
  const [view, setView] = useState<'builder' | 'json'>(spec ? 'builder' : 'json');

  return (
    <div className="glass-card rounded-2xl p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Strategy spec</h2>
        {identityId ? (
          <span className="rounded-md border border-white/10 px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
            {identityId}
          </span>
        ) : null}
        {saved ? (
          <span className="rounded-md border border-emerald-500/30 px-2 py-0.5 font-mono text-[10px] text-emerald-400">
            saved v{saved.version ?? saved.latestVersion}
          </span>
        ) : null}
        {spec && issues.length === 0 ? (
          <span className="font-mono text-[10px] text-emerald-400/80">valid</span>
        ) : null}
        {copiedPath ? (
          <span className="ml-auto font-mono text-[10px] text-muted-foreground">copied {copiedPath}</span>
        ) : null}

        <div className="ml-auto flex items-center gap-1">
          {(['builder', 'json'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setView(mode)}
              className={cn(
                'rounded-md px-2 py-0.5 text-[10px] capitalize transition',
                view === mode
                  ? 'bg-primary/15 text-foreground ring-1 ring-primary/30'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {view === 'builder' ? (
        spec ? (
          <div className="max-h-[520px] overflow-y-auto pr-1">
            <SpecBuilder
              spec={spec}
              disabled={busy}
              onChange={(next) => onEditor(JSON.stringify(next, null, 2))}
            />
          </div>
        ) : (
          <p className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">
            The editor does not contain a JSON object. Fix it in the JSON tab, then switch back.
          </p>
        )
      ) : (
        <textarea
          value={editor}
          onChange={(event) => onEditor(event.target.value)}
          rows={16}
          spellCheck={false}
          className="w-full resize-y rounded-xl border border-white/10 bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground focus:border-primary/40"
          placeholder="Draft a thesis, or paste a strategy spec here."
        />
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onValidate}
          disabled={busy || !spec}
          className="glass-button rounded-lg px-3 py-1.5 text-xs disabled:opacity-50"
        >
          Validate
        </button>
        <button
          type="button"
          onClick={onSaveAndRun}
          disabled={busy || !spec}
          className="glass-button-add flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
        >
          {saving || running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          Save and run backtest
        </button>
        {running && progress ? (
          <span className="font-mono text-[10px] text-muted-foreground">
            {progress.stage} {Math.round(progress.percent)}%
          </span>
        ) : null}
      </div>
      <div className="mt-2">
        <Issues issues={issues} onCopy={onCopyPath} />
      </div>
    </div>
  );
}
