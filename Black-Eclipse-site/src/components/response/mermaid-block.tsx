'use client';

// ── MermaidBlock — declarative technical diagrams ─────────────────────────────
// Renders a Mermaid definition (sequence, ER, class, state, gantt, flowchart, …)
// with `securityLevel: 'strict'`. Mermaid is dynamically imported so its large
// bundle is only fetched when a response actually contains a mermaid block.

import { useEffect, useRef, useState } from 'react';
import { AlertTriangle } from '@/lib/icons';

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

export function MermaidBlock({ diagram, title, description }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const baseId = useStableId();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: 'strict',
          theme: 'dark',
          fontFamily: 'var(--font-sans, sans-serif)',
        });
        const { svg } = await mermaid.render(`${baseId}-svg`, diagram);
        if (cancelled || !containerRef.current) return;
        containerRef.current.innerHTML = svg;
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Invalid Mermaid diagram');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [diagram, baseId]);

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
        <div className="overflow-auto rounded-xl border border-white/10 bg-accent/10 p-2">
          <div ref={containerRef} className="[&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full" />
        </div>
      )}
      {description && <figcaption className="sr-only">{description}</figcaption>}
    </figure>
  );
}

export default MermaidBlock;
