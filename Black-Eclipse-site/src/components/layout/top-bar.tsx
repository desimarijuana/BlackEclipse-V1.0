'use client';

import { useEffect, useState } from 'react';
import { Menu, Search, Command, Terminal } from '@/lib/icons';
import { useCommandStore } from '@/lib/search/store';
import { universeCount } from '@/lib/search/universe';
import { PriceRibbon } from '@/components/layout/price-ribbon';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { useTerminalStore } from '@/lib/terminal/store';
import { AgentWorkspaceToggle } from '@/components/agent-workspace/workspace';
import { NotificationCenter } from '@/components/layout/notification-center';

interface TopBarProps {
  onToggleMenu?: () => void;
  /** Active SPA tab, used to make the search placeholder contextual. */
  activeTab?: string;
  /** Focus mode — unmount the header for a clean canvas. */
  hidden?: boolean;
}

const TAB_PLACEHOLDER: Record<string, string> = {
  chat: 'Ask or search anything…',
  home: 'Search markets, holdings and commands…',
  portfolio: 'Search your funds and holdings…',
  journal: 'Search your trades…',
  discovery: 'Search instruments or markets…',
  news: 'Search news and headlines…',
  economics: 'Search indicators and events…',
  dashboard: 'Search widgets and commands…',
  'investor-eye': 'Search the world map — "what is affecting oil?"…',
    'market-workspace': 'Search instruments to chart…',
    'ml-lab': 'Search datasets, experiments and models…',
  chart: 'Search an instrument to chart…',
  heatmap: 'Search a market or sector…',
  alerts: 'Search price alerts…',
  settings: 'Search settings…',
};

export function TopBar({ onToggleMenu, activeTab, hidden = false }: TopBarProps) {
  const t = useT();
  const [modKey, setModKey] = useState('Ctrl');
  const [indexed, setIndexed] = useState(0);

  // Platform-aware shortcut label: ⌘ on macOS, Ctrl elsewhere. Resolved on the
  // client so SSR stays stable.
  useEffect(() => {
    const isMac = typeof navigator !== 'undefined' && /mac|iphone|ipad/i.test(navigator.platform);
    setModKey(isMac ? '⌘' : 'Ctrl');
  }, []);

  // Reflect warm index status in the trigger (0 until the palette first loads).
  useEffect(() => {
    const read = () => setIndexed(universeCount());
    read();
    const unsub = useCommandStore.subscribe(read);
    return unsub;
  }, []);

  const placeholder = (activeTab && TAB_PLACEHOLDER[activeTab]) || t('topbar.searchPlaceholder');

  if (hidden) return null;

  return (
    <div className={cn('w-full h-12 flex items-center justify-between px-3 md:px-6 gap-2 md:gap-4 z-20 shrink-0', activeTab === 'bots' && 'md:hidden')}>
       {/* Mobile menu toggle. The brand already lives in the sidebar drawer, so
           the header shows ONLY this icon on small screens — no duplicate
           wordmark competing with the search field. */}
       <div className="flex items-center gap-2 shrink-0">
         {onToggleMenu && (
           <button
             onClick={onToggleMenu}
             aria-label={t('a11y.openMenu')}
             className="md:hidden p-1.5 text-muted-foreground hover:text-foreground rounded-xl hover:bg-accent cursor-pointer transition-colors"
           >
             <Menu size={20} />
           </button>
         )}
       </div>

         {/* Live price ribbon (flexible, fills the middle) + search + terminal */}
         <div className="flex-1 flex items-center justify-end gap-2 md:gap-3 min-w-0 px-2">
            <PriceRibbon className="flex-1" />
            <button
              onClick={() => useCommandStore.getState().setOpen(true)}
              className="command-glass-bar group flex flex-1 min-w-0 max-w-md shrink items-center gap-2.5 rounded-xl px-3 sm:px-4 py-2.5 transition-all cursor-pointer text-left"
              title="Search & command center (⌘K)"
            >
              <Search size={16} className="text-muted-foreground/70 shrink-0 transition-colors group-hover:text-primary" />
              <span className="flex-1 truncate text-sm text-muted-foreground/80 font-mono">
                {placeholder}
              </span>
              {indexed > 0 && (
                <span className="hidden lg:inline-flex shrink-0 items-center gap-1 text-[10px] font-mono text-muted-foreground/40" title={`${indexed.toLocaleString()} instruments indexed`}>
                  {indexed.toLocaleString()} indexed
                </span>
              )}
              <kbd className="hidden sm:inline-flex items-center gap-1 rounded-md bg-white/[0.05] px-2 py-0.5 text-[11px] font-mono text-muted-foreground">
                {modKey === '⌘' ? <Command size={11} /> : <span>{modKey}</span>}
                K
              </kbd>
            </button>
            <AgentWorkspaceToggle />
            <NotificationCenter />
            <TerminalButton />
         </div>
     </div>
  );
}

/**
 * The terminal toggle, at the header's right edge. It reads/writes the shared
 * `useTerminalStore`, so it and the Ctrl/Cmd + ` shortcut are the same control.
 */
function TerminalButton() {
  const open = useTerminalStore((s) => s.open);
  const toggle = useTerminalStore((s) => s.toggle);
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Toggle terminal"
      aria-pressed={open}
      title="Terminal (Ctrl/Cmd + `)"
      className={cn(
        'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors',
        open
          ? 'bg-white/[0.08] text-primary'
          : 'text-muted-foreground/70 hover:bg-accent hover:text-foreground',
      )}
    >
      <Terminal size={18} />
    </button>
  );
}
