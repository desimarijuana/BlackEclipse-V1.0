'use client';

// Keep-alive wrapper for the SDK tab. Kept out of `stock-chat.tsx` so the shell
// adds only one import + one line (the shell file has a size ratchet).

import dynamic from 'next/dynamic';
import { cn } from '@/lib/utils';

const SdkScreen = dynamic(
  () => import('./sdk-screen').then((m) => m.SdkScreen),
  { ssr: false },
);

export function SdkTab({ active }: { active: boolean }) {
  return (
    <div className={cn('w-full h-full', active ? '' : 'hidden')}>
      <div className="flex-1 w-full px-4 md:px-8 py-8">
        <SdkScreen />
      </div>
    </div>
  );
}
