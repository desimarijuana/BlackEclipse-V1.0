'use client';

// ── TradingView Provider — wraps the existing TradingView embed widget ───────
// Implements the same ChartProvider contract as EclipseChartProvider so the
// ChartWidget can switch between them. TradingView brings its own data + UI;
// we only feed it the symbol/timeframe/chartType and let it render.

import { getTradingViewSymbol } from '@/lib/utils';
import type {
  ChartData, ChartDrawing, ChartIndicatorConfig, ChartProvider, ChartState, ChartType, Timeframe,
} from '@/lib/chart/types';

const EMBED_SRC = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';

/** Map our timeframe to TradingView's interval string. */
function tvInterval(tf: Timeframe): string {
  switch (tf) {
    case '1m': return '1';
    case '3m': return '3';
    case '5m': return '5';
    case '15m': return '15';
    case '30m': return '30';
    case '1H': return '60';
    case '2H': return '120';
    case '4H': return '240';
    case '1D': return 'D';
    case '1W': return 'W';
    case '1M': return 'M';
  }
}

/** Map our chart type to TradingView's style id. */
function tvStyle(type: ChartType): string {
  switch (type) {
    case 'candlestick': return '1';
    case 'ohlc': return '2';
    case 'line': return '3';
    case 'area': return '3';
    default: return '1';
  }
}

export class TradingViewProvider implements ChartProvider {
  readonly id = 'tradingview' as const;
  readonly label = 'TradingView';

  private container: HTMLElement | null = null;
  private state: ChartState;

  constructor(initial: ChartState) {
    this.state = { ...initial };
  }

  initialize(container: HTMLElement): void {
    this.container = container;
    this.inject();
  }

  destroy(): void {
    if (this.container) this.container.innerHTML = '';
    this.container = null;
  }

  setSymbol(symbol: string, market: string): void {
    this.state.symbol = symbol;
    this.state.market = market;
    this.inject();
  }

  setTimeframe(timeframe: Timeframe): void {
    this.state.timeframe = timeframe;
    this.inject();
  }

  setData(_data: ChartData): void {
    // TradingView fetches its own data; nothing to do.
  }

  addIndicator(_config: ChartIndicatorConfig): void {
    // TradingView manages its own studies.
  }
  removeIndicator(_id: string): void {
    // TradingView manages its own studies.
  }

  addDrawing(_drawing: ChartDrawing): void {
    // TradingView manages its own drawings.
  }
  removeDrawing(_id: string): void {
    // TradingView manages its own drawings.
  }

  setChartType(type: ChartType): void {
    this.state.chartType = type;
    this.inject();
  }

  resize(): void {
    // The embed widget autosizes; nothing to do.
  }

  getState(): ChartState {
    return { ...this.state };
  }

  restoreState(state: ChartState): void {
    this.state = { ...state };
    this.inject();
  }

  private inject(): void {
    const container = this.container;
    if (!container) return;
    const tvSymbol = getTradingViewSymbol(this.state.symbol, undefined, this.state.market);
    container.innerHTML = '';
    const script = document.createElement('script');
    script.src = EMBED_SRC;
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: tvSymbol,
      interval: tvInterval(this.state.timeframe),
      timezone: 'Etc/UTC',
      theme: 'dark',
      style: tvStyle(this.state.chartType),
      locale: 'en',
      backgroundColor: 'rgba(0, 0, 0, 0)',
      gridColor: 'rgba(122, 255, 120, 0.05)',
      allow_symbol_change: true,
      hide_side_toolbar: false,
      hide_legend: false,
      studies: ['STD;RSI'],
    });
    container.appendChild(script);
  }
}
