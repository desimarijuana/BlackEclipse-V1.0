'use client';

import React from 'react';
import { ArrowUp, ArrowDown, Info, Sparkles, Star } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { TableSkeleton } from './market-loaders';
import type { FundItem, ETFItem, BlueChipItem } from '@/lib/screener/data';

// ── ETF / Funds / Dividend tables ───────────────────────────────────────────
// Extracted from market-overview.tsx (memory/simplicity standing goal): the
// remaining three screener tables plus their DEMO banners.

interface FundEtfTablesProps {
  screenerTab: string;
  sectionVisible: (key: 'table_etfs' | 'table_funds' | 'table_dividend') => boolean;
  handleSymbolClick: (symbol: string, name: string, extra?: Record<string, unknown>, e?: React.MouseEvent) => void;
  onAnalyzeTicker: (ticker: string) => void;
  loadingTab: boolean;
  userCountry: string;
  priceWithCurrency: (country: string, value: number) => string;
  // ETFs
  apiEtfs: ETFItem[];
  etfSortField: keyof ETFItem;
  etfSortOrder: 'asc' | 'desc';
  toggleEtfSort: (field: keyof ETFItem) => void;
  filteredETFs: ETFItem[];
  etfTotal: number;
  etfPage: number;
  etfLimit: number;
  setEtfPage: React.Dispatch<React.SetStateAction<number>>;
  setEtfLimit: React.Dispatch<React.SetStateAction<number>>;
  // Funds
  apiFunds: FundItem[];
  fundSortField: keyof FundItem;
  fundSortOrder: 'asc' | 'desc';
  toggleFundSort: (field: keyof FundItem) => void;
  filteredFunds: FundItem[];
  fundTotal: number;
  fundPage: number;
  fundLimit: number;
  setFundPage: React.Dispatch<React.SetStateAction<number>>;
  setFundLimit: React.Dispatch<React.SetStateAction<number>>;
  // Dividends
  dividendSortField: keyof BlueChipItem;
  dividendSortOrder: 'asc' | 'desc';
  toggleDividendSort: (field: keyof BlueChipItem) => void;
  filteredDividendStocks: BlueChipItem[];
}

export function FundEtfTables(props: FundEtfTablesProps) {
  const {
    screenerTab, sectionVisible, handleSymbolClick, onAnalyzeTicker, loadingTab,
    userCountry, priceWithCurrency,
    apiEtfs, etfSortField, etfSortOrder, toggleEtfSort, filteredETFs,
    etfTotal, etfPage, etfLimit, setEtfPage, setEtfLimit,
    apiFunds, fundSortField, fundSortOrder, toggleFundSort, filteredFunds,
    fundTotal, fundPage, fundLimit, setFundPage, setFundLimit,
    dividendSortField, dividendSortOrder, toggleDividendSort, filteredDividendStocks,
  } = props;
  const handleAction = onAnalyzeTicker;

  // Shared pagination footer for the server-paginated ETF/Fund directories.
  const pager = (
    total: number, page: number, limit: number,
    setPage: React.Dispatch<React.SetStateAction<number>>,
    setLimitFn: React.Dispatch<React.SetStateAction<number>>,
    noun: string,
  ) => {
    const pages = Math.max(1, Math.ceil(total / limit));
    return (
      <div className="flex items-center justify-between border-t border-border/10 pt-5 px-2 flex-wrap gap-4">
        <div className="flex items-center gap-4 text-[11px] text-muted-foreground font-medium">
          <div>
            Showing <span className="font-semibold font-mono text-foreground">{total > 0 ? ((page - 1) * limit) + 1 : 0}</span> to{' '}
            <span className="font-semibold font-mono text-foreground">{Math.min(page * limit, total)}</span> of{' '}
            <span className="font-semibold font-mono text-foreground">{total}</span> {noun}
          </div>
          <div className="flex items-center gap-2 glass-card-subtle px-3 py-1.5 rounded-xl border border-border/30">
            <span className="text-[10px] uppercase font-bold text-muted-foreground/80">Show:</span>
            <select
              value={limit}
              onChange={(e) => setLimitFn(Number(e.target.value))}
              className="bg-transparent text-[11px] font-bold text-foreground font-mono focus:outline-none cursor-pointer"
            >
              <option value={50} className="bg-card text-foreground">50</option>
              <option value={100} className="bg-card text-foreground">100</option>
            </select>
          </div>
        </div>
        {total > limit && (
          <div className="flex items-center gap-2">
            <Button
              variant="outline" size="sm"
              onClick={() => setPage((p) => Math.max(p - 1, 1))}
              disabled={page === 1}
              className="px-3 py-1 text-[11px] font-semibold h-7 border-border bg-background/50 hover:bg-accent disabled:opacity-50"
            >
              Previous
            </Button>
            <div className="text-[11px] font-mono font-bold px-2.5 py-0.5 bg-accent/30 rounded-lg">
              Page {page} of {pages}
            </div>
            <Button
              variant="outline" size="sm"
              onClick={() => setPage((p) => Math.min(p + 1, pages))}
              disabled={page >= pages}
              className="px-3 py-1 text-[11px] font-semibold h-7 border-border bg-background/50 hover:bg-accent disabled:opacity-50"
            >
              Next
            </Button>
          </div>
        )}
      </div>
    );
  };

  return (
    <>
        {screenerTab === 'etfs' && sectionVisible('table_etfs') && (
          <div>
            {apiEtfs.length === 0 && (
              <div className="glass-card-subtle border border-amber-500/10 rounded-2xl p-3 flex items-center gap-3 text-amber-400 mb-3">
                <Info className="w-4 h-4 shrink-0" />
                <span className="text-xs font-semibold flex-1">SIMULATED DATA — no ETF universe loaded in JDDS; showing a curated demo list, not live prices.</span>
                <span className="text-[9px] bg-amber-500/15 px-2 py-0.5 rounded font-mono font-bold">DEMO</span>
              </div>
            )}
          <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleEtfSort('symbol')}>
                    Symbol {etfSortField === 'symbol' && (etfSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleEtfSort('name')}>
                    ETF Name {etfSortField === 'name' && (etfSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleEtfSort('category')}>
                    Category {etfSortField === 'category' && (etfSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleEtfSort('price')}>
                    Price {etfSortField === 'price' && (etfSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleEtfSort('changePercent')}>
                    Change % {etfSortField === 'changePercent' && (etfSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right font-mono hidden md:table-cell whitespace-nowrap">Volume</th>
                  <th className="py-3 px-4 text-right font-mono hidden md:table-cell whitespace-nowrap">AUM</th>
                  <th className="py-3 px-4 text-right font-mono hidden lg:table-cell whitespace-nowrap">Expense Ratio</th>
                  <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                </tr>
              </thead>
              <tbody>
                {loadingTab ? (
                  <TableSkeleton cols={9} rows={6} />
                ) : filteredETFs.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                      No matching ETFs found.
                    </td>
                  </tr>
                ) : (
                  filteredETFs.map((etf) => {
                    const isPositive = etf.changePercent >= 0;
                    return (
                      <tr 
                        key={etf.symbol}
                        className="hover:bg-accent/20 even:bg-accent/5 odd:bg-transparent transition-colors font-medium"
                      >
                        <td
                          onClick={(e) => handleSymbolClick(etf.symbol, etf.name, { marketCap: etf.aum, price: etf.price, changePercent: etf.changePercent, volume: etf.volume }, e)}
                          title="Ctrl+click to open in new tab"
                          className="py-1 px-2 border border-border/30 font-bold font-mono text-foreground/80 hover:underline whitespace-nowrap cursor-pointer"
                        >
                          {etf.symbol}
                        </td>
                        <td className="py-3 px-4 text-foreground/80 truncate max-w-[130px] whitespace-nowrap">{etf.name}</td>
                        <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap">{etf.category}</td>
                        <td className="py-3 px-4 text-right font-mono font-bold text-foreground whitespace-nowrap">{priceWithCurrency(userCountry, etf.price)}</td>
                        <td className={cn(
                          "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                          isPositive ? 'text-emerald-400' : 'text-rose-400'
                        )}>
                          {isPositive ? '+' : ''}{etf.changePercent.toFixed(2)}%
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden md:table-cell whitespace-nowrap">{etf.volume}</td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden md:table-cell whitespace-nowrap">{etf.aum}</td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden lg:table-cell whitespace-nowrap">{etf.expenseRatio}</td>
                        <td className="py-3 px-4 text-center whitespace-nowrap">
                          <Button
                            size="sm"
                            onClick={() => handleAction(etf.symbol)}
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
          {pager(etfTotal, etfPage, etfLimit, setEtfPage, setEtfLimit, 'ETFs')}
          </div>
        )}

        {screenerTab === 'funds' && sectionVisible('table_funds') && (
          <div>
            {apiFunds.length === 0 && (
              <div className="glass-card-subtle border border-amber-500/10 rounded-2xl p-3 flex items-center gap-3 text-amber-400 mb-3">
                <Info className="w-4 h-4 shrink-0" />
                <span className="text-xs font-semibold flex-1">SIMULATED DATA — no fund universe loaded in JDDS; showing a curated demo list, not live NAVs.</span>
                <span className="text-[9px] bg-amber-500/15 px-2 py-0.5 rounded font-mono font-bold">DEMO</span>
              </div>
            )}
          <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleFundSort('symbol')}>
                    Symbol {fundSortField === 'symbol' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleFundSort('name')}>
                    Fund Name {fundSortField === 'name' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleFundSort('category')}>
                    Category {fundSortField === 'category' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleFundSort('nav')}>
                    NAV {fundSortField === 'nav' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleFundSort('changePercent')}>
                    1D Change % {fundSortField === 'changePercent' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors hidden md:table-cell whitespace-nowrap" onClick={() => toggleFundSort('ytdReturn')}>
                    YTD Return % {fundSortField === 'ytdReturn' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors hidden lg:table-cell whitespace-nowrap" onClick={() => toggleFundSort('expenseRatio')}>
                    Expense Ratio {fundSortField === 'expenseRatio' && (fundSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-center hidden md:table-cell whitespace-nowrap">Morningstar</th>
                  <th className="py-3 px-4 text-right font-mono hidden lg:table-cell whitespace-nowrap">AUM</th>
                  <th className="py-3 px-4 text-center whitespace-nowrap">AI Brief</th>
                </tr>
              </thead>
              <tbody>
                {loadingTab ? (
                  <TableSkeleton cols={10} rows={6} />
                ) : filteredFunds.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                      No matching funds found.
                    </td>
                  </tr>
                ) : (
                  filteredFunds.map((fund) => {
                    const isPositive = fund.changePercent >= 0;
                    return (
                      <tr 
                        key={fund.symbol}
                        className="hover:bg-accent/20 even:bg-accent/5 odd:bg-transparent transition-colors font-medium"
                      >
                        <td
                          onClick={(e) => handleSymbolClick(fund.symbol, fund.name, { marketCap: fund.aum, price: fund.nav, changePercent: fund.changePercent }, e)}
                          title="Ctrl+click to open in new tab"
                          className="py-1 px-2 border border-border/30 font-bold font-mono text-foreground/80 hover:underline whitespace-nowrap cursor-pointer"
                        >
                          {fund.symbol}
                        </td>
                        <td className="py-3 px-4 text-foreground/80 truncate max-w-[130px] whitespace-nowrap">{fund.name}</td>
                        <td className="py-3 px-4 text-foreground/75 hidden sm:table-cell whitespace-nowrap">{fund.category}</td>
                        <td className="py-3 px-4 text-right font-mono font-semibold text-foreground whitespace-nowrap">{priceWithCurrency(userCountry, fund.nav)}</td>
                        <td className={cn(
                          "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                          isPositive ? 'text-emerald-400' : 'text-rose-400'
                        )}>
                          {isPositive ? '+' : ''}{fund.changePercent.toFixed(2)}%
                        </td>
                        <td className="py-3 px-4 text-right font-mono hidden md:table-cell whitespace-nowrap">
                          {fund.ytdReturn == null
                            ? <span className="text-muted-foreground/60">N/A</span>
                            : <span className="text-emerald-400 font-semibold">{fund.ytdReturn.toFixed(2)}%</span>}
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden lg:table-cell whitespace-nowrap">
                          {fund.expenseRatio == null ? 'N/A' : `${fund.expenseRatio}%`}
                        </td>
                        <td className="py-3 px-4 hidden md:table-cell whitespace-nowrap">
                          {fund.rating == null ? (
                            <div className="text-center text-[10px] text-muted-foreground/60 font-mono">N/A</div>
                          ) : (
                            <div className="flex items-center justify-center gap-0.5 text-amber-400">
                              {Array.from({ length: 5 }).map((_, idx) => (
                                <Star 
                                  key={idx} 
                                  size={11} 
                                  fill={idx < (fund.rating ?? 0) ? 'currentColor' : 'none'}
                                  className={idx < (fund.rating ?? 0) ? 'text-amber-400' : 'text-muted-foreground/30'}
                                />
                              ))}
                            </div>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden lg:table-cell whitespace-nowrap">{fund.aum}</td>
                        <td className="py-3 px-4 text-center whitespace-nowrap">
                          <Button
                            size="sm"
                            onClick={() => handleAction(fund.symbol)}
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
          {pager(fundTotal, fundPage, fundLimit, setFundPage, setFundLimit, 'funds')}
          </div>
        )}

        {screenerTab === 'dividend_stocks' && sectionVisible('table_dividend') && (
          <div>
            {/* Dividend stocks are a curated static list — never live prices. */}
            <div className="glass-card-subtle border border-amber-500/10 rounded-2xl p-3 flex items-center gap-3 text-amber-400 mb-3">
              <Info className="w-4 h-4 shrink-0" />
              <span className="text-xs font-semibold flex-1">SIMULATED DATA — dividend stock rows are a curated demo list, not live market prices.</span>
              <span className="text-[9px] bg-amber-500/15 px-2 py-0.5 rounded font-mono font-bold">DEMO</span>
            </div>
            <div className="w-full overflow-x-auto custom-scrollbar glass-card-subtle border border-white/10 dark:border-white/5 rounded-2xl shadow-md">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px] uppercase tracking-wider font-mono font-semibold bg-white/[0.01]">
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground font-mono transition-colors whitespace-nowrap" onClick={() => toggleDividendSort('symbol')}>
                    Symbol {dividendSortField === 'symbol' && (dividendSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleDividendSort('name')}>
                    Company Name {dividendSortField === 'name' && (dividendSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors hidden sm:table-cell whitespace-nowrap" onClick={() => toggleDividendSort('dividendYield')}>
                    Dividend Yield {dividendSortField === 'dividendYield' && (dividendSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleDividendSort('price')}>
                    Price {dividendSortField === 'price' && (dividendSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right cursor-pointer hover:text-foreground transition-colors whitespace-nowrap" onClick={() => toggleDividendSort('changePercent')}>
                    Change % {dividendSortField === 'changePercent' && (dividendSortOrder === 'asc' ? <ArrowUp className="inline w-2.5 h-2.5" /> : <ArrowDown className="inline w-2.5 h-2.5" />)}
                  </th>
                  <th className="py-3 px-4 text-right font-mono hidden md:table-cell whitespace-nowrap">Volume</th>
                  <th className="py-3 px-4 text-right font-mono hidden md:table-cell whitespace-nowrap">Market Cap</th>
                  <th className="py-3 px-4 text-right font-mono hidden sm:table-cell whitespace-nowrap">P/E Ratio</th>
                  <th className="py-3 px-4 text-center font-mono hidden lg:table-cell whitespace-nowrap">Safety Rating</th>
                  <th className="py-3 px-4 text-center whitespace-nowrap">AI Analyst</th>
                </tr>
              </thead>
              <tbody>
                {loadingTab ? (
                  <TableSkeleton cols={10} rows={6} />
                ) : filteredDividendStocks.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="p-6 text-center text-muted-foreground font-medium whitespace-nowrap ">
                      No matching Dividend Stocks found.
                    </td>
                  </tr>
                ) : (
                  filteredDividendStocks.map((dividendStock) => {
                    const isPositive = dividendStock.changePercent >= 0;
                    return (
                      <tr 
                        key={dividendStock.symbol}
                        className="hover:bg-accent/20 even:bg-accent/5 odd:bg-transparent transition-colors font-medium"
                      >
                        <td
                          onClick={(e) => handleSymbolClick(dividendStock.symbol, dividendStock.name, { peRatio: dividendStock.peRatio, marketCap: dividendStock.marketCap, dividendYield: dividendStock.dividendYield, price: dividendStock.price, changePercent: dividendStock.changePercent, volume: dividendStock.volume }, e)}
                          title="Ctrl+click to open in new tab"
                          className="py-1 px-2 border border-border/30 font-bold font-mono text-foreground/80 hover:underline whitespace-nowrap cursor-pointer"
                        >
                          {dividendStock.symbol}
                        </td>
                        <td className="py-3 px-4 text-foreground/80 truncate max-w-[130px] whitespace-nowrap">{dividendStock.name}</td>
                        <td className="py-3 px-4 text-emerald-400 font-bold font-mono hidden sm:table-cell whitespace-nowrap">{dividendStock.dividendYield}</td>
                        <td className="py-3 px-4 text-right font-mono font-semibold text-foreground whitespace-nowrap">{priceWithCurrency(userCountry, dividendStock.price)}</td>
                        <td className={cn(
                          "py-1 px-2 border border-border/30 text-right font-mono font-bold whitespace-nowrap",
                          isPositive ? 'text-emerald-400' : 'text-rose-400'
                        )}>
                          {isPositive ? '+' : ''}{dividendStock.changePercent.toFixed(2)}%
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden md:table-cell whitespace-nowrap">{dividendStock.volume}</td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden md:table-cell whitespace-nowrap">{dividendStock.marketCap}</td>
                        <td className="py-3 px-4 text-right font-mono text-foreground/75 hidden sm:table-cell whitespace-nowrap">{dividendStock.peRatio}</td>
                        <td className="py-3 px-4 text-center whitespace-nowrap hidden lg:table-cell text-emerald-400 font-bold font-mono">
                          {dividendStock.safetyRating}
                        </td>
                        <td className="py-3 px-4 text-center whitespace-nowrap">
                          <Button
                            size="sm"
                            onClick={() => handleAction(dividendStock.symbol)}
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
          </div>
        )}
    </>
  );
}
