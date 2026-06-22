import { TradeRecord } from './analytics-engine';

export interface AICoachReport {
  insights: string[];
  recommendations: string[];
}

export function generateAICoachReport(trades: TradeRecord[]): AICoachReport {
  const insights: string[] = [];
  const recommendations: string[] = [];

  if (trades.length < 5) {
    return {
      insights: ['Insufficient trade history for AI diagnostic analysis. Minimum 5 trades required.'],
      recommendations: ['Perform at least 5 simulated trades to build setup diagnostic context.']
    };
  }

  // 1. Analyze setup styles (LONG vs SHORT)
  const longs = trades.filter(t => t.direction === 'LONG');
  const shorts = trades.filter(t => t.direction === 'SHORT');

  const longWins = longs.filter(t => t.pnl > 0).length;
  const longWinRate = longs.length > 0 ? (longWins / longs.length) * 100 : 0;

  const shortWins = shorts.filter(t => t.pnl > 0).length;
  const shortWinRate = shorts.length > 0 ? (shortWins / shorts.length) * 100 : 0;

  if (longs.length >= 3 && shorts.length >= 3) {
    if (Math.abs(longWinRate - shortWinRate) > 15) {
      const betterDirection = longWinRate > shortWinRate ? 'LONG' : 'SHORT';
      const worseDirection = longWinRate > shortWinRate ? 'SHORT' : 'LONG';
      const diff = Math.abs(longWinRate - shortWinRate).toFixed(1);
      
      insights.push(`Your ${betterDirection.toLowerCase()} trades perform significantly better (${diff}% higher win rate) than your ${worseDirection.toLowerCase()} trades.`);
      recommendations.push(`Filter out low-probability ${worseDirection.toLowerCase()} entries, or reduce position sizes on ${worseDirection.toLowerCase()} setups by 50%.`);
    }
  }

  // 2. NYC Lunch session performance leak check (Heuristic based on time tags)
  // Let's check exitDate or entryDate hour
  let lunchLossesCount = 0;
  let lunchTotalCount = 0;

  for (const t of trades) {
    const entryHour = new Date(t.entryDate).getHours();
    if (entryHour >= 12 && entryHour <= 13) {
      lunchTotalCount++;
      if (t.pnl < 0) {
        lunchLossesCount++;
      }
    }
  }

  if (lunchTotalCount >= 3) {
    const lunchLossPercent = (lunchLossesCount / lunchTotalCount) * 100;
    if (lunchLossPercent > 60) {
      insights.push(`A substantial percentage of your losses (${lunchLossPercent.toFixed(1)}%) occur during the NYC lunch session (12:00 PM - 2:00 PM).`);
      recommendations.push(`Implement a strict trade restriction during the lunch block (12:00 - 14:00 EST) to protect accumulated morning equity.`);
    }
  }

  // 3. Drawdown & Revenge Trading Detection (Quick sequence of consecutive losses)
  let consecutiveLossCount = 0;
  let maxConsecutiveLosses = 0;

  for (const t of trades) {
    if (t.pnl < 0) {
      consecutiveLossCount++;
      if (consecutiveLossCount > maxConsecutiveLosses) {
        maxConsecutiveLosses = consecutiveLossCount;
      }
    } else {
      consecutiveLossCount = 0;
    }
  }

  if (maxConsecutiveLosses >= 3) {
    insights.push(`Revenge trading triggers detected. You experienced a streak of ${maxConsecutiveLosses} consecutive losses.`);
    recommendations.push(`Set a daily loss limit ruleset. After 2 consecutive losses, step away from the terminal for at least 4 hours.`);
  }

  // Default fallbacks if no strong anomalies found
  if (insights.length === 0) {
    insights.push('Consistency metrics are stable. No major session or direction anomalies detected.');
    recommendations.push('Maintain strict risk control limits and continue scaling strategy size incrementally.');
  }

  return { insights, recommendations };
}
