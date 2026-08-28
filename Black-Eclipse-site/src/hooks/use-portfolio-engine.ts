import { useMemo } from 'react';
import type { Transaction } from '@/components/screens/my-portfolio';

export interface PortfolioStats {
  /** Total portfolio value expressed in the base (reporting) currency USD. */
  totalValue: number;
  /** Blended portfolio cost basis in USD-equivalent. */
  costBasis: number;
  unrealizedPnL: number;
  /** Realized P/L realized in each asset's native currency and converted at the live FX rate (approximation). */
  realizedPnL: number;
  roiPercent: number;
  dailyChangeValue: number;
  dailyChangePercent: number;
  /** Reporting currency. Fixed to USD — all aggregates are USD-equivalents. */
  base: 'USD';
  holdings: Array<{
    symbol: string;
    name: string;
    currency: 'USD' | 'PKR';
    /** Native currency price. */
    currentPrice: number;
    /** Live FX rate: 1 unit of `currency` = fxToUsd USD. */
    fxToUsd: number;
    quantity: number;
    avgCost: number;
    value: number;
    /** USD-equivalent value for cross-asset aggregation. */
    valueUsd: number;
    unrealizedPnL: number;
    unrealizedPnLUsd: number;
    allocation: number;
    realizedPnL: number;
    realizedPnLUsd: number;
    dayPct: number;
  }>;
}

export interface LiveAssetInput {
  symbol: string;
  price?: number;
  changePercent?: number;
  currency?: 'USD' | 'PKR' | string;
  fxToUsd?: number;
  name?: string;
}

const EPS = 1e-9;
const precisionThreshold = 1e-6;

// ── FIFO/LIFO costs in native currency, then converted at live FX ───────────
export function computePortfolioStats(
  transactions: Transaction[],
  liveAssets: LiveAssetInput[],
  taxMethod: 'FIFO' | 'LIFO' = 'FIFO'
): PortfolioStats {
  const liveMap = new Map<string, LiveAssetInput>();
  for (const a of liveAssets) liveMap.set(a.symbol, a);

  const grouped = new Map<string, Transaction[]>();
  for (const tx of transactions) {
    if (tx.type === 'DEPOSIT' || tx.type === 'WITHDRAWAL') continue;
    const list = grouped.get(tx.symbol) || [];
    list.push(tx);
    grouped.set(tx.symbol, list);
  }

  const holdings: PortfolioStats['holdings'] = [];
  let totalValueUsd = 0;
  let totalCostBasisUsd = 0;
  let totalRealizedUsd = 0;
  let dailyChangeValueUsd = 0;
  const realizedBySymbol: Record<string, number> = {};

  for (const [symbol, txs] of grouped) {
    const sorted = [...txs].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
    const live = liveMap.get(symbol);
    const currency: 'USD' | 'PKR' = (live?.currency === 'PKR' ? 'PKR' : 'USD');
    const fxToUsd = live?.fxToUsd ?? (currency === 'PKR' ? 1 / 278 : 1);

    const buyLots: Array<{ qty: number; price: number }> = [];
    let realized = 0;
    let qty = 0;
    let costBasis = 0;

    for (const tx of sorted) {
      if (tx.type === 'BUY') {
        buyLots.push({ qty: tx.quantity, price: tx.price });
        qty += tx.quantity;
        costBasis += tx.quantity * tx.price + tx.fee;
      } else if (tx.type === 'SELL') {
        let toSell = tx.quantity;
        let costOfSold = 0;
        while (toSell > EPS && buyLots.length > 0) {
          const i = taxMethod === 'FIFO' ? 0 : buyLots.length - 1;
          const lot = buyLots[i];
          if (lot.qty <= toSell) {
            toSell -= lot.qty;
            costOfSold += lot.qty * lot.price;
            buyLots.splice(i, 1);
          } else {
            lot.qty -= toSell;
            costOfSold += toSell * lot.price;
            toSell = 0;
          }
        }
        const proceeds = tx.quantity * tx.price - tx.fee;
        realized += proceeds - costOfSold;
        qty -= tx.quantity;
        costBasis -= costOfSold;
      }
    }
    realizedBySymbol[symbol] = realized;

    if (qty <= precisionThreshold) {
      if (realized !== 0) totalRealizedUsd += realized * fxToUsd;
      continue;
    }

    const currentPrice = live?.price ?? 0;
    const dayPct = live?.changePercent ?? 0;
    const value = qty * currentPrice;
    const avgCost = costBasis / qty;
    const unrealized = value - costBasis;
    const valueUsd = value * fxToUsd;

    totalValueUsd += valueUsd;
    totalCostBasisUsd += costBasis * fxToUsd;
    totalRealizedUsd += realized * fxToUsd;

    const prevPrice = currentPrice / (1 + dayPct / 100);
    dailyChangeValueUsd += (value - qty * prevPrice) * fxToUsd;

    holdings.push({
      symbol,
      name: live?.name ?? symbol,
      currency,
      currentPrice,
      fxToUsd,
      quantity: qty,
      avgCost,
      value,
      valueUsd,
      unrealizedPnL: unrealized,
      unrealizedPnLUsd: unrealized * fxToUsd,
      allocation: 0,
      realizedPnL: realized,
      realizedPnLUsd: realized * fxToUsd,
      dayPct,
    });
  }

  for (const h of holdings) {
    h.allocation = totalValueUsd > 0 ? (h.valueUsd / totalValueUsd) * 100 : 0;
  }
  holdings.sort((a, b) => b.valueUsd - a.valueUsd);

  const unrealizedPnLUsd = totalValueUsd - totalCostBasisUsd;
  const roiPercent = totalCostBasisUsd > 0 ? (unrealizedPnLUsd / totalCostBasisUsd) * 100 : 0;
  const prevTotalUsd = totalValueUsd - dailyChangeValueUsd;
  const dailyChangePercent = prevTotalUsd > 0 ? (dailyChangeValueUsd / prevTotalUsd) * 100 : 0;

  return {
    totalValue: totalValueUsd,
    costBasis: totalCostBasisUsd,
    unrealizedPnL: unrealizedPnLUsd,
    realizedPnL: totalRealizedUsd,
    roiPercent,
    dailyChangeValue: dailyChangeValueUsd,
    dailyChangePercent,
    base: 'USD',
    holdings,
  };
}

export function usePortfolioEngine(
  transactions: Transaction[],
  liveAssets: LiveAssetInput[],
  taxMethod: 'FIFO' | 'LIFO' = 'FIFO'
): PortfolioStats {
  return useMemo(
    () => computePortfolioStats(transactions, liveAssets, taxMethod),
    [transactions, liveAssets, taxMethod]
  );
}