'use client';

// ── MobileBottomNav — thumb-reach primary navigation for phones ──────────────
// A fixed bottom bar whose tabs FOLLOW THE ACTIVE MENU MODE (Terminal /
// Agentic / Bots), mirroring the desktop sidebar: the first four enabled tabs
// of the mode sit in the bar, the rest (plus the desktop-only labs) live in the
// "More" sheet. The sheet also carries a mode switcher so the whole menu can be
// changed on a phone. Only rendered below `md`; on desktop the sidebar owns nav.

import React, { useState } from 'react';
import {
  Bot, LayoutDashboard, GlobeStand, ChartPie, MoreHorizontal, Home,
  ChartCandlestick, ScanEye, BookOpen, Newspaper, Orbit, Globe, Bell,
  Blocks, Brain, FolderOpen, ListChecks, LayoutTemplate, LayoutGrid,
  ChartLine, Database, Sigma, FlaskConical, Ghost, X, GitBranch as GitBranchIcon,
  SquareTerminal, BrainCircuit, type LucideIcon,
} from '@/lib/icons';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { cn } from '@/lib/utils';
import { useT, navLabelKey } from '@/lib/i18n';
import { useSidebarConfigStore, useHydrateSidebarConfig } from '@/lib/sidebar/store';
import { configMap, type NavGroup } from '@/lib/sidebar/config';
import type { AppTab } from '@/lib/app-tabs';

interface TabMeta { icon: LucideIcon; label?: string }

// Keyed by AppTab so a typo'd id is a compile error; `Partial` because some tabs
// are not nav-bar destinations (settings, chart). The coverage guard test
// (`mobile-bottom-nav.test.ts`) enforces an entry for every tab a mode lists —
// a missing one used to render `undefined.icon` and blank the whole shell.
export const TAB_META: Partial<Record<AppTab, TabMeta>> = {
  chat: { icon: Bot },
  tables: { icon: Database },
  overview: { icon: LayoutDashboard },
  home: { icon: Home },
  dashboard: { icon: LayoutDashboard },
  discovery: { icon: GlobeStand },
  portfolio: { icon: ChartPie },
  'investor-eye': { icon: ScanEye },
  'market-workspace': { icon: ChartCandlestick },
  journal: { icon: BookOpen },
  news: { icon: Newspaper },
  heatmap: { icon: Orbit },
  economics: { icon: Globe },
  alerts: { icon: Bell },
  skills: { icon: Blocks },
  memory: { icon: Brain },
  artifacts: { icon: FolderOpen },
  tasks: { icon: ListChecks },
  pages: { icon: LayoutTemplate },
  bots: { icon: Ghost },
  'ui-builder': { icon: LayoutGrid },
  backtest: { icon: ChartLine },
  'research-data': { icon: Database },
  'factor-lab': { icon: Sigma, label: 'Factor Lab' },
  'ml-lab': { icon: FlaskConical, label: 'ML Lab' },
  'graph-studio': { icon: GitBranchIcon },
};

/** Tab order per menu mode. `bots` lists no sidebar sections, so its entries are
 *  declared here (bots first, then the shared agent surface). */
export const MODE_TABS: Record<NavGroup, AppTab[]> = {
  terminal: ['chat', 'tables', 'home', 'dashboard', 'discovery', 'portfolio', 'investor-eye', 'market-workspace', 'journal', 'news', 'heatmap', 'economics', 'alerts'],
  agentic: ['chat', 'overview', 'tables', 'skills', 'memory', 'artifacts', 'tasks', 'pages'],
  bots: ['bots', 'chat', 'tasks', 'artifacts', 'memory', 'skills'],
  graph: ['graph-studio', 'chat', 'tables', 'artifacts'],
};

const MODES: { id: NavGroup; icon: LucideIcon }[] = [
  { id: 'terminal', icon: SquareTerminal },
  { id: 'agentic', icon: BrainCircuit },
  { id: 'bots', icon: Ghost },
  { id: 'graph', icon: GitBranchIcon },
];

const MODE_LABEL_KEY: Record<NavGroup, 'sidebar.terminal' | 'sidebar.agentic' | 'nav.bots' | 'sidebar.graphStudio'> = {
  terminal: 'sidebar.terminal',
  agentic: 'sidebar.agentic',
  bots: 'nav.bots',
  graph: 'sidebar.graphStudio',
};

export const LABS: AppTab[] = ['ui-builder', 'backtest', 'research-data', 'factor-lab', 'ml-lab'];

function useTabLabel() {
  const t = useT();
  return (id: AppTab) => {
    const meta = TAB_META[id];
    if (meta?.label) return meta.label;
    const key = navLabelKey(id);
    return key ? t(key) : id;
  };
}

export function MobileBottomNav({
  activeTab,
  onChangeTab,
  hidden = false,
}: {
  activeTab: AppTab;
  onChangeTab: (tab: AppTab) => void;
  hidden?: boolean;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  const t = useT();
  const label = useTabLabel();
  useHydrateSidebarConfig();

  const mode = useSidebarConfigStore((s) => s.mode);
  const setMode = useSidebarConfigStore((s) => s.setMode);
  const config = useSidebarConfigStore((s) => s.config);
  const cfgMap = configMap(config);

  if (hidden) return null;

  const enabled = (id: AppTab) => cfgMap.get(id)?.enabled !== false;
  // A persisted mode from an older build may not be in the table — fall back
  // rather than crash the whole shell.
  const modeTabs = (MODE_TABS[mode] ?? MODE_TABS.terminal).filter(enabled);
  const primary = modeTabs.slice(0, 4);
  const more = modeTabs.slice(4);

  const activeInPrimary = primary.includes(activeTab);

  const go = (id: AppTab) => {
    setMoreOpen(false);
    onChangeTab(id);
  };

  const switchMode = (id: NavGroup) => {
    setMode(id);
    // Dedicated modes also open their workspace, mirroring the desktop switcher.
    if (id === 'bots') onChangeTab('bots');
    if (id === 'graph') onChangeTab('graph-studio');
  };

  const itemCls = (active: boolean) => cn(
    'flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-[10px] font-medium transition-colors touch-target',
    active ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
  );

  return (
    <>
      <nav
        aria-label={t('a11y.mainNavigation')}
        className="fixed inset-x-0 bottom-0 z-40 flex items-stretch gap-0.5 border-t border-border/10 glass-card-strong px-1 pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {primary.map((id) => {
          // `TAB_META` must cover every tab any mode lists; the guard test
          // enforces it, and the fallback keeps a miss from blanking the app.
          const Icon = TAB_META[id]?.icon ?? SquareTerminal;
          const active = activeTab === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => go(id)}
              aria-current={active ? 'page' : undefined}
              className={itemCls(active)}
            >
              <Icon size={20} className="shrink-0" />
              <span className="w-full truncate text-center">{label(id)}</span>
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          aria-expanded={moreOpen}
          className={itemCls(!activeInPrimary || moreOpen)}
        >
          <MoreHorizontal size={20} className="shrink-0" />
          <span className="w-full truncate text-center">More</span>
        </button>
      </nav>

      <Sheet open={moreOpen} onOpenChange={setMoreOpen}>
        <SheetContent side="bottom" className="max-h-[85dvh] overflow-y-auto rounded-t-2xl p-0" showCloseButton={false}>
          <SheetHeader className="flex-row items-center justify-between border-b border-border/10">
            <SheetTitle>{t(MODE_LABEL_KEY[mode])}</SheetTitle>
            <button
              type="button"
              onClick={() => setMoreOpen(false)}
              aria-label={t('common.close')}
              className="touch-target flex items-center justify-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <X size={16} />
            </button>
          </SheetHeader>

          <div className="flex flex-col gap-4 p-4">
            {/* Mode switcher — rebuilds the whole menu for the chosen mode. */}
            <div className="flex items-center gap-1 rounded-2xl border border-border/30 glass-card-subtle p-1">
              {MODES.map(({ id, icon: Icon }) => {
                const active = mode === id;
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => switchMode(id)}
                    aria-pressed={active}
                    className={cn(
                      'flex flex-1 items-center justify-center gap-1.5 rounded-xl px-2 py-2 text-[11px] font-bold transition-colors touch-target',
                      active ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    <Icon size={14} className="shrink-0" />
                    <span className="truncate">{t(MODE_LABEL_KEY[id])}</span>
                  </button>
                );
              })}
            </div>

            {more.length > 0 && (
              <div>
                <p className="mb-2 px-1 text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/60">
                  {t(MODE_LABEL_KEY[mode])}
                </p>
                <div className="grid grid-cols-3 gap-2">
                  {more.map((id) => (
                    <MoreTile key={id} id={id} label={label(id)} active={activeTab === id} onClick={() => go(id)} />
                  ))}
                </div>
              </div>
            )}

            {/* Desktop-grade labs — reachable but flagged. */}
            <div>
              <p className="mb-2 px-1 text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground/60">
                Labs · best on desktop
              </p>
              <div className="grid grid-cols-3 gap-2">
                {LABS.map((id) => (
                  <MoreTile key={id} id={id} label={label(id)} active={activeTab === id} onClick={() => go(id)} />
                ))}
              </div>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}

function MoreTile({ id, label, active, onClick }: { id: AppTab; label: string; active: boolean; onClick: () => void }) {
  const Icon = TAB_META[id]?.icon ?? SquareTerminal;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'flex flex-col items-center justify-center gap-1.5 rounded-2xl border px-2 py-3 text-[11px] font-medium transition-colors touch-target',
        active
          ? 'border-border/40 bg-white/[0.08] text-foreground'
          : 'border-transparent text-muted-foreground hover:bg-accent/40 hover:text-foreground',
      )}
    >
      <Icon size={19} className="shrink-0" />
      <span className="w-full truncate text-center leading-tight">{label}</span>
    </button>
  );
}
