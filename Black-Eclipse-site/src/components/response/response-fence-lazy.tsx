'use client';

// A tiny, synchronous front for the structured response renderer.
//
// `ResponseFence` pulls the Zod contract and every block renderer (a large
// chunk). This wrapper paints a readable projection of the fence's prose
// immediately, then swaps in the real renderer once its chunk is ready. It is
// also SSR/test-safe: static markup renders the fallback instead of a spinner.

import { useEffect, useState, type ComponentType } from 'react';
import type { ResponseFenceProps } from './response-fence';

type Props = ResponseFenceProps;

function fallbackText(source: string): string | null {
  try {
    const parsed = JSON.parse(source) as { blocks?: unknown };
    if (!Array.isArray(parsed.blocks)) return null;
    const parts: string[] = [];
    for (const raw of parsed.blocks) {
      if (!raw || typeof raw !== 'object') continue;
      const block = raw as Record<string, unknown>;
      if (block.type === 'markdown' && typeof block.markdown === 'string') parts.push(block.markdown);
      else if (block.type === 'heading' && typeof block.text === 'string') parts.push(block.text);
    }
    return parts.length > 0 ? parts.join('\n\n') : null;
  } catch {
    return null;
  }
}

function ResponseFenceFallback({ source }: { source: string }) {
  const text = fallbackText(source);
  if (text) {
    return <div className="whitespace-pre-wrap text-foreground break-words">{text}</div>;
  }
  return (
    <span className="inline-flex items-center gap-2 text-[12px] text-muted-foreground">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-primary" />
      Rendering response…
    </span>
  );
}

export function ResponseFenceLazy(props: Props) {
  const [Ready, setReady] = useState<ComponentType<Props> | null>(null);

  useEffect(() => {
    let live = true;
    void import('./response-fence').then((m) => {
      if (live) setReady(() => m.ResponseFence);
    });
    return () => {
      live = false;
    };
  }, []);

  if (Ready) return <Ready {...props} />;
  return <ResponseFenceFallback source={props.source} />;
}
