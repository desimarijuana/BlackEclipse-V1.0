'use client';

// ── DashboardScreen — the customizable Financial Command Center ───────────────
// Hosts the workspace kernel (WorkspaceCanvas) for the active dashboard, plus
// the dashboard switcher, onboarding, widget library, and config panel.

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import {
  ChevronDown, ChevronLeft, ChevronRight, Copy, Download, Globe, LayoutDashboard, List, Maximize2, Minimize2, Plus, RotateCcw, Settings2, Star, Trash2, Upload,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useDashboards, isOnboarded, markOnboarded } from '@/lib/dashboard/use-dashboards';
import { DASHBOARD_WIDGETS, DASHBOARD_WIDGET_IDS, widgetIcon, renderDashboardWidget, buildMarketViewLayout } from '@/lib/dashboard/registry';
import { getDashboardTemplate } from '@/lib/dashboard/templates';
import { getDefaultBoard } from '@/lib/dashboard/default-board';
import { useMarketViews } from '@/lib/dashboard/market-views';
import { CustomizableWorkspace, StatusBar } from '@/components/workspace';
import { TopBar } from '@/components/layout/top-bar';
import { AuroraGlow } from '@/components/layout/aurora-glow';
import { DashboardOnboarding, type OnboardingResult } from './onboarding';
import { MarketTabs } from './market-tabs';

export function DashboardScreen() {
  const dashboards = useDashboards();
  const markets = useMarketViews();
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [watchlistOpen, setWatchlistOpen] = useState(true);
  const [marketOpen, setMarketOpen] = useState(true);
  // In-app fullscreen: the Command Center expands to a fixed full-viewport
  // overlay (its own slim bar), hiding the app chrome for a focused board.
  const [isFullscreen, setIsFullscreen] = useState(false);

  // The active layout's id + default market. The layout id keys the workspace
  // (each named layout owns its own widgets); the market drives "follow the tab"
  // widgets. A widget can still be pinned to any market from its own header.
  const layoutId = markets.active?.id ?? 'US';
  const activeMarket = markets.active?.market ?? 'US';

  // Seed the starting workspace for this layout. Priority:
  //   1. a layout explicitly created from a persona preset (its own templateId);
  //   2. the SHIPPED curated board (DEFAULT_BOARD_JSON) — the product default
  //      every new user downloads into;
  //   3. the dashboard's persona template (onboarding pick / legacy).
  // Side rails (Watchlist / Market) are layered on top in every case.
  const explicitTemplateId = markets.active?.templateId;
  const dashboardTemplateId = dashboards.active?.templateId ?? 'tape-reader';
  const defaultLayout = useMemo(() => {
    const known = new Set(DASHBOARD_WIDGET_IDS);
    // A layout created from a persona preset always honours that preset;
    // everything else (new users, resets) starts from the SHIPPED curated board
    // when one is configured. `buildMarketViewLayout` frames it with the side
    // rails and dedupes globally, so a curated widget that also lives in a rail
    // is never rendered twice.
    const curated = explicitTemplateId ? null : getDefaultBoard(known);
    const base = curated ?? (() => {
      const t = getDashboardTemplate(explicitTemplateId ?? dashboardTemplateId);
      return t ? t.build(DASHBOARD_WIDGET_IDS) : undefined;
    })();
    return buildMarketViewLayout(activeMarket, DASHBOARD_WIDGET_IDS, base ?? undefined);
  }, [activeMarket, explicitTemplateId, dashboardTemplateId]);

  // Per-dashboard + per-layout storage key. v7 is a deliberate reset into the
  // track board; pre-v7 arrangements are NOT carried forward (the old band
  // grammar was inherently gappy), so no legacy market-key seeding here.
  const storageKey = useMemo(() => {
    const baseKey = dashboards.active?.storageKey ?? 'be_ws_dashboard_none';
    return `${baseKey}__m_${layoutId}`;
  }, [dashboards.active?.storageKey, layoutId]);

  // First-run onboarding.
  const [onboarded, setOnboarded] = useState<boolean>(() => isOnboarded());
  const showOnboarding = dashboards.loaded && !onboarded;

  const handleOnboard = (result: OnboardingResult) => {
    markOnboarded();
    setOnboarded(true);
    if (dashboards.list.length === 1 && dashboards.list[0].name === 'Main') {
      dashboards.rename(dashboards.list[0].id, result.name);
    }
  };

  const rootRef = useRef<HTMLDivElement>(null);
  const createDashboard = () => {
    setSwitcherOpen(false);
    const name = prompt('New dashboard name');
    if (name) dashboards.create(name, 'tape-reader');
  };

  const toggleFullscreen = () => setIsFullscreen(v => !v);

  usePageShortcuts(rootRef, [
    { id: 'dashboard-new', label: 'New dashboard', keys: 'shift+d', run: createDashboard, enabled: dashboards.loaded && !showOnboarding },
    { id: 'dashboard-fullscreen', label: 'Toggle fullscreen', keys: 'shift+f', run: toggleFullscreen, enabled: dashboards.loaded && !showOnboarding },
  ]);

  // Lock page scroll while fullscreen so the reclaimed space is usable and the
  // background can't drift behind the overlay. Esc exits.
  useEffect(() => {
    if (!isFullscreen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    // Esc exits — unless the workspace already consumed it (active drag/grab),
    // in which case the card gesture should win.
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !e.defaultPrevented) setIsFullscreen(false); };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [isFullscreen]);

  // The workspace is rendered either inline (normal) or inside the fullscreen
  // portal. It is hoisted into a variable so both paths share one instance.
  const workspaceEl = (
    <CustomizableWorkspace
      key={storageKey}
      storageKey={storageKey}
      defaultLayout={defaultLayout}
      widgets={DASHBOARD_WIDGETS}
      widgetIcon={widgetIcon}
      renderWidget={(widgetId, placement) => renderDashboardWidget(widgetId, placement)}
      dense
      zones={{
        left: {
          className: 'hidden xl:block w-64',
          collapsed: !watchlistOpen,
          onToggle: () => setWatchlistOpen(v => !v),
          header: (
            <div className="mb-2 flex items-center justify-between rounded-2xl glass-card px-3 py-2">
              <span className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                <List size={13} className="text-primary" /> Watchlist
              </span>
              <button
                onClick={() => setWatchlistOpen(false)}
                className="glass-button rounded-lg p-1 text-muted-foreground hover:text-foreground cursor-pointer"
                title="Collapse watchlist panel"
              >
                <ChevronLeft size={14} />
              </button>
            </div>
          ),
        },
        right: {
          className: 'hidden lg:block w-72',
          collapsed: !marketOpen,
          onToggle: () => setMarketOpen(v => !v),
          header: (
            <div className="mb-2 flex items-center justify-between rounded-2xl glass-card px-3 py-2">
              <span className="flex items-center gap-1.5 text-xs font-bold text-foreground">
                <Globe size={13} className="text-primary" /> Market
              </span>
              <button
                onClick={() => setMarketOpen(false)}
                className="glass-button rounded-lg p-1 text-muted-foreground hover:text-foreground cursor-pointer"
                title="Collapse market panel"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          ),
        },
      }}
      statusBar={<StatusBar version="v0.1.0" layoutStatus="saved" pendingOrders={0} notifications={0} />}
    />
  );

  // Fullscreen, portaled to <body>: the app shell is wrapped in a glass-card
  // (backdrop-filter creates a containing block), so a bare `position: fixed`
  // would be trapped and the global nav would stay on top. Same reason the
  // Chart Workspace portals its full-page overlay. Early-returned so exactly
  // one keyboard scope / rootRef exists at a time.
  if (isFullscreen && typeof document !== 'undefined') {
    return createPortal(
      <div
        ref={rootRef}
        tabIndex={-1}
        data-keyboard-scope="Command Center"
        className="fixed inset-0 z-[80] flex h-[100dvh] w-screen flex-col overflow-hidden bg-background/95 backdrop-blur-md outline-none"
      >
        {/* Aurora is mounted in the app shell at z-0, but this overlay portals
            to <body> above it, so fullscreen needs its own copy of the glow.
            Rendered first (behind the TopBar + workspace). */}
        <AuroraGlow />
        {/* The REAL app TopBar — price ribbon + global ⌘K search. No custom
            bar; fullscreen keeps the live market chrome the app already has. */}
        <div className="relative z-10 flex min-h-0 flex-1 flex-col">
          <div className="flex shrink-0 items-center gap-2">
            <div className="min-w-0 flex-1">
              <TopBar activeTab="dashboard" />
            </div>
            {/* Exit lives in the top bar row, aligned with the app chrome,
                instead of floating over the bottom of the board. */}
            <button
              onClick={toggleFullscreen}
              className="glass-button mr-3 inline-flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer md:mr-6"
              title="Exit fullscreen (Esc)"
            >
              <Minimize2 size={13} /> Exit
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">{workspaceEl}</div>
        </div>
        {/* The app-wide ChatDock (mounted once in StockChat) portals to <body>
            at z-[90], above this z-[80] overlay, so fullscreen needs no copy. */}
        {showOnboarding && (
          <DashboardOnboarding open onComplete={(r) => handleOnboard(r)} />
        )}
      </div>,
      document.body,
    );
  }

  return (
    <div ref={rootRef} data-keyboard-scope="Command Center" className="animate-fade-in-up w-full">
      {/* Header + toolbar — denser than a content page; this is a dashboard. */}
      <div className="mb-3 flex flex-wrap items-center gap-3 border-b border-border/10 pb-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
          <LayoutDashboard className="text-primary" size={20} />
        </div>
        <div className="min-w-0">
          <h1 className="font-serif text-xl font-semibold tracking-tight text-foreground">Command Center</h1>
          <p className="text-muted-foreground text-[11px] mt-0.5 hidden sm:block">Arrange widgets, sections and columns to suit how you trade.</p>
        </div>

        {/* Dashboard switcher */}
        <div className="relative ml-auto">
          <button
            onClick={() => setSwitcherOpen(v => !v)}
            className="glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer"
          >
            {dashboards.active?.name ?? 'Dashboard'}
            <ChevronDown size={13} />
          </button>
          {switcherOpen && (
            <div className="absolute left-0 top-full z-40 mt-2 w-64 rounded-2xl border border-white/15 dark:border-white/10 glass-card-strong shadow-2xl shadow-black/40 p-2 animate-fade-in">
              <div className="flex flex-col gap-1">
                {dashboards.list.map(d => (
                  <div
                    key={d.id}
                    className={cn(
                      'group flex items-center gap-2 rounded-xl px-2.5 py-2 text-xs cursor-pointer transition-colors',
                      d.id === dashboards.activeId ? 'bg-primary/10 text-primary' : 'hover:bg-accent/40 text-foreground',
                    )}
                    onClick={() => { dashboards.switchTo(d.id); setSwitcherOpen(false); }}
                  >
                    <span className="flex-1 truncate font-semibold">{d.name}</span>
                    {d.isDefault && <Star size={11} className="text-amber-400 shrink-0" />}
                    <span className="hidden group-hover:flex items-center gap-1 shrink-0">
                      <button
                        onClick={(e) => { e.stopPropagation(); const n = prompt('Rename dashboard', d.name); if (n) dashboards.rename(d.id, n); }}
                        className="rounded p-1 text-muted-foreground hover:text-primary cursor-pointer" title="Rename"
                      ><Settings2 size={11} /></button>
                      <button
                        onClick={(e) => { e.stopPropagation(); dashboards.duplicate(d.id); }}
                        className="rounded p-1 text-muted-foreground hover:text-primary cursor-pointer" title="Duplicate"
                      ><Copy size={11} /></button>
                      <button
                        onClick={(e) => { e.stopPropagation(); dashboards.setDefault(d.id); }}
                        className="rounded p-1 text-muted-foreground hover:text-amber-400 cursor-pointer" title="Set default"
                      ><Star size={11} /></button>
                      <button
                        onClick={(e) => { e.stopPropagation(); if (confirm(`Delete "${d.name}"?`)) dashboards.remove(d.id); }}
                        className="rounded p-1 text-muted-foreground hover:text-rose-400 cursor-pointer" title="Delete"
                      ><Trash2 size={11} /></button>
                    </span>
                  </div>
                ))}
              </div>
              <div className="mt-1 border-t border-border/10 pt-1.5">
                <button
                  onClick={createDashboard}
                  title="New dashboard (Shift+D)"
                  className="flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-xs font-semibold text-primary hover:bg-primary/10 cursor-pointer"
                >
                  <Plus size={13} /> New dashboard
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={toggleFullscreen}
            className="glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer"
            title="Fullscreen (Shift+F)"
          >
            <Maximize2 size={13} /> Fullscreen
          </button>
          <button
            onClick={() => {
              const json = dashboards.exportLayout(dashboards.activeId!);
              if (json) {
                const blob = new Blob([json], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${dashboards.active?.name ?? 'dashboard'}.json`;
                a.click();
                URL.revokeObjectURL(url);
              }
            }}
            className="glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer"
            title="Export this dashboard layout"
          >
            <Download size={13} /> Export
          </button>
          <button
            onClick={() => {
              const input = document.createElement('input');
              input.type = 'file';
              input.accept = '.json';
              input.onchange = async () => {
                const file = input.files?.[0];
                if (!file) return;
                const text = await file.text();
                dashboards.importLayout(text);
              };
              input.click();
            }}
            className="glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer"
            title="Import a dashboard layout"
          >
            <Upload size={13} /> Import
          </button>
          <button
            onClick={() => dashboards.reset(dashboards.activeId!)}
            className="glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer"
            title="Reset this dashboard to its template"
          >
            <RotateCcw size={13} /> Reset
          </button>
        </div>
      </div>

      {/* Market tabs — pick a country/market; each keeps its own widget layout. */}
      <MarketTabs />

      {/* Reusable customizable workspace — left, centre and right are ONE
          workspace. The single Customize button drives all three, cards drag
          between them, and the left/right panels can be removed from Customize. */}
      {workspaceEl}

      {/* Onboarding */}
      {showOnboarding && (
        <DashboardOnboarding
          open
          onComplete={(r) => handleOnboard(r)}
        />
      )}
    </div>
  );
}


