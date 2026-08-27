import type {Metadata} from 'next';
import './globals.css';
import { cn } from "@/lib/utils";
import { AgentationToolbar } from "@/components/layout/agentation-toolbar";
import { GlobalLoader } from "@/components/ui/global-loader";

export const metadata: Metadata = {
  title: 'BlackEclipse — AI Stock Research & Screening Platform',
  description: 'Advanced glassmorphic stock screening tables, live sectors treemap heatmap, portfolio watchlist, and financial news, backed by an autonomous AI research analyst.',
};

export default function RootLayout({children}: {children: React.ReactNode}) {
  return (
    <html lang="en" className={cn("dark", "font-sans")}>
      <body suppressHydrationWarning>
        <GlobalLoader />
        {children}
        <AgentationToolbar />
      </body>
    </html>
  );
}
