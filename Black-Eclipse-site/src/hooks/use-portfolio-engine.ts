import { useMemo } from 'react';
import { Transaction } from '@/components/screens/my-portfolio';

export interface PortfolioStats {
  totalValue: number;
  costBasis: number;
  unrealizedPnL: number;
  realizedPnL: number;
  roiPercent: number;
  dailyChangeValue: number;
  dailyChangePercent: number;
  holdings: Array<{
    symbol: string;
    quantity: number;
    avgCost: number;
    currentPrice: number;
    value: number;
    unrealizedPnL: number;
    allocation: number;
    realizedPnL: number;
  }>;
}

export function usePortfolioEngine(
  transactions: Transaction[],
  liveAssets: any[], // From JDdS
  taxMethod: 'FIFO' | 'LIFO' = 'FIFO'
): PortfolioStats {
  return useMemo(() => {
    // 1. Group transactions by symbol
    const txBySymbol = new Map<string, Transaction[]>();
    for (const tx of transactions) {
      if (tx.type === 'DEPOSIT' || tx.type === 'WITHDRAWAL') continue; // Handled separately if needed
      
      const list = txBySymbol.get(tx.symbol) || [];
      list.push(tx);
      txBySymbol.set(tx.symbol, list);
    }

    let totalValue = 0;
    let totalCostBasis = 0;
    let totalRealizedPnL = 0;
    let dailyChangeValue = 0;

    const holdings: PortfolioStats['holdings'] = [];

    // Map live prices
    const liveMap = new Map<string, { price: number; change24h: number }>();
    for (const asset of liveAssets) {
      liveMap.set(asset.symbol, {
        price: asset.price || 0,
        change24h: asset.changePercent || 0,
      });
    }

    // 2. Process each symbol
    for (const [symbol, txs] of txBySymbol.entries()) {
      // Sort by date ascending
      const sortedTxs = [...txs].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
      
      let realizedPnL = 0;
      
      // We keep track of lots to match buys with sells
      const buyLots: { qty: number; price: number }[] = [];
      
      let currentQty = 0;
      let costBasis = 0;

      for (const tx of sortedTxs) {
        if (tx.type === 'BUY') {
          buyLots.push({ qty: tx.quantity, price: tx.price });
          currentQty += tx.quantity;
          costBasis += (tx.quantity * tx.price) + tx.fee;
        } else if (tx.type === 'SELL') {
          // Process sell against lots
          let qtyToSell = tx.quantity;
          let costOfSoldLots = 0;
          
          while (qtyToSell > 0 && buyLots.length > 0) {
            const lotIndex = taxMethod === 'FIFO' ? 0 : buyLots.length - 1;
            const lot = buyLots[lotIndex];
            
            if (lot.qty <= qtyToSell) {
              // Consume whole lot
              qtyToSell -= lot.qty;
              costOfSoldLots += lot.qty * lot.price;
              buyLots.splice(lotIndex, 1);
            } else {
              // Consume partial lot
              lot.qty -= qtyToSell;
              costOfSoldLots += qtyToSell * lot.price;
              qtyToSell = 0;
            }
          }
          
          // Calculate realized PnL for this sell
          const proceeds = (tx.quantity * tx.price) - tx.fee;
          realizedPnL += (proceeds - costOfSoldLots);
          
          currentQty -= tx.quantity;
          costBasis -= costOfSoldLots; // Remove sold cost from active cost basis
        }
      }

      // If we have remaining quantity, add to holdings
      if (currentQty > 0.000001) { // Precision threshold
        const liveData = liveMap.get(symbol);
        const currentPrice = liveData?.price || 0;
        const change24h = liveData?.change24h || 0;
        
        const value = currentQty * currentPrice;
        const avgCost = costBasis / currentQty;
        const unrealizedPnL = value - costBasis;
        
        // Calculate daily impact
        const prevPrice = currentPrice / (1 + (change24h / 100));
        const dayChange = value - (currentQty * prevPrice);

        totalValue += value;
        totalCostBasis += costBasis;
        totalRealizedPnL += realizedPnL;
        dailyChangeValue += dayChange;

        holdings.push({
          symbol,
          quantity: currentQty,
          avgCost,
          currentPrice,
          value,
          unrealizedPnL,
          allocation: 0, // Calculated after totalValue is known
          realizedPnL,
        });
      } else {
        totalRealizedPnL += realizedPnL;
      }
    }

    // 3. Finalize stats
    for (const h of holdings) {
      if (totalValue > 0) {
        h.allocation = (h.value / totalValue) * 100;
      }
    }

    // Sort holdings by value
    holdings.sort((a, b) => b.value - a.value);

    const unrealizedPnL = totalValue - totalCostBasis;
    const roiPercent = totalCostBasis > 0 ? (unrealizedPnL / totalCostBasis) * 100 : 0;
    
    // Daily percentage
    const prevTotalValue = totalValue - dailyChangeValue;
    const dailyChangePercent = prevTotalValue > 0 ? (dailyChangeValue / prevTotalValue) * 100 : 0;

    return {
      totalValue,
      costBasis: totalCostBasis,
      unrealizedPnL,
      realizedPnL: totalRealizedPnL,
      roiPercent,
      dailyChangeValue,
      dailyChangePercent,
      holdings,
    };
  }, [transactions, liveAssets, taxMethod]);
}
