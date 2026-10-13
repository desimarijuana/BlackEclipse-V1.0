'use client';

// ── MermaidBlock — declarative technical diagrams ─────────────────────────────
// Renders a Mermaid definition (sequence, ER, class, state, gantt, flowchart, …)
// with `securityLevel: 'strict'`. Mermaid is dynamically imported so its large
// bundle is only fetched when a response actually contains a mermaid block.

import { useEffect, useRef, useState } from 'react';
import { AlertTriangle } from '@/lib/icons';
import { useDarkScheme } from '@/hooks/use-dark-scheme';
import { repairMermaid } from '@/lib/response/mermaid-repair';

function useStableId(): string {
  const ref = useRef<string | null>(null);
  if (ref.current === null) {
    ref.current = `eclipse-mermaid-${Math.random().toString(36).slice(2, 10)}`;
  }
  return ref.current;
}

export interface MermaidBlockProps {
  diagram: string;
  title?: string;
  description?: string;
}

// Mermaid keeps the parsed configuration and theme in module-global state, so two
// diagrams rendering at once (a multi-diagram answer) can clobber each other. All
// renders are serialised through this one chain.
let mermaidQueue: Promise<unknown> = Promise.resolve();
function runMermaidSerial<T>(task: () => Promise<T>): Promise<T> {
  const run = mermaidQueue.then(task, task);
  mermaidQueue = run.then(
    () => undefined,
    () => undefined,
  );
  return run;
}

export function MermaidBlock({ diagram, title, description }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const baseId = useStableId();
  const isDark = useDarkScheme();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    const source = repairMermaid(diagram?.trim() ?? '');
    if (!source) return;

    runMermaidSerial(async () => {
      const mermaid = (await import('mermaid')).default;
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        // Mermaid has no light/dark auto mode; follow the app's `dark` class.
        theme: isDark ? 'dark' : 'default',
        fontFamily: 'var(--font-sans, sans-serif)',
      });
      return mermaid.render(`${baseId}-svg`, source);
    })
      .then(({ svg }) => {
        if (cancelled || !containerRef.current) return;
        containerRef.current.innerHTML = svg;
      })
      .catch((e: unknown) => {
        // Everything — dynamic import, initialize and render — degrades to the
        // inline card. A bad diagram must never escape to the error boundary.
        if (!cancelled) setError(e instanceof Error ? e.message : 'Invalid Mermaid diagram');
      });

    return () => {
      cancelled = true;
    };
  }, [diagram, baseId, isDark]);

  return (
    <figure className="w-full">
      {title && <figcaption className="mb-2 text-sm font-semibold text-foreground">{title}</figcaption>}
      {error ? (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/[0.06] px-3 py-2 text-[12px] text-rose-200/90">
          <div className="flex items-center gap-1.5 font-medium">
            <AlertTriangle size={13} /> Diagram could not be rendered
          </div>
          <p className="mt-0.5 font-mono text-[10px] opacity-70">{error}</p>
        </div>
      ) : (
        <div className="glass-card-subtle overflow-auto rounded-xl p-3">
          <div ref={containerRef} className="[&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full" />
        </div>
      )}
      {description && <figcaption className="sr-only">{description}</figcaption>}
    </figure>
  );
}

export default MermaidBlock;
