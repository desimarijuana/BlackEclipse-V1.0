import type {Metadata} from 'next';
import './globals.css';
import './fonts.css';
import { cn } from "@/lib/utils";
import { AgentationMount } from "@/components/layout/agentation-mount";
import { GlobalLoader } from "@/components/ui/global-loader";
import { GlobalSearchMount } from "@/components/layout/global-search-mount";
import { KeyboardShortcuts } from "@/components/layout/keyboard-shortcuts";
import { AlertNotificationProvider } from "@/components/layout/alert-notification-provider";
import { TaskCompletionWatcher } from "@/lib/notifications/task-watcher";
import { BotsRunWatcher } from "@/lib/notifications/bots-run-watcher";
import { ChannelActivityWatcher } from "@/lib/notifications/channel-watcher";
import { BrowserTabIndicator } from "@/lib/notifications/tab-indicator";
import { SoundProvider } from "@/lib/sounds";
import { TerminalKeybind } from "@/components/layout/terminal-keybind";
import { WorkspaceKeybind } from "@/components/agent-workspace/workspace-keybind";

// ── Landing-wordmark fonts ──────────────────────────────────────────────────
// Real display faces for the ChatBot wordmark (Settings › General › Background),
// exposed as CSS variables the wordmark options reference. Curated for range:
// elegant serif, sci-fi display, pixel, ASCII/mono and blackletter. Keep this
// list in sync with WORDMARK_FONT_OPTIONS in src/lib/theme/tokens.ts.
//
// They are SELF-HOSTED (public/fonts/ + src/app/fonts.css), not fetched from
// Google at build time: a live fetch makes the build depend on the network and
// on Google answering with exactly one font entry per query. When it did not,
// Turbopack could not resolve the import and the WHOLE app failed to compile.

export const metadata: Metadata = {
  title: 'BlackEclipse — AI Stock Research & Screening Platform',
  description: 'Advanced glassmorphic stock screening tables, live sectors treemap heatmap, portfolio watchlist, and financial news, backed by an autonomous AI research analyst.',
  icons: { icon: '/branding/FAVICON.svg' },
};

export default function RootLayout({children}: {children: React.ReactNode}) {
  return (
    <html lang="en" suppressHydrationWarning className={cn("dark", "font-sans")}>
      <body suppressHydrationWarning>
        {/* Pre-paint scheme sync. The default document is `dark` (matches the
         * shipped Eclipse theme, no flash). If the user saved a light-scheme
         * theme, flip the `dark` class before first paint so they don't get a
         * black frame while React hydrates. Reads the same key the theme store
         * persists; a malformed payload is ignored and the dark default stays. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=JSON.parse(localStorage.getItem('be_theme_v1')||'null');if(t&&t.scheme==='light'){document.documentElement.classList.remove('dark');}}catch(e){}`,
          }}
        />
        <GlobalLoader />
        {children}
        <AgentationMount />
        <GlobalSearchMount />
        <KeyboardShortcuts />
        <TerminalKeybind />
        <WorkspaceKeybind />
        <SoundProvider />
        <AlertNotificationProvider />
        <TaskCompletionWatcher />
        <BotsRunWatcher />
        <ChannelActivityWatcher />
        <BrowserTabIndicator />
      </body>
    </html>
  );
}
