'use client';

import React from 'react';
import {
  ArrowUp, ArrowDown, ArrowUpRight, ArrowDownRight, ArrowRight, Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { currencyCodeFor as currencyFor } from '@/lib/market-currency';
import { TableSkeleton } from './market-loaders';
import type { StockItem } from '@/lib/screener/data';

// ── Stocks & Crypto tables ──────────────────────────────────────────────────
// Extracted from market-overview.tsx (memory/simplicity standing goal): the
// two largest screener tables, including the crypto expansion row, ATH badge
// math, and both pagination footers.

interface StockCryptoTablesProps {
  screenerTab: string;
  sectionVisible: (key: 'table_stocks' | 'table_crypto') => boolean;
  stockSortField: keyof StockItem;
  stockSortOrder: 'asc' | 'desc';
  toggleStockSort: (field: keyof StockItem) => void;
  loadingTab: boolean;
  loadingApi: boolean;
  filteredStocks: StockItem[];
  expandedSymbol: string | null;
  setExpandedSymbol: React.Dispatch<React.SetStateAction<string | null>>;
  tableNav: {
    rowAttributes: (id: string) => Record<string, unknown>;
    isSelected: (id: string) => boolean;
  };
  handleSymbolClick: (symbol: string, name: string, extra?: Partial<StockItem>, e?: React.MouseEvent) => void;
  onAnalyzeTicker: (ticker: string, customContext?: string) => void;
  currentPage: number;
  setCurrentPage: React.Dispatch<React.SetStateAction<number>>;
  limit: number;
  setLimit: React.Dispatch<React.SetStateAction<number>>;
  totalStocks: number;
  userCountry: string;
  priceWithCurrency: (country: string, value: number) => string;
}

export function StockCryptoTables(props: StockCryptoTablesProps) {
  const {
    screenerTab, sectionVisible,
    stockSortField, stockSortOrder, toggleStockSort, loadingTab, loadingApi,
    filteredStocks, expandedSymbol, setExpandedSymbol, tableNav,
    handleSymbolClick, onAnalyzeTicker, currentPage, setCurrentPage,
    limit, setLimit, totalStocks, userCountry, priceWithCurrency,
  } = props;
  const handleAction = onAnalyzeTicker;

  return (
    <>
        {screenerTab === 'stocks' && sectionVisible('table_stocks') && (
          <>
            <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
              <table className="w-full text-left border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleStockSort('symbol')}>
                      Ticker {stockSortField === 'symbol' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('name')}>
                      Company {stockSortField === 'name' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden md:table-cell whitespace-nowrap" onClick={() => toggleStockSort('securityType')}>
                      Type {stockSortField === 'securityType' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden lg:table-cell whitespace-nowrap" onClick={() => toggleStockSort('industry')}>
                      Industry {stockSortField === 'industry' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden lg:table-cell whitespace-nowrap" onClick={() => toggleStockSort('country')}>
                      Country {stockSortField === 'country' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleStockSort('marketCap')}>
                      Market Cap {stockSortField === 'marketCap' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleStockSort('peRatio')}>
                      P/E {stockSortField === 'peRatio' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('price')}>
                      Price {stockSortField === 'price' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('changePercent')}>
                      Change {stockSortField === 'changePercent' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                  </tr>
                </thead>
                <tbody>
                  {(loadingTab || (loadingApi && filteredStocks.length === 0)) ? (
                    <TableSkeleton cols={10} rows={8} />
                  ) : filteredStocks.length === 0 ? (
                    <tr>
                      <td colSpan={10} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                        No matching stocks found.
                      </td>
                    </tr>
                  ) : (
                    filteredStocks.map((stock) => {
                      const isPositive = stock.changePercent >= 0;
                      return (
                        <tr
                          key={stock.symbol}
                          {...tableNav.rowAttributes(stock.symbol)}
                          onClick={(e) => handleSymbolClick(stock.symbol, stock.name, stock, e)}
                          className={cn("border-b border-white/5 hover:bg-white/[0.02] transition-colors cursor-pointer group", tableNav.isSelected(stock.symbol) && "bg-primary/10 ring-1 ring-inset ring-primary/40")}
                        >
                          <td
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSymbolClick(stock.symbol, stock.name, stock, e);
                            }}
                            title="Ctrl+click to open in new tab"
                            className="py-1 px-2 border border-border/30 font-bold font-mono text-foreground/80 hover:underline whitespace-nowrap"
                          >
                            {stock.symbol}
                          </td>
                          <td className="py-3 px-4 text-foreground/85 whitespace-nowrap">{stock.name}</td>
                          <td className="py-3 px-4 text-foreground/75 hidden md:table-cell whitespace-nowrap">
                            <span className="bg-primary/5 text-primary border border-primary/10 rounded-full px-2 py-0.5 text-[9px] font-bold">
                              {stock.securityType || 'N/A'}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-foreground/75 hidden lg:table-cell whitespace-nowrap">{stock.industry}</td>
                          <td className="py-3 px-4 text-foreground/75 hidden lg:table-cell whitespace-nowrap">{stock.country}</td>
                          <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden sm:table-cell whitespace-nowrap">{stock.marketCap}</td>
                          <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden sm:table-cell whitespace-nowrap">{stock.peRatio}</td>
                          <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">
                            {stock.priceMissing || !stock.price || stock.price <= 0 ? (
                              <span className="inline-flex items-center gap-1.5">
                                <span className="text-[9px] text-muted-foreground/60 animate-pulse">⠹ fetchingâ ¹</span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1.5">
                                {priceWithCurrency(stock.country || userCountry, stock.price)}
                                {stock.priceSource === 'csv' && (
                                  <span
                                    className="text-[8px] uppercase font-bold px-1 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                    title="Imported historical / API price"
                                  >
                                    CSV
                                  </span>
                                )}
                              </span>
                            )}
                          </td>
                          <td className={cn(
                            "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                            isPositive ? 'text-emerald-400' : 'text-rose-400'
                          )}>
                            {stock.priceMissing || !stock.price || stock.price <= 0 ? (
                              <span className="text-[9px] text-muted-foreground/60 animate-pulse">⠹</span>
                            ) : (
                              `${isPositive ? '+' : ''}${stock.changePercent.toFixed(2)}%`
                            )}
                          </td>
                          <td className="py-3 px-4 text-center whitespace-nowrap" onClick={e => e.stopPropagation()}>
                            <Button
                              size="sm"
                              onClick={() => handleAction(stock.symbol)}
                              className="inline-flex items-center gap-1 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 px-2 rounded-lg py-0.5 h-auto text-[9px] font-semibold transition-all hover:scale-105 cursor-pointer"
                            >
                              <Sparkles size={10} className="mr-1 inline animate-pulse" /> Analyze
                            </Button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center justify-between border-t border-border/10 pt-5 px-2 flex-wrap gap-4">
              <div className="flex items-center gap-4 text-[11px] text-muted-foreground font-medium">
                <div>
                  Showing <span className="font-semibold font-mono text-foreground">{totalStocks > 0 ? ((currentPage - 1) * limit) + 1 : 0}</span> to{' '}
                  <span className="font-semibold font-mono text-foreground">{Math.min(currentPage * limit, totalStocks)}</span> of{' '}
                  <span className="font-semibold font-mono text-foreground">{totalStocks}</span> stocks
                </div>
                <div className="flex items-center gap-2 glass-card-subtle px-3 py-1.5 rounded-xl border border-border/30">
                  <span className="text-[10px] uppercase font-bold text-muted-foreground/80">Show:</span>
                  <select
                    value={limit}
                    onChange={(e) => setLimit(Number(e.target.value))}
                    className="bg-transparent text-[11px] font-bold text-foreground font-mono focus:outline-none cursor-pointer"
                  >
                    <option value={20} className="bg-card text-foreground">20</option>
                    <option value={50} className="bg-card text-foreground">50</option>
                    <option value={100} className="bg-card text-foreground">100</option>
                  </select>
                </div>
              </div>
              {totalStocks > limit && (
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                    disabled={currentPage === 1}
                    className="px-3 py-1 text-[11px] font-semibold h-7 border-border bg-background/50 hover:bg-accent disabled:opacity-50"
                  >
                    Previous
                  </Button>
                  <div className="text-[11px] font-mono font-bold px-2.5 py-0.5 bg-accent/30 rounded-lg">
                    Page {currentPage} of {Math.ceil(totalStocks / limit)}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(prev => Math.min(prev + 1, Math.ceil(totalStocks / limit)))}
                    disabled={currentPage >= Math.ceil(totalStocks / limit)}
                    className="px-3 py-1 text-[11px] font-semibold h-7 border-border bg-background/50 hover:bg-accent disabled:opacity-50"
                  >
                    Next
                  </Button>
                </div>
              )}
            </div>
          </>
        )}

        {screenerTab === 'crypto' && sectionVisible('table_crypto') && (
          <>
            <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
              <table className="w-full text-left border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                    <th className="py-3 px-4 text-center whitespace-nowrap cursor-pointer hover:text-foreground transition-colors" onClick={() => toggleStockSort('rank')}>
                      Rank {stockSortField === 'rank' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleStockSort('symbol')}>
                      Symbol {stockSortField === 'symbol' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('name')}>
                      Asset Name {stockSortField === 'name' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('sector')}>
                      Category {stockSortField === 'sector' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('price')}>
                      Price {stockSortField === 'price' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('changePercent')}>
                      24H Change {stockSortField === 'changePercent' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('marketCap')}>
                      Market Cap {stockSortField === 'marketCap' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('volume')}>
                      24H Volume {stockSortField === 'volume' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('circulatingSupply')}>
                      Circulating Supply {stockSortField === 'circulatingSupply' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('maxSupply')}>
                      Max Supply {stockSortField === 'maxSupply' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-center cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleStockSort('ath')}>
                      ATH Distance {stockSortField === 'ath' && (stockSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                    </th>
                    <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                  </tr>
                </thead>
                <tbody>
                  {(loadingTab || (loadingApi && filteredStocks.length === 0)) ? (
                    <TableSkeleton cols={12} rows={8} />
                  ) : filteredStocks.length === 0 ? (
                    <tr>
                      <td colSpan={12} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                        No matching cryptocurrencies found.
                      </td>
                    </tr>
                  ) : (
                    (() => {
                      const maxMarketCapRaw = Math.max(...filteredStocks.map(s => s.marketCapRaw || 0), 1);
                      return filteredStocks.map((stock) => {
                        const isPositive = stock.changePercent >= 0;
                        const formatCryptoPrice = (val: number) => {
                          if (val === 0) return '0.00';
                          if (val < 0.0001) return val.toFixed(8);
                          if (val < 0.01) return val.toFixed(6);
                          if (val < 1) return val.toFixed(4);
                          if (val >= 1000) return val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                          return val.toFixed(2);
                        };
                        
                        const circPercent = stock.maxSupplyRaw && stock.maxSupplyRaw > 0
                          ? ((stock.circulatingSupplyRaw || 0) / stock.maxSupplyRaw * 100).toFixed(1) + '%'
                          : '100.0%';

                        const athDist = stock.athChangePercent || 0;
                        let athBadgeText = 'Mid Range';
                        let athColorClass = 'text-amber-400 bg-amber-500/10 border-amber-500/25';
                        let AthIcon = ArrowRight;
                        if (athDist >= -10) {
                          athBadgeText = 'Near ATH';
                          athColorClass = 'text-emerald-400 bg-emerald-500/10 border-emerald-500/25';
                          AthIcon = ArrowUpRight;
                        } else if (athDist <= -50) {
                          athBadgeText = 'Deep Discount';
                          athColorClass = 'text-rose-400 bg-rose-500/10 border-rose-500/25';
                          AthIcon = ArrowDownRight;
                        }

                        const isExpanded = expandedSymbol === stock.symbol;

                        return (
                          <React.Fragment key={stock.symbol}>
                            <tr 
                              {...tableNav.rowAttributes(stock.symbol)}
                              onClick={() => setExpandedSymbol(isExpanded ? null : stock.symbol)}
                              className={cn("border-b border-white/5 hover:bg-white/[0.02] transition-colors cursor-pointer group", tableNav.isSelected(stock.symbol) && "bg-primary/10 ring-1 ring-inset ring-primary/40")}
                            >
                              <td className="py-3 px-4 text-muted-foreground text-center font-mono">
                                #{stock.rank || 999}
                              </td>
                              <td
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleSymbolClick(stock.symbol, stock.name, stock, e);
                                }}
                                title="Ctrl+click to open in new tab"
                                className="py-2 px-2 border border-border/30 font-bold font-mono text-foreground/80 hover:underline whitespace-nowrap"
                              >
                                {stock.symbol}
                              </td>
                              <td
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleSymbolClick(stock.symbol, stock.name, stock, e);
                                }}
                                title="Ctrl+click to open in new tab"
                                className="py-2 px-2 border border-border/30 text-foreground/85 truncate max-w-[130px] whitespace-nowrap hover:underline"
                              >
                                {stock.name}
                              </td>
                              <td className="py-3 px-4 text-foreground/75 whitespace-nowrap">
                                <span className="bg-primary/5 text-primary border border-primary/10 rounded-full px-2 py-0.5 text-[9px] font-bold">
                                  {stock.sector}
                                </span>
                              </td>
                              <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">
                                {stock.priceMissing || !stock.price || stock.price <= 0 ? (
                                  <span className="inline-flex items-center gap-1.5">
                                    <span className="text-[9px] text-muted-foreground/60 animate-pulse">⠹ fetchingâ ¹</span>
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1.5">
                                    {currencyFor('CRYPTO')}{formatCryptoPrice(stock.price)}
                                    {stock.priceSource === 'csv' && (
                                      <span
                                        className="text-[8px] uppercase font-bold px-1 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                        title="Imported historical / API price"
                                      >
                                        CSV
                                      </span>
                                    )}
                                  </span>
                                )}
                              </td>
                              <td className={cn(
                                "py-2 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                                isPositive ? 'text-emerald-400' : 'text-rose-400'
                              )}>
                                {stock.priceMissing || !stock.price || stock.price <= 0 ? (
                                  <span className="text-[9px] text-muted-foreground/60 animate-pulse">⠹</span>
                                ) : (
                                  `${isPositive ? '+' : ''}${stock.changePercent.toFixed(2)}%`
                                )}
                              </td>
                              <td className="py-3 px-4 font-mono text-foreground/75 whitespace-nowrap">
                                <div className="flex flex-col gap-1 w-24 ml-auto">
                                  <div className="text-right">{stock.marketCap}</div>
                                  <div className="w-full h-1 bg-accent/40 rounded-full overflow-hidden">
                                    <div 
                                      className="h-full bg-primary rounded-full" 
                                      style={{ width: `${Math.min(100, ((stock.marketCapRaw || 0) / maxMarketCapRaw) * 100)}%` }} 
                                    />
                                  </div>
                                </div>
                              </td>
                              <td className="py-3 px-4 text-right font-mono text-foreground/75 whitespace-nowrap">
                                {stock.volume || 'N/A'}
                              </td>
                              <td className="py-3 px-4 text-right font-mono text-foreground/75 whitespace-nowrap">
                                {stock.circulatingSupply || 'N/A'}
                              </td>
                              <td className="py-3 px-4 text-right font-mono text-foreground/75 whitespace-nowrap">
                                {stock.maxSupply || 'N/A'}
                              </td>
                              <td className="py-3 px-4 text-center whitespace-nowrap">
                                <span className={cn("inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[9px] font-bold border", athColorClass)}>
                                  <AthIcon className="w-3 h-3 text-inherit" /> {athBadgeText} ({athDist.toFixed(1)}%)
                                </span>
                              </td>
                              <td className="py-3 px-4 text-center whitespace-nowrap" onClick={e => e.stopPropagation()}>
                                <Button
                                  size="sm"
                                  onClick={() => {
                                    const customContext = `${stock.symbol} currently trades ${Math.abs(stock.athChangePercent || 0).toFixed(1)}% below its all-time high while maintaining a ${stock.marketCap} market capitalization and ${stock.volumeRaw ? '$' + (stock.volumeRaw / 1e6).toFixed(1) + 'M' : 'N/A'} daily volume. Circulating supply stands at ${circPercent} of maximum issuance, suggesting most dilution has already occurred.`;
                                    onAnalyzeTicker(stock.symbol, customContext);
                                  }}
                                  className="inline-flex items-center gap-1 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 px-2 rounded-lg py-0.5 h-auto text-[9px] font-semibold transition-all hover:scale-105 cursor-pointer"
                                >
                                  <Sparkles size={10} className="mr-1 inline animate-pulse" /> Analyze
                                </Button>
                              </td>
                            </tr>

                            {isExpanded && (
                              <tr className="bg-accent/10">
                                <td colSpan={12} className="p-4 ">
                                  <div className="flex flex-wrap items-center gap-6 justify-center md:justify-start">
                                    <div className="flex flex-col gap-1 glass-card-subtle border border-border/20 rounded-xl p-3 min-w-[150px]">
                                      <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-wider font-mono">Liquidity</span>
                                      <span className="text-xs font-mono font-bold text-foreground">24H Volume:</span>
                                      <span className="text-sm font-mono font-black text-primary">{stock.volume || 'N/A'}</span>
                                    </div>
                                    <div className="flex flex-col gap-1 glass-card-subtle border border-border/20 rounded-xl p-3 min-w-[180px]">
                                      <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-wider font-mono">Supply Status</span>
                                      <span className="text-xs font-mono font-bold text-foreground">Circulating / Max:</span>
                                      <span className="text-xs font-mono text-foreground">{stock.circulatingSupply || 'N/A'} / {stock.maxSupply || 'N/A'}</span>
                                    </div>
                                    <div className="flex flex-col gap-1 glass-card-subtle border border-border/20 rounded-xl p-3 min-w-[150px]">
                                      <span className="text-[9px] uppercase font-bold text-muted-foreground tracking-wider font-mono">Scarcity Indicator</span>
                                      <span className="text-xs font-mono font-bold text-foreground">Supply Mined:</span>
                                      <span className="text-sm font-mono font-black text-emerald-400">{circPercent} mined</span>
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      });
                    })()
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center justify-between border-t border-border/10 pt-5 px-2 flex-wrap gap-4">
              <div className="flex items-center gap-4 text-[11px] text-muted-foreground font-medium">
                <div>
                  Showing <span className="font-semibold font-mono text-foreground">{totalStocks > 0 ? ((currentPage - 1) * limit) + 1 : 0}</span> to{' '}
                  <span className="font-semibold font-mono text-foreground">{Math.min(currentPage * limit, totalStocks)}</span> of{' '}
                  <span className="font-semibold font-mono text-foreground">{totalStocks}</span> tokens
                </div>
                <div className="flex items-center gap-2 glass-card-subtle px-3 py-1.5 rounded-xl border border-border/30">
                  <span className="text-[10px] uppercase font-bold text-muted-foreground/80">Show:</span>
                  <select
                    value={limit}
                    onChange={(e) => setLimit(Number(e.target.value))}
                    className="bg-transparent text-[11px] font-bold text-foreground font-mono focus:outline-none cursor-pointer"
                  >
                    <option value={20} className="bg-card text-foreground">20</option>
                    <option value={50} className="bg-card text-foreground">50</option>
                    <option value={100} className="bg-card text-foreground">100</option>
                  </select>
                </div>
              </div>
              {totalStocks > limit && (
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                    disabled={currentPage === 1}
                    className="px-3 py-1 text-[11px] font-semibold h-7 border-border bg-background/50 hover:bg-accent disabled:opacity-50"
                  >
                    Previous
                  </Button>
                  <div className="text-[11px] font-mono font-bold px-2.5 py-0.5 bg-accent/30 rounded-lg">
                    Page {currentPage} of {Math.ceil(totalStocks / limit)}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage(prev => Math.min(prev + 1, Math.ceil(totalStocks / limit)))}
                    disabled={currentPage >= Math.ceil(totalStocks / limit)}
                    className="px-3 py-1 text-[11px] font-semibold h-7 border-border bg-background/50 hover:bg-accent disabled:opacity-50"
                  >
                    Next
                  </Button>
                </div>
              )}
            </div>
          </>
        )}
    </>
  );
}
