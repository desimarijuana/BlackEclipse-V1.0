'use client';

// ── InteractiveBlock — a model-authored mini-app, running sandboxed ──────────
//
// The card owns the lifecycle: compose the document, load an optional market
// series through the host, mount the sandboxed frame, and show honest states.
// The widget itself is untrusted; this component never touches its DOM.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, RefreshCw, Sparkles } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { composeInteractiveDocument } from '@/lib/interactive/document';
import {
  loadInteractiveDataset,
  staticDatasetEnvelope,
  type InteractiveDatasetEnvelope,
} from '@/lib/interactive/dataset';
import type { InteractiveBlock as InteractiveBlockData } from '@/lib/response/blocks/interactive';
import { InteractiveFrame } from './interactive-frame';

function clampHeight(value: number | undefined): number {
  if (!Number.isFinite(value)) return 420;
  return Math.max(240, Math.min(900, Math.round(value as number)));
}

function makeNonce(): string {
  const cryptoApi = globalThis.crypto as Crypto | undefined;
  if (cryptoApi?.randomUUID) return cryptoApi.randomUUID().replace(/-/g, '');
  return `${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}

function datasetLabel(envelope: InteractiveDatasetEnvelope): string | null {
  if (envelope.status !== 'ready' || envelope.bars.length === 0) return null;
  const asOf = envelope.asOf ? `${envelope.stale ? 'stale · ' : ''}${envelope.asOf}` : null;
  return [envelope.source, envelope.interval, asOf].filter(Boolean).join(' · ');
}

export function InteractiveBlock({ block }: { block: InteractiveBlockData }) {
  const [nonce, setNonce] = useState(makeNonce);
  const [reloadKey, setReloadKey] = useState(0);
  const [height, setHeight] = useState(() => clampHeight(block.height));
  const [envelope, setEnvelope] = useState<InteractiveDatasetEnvelope>(() =>
    block.dataset ? { status: 'loading' } : staticDatasetEnvelope(),
  );

  const dataKey = useMemo(() => JSON.stringify(block.data ?? null), [block.data]);
  const datasetKey = block.dataset ? JSON.stringify(block.dataset) : '';

  useEffect(() => {
    if (!block.dataset) {
      setEnvelope(staticDatasetEnvelope());
      return;
    }

    const controller = new AbortController();
    setEnvelope({ status: 'loading' });
    loadInteractiveDataset(block.dataset, { signal: controller.signal }).then((next) => {
      if (!controller.signal.aborted) setEnvelope(next);
    });
    return () => controller.abort();
    // `datasetKey` is the stable serialization of `block.dataset`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetKey]);

  const doc = useMemo(
    () =>
      composeInteractiveDocument({
        html: block.html,
        css: block.css,
        js: block.js,
        data: block.data,
        nonce,
      }),
    // `dataKey` is the stable serialization of `block.data`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [block.html, block.css, block.js, dataKey, nonce],
  );

  const onResize = useCallback((next: number) => {
    setHeight((current) => (Math.abs(current - next) > 2 ? next : current));
  }, []);

  const reload = useCallback(() => {
    setNonce(makeNonce());
    setReloadKey((key) => key + 1);
    setHeight(clampHeight(block.height));
    if (block.dataset) {
      setEnvelope({ status: 'loading' });
      loadInteractiveDataset(block.dataset).then(setEnvelope);
    }
  }, [block.dataset, block.height]);

  const title = block.title?.trim() || 'Interactive app';
  const provenance = datasetLabel(envelope);
  const loading = envelope.status === 'loading';
  const unavailable = envelope.status === 'unavailable';

  return (
    <section
      className="glass-card-subtle overflow-hidden rounded-xl border border-border/40"
      aria-label={title}
    >
      <header className="flex items-center gap-2 border-b border-border/40 px-3 py-2">
        <Sparkles size={13} className="shrink-0 text-primary/80" />
        <h4 className="min-w-0 flex-1 truncate text-sm font-semibold tracking-tight text-foreground" title={title}>
          {title}
        </h4>
        {block.provenance === 'illustrative' && (
          <span className="shrink-0 rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[10px] text-amber-300/90">
            Illustrative
          </span>
        )}
        {provenance && (
          <span className="hidden shrink-0 truncate font-mono text-[10px] text-muted-foreground/60 sm:inline" title={provenance}>
            {provenance}
          </span>
        )}
        <button
          type="button"
          onClick={reload}
          title="Reload the app"
          aria-label="Reload the app"
          className="shrink-0 rounded-full border border-border/50 bg-accent/30 p-1 text-muted-foreground transition-colors hover:bg-accent/60 hover:text-foreground"
        >
          <RefreshCw size={12} />
        </button>
      </header>

      {block.description && (
        <p className="border-b border-border/30 px-3 py-2 text-[12px] text-muted-foreground">{block.description}</p>
      )}

      {unavailable && (
        <div className="flex items-start gap-2 border-b border-amber-400/20 bg-amber-400/5 px-3 py-2 text-[11px] text-amber-200/90">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          <span>Data unavailable — {envelope.reason}</span>
        </div>
      )}

      <div className="relative" style={{ height }}>
        <InteractiveFrame
          key={reloadKey}
          srcDoc={doc}
          title={title}
          height={height}
          nonce={nonce}
          envelope={envelope}
          onResize={onResize}
        />
        {loading && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-background/40 backdrop-blur-[1px]">
            <span className="inline-flex items-center gap-2 rounded-full border border-border/50 bg-background/80 px-3 py-1.5 text-[11px] text-muted-foreground">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
              Loading market data…
            </span>
          </div>
        )}
      </div>

      {block.caption && (
        <p className={cn('border-t border-border/30 px-3 py-1.5 text-[10px] text-muted-foreground/60')}>
          {block.caption}
        </p>
      )}
    </section>
  );
}
