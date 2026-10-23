// Shared contract for stock-detail intelligence charts. Values are always
// derived from retrieved data and carry the exact sources used, so the UI never
// presents a chart as if it came from an unsourced or synthetic series.

export type StockChartId =
  | 'price-trend'
  | 'drawdown'
  | 'relative-performance'
  | 'valuation-band'
  | 'earnings-surprise';

export type StockChartUnit = 'percent' | 'ratio' | 'price';

export type StockChartState = 'READY' | 'UNAVAILABLE';

/**
 * Provenance states match the fundamentals vocabulary plus the extension states
 * reserved for web/AI-enriched facts.
 */
export type StockFactState =
  | 'LIVE'
  | 'CACHED'
  | 'HISTORICAL'
  | 'FILING'
  | 'WEB'
  | 'AI_EXTRACTED'
  | 'DERIVED'
  | 'UNAVAILABLE';

export type StockSourceTier =
  | 'jdds'
  | 'provider'
  | 'filing'
  | 'web'
  | 'derived'
  | 'none';

export interface StockSourceRef {
  id: string;
  label: string;
  tier: StockSourceTier;
  url?: string;
  asOf?: string | null;
  retrievedAt?: string | null;
}

export interface StockProvenance {
  state: StockFactState;
  sources: StockSourceRef[];
}

export interface StockChartSeries {
  name: string;
  values: Array<number | null>;
}

export interface StockChart {
  id: StockChartId;
  title: string;
  subtitle: string;
  unit: StockChartUnit;
  state: StockChartState;
  labels: string[];
  series: StockChartSeries[];
  provenance: StockProvenance;
  note?: string;
  /** Why the chart is unavailable. Only set when state = UNAVAILABLE. */
  reason?: string;
}

export interface StockIntelligenceResponse {
  available: boolean;
  symbol: string;
  market: string;
  currency: string | null;
  generatedAt: string;
  charts: StockChart[];
  warnings: string[];
  reason?: string;
}
