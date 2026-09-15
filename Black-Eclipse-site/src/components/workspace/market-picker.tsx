'use client';

// ── MarketPicker — inline "which market does this card show?" control ────────
// Widgets that render market data drop this into their header so the user can
// switch the card's market without opening the config panel. Writes straight
// through to the widget instance's persisted `config.market` via the
// WidgetConfigContext channel.
//
// "Follow tab" (the default) keeps the card in sync with the active Command
// Center market tab; picking an explicit market pins just this card.

import React from 'react';
import { ChevronDown, Globe } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWidgetConfigApi } from '@/lib/workspace/widget-config-context';
import { MARKET_FOLLOW, MARKET_OPTIONS, marketViewName, useActiveMarket, useWidgetMarket } from '@/lib/dashboard/market-views';
import type { WidgetPlacement } from '@/lib/workspace/types';

export function MarketPicker({
  placement,
  className,
}: {
  placement?: WidgetPlacement;
  className?: string;
}) {
  const api = useWidgetConfigApi();
  const activeMarket = useActiveMarket();
  const market = useWidgetMarket(placement);
  const pinned = Boolean(placement?.config?.market);

  // No write channel (widget rendered outside a workspace) → static label.
  if (!api || !placement) {
    return (
      <span className={cn('font-mono text-[9px] font-bold uppercase tracking-wide text-primary shrink-0', className)}>
        {marketViewName(market)}
      </span>
    );
  }

  return (
    <span className={cn('relative inline-flex shrink-0 items-center', className)}>
      <Globe size={10} className={cn('pointer-events-none absolute left-1.5', pinned ? 'text-primary' : 'text-muted-foreground/60')} />
      <select
        value={pinned ? market : MARKET_FOLLOW}
        onChange={e => api.set(placement.id, { market: e.target.value })}
        onPointerDown={e => e.stopPropagation()}
        onClick={e => e.stopPropagation()}
        title="Choose the market this widget shows"
        className={cn(
          'cursor-pointer appearance-none rounded-lg border bg-background/60 py-0.5 pl-5 pr-4 text-[9px] font-bold uppercase tracking-wide outline-none transition-colors focus:ring-1 focus:ring-primary',
          pinned ? 'border-primary/40 text-primary' : 'border-border/30 text-muted-foreground hover:text-foreground',
        )}
      >
        <option value={MARKET_FOLLOW} className="bg-[#121212] text-foreground normal-case">
          {marketViewName(activeMarket)} (tab)
        </option>
        {MARKET_OPTIONS.map(o => (
          <option key={o.id} value={o.id} className="bg-[#121212] text-foreground normal-case">
            {o.name}
          </option>
        ))}
      </select>
      <ChevronDown size={9} className="pointer-events-none absolute right-1 text-muted-foreground" />
    </span>
  );
}
