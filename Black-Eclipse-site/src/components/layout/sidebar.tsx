"use client";

import React, { useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { X, Check, ChevronDown, ChevronLeft, ChevronRight, Settings, SquareTerminal, BrainCircuit, Ghost, Network, ChatsCircle, GitBranch, type LucideIcon } from '@/lib/icons';
import { useSidebarConfigStore, useHydrateSidebarConfig } from '@/lib/sidebar/store';
import { DEFAULT_SIDEBAR_SECTIONS, configMap, modeForTab, type NavGroup } from '@/lib/sidebar/config';
import { MODE_SHORTCUTS } from '@/hooks/use-sidebar-keybinds';
import { formatShortcutKeys } from '@/lib/keyboard';
import { destinationToHref } from '@/lib/search/deep-link';
import { useNotificationsStore, unreadCountsByTab, totalUnread } from '@/lib/notifications/store';
import { useT, navLabelKey } from '@/lib/i18n';
import { useIsMobile } from '@/hooks/use-media-query';
import { useSettingsPrefetch } from '@/hooks/use-settings-prefetch';
import { useThemeStore, BRAND_MARK_SRC, BRAND_WORDMARK_SRC } from '@/lib/theme';
import { ChatHistoryPanel } from '@/components/layout/chat-history-panel';
import { SidebarBrokerButton } from '@/components/layout/sidebar-broker-dialog';
import { BotsSidebarPanel } from '@/components/bots/bots-sidebar-panel';
import { SavedPagesNav } from '@/components/layout/saved-pages-nav';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { ChatOrganizationApi, Conversation } from '@/lib/chat/chat-organization';

// The conversation + folder shapes live in `lib/chat/chat-organization` (alongside
// their persistence + view logic); re-exported here so existing importers keep
// resolving `Conversation` from the sidebar module.
export type { ChatFolder, Conversation } from '@/lib/chat/chat-organization';

// Closed-by-default dialogs/panels: the graph dialog pulls in two ECharts
// force-graphs, and the mode panel pulls the workflow/node-library graph. Keep
// them out of the shell's first-load bundle; each loads on first open.
const SidebarGraphDialog = dynamic(
  () => import('@/components/layout/sidebar-graph-dialog').then((m) => m.SidebarGraphDialog),
  { ssr: false },
);
const SidebarGatewayDialog = dynamic(
  () => import('@/components/layout/sidebar-gateway-dialog').then((m) => m.SidebarGatewayDialog),
  { ssr: false },
);


const NAV_DEF = new Map(DEFAULT_SIDEBAR_SECTIONS.map((s) => [s.id, s]));

/** The top-level menu switcher. Terminal and Agentic choose a nav MODE; Bots is
 *  the one DEDICATED panel mode. Graph Studio is its own mode too, but renders
 *  the standard nav list (workflows/tables) instead of a custom panel. */
type NavSwitcherId = NavGroup;
const NAV_MODES: Array<{
  id: NavSwitcherId;
  labelKey: 'sidebar.terminal' | 'sidebar.agentic' | 'nav.bots' | 'sidebar.graphStudio';
  icon: LucideIcon;
  /** The workspace tab a dedicated mode opens when selected. */
  opens?: AppTab;
}> = [
  { id: 'terminal', labelKey: 'sidebar.terminal', icon: SquareTerminal },
  { id: 'agentic', labelKey: 'sidebar.agentic', icon: BrainCircuit },
  { id: 'bots', labelKey: 'nav.bots', icon: Ghost, opens: 'bots' },
  { id: 'graph', labelKey: 'sidebar.graphStudio', icon: GitBranch, opens: 'overview' },
];

/** Display labels for the mode hotkeys, shown on each switcher entry so the
 *  shortcuts are discoverable without opening the help dialog. */
const MODE_SHORTCUT_LABELS = new Map(MODE_SHORTCUTS.map((s) => [s.mode, formatShortcutKeys(s.keys)] as const));

// The tab vocabulary lives ONCE in `lib/app-tabs.ts`; this shell re-exports it so
// `lib/search/types.ts` (which mirrors it) can never silently drift.
import type { AppTab } from '@/lib/app-tabs';
export type { AppTab };

interface SidebarProps {
  activeTab: AppTab;
  onChangeTab: (tab: AppTab) => void;
  conversations: Conversation[];
  organization: ChatOrganizationApi;
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onDeleteConversation: (id: string) => void;
  onOpenSettings?: () => void;
  mobileOpen?: boolean;
  onCloseMobile?: () => void;
  /** Focus mode — unmount the sidebar (desktop + mobile) for a clean canvas. */
  hidden?: boolean;
}

export function Sidebar({
  activeTab,
  onChangeTab,
  conversations,
  organization,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  onOpenSettings,
  mobileOpen = false,
  onCloseMobile,
  hidden = false,
}: SidebarProps) {
  const [desktopCollapsed, setDesktopCollapsed] = useState(false);
  const prefetchSettings = useSettingsPrefetch();
  // Quick launchers below the mode switcher: the Channel Gateway (Telegram,
  // Discord, WhatsApp, …) and the relationship/skills graph browser.
  const [gatewayOpen, setGatewayOpen] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);
  // The collapse/expand affordance is a DESKTOP preference: the mobile drawer is
  // always full-width (expanded) and is dismissed with its own close (X) button,
  // so it never shows the collapse chevron alongside the cross.
  const isMobile = useIsMobile();
  const isCollapsed = desktopCollapsed && !isMobile;
  const t = useT();
  // Centralized branding (Settings › Customization). Falls back to the shipped
  // Eclipse mark/name when not customized.
  const appName = useThemeStore((s) => s.theme.appName);
  const logoText = useThemeStore((s) => s.theme.logoText);
  const logoUrl = useThemeStore((s) => s.theme.logoUrl);
  const logoScale = useThemeStore((s) => s.theme.logoScale);
  const logoBox = { width: `${2 * logoScale}rem`, height: `${2 * logoScale}rem` };
  // A user-uploaded logo takes precedence over the shipped Eclipse assets; the
  // text monogram remains the final fallback at the collapsed width.
  const markSrc = logoUrl || BRAND_MARK_SRC;
  const wordmarkSrc = logoUrl || BRAND_WORDMARK_SRC;
  const monogram = (logoText || appName.charAt(0) || 'B').slice(0, 2).toUpperCase();

  // User-customized menu: order, visibility, and shortcuts come from the
  // shared store (edited in Settings › Sidebar). Hydrate once on mount.
  useHydrateSidebarConfig();
  const sidebarConfig = useSidebarConfigStore((s) => s.config);
  const navMode = useSidebarConfigStore((s) => s.mode);
  const setNavMode = useSidebarConfigStore((s) => s.setMode);
  const setNavModeFromNavigation = useSidebarConfigStore((s) => s.setModeFromNavigation);
  const activeMode = NAV_MODES.find((m) => m.id === navMode) ?? NAV_MODES[0];
  const ActiveModeIcon = activeMode.icon;
  const cfgMap = configMap(sidebarConfig);
  const navItems = sidebarConfig.sections
    .filter((s) => cfgMap.get(s.id)?.enabled !== false)
    .map((s) => {
      const def = NAV_DEF.get(s.id);
      if (!def) return null;
      // Only items belonging to the active mode are listed. ChatBot is `both`,
      // so it stays in either mode. This still applies while collapsed — switch
      // modes with Alt+T / Alt+A (the switcher itself is hidden when collapsed).
      if (def.group !== 'both' && def.group !== navMode) return null;
      const key = navLabelKey(s.id);
      return { ...def, label: key ? t(key) : def.label, shortcut: s.shortcut };
    })
    .filter((x): x is NonNullable<typeof x> => x !== null);

  // Graph mode has one workspace page (Overview); keep it directly below the
  // shared ChatBot item regardless of the saved custom order.
  if (navMode === 'graph') {
    const rank = (id: AppTab) => (id === 'chat' ? 0 : id === 'overview' ? 1 : 2);
    navItems.sort((a, b) => rank(a.id) - rank(b.id));
  }

  // Red unread badges, fed by the notification center (price alerts, agent
  // approvals, finished background tasks). Counts key by the owning AppTab.
  const notificationItems = useNotificationsStore((s) => s.items);
  const unreadByTab = useMemo(() => unreadCountsByTab(notificationItems), [notificationItems]);

  // Unread belonging to tabs the CURRENT mode does not list (e.g. Agentic
  // items while in Terminal mode) is surfaced on the menu switcher so it is
  // not invisible. Bots mode lists no static nav, so every item counts.
  const hiddenUnread = useMemo(() => {
    if (navMode === 'bots') return totalUnread(notificationItems);
    let total = 0;
    for (const def of DEFAULT_SIDEBAR_SECTIONS) {
      if (def.group === 'both' || def.group === navMode) continue;
      total += unreadByTab[def.id] ?? 0;
    }
    return total;
  }, [navMode, notificationItems, unreadByTab]);

  // Keep the switcher in sync with programmatic navigation: opening a Terminal
  // screen (command palette, deep link, cross-screen CTA) shows the Terminal
  // menu, and likewise for Agentic. ChatBot is shared and never forces a switch.
  //
  // This must fire ONLY when the active tab changes — not when the mode changes.
  // Otherwise a manual switch would be immediately reverted by this effect while
  // sitting on a screen belonging to the other mode. The last-synced tab is kept
  // in a ref so choosing the other mode for the same screen is respected.
  const lastSyncedTabRef = useRef<AppTab | null>(null);
  useEffect(() => {
    if (lastSyncedTabRef.current === activeTab) return;
    lastSyncedTabRef.current = activeTab;
    const mode = modeForTab(activeTab);
    if (mode) setNavModeFromNavigation(mode);
  }, [activeTab, setNavModeFromNavigation]);

  // Track the visible tab in the notification center: opening a tab clears its
  // red badge, and a notification raised for the visible tab never badges (it
  // is already in front of the operator). The sidebar stays mounted for the
  // whole SPA session (even `hidden`, its hooks still run), so this is the
  // shell's single visible-tab signal.
  useEffect(() => {
    useNotificationsStore.getState().setActiveTab(activeTab);
  }, [activeTab]);

  const handleSelectChat = (id: string) => {
    onSelectConversation(id);
    onChangeTab('chat');
    onCloseMobile?.();
  };

  const handleTabClick = (tab: AppTab) => {
    // Clicking the ChatBot icon always starts a fresh chat, never resumes the
    // previous conversation (history is still reachable from the list above).
    if (tab === 'chat') onNewChat();
    onChangeTab(tab);
    onCloseMobile?.();
  };

  const sidebarContent = (
    <div 
      className={`sidebar-root h-full flex flex-col glass-card-strong border-r-0 shrink-0 justify-between select-none text-foreground font-sans relative transition-all duration-300 group/sidebar ${
        isCollapsed ? 'w-12 px-0 items-center' : 'w-60 px-4'
      }`}
    >
      {/* Brand logo header */}
      <div className={`flex h-12 items-center shrink-0 relative w-full ${
        isCollapsed ? 'justify-center' : 'justify-between gap-2 px-1'
      }`}>
        <div className="flex items-center gap-2.5 overflow-hidden">
          {isCollapsed ? (
            /* Collapsed — show only the favicon in its place. */
            <div className="relative flex items-center justify-center shrink-0" style={logoBox}>
              <img
                src={markSrc}
                alt={appName}
                className="h-6 w-6 object-contain transition-all duration-200 group-hover/sidebar:opacity-0 group-hover/sidebar:scale-75"
              />
              <button
                onClick={() => setDesktopCollapsed(false)}
                className="absolute inset-0 flex items-center justify-center rounded-xl border border-border/40 bg-card text-muted-foreground hover:text-foreground cursor-pointer shadow opacity-0 scale-75 group-hover/sidebar:opacity-100 group-hover/sidebar:scale-100 transition-all duration-200 hover:bg-accent"
                title="Expand Sidebar"
              >
                <ChevronRight size={15} />
              </button>
            </div>
          ) : (
            /* Expanded — the proper brand wordmark (mark + name). */
            <img
              src={wordmarkSrc}
              alt={appName}
              className="h-7 w-auto max-w-[170px] object-contain select-none"
            />
          )}
        </div>

        {/* Collapse button on the right of logo when expanded (desktop only — the
            mobile drawer closes via its own X). */}
        {!isCollapsed && !isMobile && (
          <button
            onClick={() => setDesktopCollapsed(true)}
            className="rounded-lg p-1 text-muted-foreground hover:bg-accent hover:text-foreground cursor-pointer opacity-0 group-hover/sidebar:opacity-100 transition-opacity duration-200"
            title="Collapse Sidebar"
          >
            <ChevronLeft size={16} className="transition-transform duration-300" />
          </button>
        )}
      </div>

      {/* Sidebar Content (Chat History at Top, followed by Navigation Tabs) */}
      <div className={`flex-1 flex flex-col gap-5 py-4 overflow-y-auto scrollbar-hide w-full ${
        isCollapsed ? 'items-center' : ''
      }`}>

        {/* Top-level mode switcher: Terminal (market tools), Agentic (chat,
            skills, memory), Graph Studio or Bots. A glass dropdown keeps the
            top-level menus in one place without crowding the sidebar. Hidden
            while collapsed — the switcher itself is not shown in the icon rail. */}
        {!isCollapsed && (
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <button
                  type="button"
                  aria-label={t('sidebar.modeSwitcher')}
                  title={t('sidebar.modeSwitcher')}
                  className="shrink-0 flex w-full items-center justify-between gap-2 rounded-xl glass-card-subtle border border-border/20 px-3 py-2.5 text-[13px] font-bold text-foreground transition-colors hover:bg-white/[0.04] outline-none focus-visible:border-border/40 cursor-pointer"
                />
              }
            >
              <span className="flex items-center gap-2 min-w-0">
                <ActiveModeIcon size={15} className="shrink-0" />
                <span className="truncate">{t(activeMode.labelKey)}</span>
              </span>
              <span className="flex items-center gap-2 shrink-0">
                {hiddenUnread > 0 && (
                  <span
                    title="Unread notifications in other menus"
                    className="flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold leading-none text-white"
                  >
                    {hiddenUnread > 9 ? '9+' : hiddenUnread}
                  </span>
                )}
                <ChevronDown size={15} className="shrink-0 opacity-70" />
              </span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-(--anchor-width) nav-menu-glass">
              {NAV_MODES.map(({ id, labelKey, icon: Icon }) => {
                const isActive = navMode === id;
                return (
                  <DropdownMenuItem
                    key={id}
                    onClick={() => {
                      // Bots / Graph Studio are dedicated modes; also open their
                      // workspace so the panel and the page never disagree. For
                      // Terminal/Agentic, only navigate when the current screen
                      // does not belong to the chosen mode (leaving Bots used to
                      // keep the Bots page under a Terminal sidebar).
                      setNavMode(id);
                      const opens = NAV_MODES.find((m) => m.id === id)?.opens;
                      if (opens) {
                        onChangeTab(opens);
                        return;
                      }
                      const def = NAV_DEF.get(activeTab);
                      const stays = Boolean(def && (def.group === 'both' || def.group === id));
                      if (!stays) onChangeTab(id === 'agentic' ? 'chat' : 'home');
                    }}
                    className="gap-2"
                  >
                    <Icon size={14} className="shrink-0" />
                    <span className="flex-1">{t(labelKey)}</span>
                    {MODE_SHORTCUT_LABELS.has(id) && (
                      <span className="shrink-0 rounded-md border border-border/40 px-1 py-0.5 text-[9px] font-mono font-bold leading-none text-muted-foreground">
                        {MODE_SHORTCUT_LABELS.get(id)}
                      </span>
                    )}
                    {isActive && <Check size={13} className="shrink-0 opacity-70" />}
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        {/* Quick launchers — the Channel Gateway (connect Eclipse to Telegram,
            Discord, WhatsApp, …) and the relation/skills graph browser. Shares
            the control-strip tier and the same subtle border as the switcher. */}
        {!isCollapsed && (
          <div className="-mt-3 flex items-center justify-start gap-1.5">
            <button
              type="button"
              onClick={() => setGatewayOpen(true)}
              title={t('sidebar.gatewayHint')}
              aria-label={t('sidebar.gateway')}
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.04] hover:text-foreground outline-none focus-visible:ring-1 focus-visible:ring-primary/50 cursor-pointer"
            >
              <ChatsCircle size={15} className="shrink-0" />
            </button>
            <button
              type="button"
              onClick={() => setGraphOpen(true)}
              title={t('sidebar.graphHint')}
              aria-label={t('sidebar.graph')}
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.04] hover:text-foreground outline-none focus-visible:ring-1 focus-visible:ring-primary/50 cursor-pointer"
            >
              <Network size={15} className="shrink-0" />
            </button>
            <SidebarBrokerButton variant="launcher" />
          </div>
        )}

        {/* Chat History Panel on Top of the menu list */}
        {activeTab === 'chat' && !isCollapsed && (
          <ChatHistoryPanel
            conversations={conversations}
            organization={organization}
            activeConversationId={activeConversationId}
            onSelectConversation={handleSelectChat}
            onNewChat={onNewChat}
            onDeleteConversation={onDeleteConversation}
          />
        )}

        {/* Bots is the one DEDICATED mode: the sidebar lists the user's bots
            instead of the generic nav list. Every other mode — including Graph
            Studio — shows the SAME standard navigation. */}
        {navMode === 'bots' ? (
          <BotsSidebarPanel
            collapsed={isCollapsed}
            onActivate={() => {
              onChangeTab('bots');
              onCloseMobile?.();
            }}
          />
        ) : (
          <nav
            aria-label={t('a11y.mainNavigation')}
            className={`flex flex-col gap-1.5 pt-4 border-t border-border/10 w-full ${
              isCollapsed ? 'items-center px-2' : ''
            }`}
          >
          {navItems.map((tab) => {
            const isSelected = activeTab === tab.id;
            const Icon = tab.icon;
            const unreadCount = unreadByTab[tab.id] ?? 0;

            return (
              <a
                key={tab.id}
                href={destinationToHref({ tab: tab.id })}
                data-sound="tick"
                aria-current={isSelected ? 'page' : undefined}
                onClick={(e) => {
                  // Let Ctrl/Cmd/Shift/middle-click open in a new tab (or window)
                  // via the href; only a plain left-click is handled in-page.
                  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
                  e.preventDefault();
                  handleTabClick(tab.id);
                }}
                title={isCollapsed
                  ? `${tab.shortcut ? `${tab.label} (${tab.shortcut})` : tab.label}${unreadCount ? ` · ${unreadCount} unread` : ''}`
                  : undefined}
                className={`h-8 flex items-center px-3 py-1.5 text-xs font-semibold transition-colors cursor-pointer overflow-hidden no-underline outline-none focus-visible:ring-1 focus-visible:ring-primary/50 ${
                  isSelected
                    ? 'rounded-lg bg-white/[0.07] text-foreground'
                    : 'rounded-lg bg-transparent text-muted-foreground hover:bg-white/[0.04] hover:text-foreground'
                } ${isCollapsed ? 'justify-center w-9 px-0 gap-0' : 'justify-start w-full gap-2.5'}`}
              >
                <span className="relative shrink-0 flex items-center justify-center">
                  <Icon size={15} className="transition-colors duration-300" />
                  {unreadCount > 0 && isCollapsed && (
                    <span className="absolute -right-1.5 -top-1.5 h-2 w-2 rounded-full bg-rose-500 ring-2 ring-background" />
                  )}
                </span>
                <span className={`shrink-0 whitespace-nowrap transition-all duration-300 overflow-hidden flex-1 text-left ${
                  isCollapsed ? 'opacity-0 -translate-x-2 w-0' : 'opacity-100 translate-x-0 w-auto'
                }`}>{tab.label}</span>
                {unreadCount > 0 && !isCollapsed && (
                  <span
                    title={`${unreadCount} unread`}
                    className="shrink-0 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-bold leading-none text-white"
                  >
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
                {tab.shortcut && !isCollapsed && (
                    <span className={`shrink-0 rounded-md border px-1 py-0.5 text-[9px] font-mono font-bold leading-none transition-colors duration-300 ${
                      isSelected ? 'border-border/40 text-foreground' : 'border-border/40 text-muted-foreground'
                    }`}>{tab.shortcut}</span>
                  )}
                </a>
            );
          })}
          <SavedPagesNav
            collapsed={isCollapsed}
            active={activeTab === 'pages'}
            onNavigate={onCloseMobile}
          />
          </nav>
        )}
      </div>

      {/* Footer */}
      <div className={`border-t border-border/10 py-4 shrink-0 flex flex-col gap-2 w-full ${
        isCollapsed ? 'items-center' : ''
      }`}>
        {isCollapsed ? (
          <div className="flex flex-col items-center gap-2">
            <SidebarBrokerButton collapsed />
            <button
              onClick={onOpenSettings}
              onPointerEnter={prefetchSettings}
              onFocus={prefetchSettings}
              className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent border border-border text-foreground text-xs font-bold hover:bg-accent/70 transition-colors cursor-pointer"
              title={t('sidebar.openSettings')}
              aria-label={t('sidebar.openSettings')}
            >
              {monogram}
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2 px-1 text-[11px] transition-all duration-300">
            <div className="flex flex-col min-w-0">
              <span className="font-semibold text-foreground truncate leading-tight">{appName}</span>
              <span className="text-[9px] text-muted-foreground uppercase tracking-wide leading-tight">{t(activeMode.labelKey)}</span>
            </div>
            {/* Settings gear button — bottom-right of the Terminal footer */}
            <button
              onClick={onOpenSettings}
              onPointerEnter={prefetchSettings}
              onFocus={prefetchSettings}
              className={`shrink-0 rounded-lg p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors cursor-pointer ${
                activeTab === 'settings' ? 'text-foreground bg-white/[0.08]' : ''
              }`}
              title={t('sidebar.openSettings')}
              aria-label={t('sidebar.openSettings')}
            >
              <Settings size={16} />
            </button>
          </div>
        )}
      </div>

      {gatewayOpen && <SidebarGatewayDialog open onOpenChange={setGatewayOpen} />}
      {graphOpen && <SidebarGraphDialog open onOpenChange={setGraphOpen} />}
    </div>
  );

  if (hidden) return null;

  return (
    <>
      {/* Desktop sidebar */}
      <div className={`hidden md:block h-screen select-none z-50 shrink-0 transition-all duration-300 ${
        isCollapsed ? 'w-12' : 'w-60'
      }`}>
        {sidebarContent}
      </div>

      {/* Mobile drawer overlays */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-40 flex">
          <div className="fixed inset-0 bg-background/80 backdrop-blur-sm" onClick={onCloseMobile} />
          <div className="relative flex w-60 max-w-[80vw] h-full animate-slide-in">
            {sidebarContent}
            <button
              onClick={onCloseMobile}
              className="absolute top-4 right-4 text-muted-foreground hover:text-foreground"
            >
              <X size={16} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}