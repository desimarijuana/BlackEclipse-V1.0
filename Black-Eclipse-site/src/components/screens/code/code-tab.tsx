'use client';

// Keep-alive wrapper for the Builds tab. Kept out of `stock-chat.tsx` so the
// shell adds only one import + one line (the shell file has a size ratchet) —
// the same split the SDK tab uses.

import dynamic from 'next/dynamic';
import { cn } from '@/lib/utils';

const CodeScreen = dynamic(
  () => import('./code-screen').then((m) => m.CodeScreen),
  { ssr: false },
);

export function CodeTab({ active }: { active: boolean }) {
  return (
    <div className={cn('w-full h-full', active ? '' : 'hidden')}>
      <div className="flex-1 w-full px-4 md:px-8 py-8 overflow-y-auto">
        <CodeScreen />
      </div>
    </div>
  );
}
