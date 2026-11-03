// ── Broker → journal projection (pure) ───────────────────────────────────────
// Turns the broker's reconciled deals and open positions into journal-shaped
// trades. No database, no fetch, no clock: everything comes from the input so
// the same deals always produce the same trades (and a second sync is a no-op).
//
// The broker is authoritative for execution facts. This module never invents a
// price or a fill; a deal it cannot understand is skipped and reported, not
// guessed at.

export type BrokerDealEntry = "in" | "out" | "inout" | "out_by" | "unknown";

/** One reconciled broker deal (matches BrokerFill in the Python harness). */
export interface BrokerDeal {
  dealTicket: number;
  orderTicket?: number | null;
  positionTicket?: number | null;
  symbol: string;
  /** "buy" | "sell" (case-insensitive). */
  side: string;
  /** "in" | "out" | "inout" | "out_by" (case-insensitive), or null. */
  entry: string | null;
  volume: number;
  price: number;
  commission: number;
  swap: number;
  profit: number;
  magic: number;
  comment: string | null;
  /** Epoch milliseconds. */
  dealtAt: number;
  /**
   * "broker" = the deal carries the broker's own P&L (MT5/MT4).
   * "computed" = the adapter derived it from executions (Alpaca/IBKR FIFO).
   */
  pnlBasis?: "broker" | "computed" | null;
}

/** One open broker position (matches BrokerPositionSnapshot). */
export interface BrokerOpenPosition {
  ticket: number;
  symbol: string;
  side: string;
  volume: number;
  openPrice: number;
  currentPrice: number;
  stopLoss: number | null;
  takeProfit: number | null;
  profit: number;
  swap: number;
  magic: number;
  comment: string | null;
  /** Epoch milliseconds. */
  openedAt: number;
}

/** A user-defined attribution rule (magic / comment / symbol → journal data). */
export interface AttributionRule {
  id?: string;
  /** Null/undefined applies to every connection; otherwise exact match. */
  connectionId?: string | null;
  magic?: number | null;
  commentMatch?: string | null;
  symbolMatch?: string | null;
  strategyId?: string | null;
  setupId?: string | null;
  tagNames?: string[] | null;
  priority?: number | null;
}

/** One broker deal as the journal will store it (immutable). */
export interface ProjectedFill {
  dealTicket: number;
  orderTicket: number | null;
  positionTicket: number | null;
  side: string;
  entry: BrokerDealEntry;
  volume: number;
  price: number;
  commission: number;
  swap: number;
  profit: number;
  magic: number;
  comment: string | null;
  dealtAt: string; // ISO
}

/** A journal trade derived from broker deals. */
export interface ProjectedTrade {
  /** Stable: `broker:<connectionId>:<positionTicket>`. */
  externalId: string;
  brokerConnectionId: string;
  brokerPositionTicket: number;
  symbol: string;
  direction: "LONG" | "SHORT";
  entry: number;
  exit: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  quantity: number;
  entryTime: string; // ISO
  exitTime: string | null; // ISO
  status: "open" | "closed";
  /** Broker-reported net = profit + commission + swap. */
  netPnl: number;
  /** Broker-reported gross profit before costs. */
  grossPnl: number;
  /** Positive cost = −Σ commission (a rebate becomes negative). */
  commission: number;
  /** Positive cost = −Σ swap/financing (a credit becomes negative). */
  fee: number;
  magic: number;
  comment: string | null;
  /** "broker" or "computed" (adapter FIFO), matching the deal provenance. */
  pnlBasis: "broker" | "computed";
  /**
   * Account currency per 1.0 price unit × 1.0 volume for this symbol, calibrated
   * from the broker's own gross P&L (e.g. 100 for XAUUSD, 100000 for EURUSD).
   * Null when the symbol has no closed trade to calibrate from — R is then
   * unavailable rather than inflated by using raw price × volume.
   */
  contractMultiplier: number | null;
  /** Smallest observed price increment for the symbol, when it can be inferred. */
  tickSize: number | null;
  /** How many deals the round-trip was built from. */
  fillCount: number;
  /** The underlying deals, chronological. Empty for a snapshot-only position. */
  fills: ProjectedFill[];
  strategyId?: string | null;
  setupId?: string | null;
  tagNames?: string[];
}

export interface ProjectOptions {
  connectionId: string;
  symbolMap?: Record<string, string>;
  rules?: AttributionRule[];
  /** Treat a remaining volume at or below this as closed. */
  volumeEpsilon?: number;
}

export interface ProjectionResult {
  trades: ProjectedTrade[];
  /** Human-readable problems; a sync surfaces these, never hides them. */
  warnings: string[];
  skippedDeals: number;
}

interface Accumulator {
  positionTicket: number;
  symbol: string;
  magic: number;
  comment: string | null;
  direction: "LONG" | "SHORT" | null;
  inVolume: number;
  inNotional: number;
  outVolume: number;
  outNotional: number;
  firstDealtAt: number;
  firstInAt: number | null;
  lastOutAt: number | null;
  commission: number;
  swap: number;
  profit: number;
  fillCount: number;
  fills: ProjectedFill[];
  pnlBasis: "broker" | "computed";
}

const EPSILON_DEFAULT = 1e-8;

export function normalizeEntry(raw: string | null | undefined): BrokerDealEntry {
  const v = String(raw ?? "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (v === "in") return "in";
  if (v === "out") return "out";
  if (v === "inout" || v === "in_out") return "inout";
  if (v === "out_by" || v === "outby") return "out_by";
  return "unknown";
}

function sideDirection(side: string): "LONG" | "SHORT" | null {
  const v = String(side ?? "").trim().toLowerCase();
  if (v === "buy" || v === "long") return "LONG";
  if (v === "sell" || v === "short") return "SHORT";
  return null;
}

function finite(value: number, fallback = 0): number {
  return Number.isFinite(value) ? value : fallback;
}

function iso(ms: number | null): string | null {
  if (ms == null || !Number.isFinite(ms)) return null;
  const d = new Date(ms);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

/** Exact map hit first, then a case-insensitive hit, then the symbol unchanged. */
export function mapSymbol(symbol: string, map?: Record<string, string>): string {
  if (!map) return symbol;
  const raw = String(symbol ?? "").trim();
  if (map[raw]) return map[raw];
  const upper = raw.toUpperCase();
  for (const [key, value] of Object.entries(map)) {
    if (key.trim().toUpperCase() === upper) return value;
  }
  return raw;
}

function globToRegExp(pattern: string): RegExp {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".");
  return new RegExp(`^${escaped}$`, "i");
}

/** First matching rule wins (highest priority, then input order). */
export function matchAttribution(
  input: { magic: number; comment: string | null; symbol: string },
  rules: AttributionRule[] = [],
): AttributionRule | null {
  const ordered = rules
    .map((rule, index) => ({ rule, index }))
    .sort((a, b) => (b.rule.priority ?? 0) - (a.rule.priority ?? 0) || a.index - b.index);

  for (const { rule } of ordered) {
    if (rule.magic != null && Number(rule.magic) !== input.magic) continue;
    if (rule.commentMatch) {
      const needle = rule.commentMatch.trim().toLowerCase();
      if (!needle) continue;
      if (!String(input.comment ?? "").toLowerCase().includes(needle)) continue;
    }
    if (rule.symbolMatch) {
      const pattern = rule.symbolMatch.trim();
      if (!pattern) continue;
      if (!globToRegExp(pattern).test(input.symbol)) continue;
    }
    return rule;
  }
  return null;
}

function accumulate(target: Map<number, Accumulator>, deal: BrokerDeal, warnings: string[]): void {
  const ticket = Number(deal.positionTicket ?? 0);
  if (!ticket || ticket < 0) {
    warnings.push(`deal ${deal.dealTicket}: no position ticket, skipped`);
    return;
  }
  const price = finite(deal.price, NaN);
  const volume = finite(deal.volume, NaN);
  const dealtAt = finite(deal.dealtAt, NaN);
  if (!Number.isFinite(price) || price <= 0 || !Number.isFinite(volume) || volume <= 0 || !Number.isFinite(dealtAt)) {
    warnings.push(`deal ${deal.dealTicket}: invalid price/volume/time, skipped`);
    return;
  }

  const entry = normalizeEntry(deal.entry);
  const side = sideDirection(deal.side);
  let acc = target.get(ticket);
  if (!acc) {
    acc = {
      positionTicket: ticket,
      symbol: String(deal.symbol ?? "").trim(),
      magic: finite(deal.magic, 0),
      comment: deal.comment ?? null,
      direction: null,
      inVolume: 0,
      inNotional: 0,
      outVolume: 0,
      outNotional: 0,
      firstDealtAt: dealtAt,
      firstInAt: null,
      lastOutAt: null,
      commission: 0,
      swap: 0,
      profit: 0,
      fillCount: 0,
      fills: [],
      pnlBasis: "broker",
    };
    target.set(ticket, acc);
  }

  if (!acc.symbol && deal.symbol) acc.symbol = String(deal.symbol).trim();
  if (deal.comment) acc.comment = deal.comment;
  if (deal.magic) acc.magic = finite(deal.magic, acc.magic);

  acc.fillCount += 1;
  acc.firstDealtAt = Math.min(acc.firstDealtAt, dealtAt);
  acc.commission += finite(deal.commission, 0);
  acc.swap += finite(deal.swap, 0);
  acc.profit += finite(deal.profit, 0);
  if (deal.pnlBasis === "computed") acc.pnlBasis = "computed";
  acc.fills.push({
    dealTicket: Number(deal.dealTicket),
    orderTicket: deal.orderTicket == null ? null : Number(deal.orderTicket),
    positionTicket: Number(deal.positionTicket ?? ticket),
    side: String(deal.side ?? "").toLowerCase(),
    entry,
    volume,
    price,
    commission: finite(deal.commission, 0),
    swap: finite(deal.swap, 0),
    profit: finite(deal.profit, 0),
    magic: finite(deal.magic, 0),
    comment: deal.comment ?? null,
    dealtAt: new Date(dealtAt).toISOString(),
  });

  const isIn = entry === "in" || entry === "inout";
  const isOut = entry === "out" || entry === "out_by" || entry === "inout";

  if (entry === "unknown") {
    // Without an entry tag the deal is still a fact; treat it as a closing
    // deal only when the side is opposite an already-known direction.
    if (acc.direction === "LONG" && side === "SHORT") {
      acc.outVolume += volume;
      acc.outNotional += price * volume;
      acc.lastOutAt = Math.max(acc.lastOutAt ?? dealtAt, dealtAt);
      return;
    }
    if (acc.direction === "SHORT" && side === "LONG") {
      acc.outVolume += volume;
      acc.outNotional += price * volume;
      acc.lastOutAt = Math.max(acc.lastOutAt ?? dealtAt, dealtAt);
      return;
    }
    if (side) acc.direction = side;
    acc.inVolume += volume;
    acc.inNotional += price * volume;
    acc.firstInAt = Math.min(acc.firstInAt ?? dealtAt, dealtAt);
    return;
  }

  if (isIn) {
    if (side) acc.direction = side;
    acc.inVolume += volume;
    acc.inNotional += price * volume;
    acc.firstInAt = Math.min(acc.firstInAt ?? dealtAt, dealtAt);
  }
  if (isOut) {
    // A closing deal implies the original direction: a buy closes a short.
    if (!acc.direction && side) acc.direction = side === "LONG" ? "SHORT" : "LONG";
    acc.outVolume += volume;
    acc.outNotional += price * volume;
    acc.lastOutAt = Math.max(acc.lastOutAt ?? dealtAt, dealtAt);
  }
}

function weightedPrice(notional: number, volume: number): number | null {
  if (!volume || !Number.isFinite(volume)) return null;
  const price = notional / volume;
  return Number.isFinite(price) && price > 0 ? price : null;
}

/**
 * Project reconciled deals + open positions into journal trades.
 *
 * Grouping is by `positionTicket`, which is MT5's round-trip identity: one
 * journal trade = one broker position, with scale-ins, partial closes and
 * multiple fills collapsed into weighted-average entry/exit and summed costs.
 */
export function projectBrokerTrades(
  deals: BrokerDeal[],
  positions: BrokerOpenPosition[] = [],
  options: ProjectOptions,
): ProjectionResult {
  const warnings: string[] = [];
  const eps = options.volumeEpsilon ?? EPSILON_DEFAULT;
  const groups = new Map<number, Accumulator>();

  let skippedDeals = 0;
  for (const deal of deals) {
    const beforeWarnings = warnings.length;
    accumulate(groups, deal, warnings);
    if (warnings.length > beforeWarnings) skippedDeals += 1;
  }

  const openByTicket = new Map<number, BrokerOpenPosition>();
  for (const position of positions) {
    const ticket = Number(position.ticket ?? 0);
    if (ticket > 0) openByTicket.set(ticket, position);
  }

  // A position can be open with no deal in the current history window: still
  // project it, using the snapshot as the entry fact.
  for (const [ticket, position] of openByTicket) {
    if (groups.has(ticket)) continue;
    const openedAt = finite(position.openedAt, NaN);
    if (!Number.isFinite(openedAt)) {
      warnings.push(`position ${ticket}: missing open time, skipped`);
      continue;
    }
    groups.set(ticket, {
      positionTicket: ticket,
      symbol: String(position.symbol ?? "").trim(),
      magic: finite(position.magic, 0),
      comment: position.comment ?? null,
      direction: sideDirection(position.side),
      inVolume: finite(position.volume, 0),
      inNotional: finite(position.openPrice, 0) * finite(position.volume, 0),
      outVolume: 0,
      outNotional: 0,
      firstDealtAt: openedAt,
      firstInAt: openedAt,
      lastOutAt: null,
      commission: 0,
      swap: 0,
      profit: 0,
      fillCount: 0,
      fills: [],
      pnlBasis: "broker",
    });
  }

  const trades: ProjectedTrade[] = [];
  for (const [ticket, acc] of groups) {
    const snapshot = openByTicket.get(ticket) ?? null;
    if (!acc.symbol) {
      warnings.push(`position ${ticket}: no symbol, skipped`);
      continue;
    }

    const direction =
      snapshot ? sideDirection(snapshot.side) ?? acc.direction : acc.direction;
    if (!direction) {
      warnings.push(`position ${ticket}: no direction, skipped`);
      continue;
    }

    const quantity = acc.inVolume > 0 ? acc.inVolume : snapshot ? finite(snapshot.volume, 0) : acc.outVolume;
    if (!(quantity > 0)) {
      warnings.push(`position ${ticket}: no volume, skipped`);
      continue;
    }

    const entry =
      weightedPrice(acc.inNotional, acc.inVolume) ??
      (snapshot ? finite(snapshot.openPrice, 0) : null) ??
      (acc.outVolume > 0 ? weightedPrice(acc.outNotional, acc.outVolume) : null);
    if (!entry || entry <= 0) {
      warnings.push(`position ${ticket}: no usable entry price, skipped`);
      continue;
    }

    const remaining = acc.inVolume - acc.outVolume;
    const isOpen = snapshot != null || remaining > eps;
    const exit = isOpen ? null : weightedPrice(acc.outNotional, acc.outVolume);

    const entryTime = iso(acc.firstInAt ?? acc.firstDealtAt);
    if (!entryTime) {
      warnings.push(`position ${ticket}: no entry time, skipped`);
      continue;
    }
    const exitTime = isOpen ? null : iso(acc.lastOutAt ?? acc.firstDealtAt);

    const symbol = mapSymbol(acc.symbol, options.symbolMap);
    const comment = snapshot?.comment ?? acc.comment;
    const magic = snapshot?.magic || acc.magic;
    const rule = matchAttribution({ magic, comment, symbol }, options.rules ?? []);

    trades.push({
      externalId: `broker:${options.connectionId}:${ticket}`,
      brokerConnectionId: options.connectionId,
      brokerPositionTicket: ticket,
      symbol,
      direction,
      entry,
      exit,
      stopLoss: snapshot?.stopLoss ?? null,
      takeProfit: snapshot?.takeProfit ?? null,
      quantity,
      entryTime,
      exitTime,
      status: isOpen ? "open" : "closed",
      // Broker P&L signs: commission is usually negative (a cost) and swap can
      // be either. Net is the broker's own arithmetic, never a price guess.
      grossPnl: acc.profit,
      commission: -acc.commission,
      fee: -acc.swap,
      netPnl: acc.profit + acc.commission + acc.swap,
      magic,
      comment,
      pnlBasis: acc.pnlBasis,
      contractMultiplier: null,
      tickSize: null,
      fillCount: acc.fillCount,
      fills: [...acc.fills].sort((a, b) => Date.parse(a.dealtAt) - Date.parse(b.dealtAt)),
      strategyId: rule?.strategyId ?? null,
      setupId: rule?.setupId ?? null,
      tagNames: rule?.tagNames ?? [],
    });
  }

  // Newest first is the useful order for a sync summary.
  trades.sort((a, b) => Date.parse(b.entryTime) - Date.parse(a.entryTime));

  // ── Contract multiplier (money per price point per volume) ────────────────
  // `entry/exit` are prices; `grossPnl` is account currency. For FX/CFD one
  // price point is worth 100 (XAUUSD) or 100 000 (EURUSD) per lot, so a risk
  // computed as `(entry − stop) × qty` is the wrong unit and inflates R. The
  // broker's own gross P&L calibrates the factor per symbol exactly:
  //   multiplier = Σ grossPnl / Σ (signed price move × quantity)
  // A symbol with no closed trade to calibrate from gets `null`: no R, never a
  // 100×-inflated one.
  const calibration = new Map<string, { profit: number; denom: number }>();
  for (const t of trades) {
    if (t.status !== "closed" || t.exit == null) continue;
    const sign = t.direction === "LONG" ? 1 : -1;
    const move = (t.exit - t.entry) * sign;
    if (Math.abs(move) < 1e-12 || !(t.quantity > 0) || Math.abs(t.grossPnl) < 1e-12) continue;
    const agg = calibration.get(t.symbol) ?? { profit: 0, denom: 0 };
    agg.profit += t.grossPnl;
    agg.denom += move * t.quantity;
    calibration.set(t.symbol, agg);
  }
  const multiplierBySymbol = new Map<string, number>();
  for (const [symbol, agg] of calibration) {
    if (Math.abs(agg.denom) < 1e-12) continue;
    const multiplier = agg.profit / agg.denom;
    if (Number.isFinite(multiplier) && multiplier > 0 && multiplier < 1e9) {
      multiplierBySymbol.set(symbol, multiplier);
    }
  }
  for (const t of trades) {
    t.contractMultiplier = multiplierBySymbol.get(t.symbol) ?? null;
  }

  // ── Tick size (smallest observed price increment per symbol) ──────────────
  // A stop one tick from entry is a trail moved to breakeven, not a risk basis;
  // dividing by it produced absurd 349R trade rows. The minimum observed price
  // difference across the symbol's fills is a conservative estimate.
  const pricesBySymbol = new Map<string, Set<number>>();
  for (const t of trades) {
    const set = pricesBySymbol.get(t.symbol) ?? new Set<number>();
    // Raw deal prices only — `entry`/`exit` are weighted averages and would
    // fabricate sub-tick increments (3930.165) that defeat the tick guard.
    for (const f of t.fills) if (f.price > 0) set.add(f.price);
    pricesBySymbol.set(t.symbol, set);
  }
  const tickBySymbol = new Map<string, number>();
  for (const [symbol, prices] of pricesBySymbol) {
    const sorted = [...prices].filter((p) => p > 0).sort((a, b) => a - b);
    let tick: number | null = null;
    for (let i = 1; i < sorted.length; i += 1) {
      const diff = sorted[i] - sorted[i - 1];
      if (diff > 1e-12 && (tick == null || diff < tick)) tick = diff;
    }
    if (tick != null && Number.isFinite(tick)) tickBySymbol.set(symbol, tick);
  }
  for (const t of trades) {
    t.tickSize = tickBySymbol.get(t.symbol) ?? null;
  }

  return { trades, warnings, skippedDeals };
}

/**
 * Monetary risk for a projected trade, in account currency.
 *
 * `null` means R is genuinely unmeasurable: no stop, no calibrated contract
 * multiplier, a stop on the wrong side, or a stop within one tick of entry
 * (a trail moved to breakeven — dividing by it produced ~349R rows).
 */
export function monetaryRisk(trade: ProjectedTrade): number | null {
  if (trade.stopLoss == null) return null;
  const sign = trade.direction === "LONG" ? 1 : -1;
  return monetaryDistance(trade, (trade.entry - trade.stopLoss) * sign);
}

/** Monetary reward for a projected trade, in account currency. */
export function monetaryReward(trade: ProjectedTrade): number | null {
  if (trade.takeProfit == null) return null;
  const sign = trade.direction === "LONG" ? 1 : -1;
  return monetaryDistance(trade, (trade.takeProfit - trade.entry) * sign);
}

function monetaryDistance(trade: ProjectedTrade, distance: number): number | null {
  const multiplier = trade.contractMultiplier;
  if (multiplier == null || !(multiplier > 0)) return null;
  if (!(distance > 0) || !(trade.quantity > 0)) return null;
  // A stop/target at (or inside) the smallest observed price increment is not a
  // real level — it is an artifact of a trailed/breakeven stop. 1.5 ticks
  // absorbs float noise in the inferred increment (0.00999… for 0.01).
  if (trade.tickSize != null && distance <= trade.tickSize * 1.5 + 1e-12) return null;
  const amount = distance * trade.quantity * multiplier;
  return Number.isFinite(amount) && amount > 0 ? amount : null;
}
