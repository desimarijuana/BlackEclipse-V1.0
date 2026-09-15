'use client';

// ── Market Heatmap widget ────────────────────────────────────────────────────
// A finviz-style treemap for the Command Center: pick a country / index, see
// its largest constituents grouped by sector. Tiles are sized by market cap
// (falling back to 24h volume) and coloured by percent change via an ECharts
// continuous visualMap gradient. Hovering a tile opens a frosted-glass tooltip
// with the asset's price, change, market cap, volume and sector.
//
// Real JDDS data only — an empty payload renders an UNAVAILABLE note instead
// of fabricated tiles.

import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import type { EChartsOption } from 'echarts';
import { Maximize2, Minimize2, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import { useEChart } from '@/components/screens/portfolio/use-echart';
import { useTopic } from '@/lib/workspace/data-hub';
import { cn } from '@/lib/utils';
import { HEATMAP_MARKETS, heatmapMeta, type HeatmapPayload } from '@/lib/heatmap';
import { marketViewName, useActiveMarket } from './market-views';
import type { WidgetPlacement } from '@/lib/workspace/types';

// Gradient stops shared by the visualMap and the tooltip accents.
const GRADIENT = ['#b91c1c', '#7f1d1d', '#27272a', '#166534', '#22c55e'];
const UP_TEXT = '#34d399';
const DOWN_TEXT = '#fb7185';

function fmtCap(v: number | null | undefined): string {
  if (v == null || !(v > 0)) return '—';
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toFixed(0);
}

function fmtMoney(v: number | null | undefined, currency: string): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return `${currency}${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function pctLabel(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function tooltipHtml(params: unknown, currency: string): string {
  const p = params as { data?: Record<string, unknown> };
  const d = p.data ?? {};

  // Sector header tile — summarise the group.
  if (Array.isArray(d.children)) {
    const children = d.children as Array<Record<string, unknown>>;
    const change = Number(d.change ?? 0);
    return `
      <div style="min-width:160px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace">
        <div style="display:flex;align-items:baseline;justify-content:space-between;gap:14px">
          <span style="font-weight:800;font-size:13px;color:#f8fafc">${String(d.name ?? '')}</span>
          <span style="font-weight:700;font-size:12px;color:${change >= 0 ? UP_TEXT : DOWN_TEXT}">${pctLabel(change)}</span>
        </div>
        <div style="color:#9ca3af;font-size:10px;margin-top:2px">${children.length} constituents</div>
        <div style="height:1px;background:rgba(255,255,255,.08);margin:7px 0"></div>
        <div style="color:#9ca3af;font-size:10px">Market cap <span style="color:#e5e7eb">${fmtCap(Number(d.rawMarketCap ?? 0))}</span></div>
      </div>`;
  }

  const change = Number(d.changePct ?? 0);
  const color = change >= 0 ? UP_TEXT : DOWN_TEXT;
  const row = (label: string, value: string) =>
    `<tr><td style="color:#9ca3af;padding:1px 12px 1px 0">${label}</td><td style="text-align:right;color:#e5e7eb">${value}</td></tr>`;

  return `
    <div style="min-width:172px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace">
      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:14px">
        <span style="font-weight:800;font-size:13px;letter-spacing:.3px;color:#f8fafc">${String(d.symbol ?? d.name ?? '')}</span>
        <span style="font-weight:700;font-size:12px;color:${color}">${pctLabel(change)}</span>
      </div>
      <div style="color:#9ca3af;font-size:10px;margin-top:1px;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${String(d.fullName ?? '')}</div>
      <div style="height:1px;background:rgba(255,255,255,.08);margin:7px 0"></div>
      <table style="font-size:10px;border-collapse:collapse;width:100%">
        ${row('Price', fmtMoney(Number(d.price), currency))}
        ${row('Mkt Cap', fmtCap(Number(d.rawMarketCap ?? d.marketCap ?? 0)))}
        ${row('Volume', fmtCap(Number(d.volume ?? 0)))}
        ${row('Sector', String(d.sector ?? '—'))}
      </table>
    </div>`;
}

export function MarketHeatmapWidget({ placement }: { placement?: WidgetPlacement }) {
  // The heatmap defaults to whatever market tab is active, but keeps its own
  // picker so a single heatmap card can be pinned to any asset class (equities,
  // crypto, forex, commodities) independently of the tab. Selection persists per
  // widget instance in localStorage.
  const activeMarket = useActiveMarket();
  const storageKey = `be_heatmap_market:${placement?.id ?? 'default'}`;
  const [market, setMarket] = useState<string>(() => {
    const configured = placement?.config?.market as string | undefined;
    if (configured) return configured;
    if (typeof window !== 'undefined') {
      try {
        const saved = window.localStorage.getItem(storageKey);
        if (saved) return saved;
      } catch { /* ignore */ }
    }
    return activeMarket;
  });

  // When the user has no per-card override, follow the active market tab.
  const [pinned, setPinned] = useState<boolean>(() => {
    if (placement?.config?.market) return true;
    if (typeof window !== 'undefined') {
      try { return Boolean(window.localStorage.getItem(storageKey)); } catch { /* ignore */ }
    }
    return false;
  });

  useEffect(() => {
    if (!pinned) setMarket(activeMarket);
  }, [activeMarket, pinned]);

  const chooseMarket = (next: string) => {
    setPinned(true);
    setMarket(next);
    try { window.localStorage.setItem(storageKey, next); } catch { /* ignore */ }
  };

  // Fullscreen ("expand") mode + a reset counter that re-initialises the chart
  // (the treemap roam/zoom matrix is internal, so a re-init is the cleanest way
  // to reset the view).
  const [expanded, setExpanded] = useState(false);
  const [resetKey, setResetKey] = useState(0);

  useEffect(() => {
    if (!expanded) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setExpanded(false); };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener('keydown', onKey);
    };
  }, [expanded]);

  const topic = useTopic<HeatmapPayload>(`market:heatmap:${market}`);
  const data = topic.data;
  const meta = heatmapMeta(market);

  const tree = useMemo(() => {
    if (!data?.sectors?.length) return [];
    return data.sectors.map(sec => {
      const children = sec.stocks.map(s => {
        // `sectorCap` is the server's COMPRESSED size for this leaf (it rides on
        // `marketCap`); the raw cap is kept for the tooltip via `rawMarketCap`.
        const size = s.marketCap > 0 ? s.marketCap : s.volume;
        return {
          name: s.symbol,
          value: [size, s.changePct],
          symbol: s.symbol,
          fullName: s.name,
          sector: sec.name,
          price: s.price,
          changePct: s.changePct,
          marketCap: s.marketCap,
          rawMarketCap: s.rawMarketCap ?? s.marketCap,
          volume: s.volume,
        };
      });
      // Sector tile area = sum of its children's (already compressed) sizes, so
      // the group band matches the leaves exactly.
      const total = children.reduce((a, c) => a + Number(c.value[0] ?? 0), 0);
      return {
        name: sec.name,
        value: [total, sec.change],
        change: sec.change,
        marketCap: total,
        rawMarketCap: sec.rawMarketCap ?? total,
        children,
      };
    });
  }, [data]);

  // ECharts treemap `upperLabel.height` is required to reserve space for the
  // sector band, but the installed typings omit the property — declare it on a
  // variable so the extra key is allowed structurally (excess-property checks
  // only apply to fresh object literals).
  const sectorUpperLabel = {
    show: true,
    height: 18,
    color: '#e5e7eb',
    fontSize: 10,
    fontWeight: 'bold' as const,
    backgroundColor: 'transparent',
    // Rich-text styles are NOT inherited from `label` — they must be declared
    // on `upperLabel` itself, otherwise ECharts renders the raw `{name|…}`
    // markup literally.
    rich: {
      name: { fontSize: 10, fontWeight: 'bold' as const, color: '#e5e7eb' },
      pct: { fontSize: 9, color: '#dbeafe' },
    },
    formatter: (params: unknown) => {
      const p = params as { data?: Record<string, unknown> };
      const d = p.data ?? {};
      if (d.name == null || d.name === '') return '';
      return `{name|${String(d.name)}}  {pct|${pctLabel(Number(d.change ?? 0))}}`;
    },
  };

  const ref = useEChart(() => {
    if (!tree.length) return null;
    const currency = data?.currency ?? '$';
    const option: EChartsOption = {
      backgroundColor: 'transparent',
      animationDuration: 300,
      animationEasing: 'cubicOut',
      tooltip: {
        trigger: 'item',
        confine: true,
        backgroundColor: 'rgba(18,18,20,0.5)', appendTo: 'body',
        borderColor: 'rgba(255,255,255,0.12)',
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: '#e5e7eb', fontSize: 11 },
        extraCssText:
          'backdrop-filter: blur(18px) saturate(1.35); border-radius: 14px; box-shadow: 0 8px 30px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);',
        formatter: (params: unknown) => tooltipHtml(params, currency),
      },
      visualMap: {
        type: 'continuous',
        min: -3,
        max: 3,
        calculable: false,
        orient: 'horizontal',
        left: 'center',
        bottom: 2,
        itemWidth: 12,
        itemHeight: 110,
        precision: 0,
        text: ['+3%', '-3%'],
        textStyle: { color: '#94a3b8', fontSize: 9 },
        inRange: { color: GRADIENT },
      },
      series: [
        {
          type: 'treemap',
          roam: expanded,
          nodeClick: false,
          breadcrumb: { show: false },
          width: '100%',
          height: '100%',
          top: 2,
          left: 0,
          right: 0,
          bottom: 24,
          visualDimension: 1,
          visualMin: -3,
          visualMax: 3,
          visibleMin: 8,
          childrenVisibleMin: 8,
          squareRatio: 1.15,
          levels: [
            {
              itemStyle: { borderWidth: 2, gapWidth: 3, borderColor: 'rgba(8,8,10,0.92)' },
            },
            {
              itemStyle: { borderWidth: 1, gapWidth: 1, borderColor: 'rgba(8,8,10,0.85)' },
            },
          ],
          upperLabel: sectorUpperLabel,
          label: {
            show: true,
            position: 'insideTopLeft',
            color: '#f8fafc',
            fontSize: 10,
            lineHeight: 13,
            formatter: (params: unknown) => {
              const p = params as { data?: Record<string, unknown> };
              const d = p.data ?? {};
              // Parent (sector) nodes render their name/pct via `upperLabel`
              // so the band and the tile label don't overlap.
              if (Array.isArray(d.children) || Array.isArray(d.subChildren)) return '';
              if (d.symbol == null && d.name == null) return '';
              const change = Number(d.changePct ?? 0);
              return `{sym|${String(d.symbol ?? d.name)}}\n{pct|${pctLabel(change)}}`;
            },
            rich: {
              name: { fontSize: 10, fontWeight: 'bold', color: '#e5e7eb' },
              sym: { fontSize: 11, fontWeight: 'bold', color: '#f8fafc' },
              pct: { fontSize: 9, color: '#dbeafe' },
            },
          },
          data: tree,
        },
      ],
    };
    return option;
  }, [tree, data?.currency, expanded, resetKey]);

  const overall = data?.change ?? 0;

  // Treemap zoom is driven by the roam controller, which listens for wheel
  // events on the chart canvas. Synthesising a wheel event gives us explicit
  // zoom-in / zoom-out buttons on top of wheel + drag interaction.
  const zoom = (dir: 'in' | 'out') => {
    const el = ref.current;
    if (!el) return;
    const target = el.querySelector('canvas') ?? el;
    const rect = el.getBoundingClientRect();
    target.dispatchEvent(new WheelEvent('wheel', {
      deltaY: dir === 'in' ? -120 : 120,
      clientX: rect.left + rect.width / 2,
      clientY: rect.top + rect.height / 2,
      bubbles: true,
      cancelable: true,
    }));
  };

  const chartReady = !!data && !data.empty && tree.length > 0;

  const header = (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-border/10 pb-2.5">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h3 className="font-serif text-sm font-semibold text-foreground truncate">Market Heatmap</h3>
          {data && !data.empty && (
            <span className={cn('font-mono text-[10px] font-bold', overall >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
              {pctLabel(overall)}
            </span>
          )}
        </div>
        <p className="mt-0.5 truncate text-[9px] text-muted-foreground/70">
          {marketViewName(market)} · {data?.indexName ?? meta.index}
          {data && !data.empty ? ` · ${data.live} ${data.live === 1 ? 'instrument' : 'instruments'}` : ''}
          {!pinned ? ' · following tab' : ''}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {expanded && chartReady && (
          <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-accent/30 p-0.5">
            <button
              type="button"
              onClick={() => zoom('out')}
              className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
              title="Zoom out"
            >
              <ZoomOut size={13} />
            </button>
            <button
              type="button"
              onClick={() => zoom('in')}
              className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
              title="Zoom in"
            >
              <ZoomIn size={13} />
            </button>
            <button
              type="button"
              onClick={() => setResetKey(k => k + 1)}
              className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer"
              title="Reset zoom"
            >
              <RotateCcw size={13} />
            </button>
          </div>
        )}
        {pinned && (
          <button
            type="button"
            onClick={() => {
              setPinned(false);
              setMarket(activeMarket);
              try { window.localStorage.removeItem(storageKey); } catch { /* ignore */ }
            }}
            className="hidden rounded-xl border border-white/15 dark:border-white/10 bg-accent/30 px-2 py-1.5 text-[9px] font-bold uppercase tracking-wide text-muted-foreground transition-all hover:border-primary/40 hover:text-primary cursor-pointer sm:block"
            title="Follow the active market tab"
          >
            Follow tab
          </button>
        )}
        <div className="relative shrink-0">
          <select
            value={market}
            onChange={e => chooseMarket(e.target.value)}
            className="cursor-pointer appearance-none rounded-xl border border-white/15 dark:border-white/10 bg-background/60 py-1.5 pl-2.5 pr-7 text-[10px] font-semibold text-foreground outline-none transition-all hover:border-primary/40 focus:ring-1 focus:ring-primary"
            title="Select the market to map"
          >
            {HEATMAP_MARKETS.map(m => (
              <option key={m.id} value={m.id} className="bg-[#121212] text-foreground">
                {marketViewName(m.id)} — {m.index}
              </option>
            ))}
          </select>
          <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6" /></svg>
          </span>
        </div>
        <button
          type="button"
          onClick={() => setExpanded(v => !v)}
          className="rounded-xl border border-white/15 dark:border-white/10 bg-accent/30 p-1.5 text-muted-foreground transition-all hover:border-primary/40 hover:text-primary cursor-pointer"
          title={expanded ? 'Exit fullscreen' : 'Expand heatmap'}
        >
          {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </button>
      </div>
    </div>
  );

  const body = !data ? (
    <div className="flex flex-1 items-center justify-center py-8 text-center">
      <p className="text-xs italic text-muted-foreground/70">Loading heatmap…</p>
    </div>
  ) : data.empty || !tree.length ? (
    <div className="flex flex-1 items-center justify-center py-8 text-center">
      <p className="max-w-[28ch] text-xs italic text-amber-400/80">
        No priced constituents for {marketViewName(market)} in JDDS yet.
      </p>
    </div>
  ) : (
    <div ref={ref} className={expanded ? 'h-full w-full flex-1' : 'min-h-[300px] flex-1'} />
  );

  const content = (
    <div className="flex h-full flex-col p-4">
      {header}
      {body}
    </div>
  );

  if (expanded && typeof document !== 'undefined') {
    return createPortal(
      <div className="fixed inset-0 z-[100] animate-fade-in">
        <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setExpanded(false)} />
        <div className="absolute inset-2 sm:inset-5 flex flex-col overflow-hidden rounded-2xl border border-white/10 glass-card-strong shadow-2xl shadow-black/50">
          {content}
        </div>
      </div>,
      document.body,
    );
  }

  return content;
}
