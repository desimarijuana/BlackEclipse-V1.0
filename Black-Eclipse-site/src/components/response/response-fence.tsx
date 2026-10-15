'use client';

// ── ResponseFence — renders an ```eclipse-response fence ──────────────────────
// The single bridge between ordinary Markdown and the structured response
// engine. While a turn is streaming, an incomplete JSON body shows a small
// "composing" placeholder instead of an error; once the turn is settled, a
// malformed body renders an explicit diagnostic (never a fake answer).

import { useMemo } from 'react';
import { decodeResponseFence } from '@/lib/response/parse';
import { finalizeFenceSource } from '@/lib/response/finalize';
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

  // Settled + malformed JSON: degrade to readable content rather than an error
  // card. The chokepoint shows the raw source as a code fence so the answer is
  // never gutted, and the failure is reported for telemetry — never surfaced as
  // a parse error.
  return <ResponseView response={finalizeFenceSource(source).response} compact={compact} onFollowup={onFollowup} />;
}

export default ResponseFence;
