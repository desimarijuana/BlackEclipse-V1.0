// ── Global Search & Command Center — core types ───────────────────────────
// Deterministic, registry-driven search/navigation/action system for the
// Black Eclipse terminal. Everything here is framework-agnostic so the query
// engine stays pure and unit-testable (vitest).

/** The app tabs exposed by the SPA shell (mirrors sidebar.tsx AppTab). */
export type AppTab =
  | 'chat'
  | 'news'
  | 'discovery'
  | 'heatmap'
  | 'chart'
  | 'economics'
  | 'portfolio'
  | 'journal'
  | 'settings'
  | 'alerts'
  | 'dashboard'
  | 'market-workspace';

/**
 * A resolved navigation target. Black Eclipse is a tabbed SPA (no router), so
 * a "route" is a tab + optional subroute/params that the shell applies to its
 * activeTab state machine. `search` serializes to a deep link when present.
 */
export interface Destination {
  tab: AppTab;
  /** Sub-route within a tab (e.g. 'economics.calendar', 'journal.overview'). */
  subroute?: string;
  /** Arbitrary params (e.g. symbol to load into the chart). */
  params?: Record<string, string>;
  /** Set the document URL (deep link) when navigating. */
  deepLink?: string;
}

/**
 * Kinds of searchable things. Each maps to a result group/category chip and
 * an icon in the command bar.
 */
export type EntityKind =
  | 'security'
  | 'instrument'
  | 'indicator'
  | 'event'
  | 'page'
  | 'action'
  | 'report'
  | 'agent'
  | 'doc'
  | 'user';

/** Canonical asset class of a financial entity. */
export type AssetClass =
  | 'equity'
  | 'etf'
  | 'crypto'
  | 'forex'
  | 'commodity'
  | 'index'
  | 'indicator'
  | 'other';

/**
 * One searchable entity. A unified row regardless of kind — symbol, indicator,
 * page, action, report… all resolve to this shape so the index, resolver and
 * ranker treat them uniformly.
 */
export interface SearchEntity {
  id: string;
  kind: EntityKind;
  title: string;
  /** Display symbol / ticker (e.g. 'AAPL', 'NFP', 'XAUUSD'). */
  symbol?: string;
  /** Canonical asset class (securities/instruments only). */
  assetClass?: AssetClass;
  market?: string;
  /** Non-display search terms — lets 'US jobs data' hit NFP. */
  keywords: string[];
  icon?: string;
  /** Manual popularity pin (0..1), overrides data-derived popularity. */
  rankBoost?: number;
  /** Where selecting this entity navigates. */
  destination: Destination;
  /** Secondary subtitle shown in the result row. */
  subtitle?: string;
}

/** A named, executable command (command palette action). */
export interface SearchAction {
  id: string;
  verb: string;
  title: string;
  keywords: string[];
  icon?: string;
  /** Returns the destination to apply, or null if it should do nothing. */
  run: (ctx: ActionContext) => Destination | null;
  /** Static, always-available command (independent of a typed param). */
  static?: boolean;
}

export interface ActionContext {
  /** The full raw query (for param extraction). */
  query: string;
  /** Normalized lowercased query. */
  normalized: string;
  /** Extracted symbol, if any. */
  symbol?: string;
}

/** Classified search intent — decides which resolver path to run. */
export type Intent =
  | 'entity'
  | 'indicator'
  | 'event'
  | 'page'
  | 'action'
  | 'user'
  | 'data'
  | 'ai'
  | 'unknown';

export interface IntentResult {
  intent: Intent;
  /** Raw query trimmed. */
  query: string;
  /** Normalized (lowercased, trimmed) query. */
  normalized: string;
  /** Extracted symbol token, if the query looks like an entity lookup. */
  symbol?: string;
  /** True when intent is a navigation/entity/data query vs an action. */
  isNavigation: boolean;
}
