import type {Metadata} from 'next';
import './globals.css';
import {
  Audiowide,
  Bebas_Neue,
  Bodoni_Moda,
  Cinzel,
  Cormorant_Garamond,
  IBM_Plex_Mono,
  Major_Mono_Display,
  Michroma,
  Orbitron,
  Playfair_Display,
  Press_Start_2P,
  Rubik_Glitch,
  Silkscreen,
  Space_Mono,
  UnifrakturMaguntia,
  VT323,
} from 'next/font/google';
import { cn } from "@/lib/utils";
import { AgentationToolbar } from "@/components/layout/agentation-toolbar";
import { GlobalLoader } from "@/components/ui/global-loader";
import { GlobalSearch } from "@/components/layout/global-search";
import { KeyboardShortcuts } from "@/components/layout/keyboard-shortcuts";
import { AlertNotificationProvider } from "@/components/layout/alert-notification-provider";
import { SoundProvider } from "@/lib/sounds";
import { TerminalKeybind } from "@/components/layout/terminal-keybind";
import { WorkspaceKeybind } from "@/components/agent-workspace/workspace-keybind";

// ── Landing-wordmark fonts ──────────────────────────────────────────────────
// Real display faces for the ChatBot wordmark (Settings › General › Background).
// Self-hosted by next/font (no runtime Google request, zero-config), exposed as
// CSS variables the wordmark options reference. Curated for range: elegant
// serif, sci-fi display, pixel, ASCII/mono and blackletter. Keep this list in
// sync with `WORDMARK_FONT_OPTIONS` in `src/lib/theme/tokens.ts`.
const playfair = Playfair_Display({ subsets: ['latin'], variable: '--font-playfair', display: 'swap' });
const cinzel = Cinzel({ subsets: ['latin'], variable: '--font-cinzel', display: 'swap' });
const cormorant = Cormorant_Garamond({ subsets: ['latin'], weight: ['600', '700'], variable: '--font-cormorant', display: 'swap' });
const bodoni = Bodoni_Moda({ subsets: ['latin'], variable: '--font-bodoni', display: 'swap' });
const orbitron = Orbitron({ subsets: ['latin'], variable: '--font-orbitron', display: 'swap' });
const audiowide = Audiowide({ subsets: ['latin'], weight: '400', variable: '--font-audiowide', display: 'swap' });
const michroma = Michroma({ subsets: ['latin'], weight: '400', variable: '--font-michroma', display: 'swap' });
const pressStart = Press_Start_2P({ subsets: ['latin'], weight: '400', variable: '--font-press-start', display: 'swap' });
const silkscreen = Silkscreen({ subsets: ['latin'], weight: ['400', '700'], variable: '--font-silkscreen', display: 'swap' });
const vt323 = VT323({ subsets: ['latin'], weight: '400', variable: '--font-vt323', display: 'swap' });
const majorMono = Major_Mono_Display({ subsets: ['latin'], weight: '400', variable: '--font-major-mono', display: 'swap' });
const spaceMono = Space_Mono({ subsets: ['latin'], weight: ['400', '700'], variable: '--font-space-mono', display: 'swap' });
const plexMono = IBM_Plex_Mono({ subsets: ['latin'], weight: ['400', '600'], variable: '--font-plex-mono', display: 'swap' });
const bebas = Bebas_Neue({ subsets: ['latin'], weight: '400', variable: '--font-bebas', display: 'swap' });
const blackletter = UnifrakturMaguntia({ subsets: ['latin'], weight: '400', variable: '--font-blackletter', display: 'swap' });
const glitch = Rubik_Glitch({ subsets: ['latin'], weight: '400', variable: '--font-glitch', display: 'swap' });

const wordmarkFontVars = [
  playfair, cinzel, cormorant, bodoni, orbitron, audiowide, michroma,
  pressStart, silkscreen, vt323, majorMono, spaceMono, plexMono, bebas,
  blackletter, glitch,
].map((f) => f.variable).join(' ');

export const metadata: Metadata = {
  title: 'BlackEclipse — AI Stock Research & Screening Platform',
  description: 'Advanced glassmorphic stock screening tables, live sectors treemap heatmap, portfolio watchlist, and financial news, backed by an autonomous AI research analyst.',
  icons: { icon: '/branding/FAVICON.svg' },
};

export default function RootLayout({children}: {children: React.ReactNode}) {
  return (
    <html lang="en" className={cn("dark", "font-sans", wordmarkFontVars)}>
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
        {process.env.NEXT_PUBLIC_AGENTATION === '1' && <AgentationToolbar />}
        <GlobalSearch />
        <KeyboardShortcuts />
        <TerminalKeybind />
        <WorkspaceKeybind />
        <SoundProvider />
        <AlertNotificationProvider />
      </body>
    </html>
  );
}
