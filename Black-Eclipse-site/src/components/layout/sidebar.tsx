"use client";

import React, { useEffect, useRef, useState } from 'react';
import { Plus, Trash2, X, ChevronLeft, ChevronRight, Menu, Settings, SquareTerminal, BrainCircuit } from 'lucide-react';
import { Message } from '@/types/chat';
import { useSidebarConfigStore, useHydrateSidebarConfig } from '@/lib/sidebar/store';
import { DEFAULT_SIDEBAR_SECTIONS, configMap, modeForTab, type NavGroup } from '@/lib/sidebar/config';
import { destinationToHref } from '@/lib/search/deep-link';
import { useT, navLabelKey } from '@/lib/i18n';
import { useThemeStore, BRAND_MARK_SRC, BRAND_WORDMARK_SRC } from '@/lib/theme';

const NAV_DEF = new Map(DEFAULT_SIDEBAR_SECTIONS.map((s) => [s.id, s]));

/** The two top-level menu modes and the icon each switcher button shows. */
const NAV_MODES: Array<{ id: NavGroup; labelKey: 'sidebar.terminal' | 'sidebar.agentic'; icon: typeof SquareTerminal }> = [
  { id: 'terminal', labelKey: 'sidebar.terminal', icon: SquareTerminal },
  { id: 'agentic', labelKey: 'sidebar.agentic', icon: BrainCircuit },
];

// The tab vocabulary lives ONCE in `lib/app-tabs.ts`; this shell re-exports it so
// `lib/search/types.ts` (which mirrors it) can never silently drift.
import type { AppTab } from '@/lib/app-tabs';
export type { AppTab };

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  timestamp: number;
}

interface SidebarProps {
  activeTab: AppTab;
  onChangeTab: (tab: AppTab) => void;
  conversations: Conversation[];
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
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  onOpenSettings,
  mobileOpen = false,
  onCloseMobile,
  hidden = false,
}: SidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
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

  // Keep the switcher in sync with programmatic navigation: opening a Terminal
  // screen (command palette, deep link, cross-screen CTA) shows the Terminal
  // menu, and likewise for Agentic. ChatBot is shared and never forces a switch.
  //
  // This must fire ONLY when the active tab changes — not when the mode changes.
  // Otherwise a manual switch would be immediately reverted by this effect while
  // sitting on a screen belonging to the other mode. The last-synced tab is kept
  // in a ref so choosing the other mode for the same screen is respected.
  const lastSyncedTabRef = useRef(activeTab);
  useEffect(() => {
    if (lastSyncedTabRef.current === activeTab) return;
    lastSyncedTabRef.current = activeTab;
    const mode = modeForTab(activeTab);
    if (mode) setNavMode(mode);
  }, [activeTab, setNavMode]);

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
      <div className={`flex h-14 md:h-16 items-center shrink-0 relative w-full ${
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
                onClick={() => setIsCollapsed(false)}
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

        {/* Collapse button on the right of logo when expanded (only visible on hover) */}
        {!isCollapsed && (
          <button
            onClick={() => setIsCollapsed(true)}
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

        {/* Top-level mode switcher: Terminal (market tools) vs Agentic
            (chat, skills, memory). ChatBot appears in both. Hidden while the
            sidebar is collapsed — there is no room for labels and the menu
            already collapses to icons only. */}
        {!isCollapsed && (
          <div
            role="tablist"
            aria-label={t('sidebar.modeSwitcher')}
            className="shrink-0 grid grid-cols-2 gap-1 rounded-2xl glass-card-subtle p-1 w-full"
          >
            {NAV_MODES.map(({ id, labelKey, icon: Icon }) => {
              const isActive = navMode === id;
              const label = t(labelKey);
              return (
                <button
                  key={id}
                  role="tab"
                  aria-selected={isActive}
                  data-sound="tick"
                  onClick={() => setNavMode(id)}
                  title={label}
                  className={`flex items-center justify-center gap-1.5 rounded-xl py-1.5 text-[11px] font-bold transition-all cursor-pointer ${
                    isActive
                      ? 'bg-primary/15 text-primary shadow-sm shadow-primary/5'
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'
                  }`}
                >
                  <Icon size={13} className="shrink-0" />
                  <span className="whitespace-nowrap">{label}</span>
                </button>
              );
            })}
          </div>
        )}

        {/* Chat History Panel on Top of the menu list */}
        {activeTab === 'chat' && !isCollapsed && (
          <div className="flex flex-col gap-3 pb-4">
            <div className="flex items-center justify-between px-1">
              <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-bold">{t('sidebar.chatHistory')}</span>
              <button
                onClick={onNewChat}
                className="p-1 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground flex items-center gap-1 cursor-pointer transition-all border border-border/5"
                title={t('sidebar.newChat')}
              >
                <Plus size={12} />
              </button>
            </div>
            
            <div className="flex flex-col gap-1 max-h-[180px] overflow-y-auto scrollbar-hide">
              {conversations.map((c) => {
                const isActive = activeConversationId === c.id;
                return (
                  <div
                    key={c.id}
                    onClick={() => handleSelectChat(c.id)}
                    className={`flex items-center justify-between rounded-xl px-3 py-2 text-[11px] cursor-pointer group transition-all border border-transparent ${
                      isActive
                        ? 'bg-white/[0.04] border-border/20 text-foreground font-semibold'
                        : 'bg-transparent text-muted-foreground hover:bg-accent/25 hover:text-foreground'
                    }`}
                  >
                    <span className="truncate max-w-[130px]">{c.title || t('sidebar.untitledSession')}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDeleteConversation(c.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-rose-400 rounded transition-opacity"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                );
              })}

              {conversations.length === 0 && (
                <span className="text-[10px] text-muted-foreground italic text-center py-2">{t('sidebar.noSessions')}</span>
              )}
            </div>
          </div>
        )}

        {/* Navigation list (divider line on top of icons) */}
        <nav
          aria-label={t('a11y.mainNavigation')}
          className={`flex flex-col gap-1.5 pt-4 border-t border-border/10 w-full ${
            isCollapsed ? 'items-center px-2' : ''
          }`}
        >
          {navItems.map((tab) => {
            const isSelected = activeTab === tab.id;
            const Icon = tab.icon;

            return (
              <a
                key={tab.id}
                href={destinationToHref({ tab: tab.id })}
                data-sound="tick"
                onClick={(e) => {
                  // Let Ctrl/Cmd/Shift/middle-click open in a new tab (or window)
                  // via the href; only a plain left-click is handled in-page.
                  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
                  e.preventDefault();
                  handleTabClick(tab.id);
                }}
                title={isCollapsed ? (tab.shortcut ? `${tab.label} (${tab.shortcut})` : tab.label) : undefined}
                className={`h-10 flex items-center px-3.5 py-2.5 text-xs font-semibold transition-all duration-300 cursor-pointer border overflow-hidden no-underline ${
                  isSelected
                    ? 'rounded-xl bg-primary/15 text-foreground shadow-sm shadow-primary/5 border-primary/20'
                    : 'rounded-none bg-transparent text-muted-foreground hover:rounded-xl hover:bg-accent/40 hover:text-foreground border-transparent'
                } ${isCollapsed ? 'justify-center w-10 px-0 gap-0' : 'justify-start w-full gap-3'}`}
              >
                <Icon size={16} className={`shrink-0 transition-colors duration-300 ${isSelected ? 'text-primary' : ''}`} />
                <span className={`shrink-0 whitespace-nowrap transition-all duration-300 overflow-hidden flex-1 text-left ${
                  isCollapsed ? 'opacity-0 -translate-x-2 w-0' : 'opacity-100 translate-x-0 w-auto'
                }`}>{tab.label}</span>
                {tab.shortcut && !isCollapsed && (
                  <span className={`shrink-0 rounded-md border px-1 py-0.5 text-[9px] font-mono font-bold leading-none transition-colors duration-300 ${
                    isSelected ? 'border-primary/30 text-primary' : 'border-border/40 text-muted-foreground'
                  }`}>{tab.shortcut}</span>
                )}
              </a>
            );
          })}
        </nav>
      </div>

      {/* Footer */}
      <div className={`border-t border-border/10 py-4 shrink-0 flex flex-col gap-2 w-full ${
        isCollapsed ? 'items-center' : ''
      }`}>
        {isCollapsed ? (
          <div className="flex justify-center">
            <button
              onClick={onOpenSettings}
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
              <span className="text-[9px] text-muted-foreground uppercase tracking-wide leading-tight">{t('sidebar.terminal')}</span>
            </div>
            {/* Settings gear button — bottom-right of the Terminal footer */}
            <button
              onClick={onOpenSettings}
              className={`shrink-0 rounded-lg p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors cursor-pointer ${
                activeTab === 'settings' ? 'text-primary bg-primary/10' : ''
              }`}
              title={t('sidebar.openSettings')}
              aria-label={t('sidebar.openSettings')}
            >
              <Settings size={16} />
            </button>
          </div>
        )}
      </div>
    </div>
  );

  if (hidden) return null;

  return (
    <>
      {/* Mobile drawer header toggle */}
      <div className="md:hidden fixed top-3 left-4 z-50">
        <button
          onClick={onCloseMobile}
          className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card shadow-sm hover:bg-accent text-foreground cursor-pointer"
        >
          <Menu size={16} />
        </button>
      </div>

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
          <div className="relative flex w-60 h-full animate-slide-in">
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