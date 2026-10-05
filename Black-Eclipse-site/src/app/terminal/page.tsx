import type { Metadata } from 'next';
import { TerminalWindow } from '@/components/terminal/terminal-window';

export const metadata: Metadata = {
  title: 'Eclipse Terminal',
  description: 'A standalone Eclipse terminal window attached to a running shell.',
};

// A standalone terminal window. Opened with `/terminal?session=<id>` from the
// dock's pop-out control, it ATTACHES to that running session (the same shell),
// so a command started in the dock is visible and continued here.
export default async function TerminalPage({
  searchParams,
}: {
  searchParams: Promise<{ session?: string; shell?: string }>;
}) {
  const params = await searchParams;
  return <TerminalWindow sessionId={params.session ?? null} shell={params.shell ?? null} />;
}
