'use client';

// ── Share card ──────────────────────────────────────────────────────────────
// A read-only summary you can copy as Markdown. It is the same data the studio
// already shows — identity, window, metrics, grade, paper state — with the
// disclaimer attached. The link opens this local workspace; it is not a hosted
// page.

import React, { useState } from 'react';
import { MetricGrid } from '@/components/screens/backtest/shared/metric-grid';
import { copyText } from '@/lib/desktop/clipboard';
import { buildShareCardMarkdown, type ShareCardInput } from '@/lib/strategy-studio/share-card';
import { Check, Copy, FileText, Link2 } from '@/lib/icons';
import { cn } from '@/lib/utils';

export function ShareCard({ input }: { input: ShareCardInput }) {
  const [copied, setCopied] = useState<'markdown' | 'link' | null>(null);
  const markdown = buildShareCardMarkdown(input);

  const copy = async (kind: 'markdown' | 'link') => {
    const text = kind === 'markdown' ? markdown : input.link ?? '';
    if (!text) return;
    // The text stays visible below, so a failed copy needs no error surface.
    if (!(await copyText(text))) return;
    setCopied(kind);
    setTimeout(() => setCopied(null), 1500);
  };

  return (
    <details className="glass-card rounded-2xl p-4">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 text-sm font-semibold">
        <FileText className="h-4 w-4 text-primary" />
        Share card
        <span className="font-mono text-[10px] font-normal text-muted-foreground">
          {input.name} · v{input.version}
        </span>
        <span className="ml-auto font-mono text-[10px] font-normal text-muted-foreground">
          read-only · copy as Markdown
        </span>
      </summary>

      <div className="mt-3 flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] text-muted-foreground">
          {input.symbols.length ? <span>{input.symbols.join(', ')}</span> : null}
          {input.timeframe ? <span>{input.timeframe}</span> : null}
          {input.start && input.end ? (
            <span>
              {input.start} → {input.end}
            </span>
          ) : null}
        </div>

        {input.metrics ? <MetricGrid metrics={input.metrics} /> : null}

        <div className="flex flex-wrap items-center gap-2">
          {input.grade ? (
            <span className="rounded-md border border-primary/40 bg-primary/10 px-2 py-0.5 font-mono text-[10px] text-primary">
              grade {input.grade}
              {input.score != null ? ` · ${Math.round(input.score)}/100` : ''}
            </span>
          ) : null}
          {input.paper ? (
            <span
              className={cn(
                'rounded-md border px-2 py-0.5 font-mono text-[10px] uppercase',
                input.paper.state === 'fresh'
                  ? 'border-emerald-500/30 text-emerald-400'
                  : input.paper.state === 'drifting'
                    ? 'border-rose-500/30 text-rose-400'
                    : 'border-amber-500/30 text-amber-400',
              )}
            >
              paper {input.paper.state}
            </span>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void copy('markdown')}
            className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px]"
          >
            {copied === 'markdown' ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            {copied === 'markdown' ? 'Copied' : 'Copy Markdown'}
          </button>
          {input.link ? (
            <button
              type="button"
              onClick={() => void copy('link')}
              className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px]"
            >
              {copied === 'link' ? <Check className="h-3 w-3" /> : <Link2 className="h-3 w-3" />}
              {copied === 'link' ? 'Copied' : 'Copy link'}
            </button>
          ) : null}
        </div>

        <details className="text-[11px] text-muted-foreground">
          <summary className="cursor-pointer select-none">Markdown</summary>
          <pre className="mt-1 max-h-[260px] overflow-auto whitespace-pre-wrap rounded-lg bg-black/25 p-2 font-mono text-[10px] leading-relaxed">
            {markdown}
          </pre>
        </details>
      </div>
    </details>
  );
}
