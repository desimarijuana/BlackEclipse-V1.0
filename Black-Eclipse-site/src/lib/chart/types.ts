// ── Eclipse Chart — core types ────────────────────────────────────────────────
// Framework-agnostic contracts shared by every chart provider. The ChartWidget
// only talks to these types; it never depends on a specific renderer or data
// source. This is the seam that lets users switch between Eclipse and TradingView
// without the rest of BlackEclipse changing.

/** One normalized OHLCV bar. Mirrors the shape served by /api/price-history. */
export interface PriceBar {
  date: string;
  /** Epoch ms of the bar's open — present for intraday bars (Yahoo timestamps). */
  time?: number;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
}

/** Supported timeframes. Architecture allows more to be added later. */
export type Timeframe =
  | '1m' | '3m' | '5m' | '15m' | '30m'
  | '1H' | '2H' | '4H'
  | '1D' | '1W' | '1M';

/** Chart rendering styles. Phase 1 implements candlestick/ohlc/line/area. */
export type ChartType =
  | 'candlestick'
  | 'ohlc'
  | 'line'
  | 'area'
  | 'baseline'
  | 'heikin-ashi'
  | 'histogram';

/** A chart provider — Eclipse (native) or TradingView (embed). */
export type ChartProviderId = 'eclipse' | 'tradingview';

/** Serializable chart state — the single source of truth for a chart instance. */
export interface ChartState {
  symbol: string;
  market: string;
  timeframe: Timeframe;
  chartType: ChartType;
  provider: ChartProviderId;
  /** Indicator configs (Phase 2). */
  indicators: ChartIndicatorConfig[];
  /** Drawing objects (Phase 3). */
  drawings: ChartDrawing[];
  /** Pane layout (Phase 2). */
  panes: ChartPane[];
  /** Market-structure layers (Phase 5). */
  structure: Record<string, boolean>;
  /** Free-form provider/engine settings. */
  settings: Record<string, unknown>;
}

/** Indicator configuration — registry-driven (Phase 2). */
export interface ChartIndicatorConfig {
  id: string;
  settings: Record<string, number | string | boolean>;
}

/** A chart pane (main / volume / RSI / MACD …) — Phase 2. */
export interface ChartPane {
  id: string;
  type: 'main' | 'volume' | 'indicator';
  indicatorId?: string;
  height: number;
  collapsed: boolean;
}

// ── Indicator engine (Phase 2) ────────────────────────────────────────────────

/** Where an indicator's output is drawn. */
export type IndicatorPaneType = 'overlay' | 'separate';

/** A single computed indicator series (line, bar, or band). */
export interface IndicatorSeries {
  /** Stable id within the indicator (e.g. 'ema', 'macd', 'signal'). */
  id: string;
  label: string;
  /** Series kind — determines how it's rendered. */
  kind: 'line' | 'bar' | 'band';
  /** Values aligned to the candle index (null = no value). */
  data: (number | null)[];
  /** Optional band partner id (for Bollinger upper/lower). */
  bandId?: string;
  /** Optional color override. */
  color?: string;
}

/** The result of running an indicator over candles. */
export interface IndicatorResult {
  /** Series to render. */
  series: IndicatorSeries[];
  /** Which pane this indicator lives in. */
  pane: IndicatorPaneType;
  /** Suggested pane height (fraction of chart height) for separate panes. */
  paneHeight?: number;
  /** Y-axis min/max hints for separate panes (e.g. RSI 0–100). */
  yMin?: number;
  yMax?: number;
  /** Optional mark overlays (markLine/markArea/markPoint) for structure layers. */
  marks?: {
    markLine?: unknown[];
    markArea?: unknown[];
    markPoint?: unknown[];
  };
}

/** A configurable input for an indicator. */
export interface IndicatorInput {
  key: string;
  label: string;
  type: 'number' | 'select' | 'boolean';
  default: number | string | boolean;
  min?: number;
  max?: number;
  step?: number;
  options?: Array<{ value: string; label: string }>;
}

/** A registered indicator definition. */
export interface IndicatorDefinition {
  id: string;
  name: string;
  description: string;
  category: 'trend' | 'momentum' | 'volatility' | 'volume' | 'black-eclipse';
  inputs: IndicatorInput[];
  /** Compute the indicator over candles. */
  calculate(candles: PriceBar[], settings: Record<string, number | string | boolean>): IndicatorResult;
}

// ── Drawing engine (Phase 3) ──────────────────────────────────────────────────

/** Supported drawing tool types. */
export type DrawingType =
  | 'trendline'
  | 'ray'
  | 'horizontal'
  | 'vertical'
  | 'rectangle'
  | 'fibonacci'
  | 'text'
  | 'arrow'
  | 'measure'
  | 'long-position'
  | 'short-position';

/** A market-coordinate point — the ONLY source of truth for drawing anchors. */
export interface ChartPoint {
  /** Unix timestamp (ms) of the anchor. Never a candle index. */
  time: number;
  /** Price of the anchor. */
  price: number;
}

/** Drawing style. */
export interface DrawingStyle {
  color: string;
  width: number;
  lineStyle?: 'solid' | 'dashed' | 'dotted';
  opacity?: number;
}

/** Base drawing — provider-independent, market-anchored. */
export interface BaseDrawing {
  id: string;
  type: DrawingType;
  visible: boolean;
  locked: boolean;
  selected?: boolean;
  style: DrawingStyle;
  createdAt: number;
  updatedAt: number;
}

/** Trendline / ray / arrow — two market anchors. */
export interface LineDrawing extends BaseDrawing {
  type: 'trendline' | 'ray' | 'arrow';
  start: ChartPoint;
  end: ChartPoint;
  extendLeft?: boolean;
  extendRight?: boolean;
}

/** Horizontal price line. */
export interface HorizontalDrawing extends BaseDrawing {
  type: 'horizontal';
  price: number;
}

/** Vertical time line. */
export interface VerticalDrawing extends BaseDrawing {
  type: 'vertical';
  time: number;
}

/** Rectangle — two market anchors. */
export interface RectangleDrawing extends BaseDrawing {
  type: 'rectangle';
  start: ChartPoint;
  end: ChartPoint;
  fill?: string;
  fillOpacity?: number;
}

/** Fibonacci retracement. */
export interface FibonacciDrawing extends BaseDrawing {
  type: 'fibonacci';
  start: ChartPoint;
  end: ChartPoint;
  levels: number[];
}

/** Text label. */
export interface TextDrawing extends BaseDrawing {
  type: 'text';
  point: ChartPoint;
  text: string;
}

/** Measure tool — distance between two points. */
export interface MeasureDrawing extends BaseDrawing {
  type: 'measure';
  start: ChartPoint;
  end: ChartPoint;
}

/** Long/short position — entry, stop, take-profit. */
export interface PositionDrawing extends BaseDrawing {
  type: 'long-position' | 'short-position';
  entry: ChartPoint;
  stop: ChartPoint;
  takeProfit: ChartPoint;
}

/** Union of all drawing types. */
export type ChartDrawing =
  | LineDrawing
  | HorizontalDrawing
  | VerticalDrawing
  | RectangleDrawing
  | FibonacciDrawing
  | TextDrawing
  | MeasureDrawing
  | PositionDrawing;

/** A registered drawing tool definition. */
export interface DrawingDefinition {
  type: DrawingType;
  name: string;
  description: string;
  icon: string;
  /** Number of anchor points required to complete the drawing. */
  points: number;
  /** Whether the drawing needs a text label. */
  needsText?: boolean;
}

/** Drawing tool mode — cursor (select/move) vs a specific drawing tool. */
export type DrawingToolMode = 'cursor' | DrawingType;

// ── Market structure (Phase 5) ───────────────────────────────────────────────
// BlackEclipse-native analysis objects — NOT generic indicators. Each is a
// first-class, queryable object (type/start/end/high/low/strength/status) that
// the AI context (Phase 6) can read and agents can manipulate.

/** A swing high/low point. */
export interface SwingPoint {
  index: number;
  price: number;
  type: 'high' | 'low';
  strength: number;
}

/** Break of Structure — price breaks a prior swing. */
export interface BOS {
  index: number;
  price: number;
  direction: 'bullish' | 'bearish';
  /** Index of the swing that was broken. */
  brokenSwingIndex: number;
}

/** Change of Character — trend reversal signal. */
export interface CHOCH {
  index: number;
  price: number;
  direction: 'bullish' | 'bearish';
  /** Index of the swing that was broken. */
  brokenSwingIndex: number;
}

/** An order block — the last opposing candle before a strong move. */
export interface OrderBlock {
  index: number;
  startIndex: number;
  endIndex: number;
  high: number;
  low: number;
  direction: 'bullish' | 'bearish';
  strength: number;
  /** 'fresh' | 'mitigated' | 'invalid' */
  status: 'fresh' | 'mitigated' | 'invalid';
}

/** A Fair Value Gap — price imbalance between two candles. */
export interface FVG {
  index: number;
  startIndex: number;
  endIndex: number;
  top: number;
  bottom: number;
  direction: 'bullish' | 'bearish';
  /** 'open' | 'filled' */
  status: 'open' | 'filled';
}

/** A liquidity level — equal highs/lows or sweep. */
export interface LiquidityLevel {
  index: number;
  price: number;
  type: 'equal-high' | 'equal-low' | 'sweep-high' | 'sweep-low';
  strength: number;
}

/** Session high/low levels. */
export interface SessionLevel {
  index: number;
  high: number;
  low: number;
  open: number;
  close: number;
  /** 'asia' | 'london' | 'newyork' | 'day' */
  session: string;
}

/** Opening range (first N candles of a session). */
export interface OpeningRange {
  index: number;
  high: number;
  low: number;
  /** Candle index where the range was established. */
  rangeIndex: number;
}

/** The full market-structure analysis result for a symbol. */
export interface MarketStructureResult {
  symbol: string;
  timeframe: Timeframe;
  swings: SwingPoint[];
  bos: BOS[];
  choch: CHOCH[];
  orderBlocks: OrderBlock[];
  fvgs: FVG[];
  liquidity: LiquidityLevel[];
  sessions: SessionLevel[];
  openingRanges: OpeningRange[];
  /** Overall trend from the latest structure. */
  trend: 'bullish' | 'bearish' | 'ranging';
}

/** Data payload handed to a provider. */
export interface ChartData {
  symbol: string;
  market: string;
  currency: string;
  bars: PriceBar[];
  source: string;
}

/**
 * The provider contract. The ChartWidget drives a provider through these
 * methods and never touches the underlying renderer directly. Methods that
 * belong to later phases (indicators/drawings) are part of the contract now so
 * the abstraction is stable, but may be no-ops until implemented.
 */
export interface ChartProvider {
  readonly id: ChartProviderId;
  readonly label: string;

  /** Mount into a container element. */
  initialize(container: HTMLElement): void;
  /** Tear down and release resources. */
  destroy(): void;

  /** Change the symbol (keeps timeframe/chartType/state). */
  setSymbol(symbol: string, market: string): void;
  /** Change the timeframe without destroying chart state. */
  setTimeframe(timeframe: Timeframe): void;
  /** Feed normalized bars into the chart. */
  setData(data: ChartData): void;

  /** Add/remove an indicator (Phase 2). */
  addIndicator(config: ChartIndicatorConfig): void;
  removeIndicator(id: string): void;

  /** Add/remove a drawing (Phase 3). */
  addDrawing(drawing: ChartDrawing): void;
  removeDrawing(id: string): void;

  /** Switch the chart rendering style. */
  setChartType(type: ChartType): void;

  /** Update the live last price (Phase 4 — realtime). Optional. */
  setLivePrice?(price: number | null): void;

  /** Reflow to the container's current size. */
  resize(): void;

  /** Serialize the current view/state. */
  getState(): ChartState;
  /** Restore a previously serialized state. */
  restoreState(state: ChartState): void;
}

/** Default chart state factory. */
export function defaultChartState(overrides: Partial<ChartState> = {}): ChartState {
  return {
    symbol: 'AAPL',
    market: 'US',
    timeframe: '1D',
    chartType: 'candlestick',
    provider: 'eclipse',
    indicators: [],
    drawings: [],
    panes: [],
    structure: {},
    settings: {},
    ...overrides,
  };
}

/** Map a timeframe to the Yahoo chart interval + a sensible default range. */
export function timeframeToYahoo(timeframe: Timeframe): { interval: string; range: string } {
  switch (timeframe) {
    case '1m': return { interval: '1m', range: '1d' };
    case '3m': return { interval: '1m', range: '1d' };
    case '5m': return { interval: '5m', range: '5d' };
    case '15m': return { interval: '15m', range: '1mo' };
    case '30m': return { interval: '30m', range: '1mo' };
    case '1H': return { interval: '60m', range: '3mo' };
    case '2H': return { interval: '60m', range: '6mo' };
    case '4H': return { interval: '60m', range: '6mo' };
    case '1D': return { interval: '1d', range: '6mo' };
    case '1W': return { interval: '1wk', range: '1y' };
    case '1M': return { interval: '1mo', range: '5y' };
  }
}

/** All supported timeframes, in display order. */
export const TIMEFRAMES: Timeframe[] = [
  '1m', '3m', '5m', '15m', '30m', '1H', '2H', '4H', '1D', '1W', '1M',
];

/** Chart types implemented in Phase 1. */
export const CHART_TYPES: ChartType[] = [
  'candlestick', 'ohlc', 'line', 'area',
];
