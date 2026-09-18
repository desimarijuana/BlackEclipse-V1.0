// ── WidgetDefinition — the plug-and-play widget contract ─────────────────────
// Every customizable-workspace widget implements this interface. The workspace
// engine only knows about WidgetDefinition; it never hard-codes a widget.
// Adding a new widget = registering a definition — no engine rewrite.
//
// This is the SHARED contract used by the Command Center dashboard, the
// portfolio fund workspaces, and any future customizable page.

import type { WidgetPlacement } from './types';

/** Widget categories shown in the Widget Library. */
export type WidgetCategory =
  | 'markets'
  | 'portfolio'
  | 'trading'
  | 'macro'
  | 'news'
  | 'intelligence'
  | 'ai'
  | 'research'
  | 'tools'
  | 'geopolitics'
  | 'alerts'
  | 'journal';

export const WIDGET_CATEGORY_LABEL: Record<WidgetCategory, string> = {
  markets: 'Markets',
  portfolio: 'Portfolio',
  trading: 'Trading',
  macro: 'Macro',
  news: 'News',
  intelligence: 'Intelligence',
  ai: 'AI',
  research: 'Research',
  tools: 'Tools',
  geopolitics: 'Geopolitics',
  alerts: 'Alerts',
  journal: 'Journal',
};

/** A single configurable field rendered by the config panel. */
export interface WidgetConfigField {
  key: string;
  label: string;
  type: 'text' | 'number' | 'select' | 'boolean' | 'symbol' | 'symbols';
  options?: { value: string; label: string }[];
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
  default?: unknown;
}

/** Refresh cadence options. */
export type RefreshPolicy = 'realtime' | '30s' | '1m' | '5m' | 'manual';

export interface WidgetDefinition {
  /** Stable registry id (persisted in layouts). */
  id: string;
  category: WidgetCategory;
  label: string;
  desc: string;
  /** lucide icon name (resolved by the library). */
  icon: string;
  /** Suggested sizes. */
  sizes: Array<'small' | 'medium' | 'large' | 'full'>;
  /**
   * Intrinsic box sizing for the track board. `defaultHeight` is the preferred
   * definite height for boxes whose content fills the card and cannot size
   * itself (charts, maps, live video, scrollable lists) — the body stretches to
   * it. `minHeight` is a floor under content that GROWS (stat tiles). Both are
   * optional — a widget with neither sizes purely to content.
   */
  minHeight?: number;
  defaultHeight?: number;
  /** Default per-instance config. */
  defaultConfig?: Record<string, unknown>;
  /** Config fields exposed in the config panel. */
  configFields?: WidgetConfigField[];
  /** Data dependencies (keys into a data service). */
  dataDeps?: string[];
  refreshPolicy?: RefreshPolicy;
  /** Heavy widgets (WebGL etc.) load only when placed. */
  lazy?: boolean;
  /**
   * Render the widget content. Optional — the workspace host supplies a
   * `renderWidget` prop that is the source of truth (it can thread page data
   * into the widget). When omitted, the host's renderWidget is used.
   */
  render?: (placement: WidgetPlacement) => React.ReactNode;
}

export type { WidgetPlacement };
