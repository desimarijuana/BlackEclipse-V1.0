'use client';

// ── ResponseFence — renders an ```eclipse-response fence ──────────────────────
// The single bridge between ordinary Markdown and the structured response
// engine. While a turn is streaming, an incomplete JSON body shows a small
// "composing" placeholder instead of an error; once the turn is settled, a
// malformed body renders an explicit diagnostic (never a fake answer).

import { useMemo } from 'react';
import { AlertTriangle } from '@/lib/icons';
import { decodeResponseFence } from '@/lib/response/parse';
import { ResponseView } from './response-view';

export interface ResponseFenceProps {
  source: string;
  /** True while the turn is still streaming (see `Markdown` `streaming` prop). */
  streaming?: boolean;
  compact?: boolean;
  /** Called when a controls block submits — re-enters the chat's agent loop. */
  onFollowup?: (prompt: string) => void;
}

export function ResponseFence({ source, streaming = false, compact = false, onFollowup }: ResponseFenceProps) {
  const result = useMemo(() => decodeResponseFence(source, !streaming), [source, streaming]);

  if (result.status === 'ok') {
    return <ResponseView response={result.response} compact={compact} onFollowup={onFollowup} />;
  }

  if (result.status === 'empty') return null;

  if (result.status === 'incomplete') {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-accent/10 px-3 py-2.5 text-[12px] text-muted-foreground">
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
        Composing structured response…
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-rose-500/30 bg-rose-500/[0.06] px-3 py-2 text-[12px] text-rose-200/90">
      <div className="flex items-center gap-1.5 font-medium">
        <AlertTriangle size={13} />
        The structured response could not be parsed.
      </div>
      <p className="mt-0.5 font-mono text-[10px] opacity-70">{result.error}</p>
      {source.trim() && (
        <details className="mt-1.5">
          <summary className="cursor-pointer select-none text-[11px] opacity-80">Show the raw content</summary>
          <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-black/20 p-2 font-mono text-[10px] leading-relaxed text-rose-100/80">
            {source}
          </pre>
        </details>
      )}
    </div>
  );
}

export default ResponseFence;
