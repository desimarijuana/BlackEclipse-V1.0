'use client';

// ── Market Structure Engine (Phase 5) ─────────────────────────────────────────
// BlackEclipse-native analysis: swing highs/lows, Break of Structure (BOS),
// Change of Character (CHOCH), order blocks, fair value gaps (FVG), liquidity
// levels, session high/low, and opening range. Pure, deterministic functions
// over the candle series — no external deps. These are first-class analysis
// objects (not generic indicators) that the AI context (Phase 6) can read.

import type {
  BOS, CHOCH, FVG, LiquidityLevel, MarketStructureResult, OpeningRange, OrderBlock,
  PriceBar, SessionLevel, SwingPoint, Timeframe,
} from '@/lib/chart/types';

/** Find swing highs/lows using a fractal window (left+right bars). */
export function findSwings(candles: PriceBar[], window = 2): SwingPoint[] {
  const swings: SwingPoint[] = [];
  for (let i = window; i < candles.length - window; i++) {
    const c = candles[i];
    const high = c.high ?? c.close;
    const low = c.low ?? c.close;
    let isHigh = true;
    let isLow = true;
    for (let j = i - window; j <= i + window; j++) {
      if (j === i) continue;
      const o = candles[j];
      const oh = o.high ?? o.close;
      const ol = o.low ?? o.close;
      if (oh >= high) isHigh = false;
      if (ol <= low) isLow = false;
    }
    if (isHigh) swings.push({ index: i, price: high, type: 'high', strength: 1 });
    if (isLow) swings.push({ index: i, price: low, type: 'low', strength: 1 });
  }
  return swings;
}

/** Detect BOS and CHOCH from the swing sequence. */
export function detectStructure(swings: SwingPoint[]): { bos: BOS[]; choch: CHOCH[] } {
  const bos: BOS[] = [];
  const choch: CHOCH[] = [];
  let lastHigh: SwingPoint | null = null;
  let lastLow: SwingPoint | null = null;
  let trend: 'bullish' | 'bearish' | null = null;

  for (const s of swings) {
    if (s.type === 'high') {
      if (lastHigh && s.price > lastHigh.price) {
        // Higher high — bullish continuation (BOS if already bullish).
        if (trend === 'bullish') {
          bos.push({ index: s.index, price: s.price, direction: 'bullish', brokenSwingIndex: lastHigh.index });
        } else if (trend === 'bearish') {
          // Breaking a prior high after a downtrend = CHOCH.
          choch.push({ index: s.index, price: s.price, direction: 'bullish', brokenSwingIndex: lastHigh.index });
        }
        trend = 'bullish';
      }
      lastHigh = s;
    } else if (s.type === 'low') {
      if (lastLow && s.price < lastLow.price) {
        // Lower low — bearish continuation.
        if (trend === 'bearish') {
          bos.push({ index: s.index, price: s.price, direction: 'bearish', brokenSwingIndex: lastLow.index });
        } else if (trend === 'bullish') {
          choch.push({ index: s.index, price: s.price, direction: 'bearish', brokenSwingIndex: lastLow.index });
        }
        trend = 'bearish';
      }
      lastLow = s;
    }
  }
  return { bos, choch };
}

/** Detect order blocks — the last opposing candle before a strong move. */
export function detectOrderBlocks(candles: PriceBar[], swings: SwingPoint[], minMovePct = 0.5): OrderBlock[] {
  const blocks: OrderBlock[] = [];
  for (let i = 1; i < candles.length - 1; i++) {
    const prev = candles[i - 1];
    const cur = candles[i];
    const next = candles[i + 1];
    const prevClose = prev.close;
    const curClose = cur.close;
    const nextClose = next.close;
    const movePct = Math.abs((nextClose - curClose) / curClose) * 100;
    if (movePct < minMovePct) continue;

    // Bullish OB: a red candle followed by a strong green move.
    if (curClose < prevClose && nextClose > curClose) {
      blocks.push({
        index: i, startIndex: i, endIndex: i,
        high: cur.high ?? curClose, low: cur.low ?? curClose,
        direction: 'bullish', strength: movePct, status: 'fresh',
      });
    }
    // Bearish OB: a green candle followed by a strong red move.
    else if (curClose > prevClose && nextClose < curClose) {
      blocks.push({
        index: i, startIndex: i, endIndex: i,
        high: cur.high ?? curClose, low: cur.low ?? curClose,
        direction: 'bearish', strength: movePct, status: 'fresh',
      });
    }
  }
  return blocks;
}

/** Detect Fair Value Gaps — a gap between candle i-1's high and candle i+1's low. */
export function detectFVGs(candles: PriceBar[]): FVG[] {
  const fvgs: FVG[] = [];
  for (let i = 1; i < candles.length - 1; i++) {
    const prev = candles[i - 1];
    const next = candles[i + 1];
    const prevHigh = prev.high ?? prev.close;
    const prevLow = prev.low ?? prev.close;
    const nextHigh = next.high ?? next.close;
    const nextLow = next.low ?? next.close;

    // Bullish FVG: prev.high < next.low (gap up).
    if (prevHigh < nextLow) {
      fvgs.push({ index: i, startIndex: i, endIndex: i, top: nextLow, bottom: prevHigh, direction: 'bullish', status: 'open' });
    }
    // Bearish FVG: prev.low > next.high (gap down).
    else if (prevLow > nextHigh) {
      fvgs.push({ index: i, startIndex: i, endIndex: i, top: prevLow, bottom: nextHigh, direction: 'bearish', status: 'open' });
    }
  }
  return fvgs;
}

/** Detect liquidity levels — equal highs/lows and sweeps. */
export function detectLiquidity(candles: PriceBar[], swings: SwingPoint[], tolerancePct = 0.1): LiquidityLevel[] {
  const levels: LiquidityLevel[] = [];
  const highs = swings.filter((s) => s.type === 'high');
  const lows = swings.filter((s) => s.type === 'low');

  // Equal highs / lows within tolerance.
  for (let i = 0; i < highs.length; i++) {
    for (let j = i + 1; j < highs.length; j++) {
      const a = highs[i], b = highs[j];
      if (Math.abs(a.price - b.price) / a.price * 100 < tolerancePct) {
        levels.push({ index: b.index, price: b.price, type: 'equal-high', strength: 1 });
        break;
      }
    }
  }
  for (let i = 0; i < lows.length; i++) {
    for (let j = i + 1; j < lows.length; j++) {
      const a = lows[i], b = lows[j];
      if (Math.abs(a.price - b.price) / a.price * 100 < tolerancePct) {
        levels.push({ index: b.index, price: b.price, type: 'equal-low', strength: 1 });
        break;
      }
    }
  }
  return levels;
}

/** Detect session high/low (grouped by day) and opening range. */
export function detectSessions(candles: PriceBar[]): { sessions: SessionLevel[]; openingRanges: OpeningRange[] } {
  const sessions: SessionLevel[] = [];
  const openingRanges: OpeningRange[] = [];
  let current: SessionLevel | null = null;
  let currentDate = '';
  let rangeHigh = 0, rangeLow = Infinity, rangeIndex = 0;

  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    const date = c.date.slice(0, 10);
    if (date !== currentDate) {
      if (current) sessions.push(current);
      current = { index: i, high: c.high ?? c.close, low: c.low ?? c.close, open: c.open ?? c.close, close: c.close, session: 'day' };
      currentDate = date;
      rangeHigh = c.high ?? c.close;
      rangeLow = c.low ?? c.close;
      rangeIndex = i;
    } else if (current) {
      current.high = Math.max(current.high, c.high ?? c.close);
      current.low = Math.min(current.low, c.low ?? c.close);
      current.close = c.close;
      // Opening range = first 3 candles of the session.
      if (i - rangeIndex < 3) {
        rangeHigh = Math.max(rangeHigh, c.high ?? c.close);
        rangeLow = Math.min(rangeLow, c.low ?? c.close);
      } else if (i - rangeIndex === 3) {
        openingRanges.push({ index: i, high: rangeHigh, low: rangeLow, rangeIndex });
      }
    }
  }
  if (current) sessions.push(current);
  return { sessions, openingRanges };
}

/** Run the full market-structure analysis. */
export function analyzeMarketStructure(candles: PriceBar[], timeframe: Timeframe): MarketStructureResult {
  const swings = findSwings(candles);
  const { bos, choch } = detectStructure(swings);
  const orderBlocks = detectOrderBlocks(candles, swings);
  const fvgs = detectFVGs(candles);
  const liquidity = detectLiquidity(candles, swings);
  const { sessions, openingRanges } = detectSessions(candles);

  // Trend from the last CHOCH/BOS.
  let trend: 'bullish' | 'bearish' | 'ranging' = 'ranging';
  const lastEvent = [...bos, ...choch].sort((a, b) => b.index - a.index)[0];
  if (lastEvent) trend = lastEvent.direction;

  return {
    symbol: '',
    timeframe,
    swings,
    bos,
    choch,
    orderBlocks,
    fvgs,
    liquidity,
    sessions,
    openingRanges,
    trend,
  };
}
