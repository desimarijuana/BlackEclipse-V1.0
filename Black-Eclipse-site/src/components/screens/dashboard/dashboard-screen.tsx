'use client';

// ── DashboardScreen — the customizable Financial Command Center ───────────────
// Hosts the workspace kernel (WorkspaceCanvas) for the active dashboard, plus
// the dashboard switcher, onboarding, widget library, and config panel.

import React, { useMemo, useRef, useState } from 'react';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import {
  ChevronDown, ChevronRight, Copy, Download, Globe, LayoutDashboard, Plus, RotateCcw, Settings2, Star, Trash2, Upload,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useDashboards, isOnboarded, markOnboarded, seedMarketKeyFromLegacy } from '@/lib/dashboard/use-dashboards';
import { DASHBOARD_WIDGETS, DASHBOARD_WIDGET_IDS, widgetIcon, renderDashboardWidget, buildMarketViewLayout } from '@/lib/dashboard/registry';
import { getDashboardTemplate } from '@/lib/dashboard/templates';
import { useMarketViews } from '@/lib/dashboard/market-views';
import { CustomizableWorkspace, StatusBar } from '@/components/workspace';
import { DashboardOnboarding, type OnboardingResult } from './onboarding';
import { MarketTabs } from './market-tabs';

export function DashboardScreen() {
  const dashboards = useDashboards();
  const markets = useMarketViews();
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [marketOpen, setMarketOpen] = useState(true);

  // The active layout's id + default market. The layout id keys the workspace
  // (each named layout owns its own widgets); the market drives "follow the tab"
  // widgets. A widget can still be pinned to any market from its own header.
  const layoutId = markets.active?.id ?? 'US';
  const activeMarket = markets.active?.market ?? 'US';

  // Seed the starting workspace for this layout. A layout created from a preset
  // uses its own templateId; otherwise it inherits the dashboard's template
  // (the persona the user picked at onboarding). Asset-class lead/extra widgets
  // are layered on for the layout's default market.
  const templateId = markets.active?.templateId ?? dashboards.active?.templateId ?? 'trader';
  const defaultLayout = useMemo(() => {
    const t = getDashboardTemplate(templateId);
    const templateBase = t ? t.build(DASHBOARD_WIDGET_IDS) : undefined;
    return buildMarketViewLayout(activeMarket, DASHBOARD_WIDGET_IDS, templateBase);
  }, [activeMarket, templateId]);

  // Per-dashboard + per-layout storage key. Seed the US layout key from the
  // legacy (un-suffixed) arrangement BEFORE the workspace store is created on
  // first render, so an existing user's centre layout survives the upgrade.
  const storageKey = useMemo(() => {
    const baseKey = dashboards.active?.storageKey ?? 'be_ws_dashboard_none';
    const key = `${baseKey}__m_${layoutId}`;
    // Only the built-in US layout inherits the pre-layout arrangement.
    if (layoutId === 'US') seedMarketKeyFromLegacy(baseKey, key, 'US');
    return key;
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
    if (name) dashboards.create(name, 'trader');
  };

  usePageShortcuts(rootRef, [
    { id: 'dashboard-new', label: 'New dashboard', keys: 'shift+d', run: createDashboard, enabled: dashboards.loaded && !showOnboarding },
  ]);

  return (
    <div ref={rootRef} data-keyboard-scope="Command Center" className="animate-fade-in-up w-full">
      {/* Header + toolbar — matches the standard page heading */}
      <div className="mb-5 flex flex-wrap items-center gap-4 border-b border-border/10 pb-4">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
          <LayoutDashboard className="text-primary" size={30} />
        </div>
        <div className="min-w-0">
          <h1 className="font-serif text-2xl font-semibold tracking-tight text-foreground">Command Center</h1>
          <p className="text-muted-foreground text-xs mt-0.5">Build your workspace — arrange widgets, sections and columns to suit how you trade.</p>
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

      {/* Reusable customizable workspace — centre + rail are ONE workspace.
          The single Customize button drives both and cards drag between them. */}
      <CustomizableWorkspace
        key={storageKey}
        storageKey={storageKey}
        defaultLayout={defaultLayout}
        widgets={DASHBOARD_WIDGETS}
        widgetIcon={widgetIcon}
        renderWidget={(widgetId, placement) => renderDashboardWidget(widgetId, placement)}
        railClassName="hidden lg:block w-72"
        railCollapsed={!marketOpen}
        onToggleRail={() => setMarketOpen(v => !v)}
        railHeader={(
          <div className="mb-3 flex items-center justify-between rounded-2xl glass-card px-3 py-2">
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
        )}
        statusBar={<StatusBar version="v0.1.0" layoutStatus="saved" pendingOrders={0} notifications={0} />}
      />

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

