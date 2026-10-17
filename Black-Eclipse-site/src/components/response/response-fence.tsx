'use client';

// ── ResponseFence — renders an ```eclipse-response fence ──────────────────────
// The single bridge between ordinary Markdown and the structured response
// engine. While a turn is streaming, an incomplete JSON body shows a small
// "composing" placeholder instead of an error; once the turn is settled, a
// malformed body renders an explicit diagnostic (never a fake answer).

import { useEffect, useMemo, useRef } from 'react';
import { decodeResponseFence } from '@/lib/response/parse';
import { decodeResponseFenceStreaming } from '@/lib/response/stream-blocks';
import { finalizeFenceSource } from '@/lib/response/finalize';
import { reportResponseTelemetry } from '@/lib/response/telemetry';
import { ResponseView } from './response-view';

function Composing() {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-accent/10 px-3 py-2.5 text-[12px] text-muted-foreground">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
      Composing structured response…
    </div>
  );
}

export interface ResponseFenceProps {
  source: string;
  /** True while the turn is still streaming (see `Markdown` `streaming` prop). */
  streaming?: boolean;
  compact?: boolean;
  /** Called when a controls block submits — re-enters the chat's agent loop. */
  onFollowup?: (prompt: string) => void;
}

export function ResponseFence({ source, streaming = false, compact = false, onFollowup }: ResponseFenceProps) {
  // While streaming, render each block the moment it closes (never a half-written
  // block): completed blocks appear progressively and only the open tail shows
  // the placeholder. Once settled, the authoritative full parse runs.
  const streamed = useMemo(
    () => (streaming ? decodeResponseFenceStreaming(source) : null),
    [source, streaming],
  );
  const settled = useMemo(
    () => (streaming ? null : decodeResponseFence(source, true)),
    [source, streaming],
  );

  // Time-to-first-block: measured from the fence's first mount to the first block
  // it renders. Reported once, client-side (never in a static render).
  const startedAt = useRef<number | null>(null);
  if (startedAt.current === null && typeof performance !== 'undefined') startedAt.current = performance.now();
  const firstReported = useRef(false);
  useEffect(() => {
    const hasBlocks =
      (streaming && streamed && (streamed.kind === 'partial' || streamed.kind === 'ok')) ||
      (!streaming && settled?.status === 'ok');
    if (hasBlocks && !firstReported.current && startedAt.current != null) {
      firstReported.current = true;
      reportResponseTelemetry({
        event: 'first_block',
        timeToFirstBlockMs: Math.max(0, performance.now() - startedAt.current),
      });
    }
  }, [streaming, streamed, settled]);

  if (streaming && streamed) {
    if (streamed.kind === 'empty') return null;
    if (streamed.kind === 'ok') {
      return <ResponseView response={streamed.response} compact={compact} onFollowup={onFollowup} />;
    }
    if (streamed.kind === 'partial') {
      return (
        <>
          <ResponseView response={streamed.response} compact={compact} onFollowup={onFollowup} />
          {streamed.open && <div className="mt-2">{<Composing />}</div>}
        </>
      );
    }
    return <Composing />;
  }

  if (settled) {
    if (settled.status === 'ok') {
      return <ResponseView response={settled.response} compact={compact} onFollowup={onFollowup} />;
    }
    if (settled.status === 'empty') return null;
    // Settled + malformed JSON: degrade to readable content rather than an error
    // card. The chokepoint shows the raw source as a code fence so the answer is
    // never gutted, and the failure is reported for telemetry — never surfaced as
    // a parse error.
    return <ResponseView response={finalizeFenceSource(source).response} compact={compact} onFollowup={onFollowup} />;
  }

  return null;
}

export default ResponseFence;
