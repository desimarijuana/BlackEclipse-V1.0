'use client';

import React from 'react';
import { createPortal } from 'react-dom';
import { Globe, GripVertical, Sliders, ArrowUpRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { TableLoading } from './market-loaders';
import { priceWithCurrency, formatUsdPrice, fmtCap } from '@/lib/screener/format';
import {
  GM_COLUMN_ORDER, GM_COLUMN_LABELS, GM_DEFAULTS, reorderList,
  type GmLayout, type GmConfig, type OverviewGroup,
} from './use-global-markets';
import type { ForexPair } from './use-market-tabs';
import type { CommodityItem } from './use-market-tabs';
import type { StockItem } from '@/lib/screener/data';

// ── Global Markets overview ─────────────────────────────────────────────────
// Extracted from market-overview.tsx (memory/simplicity standing goal). This
// is the biggest single block of the screener: the persisted-preferences
// config panel, the per-market cards, drag-and-drop reordering, and the
// floating drag ghost. It renders only what the caller passes in.

interface GlobalMarketsOverviewProps {
  gmConfig: GmConfig;
  gmConfigOpen: boolean;
  setGmConfigOpen: React.Dispatch<React.SetStateAction<boolean>>;
  gmSearch: string;
  setGmSearch: React.Dispatch<React.SetStateAction<string>>;
  applyGmConfig: (patch: Partial<GmConfig>) => void;
  moveGmColumn: (key: keyof GmConfig['columns'], dir: -1 | 1) => void;
  gmSelectedRow: { marketId: string; symbol: string } | null;
  setGmSelectedRow: React.Dispatch<React.SetStateAction<{ marketId: string; symbol: string } | null>>;
  gmDragId: string | null;
  gmDragWidth: number;
  gmFloatRef: React.RefObject<HTMLDivElement | null>;
  beginGmDrag: (clientX: number, clientY: number, button: number, anchor: HTMLElement) => void;
  globalOverview: OverviewGroup[];
  loadingGlobalMarkets: boolean;
  sectionVisible: (key: 'table_forex' | 'table_commodities') => boolean;
  toggleSection: (key: 'table_forex' | 'table_commodities') => void;
  handleSymbolClick: (symbol: string, name: string, extra?: Partial<StockItem>, e?: React.MouseEvent) => void;
  handleMarketSelect: (market: string) => void;
  handleTabChange: (tab: 'forex' | 'commodities') => void;
  filteredForex: ForexPair[];
  loadingForex: boolean;
  commodities: CommodityItem[];
  loadingCommodities: boolean;
}

export function GlobalMarketsOverview(props: GlobalMarketsOverviewProps) {
  const {
    gmConfig, gmConfigOpen, setGmConfigOpen, gmSearch, setGmSearch, applyGmConfig, moveGmColumn,
    gmSelectedRow, setGmSelectedRow, gmDragId, gmDragWidth, gmFloatRef,
    beginGmDrag, globalOverview, loadingGlobalMarkets,
    sectionVisible, toggleSection, handleSymbolClick, handleMarketSelect,
    handleTabChange, filteredForex, loadingForex, commodities,
    loadingCommodities,
  } = props;

          const col = gmConfig.columns;
          const gridClass = gmConfig.layout === 'focus'
            ? 'grid-cols-1'
            : gmConfig.layout === 'comfortable'
              ? 'grid-cols-1 lg:grid-cols-2'
              : 'grid-cols-1 lg:grid-cols-2 xl:grid-cols-3';
          // Per-market stock processing: movers filter ? sort ? page size.
          const processStocks = (stocks: OverviewGroup['stocks']) => {
            let list = [...stocks];
            if (gmConfig.movers === 'gainers') list = list.filter(s => s.changePct > 0);
            else if (gmConfig.movers === 'losers') list = list.filter(s => s.changePct < 0);
            switch (gmConfig.sortBy) {
              case 'change': list.sort((a, b) => b.changePct - a.changePct); break;
              case 'price': list.sort((a, b) => b.price - a.price); break;
              case 'name': list.sort((a, b) => a.name.localeCompare(b.name)); break;
              default: list.sort((a, b) => (b.marketCap || 0) - (a.marketCap || 0));
            }
            return list.slice(0, gmConfig.rows);
          };
          const q = gmSearch.trim().toLowerCase();
          const matchesSearch = (g: OverviewGroup) =>
            !q
            || g.id.toLowerCase().includes(q)
            || (g.name ?? '').toLowerCase().includes(q)
            || g.country.toLowerCase().includes(q)
            || g.exchange.toLowerCase().includes(q)
            || g.stocks.some(s => s.symbol.toLowerCase().includes(q) || s.name.toLowerCase().includes(q));
          const groups: OverviewGroup[] = (gmConfig.countries
            ? globalOverview.filter(g => gmConfig.countries!.includes(g.id))
            : [...globalOverview]
          ).filter(matchesSearch);
          // Default card order for the ordering buttons in the config panel
          // (countries in load order, then the special cards).
          const cardIdBaseOrder: string[] = [
            ...globalOverview.map((g) => g.id),
            'FOREX',
            'COMMODITIES',
          ];
          if (gmConfig.groupOrder === 'movers') {
            const avgChange = (g: OverviewGroup) => {
              const rows = processStocks(g.stocks);
              return rows.length ? rows.reduce((acc, s) => acc + s.changePct, 0) / rows.length : -Infinity;
            };
            groups.sort((a, b) => avgChange(b) - avgChange(a));
          }
          // Manual drag order wins over the automatic group ordering. The
          // saved order spans ALL cards — country ids plus the special FOREX
          // and COMMODITIES cards — so dragging any card persists. Hidden
          // cards (Forex/Commodities via section toggles) are dropped here.
          const cardOrder: string[] = [
            ...groups.map((g) => g.id),
            ...(sectionVisible('table_forex') ? ['FOREX'] : []),
            ...(sectionVisible('table_commodities') ? ['COMMODITIES'] : []),
          ];
          if (gmConfig.order && gmConfig.order.length > 0) {
            const idx = (id: string) => {
              const i = gmConfig.order!.indexOf(id);
              return i === -1 ? Number.MAX_SAFE_INTEGER : i;
            };
            cardOrder.sort((a, b) => idx(a) - idx(b));
          }
          const anyColumn = col.ticker || col.name || col.price || col.change || col.cap;
          const rowPad = gmConfig.dense ? 'py-1' : 'py-2';
          return (
            <div className="w-full">
              <div className="flex items-center justify-between gap-3 mb-3 px-1">
                <span className="flex items-center gap-2 min-w-0">
                  <Globe className="text-primary w-4 h-4 shrink-0" />
                  <span className="text-xs font-bold text-foreground uppercase tracking-wider font-mono">Global Markets Overview</span>
                  <span className="text-[10px] text-muted-foreground font-mono hidden md:inline">
                    {groups.length} markets · top {gmConfig.rows} by{' '}
                    {gmConfig.sortBy === 'change' ? 'change' : gmConfig.sortBy === 'price' ? 'price' : gmConfig.sortBy === 'name' ? 'name' : 'market cap'}
                    {gmConfig.movers === 'gainers' ? ' (gainers)' : gmConfig.movers === 'losers' ? ' (losers)' : ''} · local currency
                  </span>
                </span>
                <button
                  onClick={() => setGmConfigOpen(o => !o)}
                  className={`flex items-center gap-1.5 text-xs font-bold tracking-wider border rounded-lg px-3.5 py-2 transition-all cursor-pointer shrink-0 ${
                    gmConfigOpen
                      ? 'text-primary bg-primary/10 border-primary/40'
                      : 'text-muted-foreground hover:text-primary bg-accent/40 hover:bg-accent/70 border-border/40'
                  }`}
                  title="Customize this overview"
                >
                  <Sliders size={14} /> Customize
                </button>
              </div>

              {/* Inline config panel — expands in flow, pushes content down */}
              {gmConfigOpen && (
                <div className="mb-3 p-3 sm:p-4 rounded-xl glass-card border border-white/10 dark:border-white/5 shadow-lg w-full max-w-full overflow-hidden animate-fade-in-up space-y-4">
                  <div className="flex items-center justify-between">
                    <p className="text-[10px] font-bold text-foreground uppercase tracking-wider">Overview Preferences</p>
                    <button
                      onClick={() => applyGmConfig(GM_DEFAULTS)}
                      className="text-[10px] font-bold text-muted-foreground hover:text-rose-400 uppercase tracking-wider cursor-pointer transition-colors"
                    >
                      Reset to defaults
                    </button>
                  </div>
                  {/* Layout */}
                  <div>
                    <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-1.5">Layout <span className="normal-case font-medium text-muted-foreground/60">— drag any table by its header to reorder</span></p>
                    <div className="flex flex-wrap gap-1.5">
                      {([
                        ['compact', 'Compact (3 cols)'],
                        ['comfortable', 'Comfortable (2 cols)'],
                        ['focus', 'Focus (1 col)'],
                      ] as [GmLayout, string][]).map(([l, label]) => (
                        <button
                          key={l}
                          onClick={() => applyGmConfig({ layout: l })}
                          className={`px-2.5 py-1.5 rounded-lg text-[11px] font-bold transition-all cursor-pointer border whitespace-nowrap ${
                            gmConfig.layout === l ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                      <span className="mx-2 w-px self-stretch bg-border/60" aria-hidden />
                      <span className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Rows:</span>
                        {[3, 5, 10].map(n => (
                          <button
                            key={n}
                            onClick={() => applyGmConfig({ rows: n })}
                            className={`px-2 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer border ${
                              gmConfig.rows === n ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                            }`}
                          >
                            {n}
                          </button>
                        ))}
                      </span>
                    </div>
                  </div>

                  {/* Columns — toggle visibility + reorder (left/right) */}
                  <div>
                    <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-1.5">Columns <span className="normal-case font-medium text-muted-foreground/60">use drag to choose what shows first</span></p>
                    <div className="flex flex-wrap gap-1.5">
                      {(gmConfig.columnOrder ?? GM_COLUMN_ORDER).map((key, idx, arr) => (
                        <span
                          key={key}
                          className={`inline-flex items-center rounded-lg border transition-all ${
                            col[key] ? 'bg-primary/10 border-primary/40' : 'bg-transparent border-border/40 opacity-60'
                          }`}
                        >
                          <button
                            onClick={() => applyGmConfig({ columns: { ...col, [key]: !col[key] } })}
                            className={`pl-2.5 pr-1.5 py-1.5 text-[11px] font-bold transition-all cursor-pointer rounded-l-lg ${
                              col[key] ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
                            }`}
                            title={col[key] ? `Hide ${GM_COLUMN_LABELS[key]}` : `Show ${GM_COLUMN_LABELS[key]}`}
                          >
                            {GM_COLUMN_LABELS[key]}
                          </button>
                          <button
                            onClick={() => moveGmColumn(key, -1)}
                            disabled={idx === 0}
                            className="px-1 py-1.5 text-[9px] text-muted-foreground hover:text-primary disabled:opacity-25 disabled:cursor-default cursor-pointer"
                            title="Move earlier"
                          >
                            ?
                          </button>
                          <button
                            onClick={() => moveGmColumn(key, 1)}
                            disabled={idx === arr.length - 1}
                            className="px-1 pr-2 py-1.5 text-[9px] text-muted-foreground hover:text-primary disabled:opacity-25 disabled:cursor-default cursor-pointer rounded-r-lg"
                            title="Move later"
                          >
                            ?
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Sorting & filters */}
                  <div>
                    <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-1.5">Sorting &amp; Filters</p>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                      <span className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Sort by</span>
                        {([
                          ['cap', 'Mkt Cap'],
                          ['change', 'Change %'],
                          ['price', 'Price'],
                          ['name', 'Name'],
                        ] as [GmConfig['sortBy'], string][]).map(([k, label]) => (
                          <button
                            key={k}
                            onClick={() => applyGmConfig({ sortBy: k })}
                            className={`px-2 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer border ${
                              gmConfig.sortBy === k ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Show</span>
                        {([
                          ['all', 'All'],
                          ['gainers', 'Gainers'],
                          ['losers', 'Losers'],
                        ] as [GmConfig['movers'], string][]).map(([k, label]) => (
                          <button
                            key={k}
                            onClick={() => applyGmConfig({ movers: k })}
                            className={`px-2 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer border ${
                              gmConfig.movers === k ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-2">
                      <span className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Rows</span>
                        {([
                          ['dense', 'Dense'],
                          ['showRank', '# Rank'],
                          ['highlightExtremes', 'Highlight ±'],
                        ] as [keyof GmConfig, string][]).map(([key, label]) => (
                          <button
                            key={String(key)}
                            onClick={() => applyGmConfig({ [key]: !gmConfig[key] } as Partial<GmConfig>)}
                            className={`px-2 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer border ${
                              gmConfig[key] ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Order markets</span>
                        {([
                          ['az', 'A ? Z'],
                          ['movers', 'Movers first'],
                        ] as [GmConfig['groupOrder'], string][]).map(([k, label]) => (
                          <button
                            key={k}
                            onClick={() => applyGmConfig({ groupOrder: k })}
                            className={`px-2 py-1 rounded-lg text-[11px] font-bold transition-all cursor-pointer border ${
                              gmConfig.groupOrder === k ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40'
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </span>
                    </div>
                  </div>

                  {/* Countries — visibility + ordering (what shows first) */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider">Countries <span className="normal-case font-medium text-muted-foreground/60">drag to order, first is default</span></p>
                      <span className="flex gap-1.5">
                        <button onClick={() => applyGmConfig({ countries: null })} className="text-[10px] font-bold text-primary hover:underline cursor-pointer uppercase tracking-wider">All</button>
                        <button onClick={() => applyGmConfig({ countries: [] })} className="text-[10px] font-bold text-muted-foreground hover:text-rose-400 cursor-pointer uppercase tracking-wider">None</button>
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {(['FOREX', 'COMMODITIES'] as const).map(special => {
                        const active = sectionVisible(special === 'FOREX' ? 'table_forex' : 'table_commodities');
                        return (
                          <button
                            key={special}
                            onClick={() => toggleSection(special === 'FOREX' ? 'table_forex' : 'table_commodities')}
                            className={`px-2.5 py-1 rounded-full text-[10px] font-bold font-mono transition-all cursor-pointer border ${
                              active ? 'bg-primary/15 text-primary border-primary/40' : 'text-muted-foreground border-border/40 hover:bg-accent/40 opacity-60'
                            }`}
                            title={active ? `Hide ${special.toLowerCase()} card` : `Show ${special.toLowerCase()} card`}
                          >
                            {active ? '' : '? '}{special}
                          </button>
                        );
                      })}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {globalOverview.map(g => {
                        const active = !gmConfig.countries || gmConfig.countries.includes(g.id);
                        return (
                          <span
                            key={g.id}
                            className={`inline-flex items-center rounded-full border transition-all ${
                              active ? 'bg-primary/10 border-primary/40' : 'bg-transparent border-border/40 opacity-60'
                            }`}
                          >
                            <button
                              onClick={() => {
                                const cur = new Set(gmConfig.countries ?? globalOverview.map(x => x.id));
                                if (cur.has(g.id)) cur.delete(g.id); else cur.add(g.id);
                                applyGmConfig({ countries: [...cur] });
                              }}
                              className={`pl-2.5 pr-1 py-1 text-[10px] font-bold font-mono transition-all cursor-pointer rounded-l-full ${
                                active ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
                              }`}
                              title={active ? `Hide ${g.id}` : `Show ${g.id}`}
                            >
                              {g.id}
                            </button>
                            <button
                              onClick={() => applyGmConfig({ order: [g.id, ...(gmConfig.order ?? cardIdBaseOrder).filter((x) => x !== g.id)] })}
                              className="px-0.5 py-1 text-[9px] text-muted-foreground hover:text-primary cursor-pointer"
                              title={`${g.id} first`}
                            >
                              ?
                            </button>
                            <button
                              onClick={() => applyGmConfig({ order: reorderList(gmConfig.order ?? cardIdBaseOrder, g.id, -1) })}
                              className="px-0.5 py-1 text-[9px] text-muted-foreground hover:text-primary cursor-pointer"
                              title="Move up"
                            >
                              ?
                            </button>
                            <button
                              onClick={() => applyGmConfig({ order: reorderList(gmConfig.order ?? cardIdBaseOrder, g.id, 1) })}
                              className="px-0.5 pr-2 py-1 text-[9px] text-muted-foreground hover:text-primary cursor-pointer rounded-r-full"
                              title="Move down"
                            >
                              ?
                            </button>
                          </span>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {loadingGlobalMarkets ? (
                <div className={`grid ${gridClass} gap-3`}>
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="p-3.5 rounded-2xl glass-card border border-white/10 dark:border-white/5 flex items-center justify-center">
                      <TableLoading pct={Math.min(95, 15 + i * 13)} label="loading" />
                    </div>
                  ))}
                </div>
              ) : cardOrder.length === 0 ? (
                <div className="py-10 text-center text-muted-foreground text-xs">
                  {globalOverview.length === 0
                    ? 'No priced markets yet - open a country screener and refresh prices to populate the overview.'
                    : gmSearch.trim()
                      ? `No markets match “${gmSearch.trim()}”.`
                      : 'All countries hidden — click Customize above and select the markets you want to see.'}
                </div>
              ) : (
                <div className={`relative grid ${gridClass} gap-3`}>
                  {cardOrder.map((cardId) => {
                    if (cardId === 'FOREX') {
                      return (
                        <div
                          key="FOREX"
                          data-gm-card
                          data-gm-id="FOREX"
                          className={cn(
                            'rounded-2xl glass-card border border-white/10 dark:border-white/5 overflow-hidden flex flex-col transition-all',
                            gmDragId === 'FOREX' && 'invisible'
                          )}
                        >
                          <div
                            data-gm-header
                            className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/5 hover:bg-accent/30 transition-colors select-none"
                          >
                            <span
                              data-gm-handle
                              role="button"
                              tabIndex={0}
                              aria-label="Drag Forex to reorder"
                              onMouseDown={(e) => beginGmDrag(e.clientX, e.clientY, e.button, e.currentTarget.closest('[data-gm-header]') as HTMLElement)}
                              className="flex items-center gap-2 min-w-0 cursor-grab active:cursor-grabbing text-left"
                              style={{ touchAction: 'none' }}
                              title="Drag to reorder"
                            >
                              <GripVertical size={14} className="text-muted-foreground/60 shrink-0" aria-hidden />
                              <span className="font-serif font-semibold text-sm text-foreground truncate">Forex</span>
                              <span className="text-[9px] text-muted-foreground font-mono truncate">Major Pairs</span>
                            </span>
                            <button
                              onClick={() => handleTabChange('forex')}
                              className="text-[9px] font-bold text-primary/90 uppercase tracking-wider shrink-0 hover:text-primary cursor-pointer bg-transparent border-none p-0"
                              title="Open Forex table"
                            >
                              Open <ArrowUpRight size={11} className="inline" />
                            </button>
                          </div>
                          <table className="w-full text-left text-[11px]">
                            <thead>
                              <tr className="text-muted-foreground/70 text-[9px] uppercase tracking-wider font-mono">
                                <th className={`${rowPad} pl-3.5 pr-2 font-semibold`}>Pair</th>
                                <th className={`${rowPad} px-2 text-right font-semibold`}>Rate (USD)</th>
                                <th className={`${rowPad} pr-3.5 pl-2 text-right font-semibold`}>Chg%</th>
                              </tr>
                            </thead>
                            <tbody>
                              {loadingForex ? (
                                <tr><td colSpan={3} className={`${rowPad} pl-3.5 pr-3.5 text-muted-foreground/60 italic`}>loading forex...</td></tr>
                              ) : filteredForex.length === 0 ? (
                                <tr><td colSpan={3} className={`${rowPad} pl-3.5 pr-3.5 text-muted-foreground/60 italic`}>No forex data</td></tr>
                              ) : filteredForex.slice(0, gmConfig.rows).map((pair) => {
                                const isPositive = pair.changePct >= 0;
                                return (
                                  <tr
                                    key={pair.symbol}
                                    onClick={(e) => handleSymbolClick(pair.symbol, pair.name, { price: pair.price, changePercent: pair.changePct }, e)}
                                    title="Ctrl+click to open in new tab"
                                    className="border-t border-white/5 transition-colors cursor-pointer hover:bg-primary/[0.04]"
                                  >
                                    <td className={`${rowPad} pl-3.5 pr-2 font-bold whitespace-nowrap text-foreground/80`}>
                                      {pair.symbol.replace('=X', '')}
                                    </td>
                                    <td className={`${rowPad} px-2 text-right font-mono font-semibold text-foreground whitespace-nowrap`}>
                                      {pair.found ? formatUsdPrice(pair.symbol, pair.price) : '—'}
                                    </td>
                                    <td className={`${rowPad} pr-3.5 pl-2 text-right whitespace-nowrap`}>
                                      <span className={`inline-block rounded px-1.5 font-mono font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                                        {pair.found ? `${isPositive ? '+' : ''}${pair.changePct.toFixed(2)}%` : '—'}
                                      </span>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      );
                    }
                    if (cardId === 'COMMODITIES') {
                      return (
                        <div
                          key="COMMODITIES"
                          data-gm-card
                          data-gm-id="COMMODITIES"
                          className={cn(
                            'rounded-2xl glass-card border border-white/10 dark:border-white/5 overflow-hidden flex flex-col transition-all',
                            gmDragId === 'COMMODITIES' && 'invisible'
                          )}
                        >
                          <div
                            data-gm-header
                            className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/5 hover:bg-accent/30 transition-colors select-none"
                          >
                            <span
                              data-gm-handle
                              role="button"
                              tabIndex={0}
                              aria-label="Drag Commodities to reorder"
                              onMouseDown={(e) => beginGmDrag(e.clientX, e.clientY, e.button, e.currentTarget.closest('[data-gm-header]') as HTMLElement)}
                              className="flex items-center gap-2 min-w-0 cursor-grab active:cursor-grabbing text-left"
                              style={{ touchAction: 'none' }}
                              title="Drag to reorder"
                            >
                              <GripVertical size={14} className="text-muted-foreground/60 shrink-0" aria-hidden />
                              <span className="font-serif font-semibold text-sm text-foreground truncate">Commodities</span>
                              <span className="text-[9px] text-muted-foreground font-mono truncate">Gold · Silver · Oil</span>
                            </span>
                            <button
                              onClick={() => handleTabChange('commodities')}
                              className="text-[9px] font-bold text-primary/90 uppercase tracking-wider shrink-0 hover:text-primary cursor-pointer bg-transparent border-none p-0"
                              title="Open Commodities table"
                            >
                              Open <ArrowUpRight size={11} className="inline" />
                            </button>
                          </div>
                          <table className="w-full text-left text-[11px]">
                            <thead>
                              <tr className="text-muted-foreground/70 text-[9px] uppercase tracking-wider font-mono">
                                <th className={`${rowPad} pl-3.5 pr-2 font-semibold`}>Commodity</th>
                                <th className={`${rowPad} px-2 text-right font-semibold`}>Price (USD)</th>
                                <th className={`${rowPad} pr-3.5 pl-2 text-right font-semibold`}>Chg%</th>
                              </tr>
                            </thead>
                            <tbody>
                              {loadingCommodities ? (
                                <tr><td colSpan={3} className={`${rowPad} pl-3.5 pr-3.5 text-muted-foreground/60 italic`}>loading commodities...</td></tr>
                              ) : commodities.length === 0 ? (
                                <tr><td colSpan={3} className={`${rowPad} pl-3.5 pr-3.5 text-muted-foreground/60 italic`}>No commodity data</td></tr>
                              ) : commodities.slice(0, gmConfig.rows).map((c) => {
                                const isPositive = c.changePct >= 0;
                                return (
                                  <tr
                                    key={c.symbol}
                                    onClick={(e) => handleSymbolClick(c.symbol, c.name, { price: c.price, changePercent: c.changePct }, e)}
                                    title="Ctrl+click to open in new tab"
                                    className="border-t border-white/5 transition-colors cursor-pointer hover:bg-primary/[0.04]"
                                  >
                                    <td className={`${rowPad} pl-3.5 pr-2 font-bold whitespace-nowrap text-foreground/80`}>
                                      {c.name}
                                      <span className="ml-1.5 text-[8px] font-mono text-muted-foreground/60 font-semibold">{c.unit}</span>
                                    </td>
                                    <td className={`${rowPad} px-2 text-right font-mono font-semibold text-foreground whitespace-nowrap`}>
                                      {c.found ? formatUsdPrice(c.symbol, c.price) : '—'}
                                    </td>
                                    <td className={`${rowPad} pr-3.5 pl-2 text-right whitespace-nowrap`}>
                                      <span className={`inline-block rounded px-1.5 font-mono font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                                        {c.found ? `${isPositive ? '+' : ''}${c.changePct.toFixed(2)}%` : '—'}
                                      </span>
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      );
                    }
                    const g = groups.find((x) => x.id === cardId);
                    if (!g) return null;
                    const isDragged = gmDragId === g.id;
                    return (
                    <div
                      key={g.id}
                      data-gm-card
                      data-gm-id={g.id}
                      className={cn(
                        'rounded-2xl glass-card border border-white/10 dark:border-white/5 overflow-hidden flex flex-col transition-all',
                        isDragged && 'invisible'
                      )}
                    >
                      {/* Drag via the grip handle only; the rest of the header
                          is a click-to-open action (pointer cursor). */}
                      <div
                        data-gm-header
                        className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/5 hover:bg-accent/30 transition-colors select-none"
                      >
                        <span
                          data-gm-handle
                          role="button"
                          tabIndex={0}
                          aria-label={`Drag ${g.country} to reorder`}
                          onMouseDown={(e) => beginGmDrag(e.clientX, e.clientY, e.button, e.currentTarget.closest('[data-gm-header]') as HTMLElement)}
                          className="flex items-center gap-2 min-w-0 cursor-grab active:cursor-grabbing text-left"
                          style={{ touchAction: 'none' }}
                          title={`Drag to reorder ${g.country}`}
                        >
                          <GripVertical size={14} className="text-muted-foreground/60 shrink-0" aria-hidden />
                          <span className="font-serif font-semibold text-sm text-foreground truncate">{g.name || g.country}</span>
                          <span className="text-[9px] text-muted-foreground font-mono truncate">{g.exchange}</span>
                        </span>
                        <button
                          onClick={() => handleMarketSelect(g.isCrypto ? 'CRYPTO' : g.id)}
                          className="text-[9px] font-bold text-primary/90 uppercase tracking-wider shrink-0 hover:text-primary cursor-pointer bg-transparent border-none p-0"
                          title={`Open ${g.country} screener`}
                        >
                          Open <ArrowUpRight size={11} className="inline" />
                        </button>
                      </div>
                      {/* Country headline index — the market's own benchmark. */}
                      {g.index && (
                        <div className="flex items-center justify-between gap-2 px-3.5 py-1.5 border-b border-white/5 bg-white/[0.02]">
                          <span
                            className="min-w-0 truncate text-[10px] font-mono text-muted-foreground"
                            title={`${g.index.name} (${g.index.symbol})`}
                          >
                            {g.indexName || g.index.name}
                          </span>
                          <span className="shrink-0 font-mono text-[11px] font-semibold text-foreground whitespace-nowrap">
                            {priceWithCurrency(g.id, g.index.price)}
                            <span className={cn('ml-1.5', g.index.changePct >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
                              {g.index.changePct >= 0 ? '+' : ''}{g.index.changePct.toFixed(2)}%
                            </span>
                          </span>
                        </div>
                      )}
                      {anyColumn && (() => {
                        const rows = processStocks(g.stocks);
                        const best = rows.length ? Math.max(...rows.map(r => r.changePct)) : 0;
                        const worst = rows.length ? Math.min(...rows.map(r => r.changePct)) : 0;
                        return (
                          <table className="w-full text-left text-[11px]">
                            <thead>
                              <tr className="text-muted-foreground/70 text-[9px] uppercase tracking-wider font-mono">
                                {(gmConfig.columnOrder ?? GM_COLUMN_ORDER).map((cKey) => {
                                  if (!col[cKey]) return null;
                                  if (cKey === 'ticker') return <th key={cKey} className={`${rowPad} pl-3.5 pr-2 font-semibold`}>Ticker</th>;
                                  if (cKey === 'name') return <th key={cKey} className={`${rowPad} px-2 font-semibold hidden sm:table-cell`}>Name</th>;
                                  if (cKey === 'price') return <th key={cKey} className={`${rowPad} px-2 text-right font-semibold`}>Price</th>;
                                  if (cKey === 'cap') return <th key={cKey} className={`${rowPad} px-2 text-right font-semibold hidden md:table-cell`}>Mkt Cap</th>;
                                  return <th key={cKey} className={`${rowPad} pr-3.5 pl-2 text-right font-semibold`}>Chg%</th>;
                                })}
                              </tr>
                            </thead>
                            <tbody>
                              {rows.length === 0 ? (
                                <tr><td colSpan={(gmConfig.columnOrder ?? GM_COLUMN_ORDER).filter((k) => col[k]).length || 5} className={`${rowPad} pl-3.5 pr-3.5 text-muted-foreground/60 italic`}>
                                  No {gmConfig.movers === 'all' ? '' : gmConfig.movers} in top {gmConfig.rows}
                                </td></tr>
                              ) : rows.map((s, idx) => {
                                const isPositive = s.changePct >= 0;
                                const isBest = gmConfig.highlightExtremes && rows.length > 1 && s.changePct === best && best > 0;
                                const isWorst = gmConfig.highlightExtremes && rows.length > 1 && s.changePct === worst && worst < 0;
                                const isSelected = gmSelectedRow?.marketId === g.id && gmSelectedRow?.symbol === s.symbol;
                                return (
                                  <tr
                                    key={s.symbol}
                                    onClick={() => {
                                      setGmSelectedRow({ marketId: g.id, symbol: s.symbol });
                                      handleSymbolClick(s.symbol, s.name, { price: s.price, changePercent: s.changePct });
                                    }}
                                    className={cn(
                                      'border-t border-white/5 transition-colors cursor-pointer',
                                      isSelected
                                        ? 'bg-primary/[0.09] shadow-[inset_2px_0_0_0_#7aff78]'
                                        : 'hover:bg-primary/[0.04]'
                                    )}
                                  >
                                    {(gmConfig.columnOrder ?? GM_COLUMN_ORDER).map((cKey) => {
                                      if (!col[cKey]) return null;
                                      if (cKey === 'ticker') return (
                                        <td key={cKey} className={`${rowPad} pl-3.5 pr-2 font-bold whitespace-nowrap ${isSelected ? 'text-foreground' : 'text-foreground/80'}`}>
                                          {gmConfig.showRank && <span className="text-muted-foreground/60 font-mono font-semibold mr-1">{idx + 1}.</span>}
                                          {/* Always the raw ticker symbol — this is what
                                              resolves on TradingView. Name lives in the
                                              tooltip + the Name column. */}
                                          <span className="font-mono" title={`${s.name} (${s.symbol})`}>{s.symbol}</span>
                                        </td>
                                      );
                                      if (cKey === 'name') return (
                                        <td key={cKey} className={`${rowPad} px-2 truncate max-w-[110px] hidden sm:table-cell ${isSelected ? 'text-foreground' : 'text-foreground/75'}`}>{s.name}</td>
                                      );
                                      if (cKey === 'price') return (
                                        <td key={cKey} className={`${rowPad} px-2 text-right font-mono font-semibold text-foreground whitespace-nowrap`}>
                                          {priceWithCurrency(g.id, s.price)}
                                        </td>
                                      );
                                      if (cKey === 'cap') return (
                                        <td key={cKey} className={`${rowPad} px-2 text-right font-mono ${isSelected ? 'text-foreground/90' : 'text-foreground/75'} hidden md:table-cell whitespace-nowrap`}>{fmtCap(s.marketCap)}</td>
                                      );
                                      return (
                                        <td key={cKey} className={`${rowPad} pr-3.5 pl-2 text-right whitespace-nowrap`}>
                                          <span className={`inline-block rounded px-1.5 font-mono font-bold ${
                                            isSelected
                                              ? 'bg-primary text-black'
                                              : isBest ? 'bg-primary/15 text-primary' : isWorst ? 'bg-rose-500/10 text-rose-400' : isPositive ? 'text-emerald-400' : 'text-rose-400'
                                          }`}>
                                            {isPositive ? '+' : ''}{s.changePct.toFixed(2)}%
                                          </span>
                                        </td>
                                      );
                                    })}
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        );
                      })()}
                    </div>
                    );
                  })}
                  {/* Floating copy of the dragged table — follows the cursor via
                      direct DOM transform (ref), zero re-renders. Rendered through
                      a portal to document.body and ALWAYS mounted: an ancestor
                      with backdrop-blur / transform would otherwise become the
                      containing block for position:fixed and the ghost would fly
                      off away from the mouse. visibility:hidden hides it when not
                      dragging so the ref is always available on drag start. */}
                  {createPortal(
                    <div
                      ref={gmFloatRef}
                      className="fixed z-[70] pointer-events-none rounded-2xl overflow-hidden bg-[#0e0e0e] dark:bg-[#0e0e0e] text-foreground shadow-[0_30px_80px_rgba(0,0,0,0.6)] will-change-transform"
                      style={{
                        left: 0,
                        top: 0,
                        width: gmDragWidth || 320,
                        visibility: gmDragId ? 'visible' : 'hidden',
                        transform: 'translate3d(-9999px, -9999px, 0) translate(-50%, -50%) scale(1.02)',
                      }}
                    >
                      {gmDragId && (() => {
                        const src = globalOverview.find(x => x.id === gmDragId);
                        if (gmDragId === 'FOREX') {
                          const rows = filteredForex.slice(0, Math.min(3, gmConfig.rows));
                          return (
                            <>
                              <div className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/10">
                                <span className="flex items-center gap-2 min-w-0">
                                  <GripVertical size={14} className="text-primary shrink-0" aria-hidden />
                                  <span className="font-serif font-semibold text-sm text-foreground truncate">Forex</span>
                                  <span className="text-[9px] text-muted-foreground font-mono truncate">Major Pairs</span>
                                </span>
                                <span className="text-[9px] font-bold text-primary uppercase tracking-wider shrink-0">moving…</span>
                              </div>
                              <div className="px-3.5 py-2.5 space-y-1.5">
                                {rows.map(pair => (
                                  <div key={pair.symbol} className="flex items-center justify-between gap-2 text-[11px]">
                                    <span className="font-mono font-bold text-foreground/80 truncate">{pair.symbol.replace('=X', '')}</span>
                                    <span className="font-mono text-foreground/80">{pair.found ? formatUsdPrice(pair.symbol, pair.price) : '—'}</span>
                                  </div>
                                ))}
                                <div className="pt-1 text-[9px] font-mono text-muted-foreground/70">{filteredForex.length} pairs · drop to place</div>
                              </div>
                            </>
                          );
                        }
                        if (gmDragId === 'COMMODITIES') {
                          const rows = commodities.slice(0, Math.min(3, gmConfig.rows));
                          return (
                            <>
                              <div className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/10">
                                <span className="flex items-center gap-2 min-w-0">
                                  <GripVertical size={14} className="text-primary shrink-0" aria-hidden />
                                  <span className="font-serif font-semibold text-sm text-foreground truncate">Commodities</span>
                                  <span className="text-[9px] text-muted-foreground font-mono truncate">Gold · Silver · Oil</span>
                                </span>
                                <span className="text-[9px] font-bold text-primary uppercase tracking-wider shrink-0">moving…</span>
                              </div>
                              <div className="px-3.5 py-2.5 space-y-1.5">
                                {rows.map(c => (
                                  <div key={c.symbol} className="flex items-center justify-between gap-2 text-[11px]">
                                    <span className="font-mono font-bold text-foreground/80 truncate">{c.name}</span>
                                    <span className="font-mono text-foreground/80">{c.found ? formatUsdPrice(c.symbol, c.price) : '—'}</span>
                                  </div>
                                ))}
                                <div className="pt-1 text-[9px] font-mono text-muted-foreground/70">{commodities.length} commodities · drop to place</div>
                              </div>
                            </>
                          );
                        }
                        if (!src) return null;
                        return (
                          <>
                            <div className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-white/10">
                              <span className="flex items-center gap-2 min-w-0">
                                <GripVertical size={14} className="text-primary shrink-0" aria-hidden />
                                <span className="font-serif font-semibold text-sm text-foreground truncate">{src.name || src.country}</span>
                                <span className="text-[9px] text-muted-foreground font-mono truncate">{src.exchange}</span>
                              </span>
                              <span className="text-[9px] font-bold text-primary uppercase tracking-wider shrink-0">moving…</span>
                            </div>
                            <div className="px-3.5 py-2.5 space-y-1.5">
                              {src.stocks.slice(0, Math.min(3, gmConfig.rows)).map(s => (
                                <div key={s.symbol} className="flex items-center justify-between gap-2 text-[11px]">
                                  <span className="font-mono font-bold text-foreground/80 truncate">{s.symbol}</span>
                                  <span className="font-mono text-foreground/80">{priceWithCurrency(src.id, s.price)}</span>
                                </div>
                              ))}
                              <div className="pt-1 text-[9px] font-mono text-muted-foreground/70">
                                {src.stocks.length} rows · drop to place
                              </div>
                            </div>
                          </>
                        );
                      })()}
                    </div>,
                    document.body
                  )}
                </div>
              )}
            </div>
          );
}
