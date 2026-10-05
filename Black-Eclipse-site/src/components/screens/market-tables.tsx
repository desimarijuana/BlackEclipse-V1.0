'use client';

import React from 'react';
import { ArrowUp, ArrowDown, Sparkles } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { TableSkeleton } from './market-loaders';
import { formatUsdPrice } from '@/lib/screener/format';
import type { ForexPair } from './use-market-tabs';
import type { CommodityItem } from './use-market-tabs';
import type { StockItem } from '@/lib/screener/data';

// ── Forex & Commodities tables ──────────────────────────────────────────────
// Extracted from market-overview.tsx (memory/simplicity standing goal): the
// dedicated full tables for the Forex and Commodities tabs. Filters/sort state
// and the fetches live in ./use-market-tabs.ts; this renders them.

interface MarketTablesProps {
  screenerTab: string;
  sectionVisible: (key: 'table_forex' | 'table_commodities') => boolean;
  handleSymbolClick: (symbol: string, name: string, extra?: Partial<StockItem>, e?: React.MouseEvent) => void;
  onAnalyzeTicker: (ticker: string) => void;
  // Forex
  forexSortField: keyof ForexPair;
  forexSortOrder: 'asc' | 'desc';
  toggleForexSort: (field: keyof ForexPair) => void;
  loadingForex: boolean;
  filteredForex: ForexPair[];
  // Commodities
  loadingCommodities: boolean;
  filteredCommodities: CommodityItem[];
}

export function MarketTables(props: MarketTablesProps) {
  const {
    screenerTab, sectionVisible, handleSymbolClick, onAnalyzeTicker,
    forexSortField, forexSortOrder, toggleForexSort, loadingForex, filteredForex,
    loadingCommodities, filteredCommodities,
  } = props;
  const handleAction = onAnalyzeTicker;

  return (
    <>
        {screenerTab === 'forex' && sectionVisible('table_forex') && (
          <>
            <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
              <table className="w-full text-left border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleForexSort('symbol')}>
                      Pair {forexSortField === 'symbol' && (forexSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleForexSort('name')}>
                      Name {forexSortField === 'name' && (forexSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleForexSort('base')}>
                      Base {forexSortField === 'base' && (forexSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleForexSort('quote')}>
                      Quote {forexSortField === 'quote' && (forexSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleForexSort('price')}>
                      Rate (USD) {forexSortField === 'price' && (forexSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleForexSort('changePct')}>
                      Change % {forexSortField === 'changePct' && (forexSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingForex ? (
                    <TableSkeleton cols={7} rows={8} />
                  ) : filteredForex.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                        No matching forex pairs found.
                      </td>
                    </tr>
                  ) : (
                    filteredForex.map((pair) => {
                      const isPositive = pair.changePct >= 0;
                      return (
                        <tr
                          key={pair.symbol}
                          className="hover:bg-accent/20 even:bg-accent/5 odd:bg-transparent transition-colors font-medium"
                        >
                          <td
                            onClick={(e) => handleSymbolClick(pair.symbol, pair.name, { price: pair.price, changePercent: pair.changePct }, e)}
                            title="Ctrl+click to open in new tab"
                            className="py-1 px-2 border border-border/30 font-bold font-mono text-foreground/80 hover:underline whitespace-nowrap cursor-pointer"
                          >
                            {pair.symbol.replace('=X', '')}
                          </td>
                          <td className="py-3 px-4 text-foreground/80 truncate max-w-[180px] whitespace-nowrap">{pair.name}</td>
                          <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap font-mono">{pair.base}</td>
                          <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap font-mono">{pair.quote}</td>
                          <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">
                            {pair.found ? formatUsdPrice(pair.symbol, pair.price) : '—'}
                          </td>
                          <td className={cn(
                            "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                            isPositive ? 'text-emerald-400' : 'text-rose-400'
                          )}>
                            {pair.found ? `${isPositive ? '+' : ''}${pair.changePct.toFixed(2)}%` : '—'}
                          </td>
                          <td className="py-3 px-4 text-center whitespace-nowrap">
                            <Button
                              size="sm"
                              onClick={() => handleAction(pair.symbol)}
                              className="inline-flex items-center gap-1 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 px-2 rounded-lg py-0.5 h-auto text-[9px] font-semibold transition-all hover:scale-105 cursor-pointer"
                            >
                              <Sparkles size={10} className="mr-1 inline" /> Analyze
                            </Button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}

        {screenerTab === 'commodities' && sectionVisible('table_commodities') && (
          <>
            <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
              <table className="w-full text-left border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                    <th className="py-3 px-4 whitespace-nowrap">Commodity</th>
                    <th className="py-3 px-4 whitespace-nowrap">Symbol</th>
                    <th className="py-3 px-4 hidden sm:table-cell whitespace-nowrap">Unit</th>
                    <th className="py-3 px-4 text-right whitespace-nowrap">Price (USD)</th>
                    <th className="py-3 px-4 text-right whitespace-nowrap">Change %</th>
                    <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                  </tr>
                </thead>
                <tbody>
                  {loadingCommodities ? (
                    <TableSkeleton cols={6} rows={8} />
                  ) : filteredCommodities.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                        No commodity data found.
                      </td>
                    </tr>
                  ) : (
                    filteredCommodities.map((c) => {
                      const isPositive = c.changePct >= 0;
                      return (
                        <tr
                          key={c.symbol}
                          className="hover:bg-accent/20 even:bg-accent/5 odd:bg-transparent transition-colors font-medium"
                        >
                          <td
                            onClick={(e) => handleSymbolClick(c.symbol, c.name, { price: c.price, changePercent: c.changePct }, e)}
                            title="Ctrl+click to open in new tab"
                            className="py-1 px-2 border border-border/30 font-bold text-foreground/80 hover:underline whitespace-nowrap cursor-pointer"
                          >
                            {c.name}
                          </td>
                          <td className="py-3 px-4 font-mono text-foreground/75 whitespace-nowrap">{c.symbol}</td>
                          <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap font-mono">{c.unit}</td>
                          <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">
                            {c.found ? formatUsdPrice(c.symbol, c.price) : '—'}
                          </td>
                          <td className={cn(
                            "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                            isPositive ? 'text-emerald-400' : 'text-rose-400'
                          )}>
                            {c.found ? `${isPositive ? '+' : ''}${c.changePct.toFixed(2)}%` : '—'}
                          </td>
                          <td className="py-3 px-4 text-center whitespace-nowrap">
                            <Button
                              size="sm"
                              onClick={() => handleAction(c.symbol)}
                              className="inline-flex items-center gap-1 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 px-2 rounded-lg py-0.5 h-auto text-[9px] font-semibold transition-all hover:scale-105 cursor-pointer"
                            >
                              <Sparkles size={10} className="mr-1 inline" /> Analyze
                            </Button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
    </>
  );
}
