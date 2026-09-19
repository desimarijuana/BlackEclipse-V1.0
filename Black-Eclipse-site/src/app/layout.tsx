import type {Metadata} from 'next';
import './globals.css';
import { cn } from "@/lib/utils";
import { AgentationToolbar } from "@/components/layout/agentation-toolbar";
import { GlobalLoader } from "@/components/ui/global-loader";
import { GlobalSearch } from "@/components/layout/global-search";
import { KeyboardShortcuts } from "@/components/layout/keyboard-shortcuts";
import { SoundProvider } from "@/lib/sounds";

export const metadata: Metadata = {
  title: 'BlackEclipse — AI Stock Research & Screening Platform',
  description: 'Advanced glassmorphic stock screening tables, live sectors treemap heatmap, portfolio watchlist, and financial news, backed by an autonomous AI research analyst.',
  icons: { icon: '/branding/FAVICON.svg' },
};

export default function RootLayout({children}: {children: React.ReactNode}) {
  return (
    <html lang="en" className={cn("dark", "font-sans")}>
      <body suppressHydrationWarning>
        <GlobalLoader />
        {children}
        {process.env.NEXT_PUBLIC_AGENTATION === '1' && <AgentationToolbar />}
        <GlobalSearch />
        <KeyboardShortcuts />
        <SoundProvider />
      </body>
    </html>
  );
}
