'use client';

// ── StreamingAppPreview — watch the app being written ────────────────────────
//
// While an ```html / ```svg / ```eclipse-app fence is still streaming, render a
// sandboxed preview of what has arrived so far. Updates are debounced (450 ms)
// so a token stream does not reload the iframe per token. The settled block
// replaces this preview when the fence closes.
//
// No dataset is requested here: the directive may still be half-written, and a
// live preview must never imply data it does not have.

import { useEffect, useMemo, useState } from 'react';
import { composeInteractiveDocument, type InteractiveContext } from '@/lib/interactive/document';
import { staticDatasetEnvelope } from '@/lib/interactive/dataset';
import { InteractiveFrame } from '@/components/response/interactive-frame';
import { cn } from '@/lib/utils';

const PREVIEW_NONCE = 'streaming-preview';

function hostTheme(): InteractiveContext {
  if (typeof document === 'undefined') return { theme: 'dark' };
  return { theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light' };
}

export function StreamingAppPreview({
  source,
  language,
  compact,
}: {
  source: string;
  language: string;
  compact: boolean;
}) {
  const [committed, setCommitted] = useState(source);
  const [ready, setReady] = useState(false);
  const [height, setHeight] = useState(340);

  useEffect(() => {
    const timer = setTimeout(() => {
      setCommitted(source);
    }, 450);
    return () => clearTimeout(timer);
  }, [source]);

  const html = useMemo(
    () =>
      language === 'svg'
        ? `<div style="display:flex;align-items:center;justify-content:center;min-height:100%">${committed}</div>`
        : committed,
    [committed, language],
  );

  const doc = useMemo(
    () => composeInteractiveDocument({ html, nonce: PREVIEW_NONCE, context: hostTheme() }),
    [html],
  );
  const envelope = useMemo(() => staticDatasetEnvelope(), []);
  const context = useMemo(() => hostTheme(), []);

  return (
    <section className={cn('glass-card-subtle w-full overflow-hidden rounded-xl border border-border/40', compact ? 'my-1' : 'my-2')}>
      <header className="flex items-center gap-2 border-b border-border/40 px-3 py-1.5">
        <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-primary" />
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/70">
          Live preview · building
        </span>
      </header>
      <div className="relative w-full" style={{ height }}>
        <InteractiveFrame
          srcDoc={doc}
          title="Live app preview"
          height={height}
          nonce={PREVIEW_NONCE}
          envelope={envelope}
          context={context}
          onScreen
          visible={ready}
          onResize={(next) => setHeight(Math.max(240, Math.min(520, next)))}
          onReady={() => setReady(true)}
        />
        {!ready && (
          <div className="pointer-events-none absolute inset-0 animate-pulse bg-accent/10" />
        )}
      </div>
    </section>
  );
}
