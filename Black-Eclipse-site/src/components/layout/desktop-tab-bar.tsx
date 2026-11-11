'use client';

// ── Desktop tab strip ────────────────────────────────────────────────────────
// Rendered only inside the Tauri shell. The native window is frameless, so this
// bar is also the window chrome: tabs on the left, a drag region through the
// empty space, and minimize / maximize / close at the right. The browser front
// door never mounts it — `hasDesktopShell()` gates on Tauri's global bridge.
//
// Tabs are INSTANCES, not a de-duplicated page set. `+` appends a real tab that
// starts on the Chat page with a fresh session; navigating inside that tab moves
// it to the page the user picks (sidebar, palette, deep link). Closing the last
// tab is refused. Switching a tab calls `onSelectTab`, so the existing
// keep-alive panels preserve each page.
//
// Window chrome prefers the core window API (minimize / toggleMaximize / close /
// startDragging) and falls back to the `be-window-action` event bridge used by
// older shells. Both paths are needed: the event bridge avoids app-command ACLs,
// while the core API is the one Tauri guarantees for remote origins.

import { useCallback, useEffect, useRef, useState } from 'react';
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
import type { AppTab } from '@/lib/app-tabs';
import { DEFAULT_SIDEBAR_SECTIONS } from '@/lib/sidebar/config';
import { navLabelKey } from '@/lib/i18n/nav';
import { useT } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import { canHandleKeyboardEvent } from '@/lib/keyboard';
import { useWindowGlass } from '@/lib/desktop/window-glass';
import {
  appendTab,
  createTab,
  moveTab,
  moveTabBy,
  moveTabToEdge,
  readStoredTabs,
  removeTab,
  saveStoredTabs,
  setTabPage,
  type DesktopTab,
} from '@/lib/desktop/tabs';

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

type WindowAction = 'minimize' | 'toggle-maximize' | 'close' | 'start-drag';

interface TauriWindowApi {
  minimize: () => Promise<void>;
  toggleMaximize: () => Promise<void>;
  close: () => Promise<void>;
  startDragging: () => Promise<void>;
}

/** The core window object Tauri injects into the page (`withGlobalTauri`). */
function tauriWindow(): TauriWindowApi | null {
  if (typeof window === 'undefined') return null;
  try {
    const bridge = window as unknown as {
      __TAURI__?: { window?: { getCurrentWindow?: () => TauriWindowApi } };
    };
    return bridge.__TAURI__?.window?.getCurrentWindow?.() ?? null;
  } catch {
    return null;
  }
}

/** Old-shell fallback: the injected script forwards this to Rust. */
function eventFallback(action: WindowAction): void {
  window.dispatchEvent(new CustomEvent('be-window-action', { detail: { action } }));
}

function windowAction(action: Exclude<WindowAction, 'start-drag'>): void {
  const win = tauriWindow();
  if (!win) {
    eventFallback(action);
    return;
  }
  const run =
    action === 'minimize'
      ? win.minimize
      : action === 'toggle-maximize'
        ? win.toggleMaximize
        : win.close;
  try {
    Promise.resolve(run.call(win)).catch(() => eventFallback(action));
  } catch {
    eventFallback(action);
  }
}

function beginWindowDrag(): void {
  const win = tauriWindow();
  if (!win) {
    eventFallback('start-drag');
    return;
  }
  try {
    Promise.resolve(win.startDragging()).catch(() => eventFallback('start-drag'));
  } catch {
    eventFallback('start-drag');
  }
}

function isChromeTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !(el && typeof el.closest === 'function' && el.closest('[data-be-no-drag]'));
}

export function DesktopTabBar({
  activeTab,
  onSelectTab,
  onNewChat,
}: {
  activeTab: AppTab;
  onSelectTab: (tab: AppTab) => void;
  /** `+` starts a fresh session and lands the new tab on the Chat page. */
  onNewChat?: () => void;
}) {
  const t = useT();
  // Applies the persisted glass-window preference at shell boot (and tells Rust
  // to apply the acrylic). Mounted for the life of the app, unlike Settings.
  useWindowGlass();
  const bootTab = useRef(activeTab);
  const bootId = useRef('boot');
  const [desktop, setDesktop] = useState(false);
  const [restored, setRestored] = useState(false);
  const [tabs, setTabs] = useState<DesktopTab[]>(() => [
    createTab(bootTab.current, bootId.current),
  ]);
  const [activeId, setActiveId] = useState(bootId.current);
  const [dragging, setDragging] = useState<string | null>(null);
  const tabListRef = useRef<HTMLDivElement>(null);

  // Detect the shell after mount (the Tauri bridge does not exist during SSR).
  // Restore the previous session's tabs once, keeping the URL/boot page open.
  useEffect(() => {
    if (!hasDesktopShell()) return;
    setDesktop(true);
    const stored = readStoredTabs();
    if (stored.length > 0) {
      const boot = stored.find((tab) => tab.page === bootTab.current);
      if (boot) {
        setTabs(stored);
        setActiveId(boot.id);
      } else {
        const added = appendTab(stored, bootTab.current);
        setTabs(added.tabs);
        setActiveId(added.tab.id);
      }
    }
    setRestored(true);
  }, []);

  // In-app navigation (sidebar, palette, deep link) moves the ACTIVE tab.
  useEffect(() => {
    if (!desktop) return;
    setTabs((prev) => setTabPage(prev, activeId, activeTab));
  }, [activeTab, activeId, desktop]);

  useEffect(() => {
    if (!desktop || !restored) return;
    saveStoredTabs(tabs);
  }, [tabs, desktop, restored]);

  const select = useCallback(
    (tab: DesktopTab) => {
      setActiveId(tab.id);
      onSelectTab(tab.page);
    },
    [onSelectTab],
  );

  const close = useCallback(
    (id: string) => {
      const result = removeTab(tabs, id, activeId);
      if (result.tabs === tabs) return;
      setTabs(result.tabs);
      if (result.activeId !== activeId) {
        const next = result.tabs.find((tab) => tab.id === result.activeId);
        setActiveId(result.activeId);
        if (next) onSelectTab(next.page);
      }
    },
    [tabs, activeId, onSelectTab],
  );

  const newTab = useCallback(() => {
    // A real new tab instance: it starts as a fresh Chat session, and whatever
    // page the user opens next becomes that tab's page.
    const { tabs: next, tab } = appendTab(tabs, 'chat');
    setTabs(next);
    setActiveId(tab.id);
    onNewChat?.();
    onSelectTab('chat');
  }, [tabs, onNewChat, onSelectTab]);

  const labelFor = useCallback(
    (tab: AppTab) => {
      const key = navLabelKey(tab);
      return key ? t(key) : metaFor(tab).label;
    },
    [t],
  );

  // Keyboard reorder for the active tab: Ctrl/Cmd+Shift+Home/End jump to an
  // edge, Ctrl/Cmd+Shift+PageUp/PageDown (or ←/→) step one slot. Skipped while
  // typing or behind a modal, exactly like every other chord.
  useEffect(() => {
    if (!desktop) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey) || !event.shiftKey || event.altKey) return;
      if (!canHandleKeyboardEvent(event)) return;
      let next: DesktopTab[] | null = null;
      switch (event.key) {
        case 'Home':
          next = moveTabToEdge(tabs, activeId, 'first');
          break;
        case 'End':
          next = moveTabToEdge(tabs, activeId, 'last');
          break;
        case 'PageUp':
        case 'ArrowLeft':
          next = moveTabBy(tabs, activeId, -1);
          break;
        case 'PageDown':
        case 'ArrowRight':
          next = moveTabBy(tabs, activeId, 1);
          break;
      }
      if (!next || next === tabs) return;
      event.preventDefault();
      setTabs(next);
      requestAnimationFrame(() => {
        tabListRef.current
          ?.querySelector('[role="tab"][aria-selected="true"]')
          ?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      });
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [desktop, tabs, activeId]);

  if (!desktop) return null;

  return (
    <div
      data-be-drag=""
      className="desktop-tab-bar relative z-30 flex h-10 w-full shrink-0 select-none items-stretch pl-2"
      onMouseDown={(event) => {
        if (event.button !== 0 || !isChromeTarget(event.target)) return;
        beginWindowDrag();
      }}
      onDoubleClick={(event) => {
        if (!isChromeTarget(event.target)) return;
        windowAction('toggle-maximize');
      }}
    >
      <div
        ref={tabListRef}
        role="tablist"
        aria-label="Open tabs"
        className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto scrollbar-hide py-1.5 pr-2"
      >
        {tabs.map((tab) => {
          const meta = metaFor(tab.page);
          const Icon = meta.icon;
          const active = tab.id === activeId;
          const label = labelFor(tab.page);
          return (
            <div
              key={tab.id}
              role="tab"
              aria-selected={active}
              tabIndex={0}
              draggable
              data-be-no-drag=""
              title={`${label} — drag to reorder`}
              onClick={() => select(tab)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  select(tab);
                }
              }}
              onAuxClick={(event) => {
                if (event.button === 1) close(tab.id);
              }}
              onDragStart={(event) => {
                setDragging(tab.id);
                event.dataTransfer.effectAllowed = 'move';
                try {
                  event.dataTransfer.setData('text/plain', tab.id);
                } catch {
                  /* some webviews refuse setData without a drag image */
                }
              }}
              onDragOver={(event) => {
                if (!dragging || dragging === tab.id) return;
                event.preventDefault();
                event.dataTransfer.dropEffect = 'move';
              }}
              onDrop={(event) => {
                event.preventDefault();
                if (dragging && dragging !== tab.id) {
                  setTabs((prev) => moveTab(prev, dragging, tab.id));
                }
                setDragging(null);
              }}
              onDragEnd={() => setDragging(null)}
              className={cn(
                'group/tab flex h-7 min-w-0 max-w-[220px] shrink-0 cursor-grab items-center gap-1.5 rounded-md pl-2.5 pr-1 text-[11.5px] font-medium outline-none transition-colors active:cursor-grabbing focus-visible:ring-1 focus-visible:ring-white/20',
                dragging === tab.id && 'opacity-50',
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
                  close(tab.id);
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

        <button
          type="button"
          data-be-no-drag=""
          onClick={newTab}
          aria-label="New tab"
          title="New tab"
          className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground outline-none focus-visible:ring-1 focus-visible:ring-white/20"
        >
          <Plus size={13} />
        </button>
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
