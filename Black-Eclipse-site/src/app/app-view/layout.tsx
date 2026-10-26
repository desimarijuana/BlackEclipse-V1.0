import type { Metadata } from 'next';
import type { ReactNode } from 'react';

// A shared app is ephemeral, user-authored content in the URL hash: never index.
export const metadata: Metadata = {
  title: 'Eclipse app',
  robots: { index: false, follow: false },
};

export default function AppViewLayout({ children }: { children: ReactNode }) {
  return children;
}
