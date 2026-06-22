export interface Candle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Position {
  id: string;
  direction: 'LONG' | 'SHORT';
  entryPrice: number;
  sizeUSD: number;
  shares: number;
  stopLoss?: number | null;
  takeProfit?: number | null;
  entryDate?: string;
  
  // Advanced features
  trailingStopEnabled?: boolean;
  trailingStopDistance?: number; // Distance in USD/Price units
  maxSeenPrice?: number; // High water mark for LONG
  minSeenPrice?: number; // Low water mark for SHORT

  tp1Price?: number | null;
  tp1Percent?: number; // e.g. 50 (representing 50%)
  tp1Hit?: boolean;
}

export interface LimitOrder {
  id: string;
  type: 'BUY_LIMIT' | 'SELL_LIMIT';
  price: number;
  sizeUSD: number;
  stopLoss?: number | null;
  takeProfit?: number | null;
}

export interface JournalTrade {
  id: string;
  symbol: string;
  direction: 'LONG' | 'SHORT';
  entryDate: string;
  entryPrice: number;
  exitDate: string;
  exitPrice: number;
  sizeUSD: number;
  pnl: number;
  pnlPercent: number;
  notes: string;
}

// ----------------------------------------------------
// Technical Indicator Calculators
// ----------------------------------------------------

export function calculateSMA(prices: number[], period: number): number[] {
  const sma: number[] = [];
  for (let i = 0; i < prices.length; i++) {
    if (i < period - 1) {
      sma.push(NaN);
      continue;
    }
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += prices[i - j];
    }
    sma.push(sum / period);
  }
  return sma;
}

export function calculateEMA(prices: number[], period: number): number[] {
  const ema: number[] = [];
  if (prices.length === 0) return ema;

  const k = 2 / (period + 1);
  let prevEma = prices[0];
  ema.push(prevEma);

  for (let i = 1; i < prices.length; i++) {
    const curEma = prices[i] * k + prevEma * (1 - k);
    ema.push(curEma);
    prevEma = curEma;
  }
  return ema;
}

export function calculateRSI(prices: number[], period: number): number[] {
  const rsi: number[] = [];
  if (prices.length === 0) return rsi;

  for (let i = 0; i < prices.length; i++) {
    if (i < period) {
      rsi.push(NaN);
      continue;
    }

    let gains = 0;
    let losses = 0;

    for (let j = i - period + 1; j <= i; j++) {
      const diff = prices[j] - prices[j - 1];
      if (diff > 0) {
        gains += diff;
      } else {
        losses -= diff;
      }
    }

    if (losses === 0) {
      rsi.push(100);
    } else {
      const rs = gains / losses;
      rsi.push(100 - 100 / (1 + rs));
    }
  }
  return rsi;
}

// ----------------------------------------------------
// Step Execution Verification Logic
// ----------------------------------------------------

export function evaluateCurrentStep(
  candle: Candle,
  activePositions: Position[],
  pendingOrders: LimitOrder[],
  closedTrades: JournalTrade[],
  cash: number,
  slippage = 0.001,
  symbol: string
): {
  activePositions: Position[];
  pendingOrders: LimitOrder[];
  closedTrades: JournalTrade[];
  cash: number;
} {
  let positions = [...activePositions];
  let orders = [...pendingOrders];
  let trades = [...closedTrades];
  let remainingCash = cash;

  const high = candle.high;
  const low = candle.low;
  const close = candle.close;
  const date = candle.date;

  // 1. Process Pending Limit Orders
  const remainingOrders: LimitOrder[] = [];

  for (const order of orders) {
    let triggered = false;

    // BUY LIMIT trigger check: price touched low boundary
    if (order.type === 'BUY_LIMIT' && low <= order.price) {
      triggered = true;
      const executePrice = order.price * (1 + slippage);
      const shares = order.sizeUSD / executePrice;
      positions.push({
        id: `pos-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        direction: 'LONG',
        entryPrice: executePrice,
        sizeUSD: order.sizeUSD,
        shares,
        stopLoss: order.stopLoss,
        takeProfit: order.takeProfit,
        entryDate: date,
      });
      remainingCash -= order.sizeUSD;
    }
    // SELL LIMIT trigger check: price touched high boundary
    else if (order.type === 'SELL_LIMIT' && high >= order.price) {
      triggered = true;
      const executePrice = order.price * (1 - slippage);
      const shares = order.sizeUSD / executePrice;
      positions.push({
        id: `pos-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        direction: 'SHORT',
        entryPrice: executePrice,
        sizeUSD: order.sizeUSD,
        shares,
        stopLoss: order.stopLoss,
        takeProfit: order.takeProfit,
        entryDate: date,
      });
      remainingCash -= order.sizeUSD;
    }

    if (!triggered) {
      remainingOrders.push(order);
    }
  }
  orders = remainingOrders;

  // 2. Evaluate Trailing Stop Loss & Partial Take Profits for active positions
  const survivingPositions: Position[] = [];

  for (let pos of positions) {
    let currentPos = { ...pos };
    let isLong = currentPos.direction === 'LONG';
    let liquidated = false;
    let exitPrice = close;
    let reason = '';

    // A. Trailing Stop Loss adjustment
    if (currentPos.trailingStopEnabled && currentPos.trailingStopDistance) {
      if (isLong) {
        currentPos.maxSeenPrice = Math.max(currentPos.maxSeenPrice || currentPos.entryPrice, high);
        const newSL = currentPos.maxSeenPrice - currentPos.trailingStopDistance;
        currentPos.stopLoss = Math.max(currentPos.stopLoss || 0, newSL);
      } else {
        currentPos.minSeenPrice = Math.min(currentPos.minSeenPrice || currentPos.entryPrice, low);
        const newSL = currentPos.minSeenPrice + currentPos.trailingStopDistance;
        currentPos.stopLoss = Math.min(currentPos.stopLoss || Infinity, newSL);
      }
    }

    // B. Partial Take Profit (TP1) target check
    if (currentPos.tp1Price && !currentPos.tp1Hit) {
      const tpPercent = currentPos.tp1Percent || 50;
      let tp1Triggered = false;

      if (isLong && high >= currentPos.tp1Price) {
        tp1Triggered = true;
        exitPrice = currentPos.tp1Price * (1 - slippage);
      } else if (!isLong && low <= currentPos.tp1Price) {
        tp1Triggered = true;
        exitPrice = currentPos.tp1Price * (1 + slippage);
      }

      if (tp1Triggered) {
        const closedSize = currentPos.sizeUSD * (tpPercent / 100);
        const closedShares = currentPos.shares * (tpPercent / 100);
        
        let pnl = 0;
        if (isLong) {
          pnl = (exitPrice - currentPos.entryPrice) * closedShares;
        } else {
          pnl = (currentPos.entryPrice - exitPrice) * closedShares;
        }

        trades.push({
          id: `trade-partial-${trades.length + 1}-${Date.now()}`,
          symbol,
          direction: currentPos.direction,
          entryDate: currentPos.entryDate || date,
          entryPrice: currentPos.entryPrice,
          exitDate: date,
          exitPrice,
          sizeUSD: closedSize,
          pnl,
          pnlPercent: (pnl / closedSize) * 100,
          notes: `Partial Close TP1 (${tpPercent}% scaled out).`,
        });

        remainingCash += closedSize + pnl;

        // Scale down remaining position
        currentPos.sizeUSD -= closedSize;
        currentPos.shares -= closedShares;
        currentPos.tp1Hit = true;
      }
    }

    // C. Evaluate full Stop-Loss and Take-Profit limits
    if (isLong) {
      if (currentPos.stopLoss && low <= currentPos.stopLoss) {
        liquidated = true;
        exitPrice = currentPos.stopLoss * (1 - slippage);
        reason = currentPos.trailingStopEnabled ? 'Trailing Stop Loss' : 'Stop Loss';
      } else if (currentPos.takeProfit && high >= currentPos.takeProfit) {
        liquidated = true;
        exitPrice = currentPos.takeProfit * (1 - slippage);
        reason = 'Take Profit';
      }
    } else {
      if (currentPos.stopLoss && high >= currentPos.stopLoss) {
        liquidated = true;
        exitPrice = currentPos.stopLoss * (1 + slippage);
        reason = currentPos.trailingStopEnabled ? 'Trailing Stop Loss' : 'Stop Loss';
      } else if (currentPos.takeProfit && low <= currentPos.takeProfit) {
        liquidated = true;
        exitPrice = currentPos.takeProfit * (1 + slippage);
        reason = 'Take Profit';
      }
    }

    if (liquidated) {
      let pnl = 0;
      if (isLong) {
        pnl = (exitPrice - currentPos.entryPrice) * currentPos.shares;
      } else {
        pnl = (currentPos.entryPrice - exitPrice) * currentPos.shares;
      }

      const pnlPercent = (pnl / currentPos.sizeUSD) * 100;

      trades.push({
        id: `trade-${trades.length + 1}-${Date.now()}`,
        symbol,
        direction: currentPos.direction,
        entryDate: currentPos.entryDate || date,
        entryPrice: currentPos.entryPrice,
        exitDate: date,
        exitPrice,
        sizeUSD: currentPos.sizeUSD,
        pnl,
        pnlPercent,
        notes: `Auto-liquidated via ${reason}.`,
      });

      remainingCash += currentPos.sizeUSD + pnl;
    } else {
      survivingPositions.push(currentPos);
    }
  }

  return {
    activePositions: survivingPositions,
    pendingOrders: orders,
    closedTrades: trades,
    cash: remainingCash,
  };
}
