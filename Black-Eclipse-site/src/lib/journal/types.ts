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
  /** Null while the position is open. */
  exit: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  quantity: number;
  entryTime: string; // ISO
  /** ISO. For open positions this falls back to entryTime so sorting/display
   * always has a timestamp; gate on `status === 'open'` for true openness. */
  exitTime: string;
  timeframe?: string | null;
  session?: string | null;
  marketRegime?: string | null;
  trend?: string | null;
  confluences?: number | null;
  emotion?: string | null;
  confidence?: number | null;
  mistakes?: string | null; // JSON string[]
  notes?: string | null;
  /** Optional letter grade (A–F) the trader assigned to their execution. */
  grade?: string | null;
  /** JSON: { [ruleId]: boolean } — pre-trade checklist state. */
  checklist?: string | null;
  status: TradeStatus;
  /** 'manual' (user/CSV) or 'demo' (seeded sample). Never fabricated prices. */
  source?: TradeSource;
  strategyId?: string | null;
  strategyName?: string | null;
  setupId?: string | null;
  setupName?: string | null;
  accountId?: string | null;
  accountName?: string | null;
  tags?: string[]; // tag names
  // Auto-computed metrics.
  grossPnl: number;
  commission: number;
  fee: number;
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

/** Equity in account currency (derived from R × risk-per-trade). */
export interface CurrencyEquityPoint {
  date: string;
  equity: number; // running balance in account currency
  drawdown: number; // drawdown from peak in currency
}

/** One calendar month's performance. */
export interface MonthlyReturn {
  month: string; // YYYY-MM
  trades: number;
  netR: number;
  netPnl: number;
  winRate: number;
}

/** A point on the rolling-performance curve (trailing window). */
export interface RollingPoint {
  date: string;
  winRate: number; // 0-1 over the trailing window
  expectancyR: number;
  netR: number;
}

/** MAE/MFE efficiency point — how much of the favourable move was captured. */
export interface MfeMaePoint {
  mfe: number; // max favourable excursion (R)
  mae: number; // max adverse excursion (R)
  rMultiple: number; // realized R
  label: string;
}

/** Confidence vs outcome scatter point. */
export interface ConfidencePoint {
  confidence: number; // 1-5
  rMultiple: number;
  pnl: number;
}

/** Summary of a trading account's P&L for the account-switcher / equity panel. */
export interface AccountSummary {
  id: string;
  name: string;
  broker?: string | null;
  currency: string;
  initialBalance: number;
  trades: number;
  netPnl: number;
  netR: number;
  /** Running balance = initialBalance + netPnl. */
  equity: number;
}

/** A watchlist item / pre-trade idea / pending order. */
export interface WatchlistItem {
  id: string;
  symbol: string;
  direction: Direction;
  idea: string | null;
  trigger: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  status: "watching" | "triggered" | "entered" | "expired";
  note: string | null;
  createdAt: string;
  updatedAt: string;
}

/** A deterministic risk/behaviour alert (no LLM). */
export interface RiskAlert {
  level: "info" | "warn" | "danger";
  title: string;
  detail: string;
}

/** One calendar year's realized report. */
export interface YearReport {
  year: string;
  trades: number;
  wins: number;
  losses: number;
  netPnl: number;
  netR: number;
  fees: number;
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
  /** Depth analytics (Phase 4). */
  monthlyReturns: MonthlyReturn[];
  rolling: RollingPoint[];
  mfeMae: MfeMaePoint[];
  confidenceScatter: ConfidencePoint[];
  durationBuckets: DimensionRow[];
  /** Equity in account currency, if a risk-per-trade/account size is known. */
  equityCurrency: CurrencyEquityPoint[];
  /** System comparison: performance by strategy. */
  byStrategy: DimensionRow[];
  /** Per-account summaries (empty when no accounts are configured). */
  accounts: AccountSummary[];
  /** Deterministic risk / behaviour alerts. */
  riskAlerts: RiskAlert[];
  /** Realized P&L reports by calendar year (tax/reporting). */
  yearReports: YearReport[];
}
