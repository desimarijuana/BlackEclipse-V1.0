'use client';

import { useEffect, useRef } from 'react';
import { getTradingViewSymbol } from '@/lib/utils';

interface EmbeddedChartProps {
  symbol: string;
}

/**
 * Embeds a TradingView widget for the given symbol.
 * Used by the "chart" tab in the terminal.
 */
export function EmbeddedChart({ symbol }: EmbeddedChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const tvSymbol = getTradingViewSymbol(symbol);

    // Clear any previous widget
    container.innerHTML = '';

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: tvSymbol,
      interval: 'D',
      timezone: 'Etc/UTC',
      theme: 'dark',
      style: '1',
      locale: 'en',
      allow_symbol_change: true,
      hide_side_toolbar: false,
      hide_legend: false,
      studies: ['STD;RSI'],
    });
    container.appendChild(script);

    return () => {
      container.innerHTML = '';
    };
  }, [symbol]);

  return (
    <div className="flex h-full w-full flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-xl font-semibold tracking-tight text-foreground">
          {symbol} — Advanced Chart
        </h2>
        <span className="rounded-md bg-accent/40 px-2 py-1 font-mono text-[10px] text-muted-foreground">
          {getTradingViewSymbol(symbol)}
        </span>
      </div>
      <div ref={containerRef} className="h-[calc(100%-3rem)] w-full overflow-hidden rounded-2xl border border-border/10" />
    </div>
  );
}
