'use client';

// ── /figure — a standalone shared 3D figure ──────────────────────────────────
//
// Decodes a `/figure#<base64>` link (see `lib/response/share.ts`) and renders the
// `model3d` block on its own, no account and no server state. Public route.

import { useEffect, useState } from 'react';
import { decodeFigure } from '@/lib/response/share';
import { Model3dBlock } from '@/components/response/model3d-block';
import type { Model3dBlock as Model3dBlockType } from '@/lib/response/contract';

export default function FigurePage() {
  const [block, setBlock] = useState<Model3dBlockType | null>(null);
  const [message, setMessage] = useState('Loading figure…');

  useEffect(() => {
    const parsed = decodeFigure(window.location.hash);
    const found = parsed?.blocks.find((candidate) => candidate.type === 'model3d');
    if (found && found.type === 'model3d') {
      setBlock(found);
      setMessage('');
    } else {
      setMessage('This link does not contain a 3D model.');
    }
  }, []);

  return (
    <main className="min-h-screen w-full bg-[#0f0f10] p-4 sm:p-8">
      <div className="mx-auto w-full max-w-6xl">
        {block ? <Model3dBlock block={block} /> : <p className="text-sm text-white/60">{message}</p>}
      </div>
    </main>
  );
}
