import { Candle } from './engine';

export interface Position {
  id: string;
  direction: 'LONG' | 'SHORT';
  entryPrice: number;
  sizeUSD: number;
  shares: number;
  stopLossBrackets: { price: number; sizeUSD: number; hit: boolean }[];
  takeProfitBrackets: { price: number; sizeUSD: number; hit: boolean }[];
  entryDate: string;
  feesPaid: number;
}

export interface ReplayState {
  cash: number;
  equity: number;
  activePositions: Position[];
  closedTrades: any[];
  replayIndex: number;
  bookmarks: { name: string; index: number }[];
}

export interface OrderInput {
  direction: 'LONG' | 'SHORT';
  type: 'MARKET' | 'LIMIT' | 'STOP' | 'STOP_LIMIT';
  price?: number;
  stopPrice?: number;
  riskAmountUSD?: number;
  riskPercent?: number;
  stopLossPrice?: number;
  takeProfitBrackets?: { price: number; percent: number }[];
}

// Automatic lot size and position calculations
export function calculatePositionSize(
  accountCapital: number,
  entryPrice: number,
  stopLossPrice: number,
  riskAmountUSD?: number,
  riskPercent?: number
): { sizeUSD: number; shares: number } {
  let riskUSD = riskAmountUSD || 0;
  if (riskPercent && riskPercent > 0) {
    riskUSD = accountCapital * (riskPercent / 100);
  }

  if (riskUSD <= 0 || !stopLossPrice || stopLossPrice === entryPrice) {
    return { sizeUSD: 0, shares: 0 };
  }

  const riskPerShare = Math.abs(entryPrice - stopLossPrice);
  const shares = riskUSD / riskPerShare;
  const sizeUSD = shares * entryPrice;

  return { sizeUSD, shares };
}

// Professional Execution simulator
export function executeOrder(
  order: OrderInput,
  currentPrice: number,
  capital: number,
  slippagePercent = 0.001,
  spreadUSD = 0,
  commissionRate = 0.0005 // 0.05%
): { position: Position; fees: number; cashRequired: number } {
  const isLong = order.direction === 'LONG';
  
  // Apply slippage and spread
  const basePrice = order.price || currentPrice;
  const slipPrice = isLong 
    ? basePrice * (1 + slippagePercent) + (spreadUSD / 2)
    : basePrice * (1 - slippagePercent) - (spreadUSD / 2);

  // Set sizing
  let sizeUSD = 0;
  let shares = 0;

  if (order.riskAmountUSD || order.riskPercent) {
    const calc = calculatePositionSize(
      capital,
      slipPrice,
      order.stopLossPrice || 0,
      order.riskAmountUSD,
      order.riskPercent
    );
    sizeUSD = calc.sizeUSD;
    shares = calc.shares;
  } else {
    // Default size fallback: 10% of capital
    sizeUSD = capital * 0.1;
    shares = sizeUSD / slipPrice;
  }

  const commission = sizeUSD * commissionRate;
  const cashRequired = sizeUSD + commission;

  const stopLossBrackets = order.stopLossPrice 
    ? [{ price: order.stopLossPrice, sizeUSD: sizeUSD, hit: false }]
    : [];

  const takeProfitBrackets = (order.takeProfitBrackets || []).map(b => ({
    price: b.price,
    sizeUSD: sizeUSD * (b.percent / 100),
    hit: false
  }));

  const position: Position = {
    id: `pos-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
    direction: order.direction,
    entryPrice: slipPrice,
    sizeUSD,
    shares,
    stopLossBrackets,
    takeProfitBrackets,
    entryDate: new Date().toISOString(),
    feesPaid: commission
  };

  return { position, fees: commission, cashRequired };
}

// Tick-by-tick / candle position evaluator
export function updateSimulationStep(
  candle: Candle,
  state: ReplayState,
  slippagePercent = 0.0005,
  commissionRate = 0.0005
): ReplayState {
  const nextState = { ...state };
  const activePositions: Position[] = [];

  for (const pos of nextState.activePositions) {
    let closed = false;
    let exitPrice = candle.close;
    let realizedPnL = 0;
    let updatedPos = { ...pos };

    // 1. Process Take Profit brackets (Partial exits)
    const activeTPs = [];
    for (const tp of updatedPos.takeProfitBrackets) {
      const isHit = pos.direction === 'LONG' 
        ? candle.high >= tp.price 
        : candle.low <= tp.price;

      if (isHit && !tp.hit) {
        // Partial exit
        const exitPriceWithSlippage = pos.direction === 'LONG'
          ? tp.price * (1 - slippagePercent)
          : tp.price * (1 + slippagePercent);

        const fraction = tp.sizeUSD / pos.sizeUSD;
        const sharesRealized = pos.shares * fraction;
        const fees = tp.sizeUSD * commissionRate;

        const pnl = pos.direction === 'LONG'
          ? (exitPriceWithSlippage - pos.entryPrice) * sharesRealized
          : (pos.entryPrice - exitPriceWithSlippage) * sharesRealized;

        nextState.cash += (sharesRealized * exitPriceWithSlippage) - fees;
        realizedPnL += pnl;

        updatedPos.sizeUSD -= tp.sizeUSD;
        updatedPos.shares -= sharesRealized;
        updatedPos.feesPaid += fees;

        activeTPs.push({ ...tp, hit: true });
      } else {
        activeTPs.push(tp);
      }
    }
    updatedPos.takeProfitBrackets = activeTPs;

    // 2. Process Stop Loss brackets (Full or partial exit)
    for (const sl of updatedPos.stopLossBrackets) {
      const isHit = pos.direction === 'LONG'
        ? candle.low <= sl.price
        : candle.high >= sl.price;

      if (isHit) {
        closed = true;
        exitPrice = pos.direction === 'LONG'
          ? sl.price * (1 - slippagePercent)
          : sl.price * (1 + slippagePercent);
        break;
      }
    }

    if (closed || updatedPos.shares <= 0.00001) {
      // Finalize position closure
      const finalExitPrice = exitPrice;
      const finalShares = updatedPos.shares;
      const fees = (finalShares * finalExitPrice) * commissionRate;
      
      const pnl = pos.direction === 'LONG'
        ? (finalExitPrice - pos.entryPrice) * finalShares
        : (pos.entryPrice - finalExitPrice) * finalShares;

      nextState.cash += (finalShares * finalExitPrice) - fees;
      
      nextState.closedTrades.push({
        id: pos.id,
        direction: pos.direction,
        entryPrice: pos.entryPrice,
        exitPrice: finalExitPrice,
        sizeUSD: pos.sizeUSD,
        pnl: realizedPnL + pnl - fees,
        pnlPercent: ((realizedPnL + pnl - fees) / pos.sizeUSD) * 100,
        entryDate: pos.entryDate,
        exitDate: candle.date
      });
    } else {
      activePositions.push(updatedPos);
    }
  }

  nextState.activePositions = activePositions;
  return nextState;
}
