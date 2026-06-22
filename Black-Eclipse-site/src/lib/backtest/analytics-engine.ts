export interface TradeRecord {
  id: string;
  direction: 'LONG' | 'SHORT';
  entryPrice: number;
  exitPrice: number;
  sizeUSD: number;
  pnl: number;
  pnlPercent: number;
  entryDate: string;
  exitDate: string;
}

export interface AnalyticsSummary {
  totalTrades: number;
  winRate: number;
  lossRate: number;
  netProfit: number;
  grossProfit: number;
  grossLoss: number;
  profitFactor: number;
  sharpeRatio: number;
  sortinoRatio: number;
  calmarRatio: number;
  expectancy: number;
  maxDrawdown: number;
  consecutiveWins: number;
  consecutiveLosses: number;
}

export function generatePerformanceAnalytics(trades: TradeRecord[], startingCapital: number): AnalyticsSummary {
  const totalTrades = trades.length;
  if (totalTrades === 0) {
    return {
      totalTrades: 0,
      winRate: 0,
      lossRate: 0,
      netProfit: 0,
      grossProfit: 0,
      grossLoss: 0,
      profitFactor: 0,
      sharpeRatio: 0,
      sortinoRatio: 0,
      calmarRatio: 0,
      expectancy: 0,
      maxDrawdown: 0,
      consecutiveWins: 0,
      consecutiveLosses: 0,
    };
  }

  const winningTrades = trades.filter(t => t.pnl > 0);
  const losingTrades = trades.filter(t => t.pnl <= 0);

  const winRate = winningTrades.length / totalTrades;
  const lossRate = losingTrades.length / totalTrades;

  const grossProfit = winningTrades.reduce((acc, t) => acc + t.pnl, 0);
  const grossLoss = Math.abs(losingTrades.reduce((acc, t) => acc + t.pnl, 0));
  const netProfit = grossProfit - grossLoss;

  const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit;

  // Expectancy calculation
  const averageWin = winningTrades.length > 0 ? grossProfit / winningTrades.length : 0;
  const averageLoss = losingTrades.length > 0 ? grossLoss / losingTrades.length : 0;
  const expectancy = (winRate * averageWin) - (lossRate * averageLoss);

  // Drawdown tracking & returns calculation
  let capital = startingCapital;
  let peak = startingCapital;
  let maxDrawdown = 0;
  const periodicReturns: number[] = [];

  for (const t of trades) {
    const prevCap = capital;
    capital += t.pnl;
    
    const ret = (capital - prevCap) / prevCap;
    periodicReturns.push(ret);

    if (capital > peak) {
      peak = capital;
    }
    const dd = (peak - capital) / peak;
    if (dd > maxDrawdown) {
      maxDrawdown = dd;
    }
  }

  // Sharpe & Sortino Calculations
  const averageReturn = periodicReturns.reduce((acc, r) => acc + r, 0) / totalTrades;
  
  const variance = periodicReturns.reduce((acc, r) => acc + Math.pow(r - averageReturn, 2), 0) / totalTrades;
  const stdDev = Math.sqrt(variance);

  const negativeReturns = periodicReturns.filter(r => r < 0);
  const downsideVariance = negativeReturns.reduce((acc, r) => acc + Math.pow(r, 2), 0) / (negativeReturns.length || 1);
  const downsideDeviation = Math.sqrt(downsideVariance);

  const riskFreeRate = 0.02 / 365; // Proxy daily rate

  const sharpeRatio = stdDev > 0 ? (averageReturn - riskFreeRate) / stdDev : 0;
  const sortinoRatio = downsideDeviation > 0 ? (averageReturn - riskFreeRate) / downsideDeviation : 0;
  const calmarRatio = maxDrawdown > 0 ? (netProfit / startingCapital) / maxDrawdown : 0;

  // Streak calculations
  let consecutiveWins = 0;
  let consecutiveLosses = 0;
  let currentWins = 0;
  let currentLosses = 0;

  for (const t of trades) {
    if (t.pnl > 0) {
      currentWins++;
      currentLosses = 0;
      if (currentWins > consecutiveWins) consecutiveWins = currentWins;
    } else {
      currentLosses++;
      currentWins = 0;
      if (currentLosses > consecutiveLosses) consecutiveLosses = currentLosses;
    }
  }

  return {
    totalTrades,
    winRate: winRate * 100,
    lossRate: lossRate * 100,
    netProfit,
    grossProfit,
    grossLoss,
    profitFactor,
    sharpeRatio,
    sortinoRatio,
    calmarRatio,
    expectancy,
    maxDrawdown: maxDrawdown * 100,
    consecutiveWins,
    consecutiveLosses,
  };
}

// Monte Carlo simulations engine (up to 1000 runs)
export function runMonteCarloSimulation(
  trades: TradeRecord[],
  startingCapital: number,
  simulationsCount = 200,
  tradesPerRun = 50
): { paths: number[][]; riskOfRuinPercent: number } {
  const paths: number[][] = [];
  let ruinCount = 0;

  if (trades.length === 0) {
    return { paths: [], riskOfRuinPercent: 0 };
  }

  for (let s = 0; s < simulationsCount; s++) {
    const currentPath: number[] = [startingCapital];
    let capital = startingCapital;
    let ruined = false;

    for (let t = 0; t < tradesPerRun; t++) {
      // Pick random trade outcome
      const randomIndex = Math.floor(Math.random() * trades.length);
      const outcome = trades[randomIndex];
      capital += outcome.pnl;

      // Risk of ruin threshold: Capital falls below 30% of start
      if (capital < startingCapital * 0.3) {
        ruined = true;
      }
      currentPath.push(capital);
    }

    if (ruined) {
      ruinCount++;
    }
    paths.push(currentPath);
  }

  const riskOfRuinPercent = (ruinCount / simulationsCount) * 100;
  return { paths, riskOfRuinPercent };
}
