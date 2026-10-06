'use client';

// ── PanelToolbar — the workspace's global control strip ──────────────────────
// Layout selector, add-panel menu, preset picker, workspace CRUD, full-page and
// edit toggles. All controls reuse the BlackEclipse glass-button / ToolbarMenu
// vocabulary so the terminal feels native.

import React from 'react';
import {
  Copy, Grid2x2, LayoutGrid, LayoutTemplate, Maximize2, Minimize2, Plus,
  RotateCcw, Save, Settings2, Trash2,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { ToolbarMenu } from '@/components/chart/toolbar-menu';
import { GRID_PRESETS, MARKET_PANEL_TYPES, type MarketPanelType } from '@/lib/market-workspace/types';
import { WORKSPACE_PRESETS } from '@/lib/market-workspace/presets';

const PANEL_LABEL: Record<MarketPanelType, string> = {
  chart: 'Chart',
  watchlist: 'Watchlist',
  'market-overview': 'Market Overview',
  news: 'News',
  fundamentals: 'Fundamentals',
  'economic-calendar': 'Economic Calendar',
  'ai-analysis': 'AI Analysis',
  portfolio: 'Portfolio',
  heatmap: 'Heatmap',
  alerts: 'Alerts',
  screener: 'Discover',
};

export interface PanelToolbarProps {
  layoutId: string;
  editMode: boolean;
  fullPage: boolean;
  panelCount: number;
  onAddPanel: (type: MarketPanelType) => void;
  onLayout: (layoutId: string) => void;
  onAutoArrange: () => void;
  onToggleEdit: () => void;
  onToggleFullPage: () => void;
  onApplyPreset: (presetId: string) => void;
  onSave: () => void;
  onReset: () => void;
  onDuplicateWorkspace?: () => void;
  onRenameWorkspace?: () => void;
  workspaceName: string;
  savedLabel?: string;
}

export function PanelToolbar({
  layoutId, editMode, fullPage, panelCount,
  onAddPanel, onLayout, onAutoArrange, onToggleEdit, onToggleFullPage,
  onApplyPreset, onSave, onReset, onDuplicateWorkspace, onRenameWorkspace,
  workspaceName, savedLabel,
}: PanelToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="hidden font-mono text-[9px] uppercase tracking-wide text-muted-foreground/60 lg:inline">{panelCount} panels</span>
      {/* Layout selector */}
      <ToolbarMenu
        icon={<LayoutGrid size={12} />}
        label={GRID_PRESETS.find(p => p.id === layoutId)?.label ?? 'Custom'}
        title="Grid layout"
        width={220}
      >
        {(close) => (
          <>
            <div className="px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Preset grid</div>
            <div className="grid grid-cols-2 gap-1">
              {GRID_PRESETS.map(p => (
                <button
                  key={p.id}
                  onClick={() => { onLayout(p.id); close(); }}
                  className={cn(
                    'rounded-lg px-2 py-1.5 text-left text-[11px] font-bold transition-colors cursor-pointer',
                    p.id === layoutId ? 'bg-primary/15 text-primary' : 'text-foreground hover:bg-accent/50',
                  )}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <div className="mt-1 border-t border-border/10 pt-1">
              <button
                onClick={() => { onLayout('custom'); close(); }}
                className={cn(
                  'flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] font-bold transition-colors cursor-pointer',
                  layoutId === 'custom' ? 'bg-primary/15 text-primary' : 'text-foreground hover:bg-accent/50',
                )}
              >
                <Settings2 size={12} /> Custom (free resize)
              </button>
              <button
                onClick={() => { onAutoArrange(); close(); }}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] font-bold text-foreground transition-colors hover:bg-accent/50 cursor-pointer"
              >
                <Grid2x2 size={12} /> Auto-arrange
              </button>
            </div>
          </>
        )}
      </ToolbarMenu>

      {/* Add panel */}
      <ToolbarMenu icon={<Plus size={12} />} label="Add Panel" title="Add a panel" width={220} align={fullPage ? 'left' : 'left'}>
        {(close) => (
          <>
            <div className="px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Panels</div>
            {MARKET_PANEL_TYPES.map(type => (
              <button
                key={type}
                onClick={() => { onAddPanel(type); close(); }}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] font-semibold text-foreground transition-colors hover:bg-accent/50 cursor-pointer"
              >
                <Plus size={11} className="text-muted-foreground" /> {PANEL_LABEL[type]}
              </button>
            ))}
          </>
        )}
      </ToolbarMenu>

      {/* Presets */}
      <ToolbarMenu icon={<LayoutTemplate size={12} />} label="Presets" title="Workspace presets" width={260}>
        {(close) => (
          <>
            <div className="px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Starting layouts</div>
            {WORKSPACE_PRESETS.map(p => (
              <button
                key={p.id}
                onClick={() => { onApplyPreset(p.id); close(); }}
                className="flex w-full flex-col rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-accent/50 cursor-pointer"
              >
                <span className="text-[11px] font-bold text-foreground">{p.name}</span>
                <span className="text-[9px] leading-snug text-muted-foreground">{p.desc}</span>
              </button>
            ))}
            <p className="px-2 pt-1 text-[9px] italic text-muted-foreground/60">Presets replace the current layout — every panel stays editable.</p>
          </>
        )}
      </ToolbarMenu>

      <button
        onClick={onToggleEdit}
        className={cn(
          'glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition-all cursor-pointer',
          editMode ? 'text-primary' : 'text-muted-foreground hover:text-primary',
        )}
        title="Customize layout (drag, resize, dupe panels)"
      >
        <Settings2 size={13} /> {editMode ? 'Done' : 'Customize'}
      </button>

      <div className="flex-1" />

      {savedLabel && <span className="hidden font-mono text-[9px] uppercase tracking-wide text-muted-foreground/60 sm:inline">{savedLabel}</span>}

      {/* Workspace CRUD */}
      <ToolbarMenu icon={<Copy size={12} />} label={null} title={`Workspace: ${workspaceName}`} width={220} align="right">
        {(close) => (
          <>
            <div className="px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Workspace</div>
            <button onClick={() => { onRenameWorkspace?.(); close(); }} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] font-semibold text-foreground hover:bg-accent/50 cursor-pointer">
              <Settings2 size={12} /> Rename workspace
            </button>
            <button onClick={() => { onDuplicateWorkspace?.(); close(); }} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] font-semibold text-foreground hover:bg-accent/50 cursor-pointer">
              <Copy size={12} /> Duplicate workspace
            </button>
            <button onClick={() => { onSave(); close(); }} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] font-semibold text-foreground hover:bg-accent/50 cursor-pointer">
              <Save size={12} /> Save now
            </button>
            <div className="my-1 border-t border-border/10" />
            <button onClick={() => { if (confirm('Reset to the default workspace layout?')) onReset(); close(); }} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] font-semibold text-rose-400 hover:bg-rose-500/10 cursor-pointer">
              <RotateCcw size={12} /> Reset workspace
            </button>
          </>
        )}
      </ToolbarMenu>

      <button
        onClick={onToggleFullPage}
        className={cn(
          'glass-button inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold transition-all cursor-pointer',
          fullPage ? 'text-primary' : 'text-muted-foreground hover:text-primary',
        )}
        title="Full page mode (Ctrl/Cmd+Enter)"
      >
        {fullPage ? <Minimize2 size={13} /> : <Maximize2 size={13} />} {fullPage ? 'Exit Full Page' : 'Full Page'}
      </button>
    </div>
  );
}

export { Trash2 };
