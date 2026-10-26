'use client';

// ── /app-view — a standalone shared interactive app ──────────────────────────
//
// Decodes an `/app-view#<base64>` link (see `lib/response/share.ts`) and renders
// the `interactive` block on its own, no account and no server storage. The app
// still runs inside the opaque-origin sandbox, so sharing does not widen trust.

import { useEffect, useState } from 'react';
import { decodeFigure } from '@/lib/response/share';
import { InteractiveBlock } from '@/components/response/interactive-block';
import type { InteractiveBlock as InteractiveBlockType } from '@/lib/response/contract';

export default function AppViewPage() {
  const [block, setBlock] = useState<InteractiveBlockType | null>(null);
  const [message, setMessage] = useState('Loading app…');

  useEffect(() => {
    const parsed = decodeFigure(window.location.hash);
    const found = parsed?.blocks.find((candidate) => candidate.type === 'interactive');
    if (found && found.type === 'interactive') {
      setBlock(found);
      setMessage('');
    } else {
      setMessage('This link does not contain an interactive app.');
    }
  }, []);

  return (
    <main className="min-h-screen w-full bg-background p-4 sm:p-8">
      <div className="mx-auto w-full max-w-6xl">
        {block ? <InteractiveBlock block={block} /> : <p className="text-sm text-muted-foreground">{message}</p>}
      </div>
    </main>
  );
}
