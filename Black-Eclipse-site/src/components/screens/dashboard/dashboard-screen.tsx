'use client';

// ── DashboardScreen — the customizable Financial Command Center ───────────────
// Hosts the workspace kernel (WorkspaceCanvas) for the active dashboard, plus
// the dashboard switcher, onboarding, widget library, and config panel.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import {
  ChevronDown, ChevronLeft, ChevronRight, Copy, Download, Globe, LayoutDashboard, List, Maximize2, Minimize2, Plus, RotateCcw, Settings2, Star, Trash2, Upload,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useIsMobile } from '@/hooks/use-media-query';
import { useDashboards, isOnboarded, markOnboarded } from '@/lib/dashboard/use-dashboards';
import { DASHBOARD_WIDGET_IDS, widgetIcon, renderDashboardWidget, buildMarketViewLayout } from '@/lib/dashboard/registry';
import { useWidgets } from '@/lib/workspace/use-widgets';
import { eclipseSdk } from '@/lib/sdk';
import { getDashboardTemplate } from '@/lib/dashboard/templates';
import { getDefaultBoard } from '@/lib/dashboard/default-board';
import { useMarketViews } from '@/lib/dashboard/market-views';
import { CustomizableWorkspace, StatusBar } from '@/components/workspace';
import {
  fetchDashboardLayout,
  isOwnPublish,
  publishDashboardLayout,
  stableLayoutKey,
} from '@/lib/ui-engineering/dashboard-blueprint';
import { loadWorkspace, saveWorkspace } from '@/lib/workspace/persistence';
import type { WorkspaceLayout } from '@/lib/workspace/types';
import { TopBar } from '@/components/layout/top-bar';
import { AuroraGlow } from '@/components/layout/aurora-glow';
import { DashboardOnboarding, type OnboardingResult } from './onboarding';
import { MarketTabs } from './market-tabs';

export function DashboardScreen() {
  const dashboards = useDashboards();
  const markets = useMarketViews();
  const widgets = useWidgets({ surface: 'dashboard' });
  const isMobile = useIsMobile();
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

  const knownWidgetIds = useMemo(() => {
    const ids = new Set<string>([...DASHBOARD_WIDGET_IDS, ...widgets.map((widget) => widget.id)]);
    const local = loadWorkspace(storageKey, defaultLayout);
    if (!local.corrupt) {
      for (const section of local.layout.sections) {
        for (const column of section.columns) {
          for (const widget of column.widgets) ids.add(widget.widgetId);
        }
      }
    }
    return [...ids];
  }, [storageKey, defaultLayout, widgets]);

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

  // Mirror the board to a UI blueprint (debounced) so Eclipse can see and edit
  // the dashboard the user actually has. Best-effort — a failure never affects
  // the UI. See docs/harness/capability-extension-plan.md (Phase E).
  const publishTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleLayoutChange = useCallback((layout: WorkspaceLayout) => {
    const active = dashboards.active;
    if (!active) return;
    if (publishTimer.current) clearTimeout(publishTimer.current);
    publishTimer.current = setTimeout(() => {
      void publishDashboardLayout({ dashboardId: active.id, title: active.name, layout });
    }, 2500);
  }, [dashboards.active]);

  // Reverse sync (Phase E): an agent (or another client) edit to this
  // dashboard's mirrored blueprint lands on the live board. On a revision this
  // client did NOT publish, the fetched layout is persisted into this
  // dashboard's storage and the workspace remounts (`remoteRevision` keys it).
  // The immediate first poll runs BEFORE the mount publish (2.5 s debounce), so
  // an edit made while the page was closed is applied, not overwritten.
  const [remoteRevision, setRemoteRevision] = useState(0);
  const syncSeen = useRef<Map<string, number>>(new Map());
  const activeDashboardId = dashboards.active?.id;
  useEffect(() => {
    if (!activeDashboardId || typeof window === 'undefined') return;
    let cancelled = false;
    let inFlight = false;
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const snapshot = await fetchDashboardLayout(activeDashboardId);
        if (cancelled || !snapshot) return;
        const seen = syncSeen.current.get(activeDashboardId) ?? 0;
        if (snapshot.revision <= seen) return;
        syncSeen.current.set(activeDashboardId, snapshot.revision);
        if (isOwnPublish(activeDashboardId, snapshot.revision)) return;
        const local = loadWorkspace(storageKey, defaultLayout);
        if (!local.corrupt && stableLayoutKey(local.layout) === stableLayoutKey(snapshot.layout)) {
          return;
        }
        saveWorkspace(storageKey, snapshot.layout);
        setRemoteRevision((value) => value + 1);
      } finally {
        inFlight = false;
      }
    };
    void poll();

    let source: EventSource | null = null;
    let fallback: ReturnType<typeof setInterval> | null = null;
    const startFallback = () => {
      if (!fallback) fallback = setInterval(() => void poll(), 60_000);
    };
    try {
      source = new EventSource('/api/ui/stream');
      source.addEventListener('changed', () => void poll());
      source.addEventListener('error', startFallback);
    } catch {
      startFallback();
    }
    return () => {
      cancelled = true;
      source?.close();
      if (fallback) clearInterval(fallback);
    };
  }, [activeDashboardId, storageKey, defaultLayout]);

  useEffect(() => {
    if (!dashboards.loaded || !dashboards.activeId) return;
    void eclipseSdk.dashboards.setActive(dashboards.activeId).catch(() => {});
  }, [dashboards.loaded, dashboards.activeId]);

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
      key={`${storageKey}:${remoteRevision}`}
      storageKey={storageKey}
      defaultLayout={defaultLayout}
      widgets={widgets}
      knownWidgetIds={knownWidgetIds}
      widgetIcon={widgetIcon}
      renderWidget={(widgetId, placement) => renderDashboardWidget(widgetId, placement)}
      onLayoutChange={handleLayoutChange}
      dense
      zones={{
        left: {
          className: 'hidden xl:block w-64',
          resizerClassName: 'hidden xl:block',
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
          resizerClassName: 'hidden lg:block',
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
      statusBar={isMobile ? undefined : <StatusBar version="v0.1.0" layoutStatus="saved" pendingOrders={0} notifications={0} />}
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
            <div className="absolute right-0 top-full z-40 mt-2 w-64 max-w-[90vw] rounded-2xl border border-white/15 dark:border-white/10 glass-card-strong shadow-2xl shadow-black/40 p-2 animate-fade-in">
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

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={toggleFullscreen}
            className="glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer"
            title="Fullscreen (Shift+F)"
          >
            <Maximize2 size={13} /> <span className="hidden sm:inline">Fullscreen</span>
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
            className="glass-button hidden items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer sm:inline-flex"
            title="Export this dashboard layout"
          >
            <Download size={13} /> <span className="hidden sm:inline">Export</span>
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
            className="glass-button hidden items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer sm:inline-flex"
            title="Import a dashboard layout"
          >
            <Upload size={13} /> <span className="hidden sm:inline">Import</span>
          </button>
          <button
            onClick={() => dashboards.reset(dashboards.activeId!)}
            className="glass-button hidden items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary transition-all cursor-pointer sm:inline-flex"
            title="Reset this dashboard to its template"
          >
            <RotateCcw size={13} /> <span className="hidden sm:inline">Reset</span>
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


