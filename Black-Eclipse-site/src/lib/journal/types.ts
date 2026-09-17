// ── Journal shared types ─────────────────────────────────────────────────────
// Dependency-free types shared by the analytics engine, API routes and the
// Journal UI. Kept separate from the Prisma client so pure functions and
// tests can import them without pulling in the DB.

export type Direction = "LONG" | "SHORT";
export type TradeStatus = "open" | "closed";
/** Provenance of a trade: user-entered vs seeded sample data. */
export type TradeSource = "manual" | "demo";

/** A normalized trade record the analytics engine consumes. */
export interface TradeRecord {
  id: string;
  symbol: string;
  direction: Direction;
  entry: number;
  exit: number;
  stopLoss: number | null;
  takeProfit: number | null;
  quantity: number;
  entryTime: string; // ISO
  exitTime: string; // ISO
  timeframe?: string | null;
  session?: string | null;
  marketRegime?: string | null;
  trend?: string | null;
  confluences?: number | null;
  emotion?: string | null;
  confidence?: number | null;
  mistakes?: string | null; // JSON string[]
  notes?: string | null;
  status: TradeStatus;
  /** 'manual' (user/CSV) or 'demo' (seeded sample). Never fabricated prices. */
  source?: TradeSource;
  strategyId?: string | null;
  strategyName?: string | null;
  setupId?: string | null;
  setupName?: string | null;
  tags?: string[]; // tag names
  // Auto-computed metrics.
  pnl: number;
  pnlPct: number;
  rMultiple: number;
  riskAmount: number | null;
  rewardAmount: number | null;
  actualRR: number | null;
  durationSec: number | null;
  mfe: number | null;
  mae: number | null;
}

/** A single day's aggregate for the calendar heatmap. */
export interface DayAggregate {
  date: string; // YYYY-MM-DD
  trades: number;
  wins: number;
  losses: number;
  breakevens: number;
  netPnl: number;
  netR: number;
  bestR: number;
  worstR: number;
  discipline: number | null;
}

/** A dimension breakdown (symbol, session, setup, ...). */
export interface DimensionRow {
  key: string;
  trades: number;
  wins: number;
  losses: number;
  winRate: number;
  netR: number;
  netPnl: number;
  expectancy: number;
  profitFactor: number;
}

export interface PerformanceStats {
  totalTrades: number;
  wins: number;
  losses: number;
  breakevens: number;
  winRate: number;
  averageWin: number;
  averageLoss: number;
  netPnl: number;
  netR: number;
  expectancy: number;
  profitFactor: number;
  averageR: number;
  maxDrawdown: number; // in R
  recoveryFactor: number;
  sharpe: number | null;
  sortino: number | null;
  winningStreak: number;
  losingStreak: number;
  currentStreak: number; // +n winning, -n losing
  averageRisk: number;
  riskConsistency: number;
  largestRisk: number;
  riskViolations: number;
  averageStopDistance: number;
  averageTargetDistance: number;
  averagePlannedRR: number;
  averageRealizedRR: number;
  averageDurationSec: number;
  averageMfe: number;
  averageMae: number;
  earlyExits: number;
  stopModifications: number;
  targetModifications: number;
  partialExits: number;
}

export interface DisciplineBreakdown {
  risk: number; // /25
  strategy: number; // /25
  stop: number; // /20
  overtrading: number; // /15
  execution: number; // /15
  total: number; // /100
}

export interface EquityPoint {
  date: string;
  equity: number; // cumulative R
  drawdown: number; // drawdown from peak in R
}

export interface JournalAnalytics {
  performance: PerformanceStats;
  equity: EquityPoint[];
  bySymbol: DimensionRow[];
  bySetup: DimensionRow[];
  bySession: DimensionRow[];
  byDirection: DimensionRow[];
  byDayOfWeek: DimensionRow[];
  byHour: DimensionRow[];
  byTimeframe: DimensionRow[];
  byRegime: DimensionRow[];
  byTrend: DimensionRow[];
  byEmotion: DimensionRow[];
  byConfidence: DimensionRow[];
  confidenceCorrelation: number | null;
  discipline: DisciplineBreakdown;
  days: DayAggregate[];
}
