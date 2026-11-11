'use client';

// ── Desktop tab strip ────────────────────────────────────────────────────────
// Rendered only inside the Tauri shell. The native window is frameless, so this
// bar is also the window chrome: tabs on the left, a drag region through the
// empty space, and minimize / maximize / close at the right. The browser front
// door never mounts it — `hasDesktopShell()` gates on Tauri's global bridge.
//
// Tabs are the SPA's top-level pages, not independent webviews. Switching a tab
// calls `onSelectTab`, so the existing keep-alive panels preserve each page.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChartLine,
  Code,
  Cpu,
  Database,
  FileText,
  FlaskConical,
  Ghost,
  GitBranch,
  ListChecks,
  Minus,
  Palette,
  Plus,
  Settings,
  Square,
  X,
  type LucideIcon,
} from '@/lib/icons';
import { APP_TABS, type AppTab } from '@/lib/app-tabs';
import { DEFAULT_SIDEBAR_SECTIONS } from '@/lib/sidebar/config';
import { navLabelKey } from '@/lib/i18n/nav';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import {
  addTab,
  readStoredTabs,
  removeTab,
  saveStoredTabs,
} from '@/lib/desktop/tabs';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface TabMeta {
  label: string;
  icon: LucideIcon;
}

const NAV_META = new Map<AppTab, TabMeta>(
  DEFAULT_SIDEBAR_SECTIONS.map((section) => [
    section.id,
    { label: section.label, icon: section.icon },
  ]),
);

/** Pages reachable without a permanent sidebar entry still deserve a tab. */
const EXTRA_META: Partial<Record<AppTab, TabMeta>> = {
  chart: { label: 'Chart', icon: ChartLine },
  settings: { label: 'Settings', icon: Settings },
  tasks: { label: 'Tasks', icon: ListChecks },
  pages: { label: 'Pages', icon: FileText },
  'ui-builder': { label: 'UI Builder', icon: Palette },
  backtest: { label: 'Backtest', icon: FlaskConical },
  'research-data': { label: 'Research Data', icon: Database },
  'factor-lab': { label: 'Factor Lab', icon: FlaskConical },
  'ml-lab': { label: 'ML Lab', icon: Cpu },
  'graph-studio': { label: 'Graph Studio', icon: GitBranch },
  code: { label: 'Code', icon: Code },
  bots: { label: 'Bots', icon: Ghost },
};

/** The pages offered by the "+" menu. Settings is a modal, not a page. */
const OPENABLE_TABS: AppTab[] = Array.from(
  new Set([
    ...DEFAULT_SIDEBAR_SECTIONS.map((section) => section.id),
    ...APP_TABS.filter((tab) => !NAV_META.has(tab) && tab !== 'settings'),
  ]),
);

function metaFor(tab: AppTab): TabMeta {
  return (
    NAV_META.get(tab) ??
    EXTRA_META[tab] ?? {
      label: tab.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      icon: FileText,
    }
  );
}

function hasDesktopShell(): boolean {
  if (typeof window === 'undefined') return false;
  const bridge = window as unknown as {
    __TAURI__?: unknown;
    __TAURI_INTERNALS__?: unknown;
  };
  return Boolean(bridge.__TAURI__ || bridge.__TAURI_INTERNALS__);
}

type WindowAction = 'minimize' | 'toggle-maximize' | 'close';

/** The shell's INIT_SCRIPT forwards these to Rust through `be-window`. */
function windowAction(action: WindowAction): void {
  window.dispatchEvent(new CustomEvent('be-window-action', { detail: { action } }));
}

export function DesktopTabBar({
  activeTab,
  onSelectTab,
}: {
  activeTab: AppTab;
  onSelectTab: (tab: AppTab) => void;
}) {
  const t = useT();
  const [desktop, setDesktop] = useState(false);
  const [restored, setRestored] = useState(false);
  const [tabs, setTabs] = useState<AppTab[]>([activeTab]);
  const bootTab = useRef(activeTab);

  // Detect the shell after mount (the Tauri bridge does not exist during SSR).
  // Restore the previous session's open pages once, keeping the URL/boot tab.
  useEffect(() => {
    if (!hasDesktopShell()) return;
    setDesktop(true);
    const stored = readStoredTabs();
    if (stored.length > 0) {
      const boot = bootTab.current;
      setTabs(stored.includes(boot) ? stored : [...stored, boot]);
    }
    setRestored(true);
  }, []);

  // Every page the user opens (sidebar, palette, deep link) earns a tab.
  useEffect(() => {
    if (!desktop) return;
    setTabs((prev) => addTab(prev, activeTab));
  }, [activeTab, desktop]);

  useEffect(() => {
    if (!desktop || !restored) return;
    saveStoredTabs(tabs);
  }, [tabs, desktop, restored]);

  const close = useCallback(
    (tab: AppTab) => {
      const result = removeTab(tabs, tab, activeTab);
      if (result.tabs === tabs) return;
      setTabs(result.tabs);
      if (result.activeTab !== activeTab) onSelectTab(result.activeTab);
    },
    [tabs, activeTab, onSelectTab],
  );

  const openPage = useCallback(
    (tab: AppTab) => {
      setTabs((prev) => addTab(prev, tab));
      onSelectTab(tab);
    },
    [onSelectTab],
  );

  const labelFor = useCallback(
    (tab: AppTab) => {
      const key = navLabelKey(tab);
      return key ? t(key) : metaFor(tab).label;
    },
    [t],
  );

  const openable = useMemo(
    () => OPENABLE_TABS.map((tab) => ({ tab, ...metaFor(tab), label: labelFor(tab) })),
    [labelFor],
  );

  if (!desktop) return null;

  return (
    <div
      data-be-drag=""
      className="relative z-30 flex h-10 w-full shrink-0 select-none items-stretch bg-[#0D0D0D] pl-2"
    >
      <div
        role="tablist"
        aria-label="Open pages"
        className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto scrollbar-hide py-1.5 pr-2"
      >
        {tabs.map((tab) => {
          const meta = metaFor(tab);
          const Icon = meta.icon;
          const active = tab === activeTab;
          const label = labelFor(tab);
          return (
            <div
              key={tab}
              role="tab"
              aria-selected={active}
              tabIndex={0}
              data-be-no-drag=""
              title={label}
              onClick={() => onSelectTab(tab)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelectTab(tab);
                }
              }}
              onAuxClick={(event) => {
                if (event.button === 1) close(tab);
              }}
              className={cn(
                'group/tab flex h-7 min-w-0 max-w-[220px] shrink-0 cursor-pointer items-center gap-1.5 rounded-md pl-2.5 pr-1 text-[11.5px] font-medium outline-none transition-colors focus-visible:ring-1 focus-visible:ring-white/20',
                active
                  ? 'bg-white/[0.08] text-foreground shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)]'
                  : 'text-muted-foreground hover:bg-white/[0.04] hover:text-foreground',
              )}
            >
              <Icon size={12} className="shrink-0 opacity-80" />
              <span className="truncate">{label}</span>
              <button
                type="button"
                aria-label={`Close ${label}`}
                title="Close tab"
                onClick={(event) => {
                  event.stopPropagation();
                  close(tab);
                }}
                className={cn(
                  'ml-0.5 grid h-4 w-4 shrink-0 place-items-center rounded text-muted-foreground/60 transition-colors hover:bg-white/10 hover:text-foreground',
                  active ? 'opacity-100' : 'opacity-0 group-hover/tab:opacity-100',
                )}
              >
                <X size={10} />
              </button>
            </div>
          );
        })}

        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                data-be-no-drag=""
                aria-label="Open a page tab"
                title="Open a page tab"
                className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground outline-none focus-visible:ring-1 focus-visible:ring-white/20"
              />
            }
          >
            <Plus size={13} />
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="start"
            className="nav-menu-glass max-h-[70vh] w-56 overflow-y-auto"
          >
            {openable.map(({ tab, label, icon: Icon }) => (
              <DropdownMenuItem key={tab} onClick={() => openPage(tab)}>
                <Icon size={13} />
                <span>{label}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div data-be-no-drag="" className="flex shrink-0 items-stretch">
        <button
          type="button"
          aria-label="Minimize window"
          title="Minimize"
          onClick={() => windowAction('minimize')}
          className="grid w-11 place-items-center text-muted-foreground transition-colors hover:bg-white/[0.08] hover:text-foreground"
        >
          <Minus size={14} />
        </button>
        <button
          type="button"
          aria-label="Maximize or restore window"
          title="Maximize / restore"
          onClick={() => windowAction('toggle-maximize')}
          className="grid w-11 place-items-center text-muted-foreground transition-colors hover:bg-white/[0.08] hover:text-foreground"
        >
          <Square size={10} />
        </button>
        <button
          type="button"
          aria-label="Close window"
          title="Close"
          onClick={() => windowAction('close')}
          className="grid w-11 place-items-center text-muted-foreground transition-colors hover:bg-[#e81123] hover:text-white"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
