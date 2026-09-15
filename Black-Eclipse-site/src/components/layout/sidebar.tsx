"use client";

import React, { useState } from 'react';
import { Sparkles, Plus, Trash2, X, ChevronLeft, ChevronRight, Menu, Settings } from 'lucide-react';
import { Message } from '@/types/chat';
import { useSidebarConfigStore, useHydrateSidebarConfig } from '@/lib/sidebar/store';
import { DEFAULT_SIDEBAR_SECTIONS, configMap } from '@/lib/sidebar/config';

const NAV_DEF = new Map(DEFAULT_SIDEBAR_SECTIONS.map((s) => [s.id, s]));

export type AppTab = 'chat' | 'news' | 'discovery' | 'heatmap' | 'chart' | 'economics' | 'portfolio' | 'journal' | 'settings' | 'alerts' | 'dashboard' | 'market-workspace' | 'investor-eye';

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
}: SidebarProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  // User-customized menu: order, visibility, and shortcuts come from the
  // shared store (edited in Settings › Sidebar). Hydrate once on mount.
  useHydrateSidebarConfig();
  const sidebarConfig = useSidebarConfigStore((s) => s.config);
  const cfgMap = configMap(sidebarConfig);
  const navItems = sidebarConfig.sections
    .filter((s) => cfgMap.get(s.id)?.enabled !== false)
    .map((s) => {
      const def = NAV_DEF.get(s.id);
      return def ? { ...def, shortcut: s.shortcut } : null;
    })
    .filter((x): x is NonNullable<typeof x> => x !== null);

  const handleSelectChat = (id: string) => {
    onSelectConversation(id);
    onChangeTab('chat');
    onCloseMobile?.();
  };

  const handleTabClick = (tab: AppTab) => {
    onChangeTab(tab);
    onCloseMobile?.();
  };

  const sidebarContent = (
    <div 
      className={`sidebar-root h-full flex flex-col glass-card-strong border-r-0 shrink-0 justify-between select-none text-foreground font-sans relative transition-all duration-300 group/sidebar ${
        isCollapsed ? 'w-16 px-0 items-center' : 'w-60 px-4'
      }`}
    >
      {/* Brand logo header */}
      <div className={`flex h-14 md:h-16 items-center shrink-0 relative w-full ${
        isCollapsed ? 'justify-center' : 'justify-between gap-2 px-1'
      }`}>
        <div className="flex items-center gap-2 overflow-hidden">
          <div className="relative w-8 h-8 flex items-center justify-center shrink-0">
            {/* Sparkles Logo (hidden on hover when collapsed) */}
            <div className={`w-8 h-8 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center text-primary-foreground shadow-sm shadow-primary/20 transition-all duration-200 ${
              isCollapsed ? 'group-hover/sidebar:opacity-0 group-hover/sidebar:scale-75' : ''
            }`}>
              <Sparkles size={14} className="animate-pulse" />
            </div>
            
            {/* Expand Slide Icon (shows on hover when collapsed) */}
            {isCollapsed && (
              <button
                onClick={() => setIsCollapsed(false)}
                className="absolute inset-0 flex items-center justify-center rounded-xl border border-border/40 bg-card text-muted-foreground hover:text-foreground cursor-pointer shadow opacity-0 scale-75 group-hover/sidebar:opacity-100 group-hover/sidebar:scale-100 transition-all duration-200 hover:bg-accent"
                title="Expand Sidebar"
              >
                <ChevronRight size={14} />
              </button>
            )}
          </div>
          {!isCollapsed && (
            <span className={`text-sm font-semibold tracking-tight truncate transition-all duration-300 ${
              isCollapsed ? 'opacity-0 translate-x-2' : 'opacity-100 translate-x-0'
            }`}>
              BlackEclipse
            </span>
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
        
        {/* Chat History Panel on Top of the menu list */}
        {activeTab === 'chat' && !isCollapsed && (
          <div className="flex flex-col gap-3 pb-4">
            <div className="flex items-center justify-between px-1">
              <span className="text-[9px] text-muted-foreground uppercase tracking-widest font-bold">Chat History</span>
              <button
                onClick={onNewChat}
                className="p-1 rounded-md text-muted-foreground hover:bg-accent hover:text-foreground flex items-center gap-1 cursor-pointer transition-all border border-border/5"
                title="New Chat"
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
                    <span className="truncate max-w-[130px]">{c.title || 'Untitled Session'}</span>
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
                <span className="text-[10px] text-muted-foreground italic text-center py-2">No active sessions</span>
              )}
            </div>
          </div>
        )}

        {/* Navigation list (divider line on top of icons) */}
        <div className={`flex flex-col gap-1.5 pt-4 border-t border-border/10 w-full ${
          isCollapsed ? 'items-center px-2' : ''
        }`}>
          {navItems.map((tab) => {
            const isSelected = activeTab === tab.id;
            const Icon = tab.icon;

            return (
              <button
                key={tab.id}
                onClick={() => handleTabClick(tab.id)}
                title={isCollapsed ? (tab.shortcut ? `${tab.label} (${tab.shortcut})` : tab.label) : undefined}
                className={`h-10 flex items-center px-3.5 py-2.5 text-xs font-semibold transition-all duration-300 cursor-pointer border overflow-hidden ${
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
              </button>
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div className={`border-t border-border/10 py-4 shrink-0 flex flex-col gap-2 w-full ${
        isCollapsed ? 'items-center' : ''
      }`}>
        {isCollapsed ? (
          <div className="flex justify-center">
            <div 
              className="w-9 h-9 rounded-xl bg-accent border border-border flex justify-center items-center font-bold text-xs text-muted-foreground"
              title="BlackEclipse"
            >
              B
            </div>
          </div>
        ) : (
          <div className={`flex items-center justify-between px-1 text-[11px] transition-all duration-300 ${
            isCollapsed ? 'opacity-0' : 'opacity-100'
          }`}>
            <div className="flex flex-col truncate max-w-[130px]">
              <span className="font-semibold text-foreground truncate">BlackEclipse</span>
              <span className="text-[9px] text-muted-foreground uppercase">Terminal</span>
            </div>
            {/* Settings gear button — bottom-right of the Terminal footer */}
            <button
              onClick={onOpenSettings}
              className={`p-1.5 rounded-none text-muted-foreground hover:text-foreground hover:bg-accent transition-colors cursor-pointer ${
                activeTab === 'settings' ? 'text-primary bg-primary/10' : ''
              }`}
              title="Settings"
              aria-label="Open Settings"
            >
              <Settings size={16} />
            </button>
          </div>
        )}
      </div>
    </div>
  );

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
        isCollapsed ? 'w-16' : 'w-60'
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