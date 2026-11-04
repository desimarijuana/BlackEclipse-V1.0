'use client';

// ── Market Bubbles — turnover atlas ──────────────────────────────────────────
// A fluid-physics bubble map of a market's most-traded instruments. Data comes
// from the SAME real JDDS source as the Command Center heatmap (`/api/heatmap`),
// which is what makes it trustworthy:
//   • every tile is a priced row straight out of JDDS — there is no demo,
//     random or per-market seed data anywhere in this file;
//   • markets are the ones the heatmap knows about (HEATMAP_MARKETS), not a
//     hardcoded country list;
//   • the default sizing metric is real 24h traded value (turnover), and the
//     Volume Analytics panel summarises the WHOLE market, not just the bubbles
//     on screen.
// An empty payload renders an explicit UNAVAILABLE state — we never invent a
// market.

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { usePageShortcuts } from '@/hooks/use-page-shortcuts';
import { useActiveInterval } from '@/hooks/use-active-interval';
import { Search, Sparkles, Orbit, RefreshCw, ZoomIn, ZoomOut, ArrowUpDown, Filter, Gauge, Sliders, TrendingUp } from '@/lib/icons';
import { TopLoader } from '@/components/ui/top-loader';
import { PageHeader } from '@/components/layout/page-header';
import { Skeleton } from '@/components/ui/skeleton';
import { VolumeAnalyticsPanel } from './volume-analytics';
import {
  HEATMAP_MARKETS, heatmapMeta, isNotionalVolume, turnoverFor,
  type HeatmapPayload, type HeatmapStock, type VolumeSummary,
} from '@/lib/heatmap';
import { resolveUserMarket, setUserMarket } from '@/lib/user-market';

interface BubbleData {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  /** Raw 24h volume: shares, or quote notional for crypto. */
  volumeRaw: number;
  /** Raw market cap (0 when unavailable). */
  marketCapRaw: number;
  /** Traded value in the market currency — the honest cross-instrument metric. */
  turnover: number;
  sector: string;
  rank: number;
}

// ── Value formatting ─────────────────────────────────────────────────────────
// Formats a RAW number for display. The old screen stored pre-formatted strings
// like "1.2B" and re-parsed them with a unit-guessing helper, which silently
// mis-scaled anything without a suffix. Real numbers flow through here instead.

/** Compact count/value (1.2B, 945.0M, 12.3K). */
function formatCompact(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return '—';
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toFixed(n < 10 ? 2 : 0);
}

/** Traded value with the market's currency prefix. */
function formatTurnover(n: number, currency: string): string {
  if (!Number.isFinite(n) || n <= 0) return '—';
  const prefix = currency && currency !== '$' ? `${currency} ` : '$';
  if (n >= 1e12) return `${prefix}${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `${prefix}${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${prefix}${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${prefix}${(n / 1e3).toFixed(1)}K`;
  return `${prefix}${n.toFixed(2)}`;
}

/** Currency-prefixed price at a sensible precision. */
function formatPrice(p: number, currency: string): string {
  const prefix = currency && currency !== '$' ? `${currency} ` : '$';
  if (!Number.isFinite(p)) return '—';
  return p >= 1
    ? `${prefix}${p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : `${prefix}${p.toFixed(4)}`;
}

class PhysicsBubble {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  targetRadius: number;
  data: BubbleData;
  isHovered: boolean = false;
  isDragged: boolean = false;

  constructor(x: number, y: number, radius: number, data: BubbleData) {
    this.x = x;
    this.y = y;
    this.vx = (Math.random() - 0.5) * 1.2;
    this.vy = (Math.random() - 0.5) * 1.2;
    this.radius = 1; // Scale up animation on mount
    this.targetRadius = radius;
    this.data = data;
  }

  /**
   * The bubble's bottom label. Always the 24h TRADED VALUE (turnover) — the
   * metric the screen is about. Shows "—" rather than a fake figure when the
   * instrument has no volume, so an empty row is never mistaken for real data.
   */
  get volumeLabel(): string {
    return formatTurnover(this.data.turnover, this.currency);
  }

  /** Currency prefix, set once by the screen for the selected market. */
  currency: string = '$';

  update(width: number, height: number, gravityType: 'single' | 'performers' | 'rank', speedMult: number) {
    if (this.radius < this.targetRadius) {
      this.radius += (this.targetRadius - this.radius) * 0.08;
    } else if (this.radius > this.targetRadius) {
      this.radius += (this.targetRadius - this.radius) * 0.08;
    }

    if (this.isDragged) return;

    // Center pull gravity variations
    if (gravityType === 'performers') {
      const isPositive = this.data.changePercent >= 0;
      const targetX = isPositive ? width * 0.72 : width * 0.28;
      const targetY = height / 2;
      this.vx += (targetX - this.x) * 0.001 * speedMult;
      this.vy += (targetY - this.y) * 0.001 * speedMult;
    } else if (gravityType === 'rank') {
      const isTopTier = (this.data.rank ?? 999) <= 30;
      const targetX = width / 2;
      const targetY = isTopTier ? height * 0.3 : height * 0.7;
      this.vx += (targetX - this.x) * 0.001 * speedMult;
      this.vy += (targetY - this.y) * 0.001 * speedMult;
    } else {
      const targetX = width / 2;
      const targetY = height / 2;
      this.vx += (targetX - this.x) * 0.00015 * speedMult;
      this.vy += (targetY - this.y) * 0.00015 * speedMult;
    }

    // Smooth Brownian drift
    this.vx += (Math.random() - 0.5) * 0.025 * speedMult;
    this.vy += (Math.random() - 0.5) * 0.025 * speedMult;

    // Fluid drag / dampening for smooth floating effect
    this.vx *= 0.982;
    this.vy *= 0.982;

    this.x += this.vx * speedMult;
    this.y += this.vy * speedMult;

    // Boundary bounces with comfortable padding
    const pad = this.radius + 6;
    if (this.x < pad) {
      this.x = pad;
      this.vx *= -0.55;
    } else if (this.x > width - pad) {
      this.x = width - pad;
      this.vx *= -0.55;
    }
    if (this.y < pad) {
      this.y = pad;
      this.vy *= -0.55;
    } else if (this.y > height - pad) {
      this.y = height - pad;
      this.vy *= -0.55;
    }
  }

  draw(ctx: CanvasRenderingContext2D, matchesSearch: boolean) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);

    // Dynamic brand colors with thin, soft borders
    let fillColor = 'rgba(75, 85, 99, 0.08)';
    let strokeColor = 'rgba(107, 114, 128, 0.25)';
    let labelColor = '#9ca3af';

    if (this.data.changePercent > 0) {
      // Translucent bright green branding outline
      fillColor = 'rgba(180, 255, 66, 0.12)';
      strokeColor = 'rgba(180, 255, 66, 0.35)';
      labelColor = '#b4ff42';
    } else if (this.data.changePercent < 0) {
      // Translucent crimson red outline
      fillColor = 'rgba(255, 74, 74, 0.12)';
      strokeColor = 'rgba(255, 74, 74, 0.35)';
      labelColor = '#ff4a4a';
    }

    ctx.fillStyle = fillColor;
    ctx.strokeStyle = strokeColor;

    // Hover design highlights
    if (this.isHovered) {
      ctx.shadowColor = this.data.changePercent >= 0 ? '#7aff77' : '#ff4a4a';
      ctx.shadowBlur = 14;
      ctx.lineWidth = 1.6;
      ctx.strokeStyle = this.data.changePercent >= 0 ? '#7aff77' : '#ff4a4a';
    } else {
      ctx.shadowBlur = 0;
      ctx.lineWidth = 0.95; // Thinner border style
    }

    if (!matchesSearch) {
      ctx.globalAlpha = 0.12;
    }

    // Frosted-glass look via a soft radial gradient (cheap — no ctx.filter blur).
    const glow = ctx.createRadialGradient(
      this.x - this.radius * 0.3,
      this.y - this.radius * 0.3,
      this.radius * 0.1,
      this.x,
      this.y,
      this.radius
    );
    glow.addColorStop(0, 'rgba(255,255,255,0.16)');
    glow.addColorStop(0.5, 'rgba(255,255,255,0.05)');
    glow.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = glow;
    ctx.fill();

    ctx.fillStyle = fillColor;
    ctx.fill();
    ctx.stroke();

    // Render Text Labels (Proportional monospace ratios)
    ctx.shadowBlur = 0;
    ctx.globalAlpha = matchesSearch ? 1.0 : 0.12;
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    if (this.radius > 34) {
      ctx.font = `bold ${Math.max(9, Math.min(15, this.radius * 0.32))}px monospace`;
      ctx.fillText(this.data.symbol, this.x, this.y - 12);

      ctx.font = `600 ${Math.max(8, Math.min(11, this.radius * 0.22))}px monospace`;
      const pct = (this.data.changePercent >= 0 ? '+' : '') + this.data.changePercent.toFixed(2) + '%';
      ctx.fillStyle = labelColor;
      ctx.fillText(pct, this.x, this.y + 2);

      // 24h traded value on the bottom line of the bubble
      ctx.font = `600 ${Math.max(7, Math.min(10, this.radius * 0.2))}px monospace`;
      ctx.fillStyle = '#cbd5e1';
      ctx.fillText(this.volumeLabel, this.x, this.y + 14);
    } else if (this.radius > 26) {
      ctx.font = `bold ${Math.max(9, Math.min(15, this.radius * 0.32))}px monospace`;
      ctx.fillText(this.data.symbol, this.x, this.y - 9);

      ctx.font = `600 ${Math.max(8, Math.min(11, this.radius * 0.22))}px monospace`;
      const pct = (this.data.changePercent >= 0 ? '+' : '') + this.data.changePercent.toFixed(2) + '%';
      ctx.fillStyle = labelColor;
      ctx.fillText(pct, this.x, this.y + 3);

      // 24h traded value on the bottom line of the bubble
      ctx.font = `600 ${Math.max(7, Math.min(10, this.radius * 0.2))}px monospace`;
      ctx.fillStyle = '#cbd5e1';
      ctx.fillText(this.volumeLabel, this.x, this.y + 13);
    } else if (this.radius > 13) {
      ctx.font = `bold ${Math.max(8, Math.min(11, this.radius * 0.45))}px monospace`;
      ctx.fillText(this.data.symbol, this.x, this.y - 4);

      ctx.font = `600 ${Math.max(6, Math.min(9, this.radius * 0.26))}px monospace`;
      ctx.fillStyle = '#cbd5e1';
      ctx.fillText(this.volumeLabel, this.x, this.y + 6);
    } else {
      // Tiny bubbles — just the symbol
      ctx.font = `bold ${Math.max(6, Math.min(9, this.radius * 0.5))}px monospace`;
      ctx.fillText(this.data.symbol, this.x, this.y);
    }

    ctx.restore();
  }
}

interface MarketBubblesProps {
  onAnalyzeTicker: (ticker: string) => void;
  active?: boolean;
}

const BUBBLE_CURRENCY: Record<string, string> = {
  US: 'USD',
  USA: 'USD',
  PK: 'PKR',
  IN: 'INR',
  CN: 'CNY',
  TW: 'TWD',
  HK: 'HKD',
  JP: 'JPY',
  KR: 'KRW',
  UK: 'GBP',
  DE: 'EUR',
  FR: 'EUR',
  NL: 'EUR',
  TR: 'TRY',
  SG: 'SGD',
  MY: 'MYR',
  AU: 'AUD',
  CA: 'CAD',
  BR: 'BRL',
  MX: 'MXN',
  SA: 'SAR',
  AE: 'AED',
  ZA: 'ZAR',
  EG: 'EGP',
  RU: 'RUB',
  ID: 'IDR',
  TH: 'THB',
  VN: 'VND',
  CRYPTO: '$',
};

const bubbleCurrencyFor = (market: string) => BUBBLE_CURRENCY[market.toUpperCase()] || '$';

export function MarketBubbles({ onAnalyzeTicker, active = true }: MarketBubblesProps) {
  
  // Basic query filters
  const [searchQuery, setSearchQuery] = useState('');
  // How many of the market's most-traded instruments to draw as bubbles.
  // The server caps the heatmap payload at MAX_LIMIT (220).
  const [topN, setTopN] = useState<number>(60);
  // Goal of this screen: compare which instrument moves the most value —
  // default to the real traded value (turnover), not a re-scaled proxy.
  const [sizeMetric, setSizeMetric] = useState<'marketCap' | 'turnover' | 'change'>('turnover');
  const [gravityType, setGravityType] = useState<'single' | 'performers' | 'rank'>('single');
  const [loading, setLoading] = useState(false);
  const [rawList, setRawList] = useState<BubbleData[]>([]);
  // Whole-market turnover profile (all priced instruments, not just the bubbles).
  const [volumeSummary, setVolumeSummary] = useState<VolumeSummary | null>(null);
  // True when the market genuinely has no priced instruments in JDDS.
  const [unavailable, setUnavailable] = useState(false);
  // Selected market id — the heatmap market list is the source of truth. The
  // initial value follows the user's shared market preference (last explicit
  // choice → locale), NOT a hard-coded CRYPTO, so the Bubbles page agrees with
  // whatever country the user picked on the Screener.
  const [selectedMarket, setSelectedMarket] = useState<string>(() => resolveUserMarket());

  // Advanced filters
  const [selectedSector, setSelectedSector] = useState<string>('All');
  const [selectedPerformance, setSelectedPerformance] = useState<string>('All');
  const [selectedRankTier, setSelectedRankTier] = useState<string>('All');
  const [selectedVolumeTier, setSelectedVolumeTier] = useState<string>('All');

  // Slider adjustments (Bubble Scale defaults to 1.4 / 140%)
  const [speedMultiplier, setSpeedMultiplier] = useState<number>(0.9);
  const [bubbleSizeMultiplier, setBubbleSizeMultiplier] = useState<number>(1.4);

  // Zoom scale state (Initial scale defaults to 1.4 / 140%)
  const [zoomScale, setZoomScale] = useState(1.4);

  // Table sorting state
  const [sortField, setSortField] = useState<'rank' | 'symbol' | 'price' | 'changePercent' | 'marketCap' | 'turnover'>('turnover');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  // Table pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);

  // Simulation states
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const bubblesRef = useRef<PhysicsBubble[]>([]);
  const animationRef = useRef<number | null>(null);

  // Hovered bubble state
  const [hoveredData, setHoveredData] = useState<BubbleData | null>(null);
  const [hoverPos, setHoverPos] = useState({ x: 0, y: 0 });

  // Drag state
  const dragRef = useRef<{ bubble: PhysicsBubble; offsetX: number; offsetY: number } | null>(null);
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);
  const hasMovedRef = useRef<boolean>(false);

  const currency = bubbleCurrencyFor(selectedMarket);
  const marketLabel = heatmapMeta(selectedMarket).country;

  // Load bubble data for the selected market from JDDS via /api/heatmap — the
  // SAME route the Command Center heatmap uses. `volume=1` additionally returns
  // a whole-market turnover summary over every priced instrument.
  // silent=true skips the TopLoader (background poll over live bubbles).
  const loadMarketData = async (market: string, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await fetch(
        `/api/heatmap?market=${encodeURIComponent(market)}&limit=${topN}&volume=1`,
      );
      if (!res.ok) throw new Error(`heatmap HTTP ${res.status}`);
      const data = (await res.json()) as HeatmapPayload;

      // Flatten the sector-grouped payload into a bubble list. Rank by traded
      // value so "rank 1" is the market's most-traded instrument.
      const flat: HeatmapStock[] = (data.sectors ?? []).flatMap(s => s.stocks ?? []);
      const mapped: BubbleData[] = flat
        .filter(s => s.price > 0)
        .map(s => ({
          symbol: s.symbol,
          name: s.name,
          price: s.price,
          changePercent: s.changePct,
          volumeRaw: s.volume ?? 0,
          marketCapRaw: s.rawMarketCap ?? s.marketCap ?? 0,
          turnover: turnoverFor(s.volume ?? 0, s.price, market),
          sector: s.sector || 'Other',
          rank: 0,
        }))
        .sort((a, b) => b.turnover - a.turnover)
        .map((b, i) => ({ ...b, rank: i + 1 }));

      // A silent refresh must not blow away a live board on a transient failure.
      if (mapped.length > 0 || !silent) {
        setRawList(mapped);
        setUnavailable(mapped.length === 0);
        setVolumeSummary(data.volume ?? null);
      }
    } catch (e) {
      // Never substitute invented data. On a silent poll keep the current board;
      // on an initial load show the UNAVAILABLE state.
      if (silent) {
        console.warn('[bubbles] poll fetch failed, keeping current data', e);
      } else {
        console.error('Failed to load market bubble data', e);
        setRawList([]);
        setVolumeSummary(null);
        setUnavailable(true);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  };

  // Switch market and reload data.
  const handleMarketChange = (market: string) => {
    setUserMarket(market);
    setSelectedMarket(market);
    setSearchQuery('');
    setSelectedSector('All');
    setSelectedPerformance('All');
    setSelectedRankTier('All');
    setSelectedVolumeTier('All');
    setRawList([]);
    setVolumeSummary(null);
    loadMarketData(market);
  };

  // Memoized lists of available sectors for filters
  const sectorsList = useMemo(() => {
    const list = new Set<string>();
    rawList.forEach(c => {
      if (c.sector) list.add(c.sector);
    });
    return ['All', ...Array.from(list)];
  }, [rawList]);

  // Filters computed list based on selectors
  const filteredAssets = useMemo(() => {
    return rawList.filter(c => {
      // Sector filter
      if (selectedSector !== 'All' && c.sector !== selectedSector) return false;
      
      // Performance filter
      if (selectedPerformance === 'gainers' && c.changePercent <= 0) return false;
      if (selectedPerformance === 'losers' && c.changePercent >= 0) return false;
      if (selectedPerformance === 'bigGainers' && c.changePercent <= 5) return false;
      if (selectedPerformance === 'bigLosers' && c.changePercent >= -5) return false;

      // Rank Range filter
      const r = c.rank ?? 999;
      if (selectedRankTier === 'top10' && r > 10) return false;
      if (selectedRankTier === 'top50' && r > 50) return false;
      if (selectedRankTier === 'top100' && r > 100) return false;
      if (selectedRankTier === 'mid' && (r <= 100 || r > 200)) return false;
      if (selectedRankTier === 'small' && r <= 200) return false;

      // Turnover Range filter — thresholds on traded value (market currency),
      // so a "high volume" pick means the same thing whether the market quotes
      // in USD, PKR or IDR.
      const tv = c.turnover;
      if (selectedVolumeTier === 'ultra' && tv < 1e9) return false;
      if (selectedVolumeTier === 'high' && (tv < 1e8 || tv >= 1e9)) return false;
      if (selectedVolumeTier === 'medium' && (tv < 1e7 || tv >= 1e8)) return false;
      if (selectedVolumeTier === 'low' && tv >= 1e7) return false;
      
      return true;
    });
  }, [rawList, selectedSector, selectedPerformance, selectedRankTier, selectedVolumeTier]);

  // Sync new data into existing physics objects to keep trajectory
  const syncBubbles = (cryptos: BubbleData[]) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const width = canvas.width / window.devicePixelRatio;
    const height = canvas.height / window.devicePixelRatio;

    // Scaling factors are computed on RAW numbers — no string re-parsing.
    const maxMC = Math.max(...cryptos.map(c => c.marketCapRaw), 1);
    const maxTurnover = Math.max(...cryptos.map(c => c.turnover), 1);
    const maxChange = Math.max(...cryptos.map(c => Math.abs(c.changePercent)), 1);

    const getTargetRadius = (c: BubbleData) => {
      // Default to the smallest bubble when the chosen metric is missing for
      // this instrument, rather than pretending it sits in the middle.
      let relativeValue = 0;
      if (sizeMetric === 'marketCap') {
        relativeValue = c.marketCapRaw > 0 ? c.marketCapRaw / maxMC : 0;
      } else if (sizeMetric === 'turnover') {
        relativeValue = c.turnover > 0 ? c.turnover / maxTurnover : 0;
      } else {
        relativeValue = Math.abs(c.changePercent) / maxChange;
      }
      
      // Declutter size boundaries: scaled by size multiplier
      const baseMin = 10;
      const baseMax = 38;
      return (baseMin + Math.pow(relativeValue, 0.45) * baseMax) * bubbleSizeMultiplier;
    };

    const existing = bubblesRef.current;
    const updated: PhysicsBubble[] = [];

    cryptos.forEach((c) => {
      const radius = getTargetRadius(c);
      const prev = existing.find(eb => eb.data.symbol === c.symbol);

      if (prev) {
        prev.data = c;
        prev.targetRadius = radius;
        prev.currency = currency;
        updated.push(prev);
      } else {
        // Spawn scattered around center
        const x = width / 2 + (Math.random() - 0.5) * 160;
        const y = height / 2 + (Math.random() - 0.5) * 160;
        const b = new PhysicsBubble(x, y, radius, c);
        b.currency = currency;
        updated.push(b);
      }
    });

    bubblesRef.current = updated;
  };

  // Sync physics objects when lists, metrics, sizes, or the market change
  // (the market drives the currency prefix drawn on each bubble).
  useEffect(() => {
    if (rawList.length > 0) {
      syncBubbles(filteredAssets);
    }
    // syncBubbles is stable per-render and reads current state internally.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sizeMetric, rawList, filteredAssets, bubbleSizeMultiplier, currency]);

  // Init live poll — initial load shows the loader, refreshes are silent.
  useEffect(() => {
    loadMarketData(selectedMarket);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMarket, topN]);
  useActiveInterval(active, () => loadMarketData(selectedMarket, true), 20000);

  // Reset page position to 1 when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, selectedSector, selectedPerformance, selectedRankTier, selectedVolumeTier]);

  // Keep the table showing the whole top-N set by default when Top N changes.
  useEffect(() => {
    setItemsPerPage(topN);
    setCurrentPage(1);
  }, [topN]);

  // Main Canvas loop and Physics simulation
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Resize handler
    const handleResize = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * window.devicePixelRatio;
      canvas.height = rect.height * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };
    handleResize();
    window.addEventListener('resize', handleResize);

    // Bind wheel zoom manually
    const handleWheelEvent = (e: WheelEvent) => {
      e.preventDefault();
      const zoomFactor = 1.08;
      if (e.deltaY < 0) {
        setZoomScale(prev => Math.min(2.5, prev * zoomFactor));
      } else {
        setZoomScale(prev => Math.max(0.3, prev / zoomFactor));
      }
    };
    canvas.addEventListener('wheel', handleWheelEvent, { passive: false });

    const simulate = () => {
      const w = canvas.width / window.devicePixelRatio;
      const h = canvas.height / window.devicePixelRatio;

      ctx.clearRect(0, 0, w, h);

      const bubbles = bubblesRef.current;

      // Spatial-hash grid collision detection (O(n) instead of O(n^2)).
      // Cell size = max radius * 2 so only neighbor cells can overlap.
      let cellSize = 8;
      for (let i = 0; i < bubbles.length; i++) {
        const r = bubbles[i].radius;
        if (r > cellSize) cellSize = r;
      }
      cellSize *= 2;
      const grid = new Map<number, number[]>();
      for (let i = 0; i < bubbles.length; i++) {
        const b = bubbles[i];
        const cx = (b.x / cellSize) | 0;
        const cy = (b.y / cellSize) | 0;
        const key = cx * 73856093 ^ cy * 19349663;
        const bucket = grid.get(key);
        if (bucket) bucket.push(i);
        else grid.set(key, [i]);
      }

      // Handle circle-to-circle collisions
      for (let i = 0; i < bubbles.length; i++) {
        const b1 = bubbles[i];
        const gx = (b1.x / cellSize) | 0;
        const gy = (b1.y / cellSize) | 0;

        // Only check bubbles in the 3x3 neighborhood of this cell.
        for (let ox = -1; ox <= 1; ox++) {
          for (let oy = -1; oy <= 1; oy++) {
            const key = (gx + ox) * 73856093 ^ (gy + oy) * 19349663;
            const bucket = grid.get(key);
            if (!bucket) continue;
            for (let k = 0; k < bucket.length; k++) {
              const j = bucket[k];
              if (j <= i) continue; // each pair once
              const b2 = bubbles[j];

              const dx = b2.x - b1.x;
              const dy = b2.y - b1.y;
              const dist = Math.hypot(dx, dy);
              const minDist = b1.radius + b2.radius;

              if (dist < minDist) {
                // Push out overlap
                const overlap = minDist - dist;
                const nx = dx / (dist || 1);
                const ny = dy / (dist || 1);

                // Resolve overlapping coordinate positions
                if (!b1.isDragged) {
                  b1.x -= nx * overlap * 0.42;
                  b1.y -= ny * overlap * 0.42;
                }
                if (!b2.isDragged) {
                  b2.x += nx * overlap * 0.42;
                  b2.y += ny * overlap * 0.42;
                }

                // Smoother elastic bounce velocities transfer
                const kx = b1.vx - b2.vx;
                const ky = b1.vy - b2.vy;
                const p = 2 * (nx * kx + ny * ky) / 2;

                if (!b1.isDragged) {
                  b1.vx -= nx * p * 0.45;
                  b1.vy -= ny * p * 0.45;
                }
                if (!b2.isDragged) {
                  b2.vx += nx * p * 0.45;
                  b2.vy += ny * p * 0.45;
                }
              }
            }
          }
        }
      }

      ctx.save();
      // Apply center scaling
      ctx.translate(w / 2, h / 2);
      ctx.scale(zoomScale, zoomScale);
      ctx.translate(-w / 2, -h / 2);

      // Update positions and Draw bubbles
      bubbles.forEach((b) => {
        b.update(w, h, gravityType, speedMultiplier);
        const matches = searchQuery ? b.data.symbol.includes(searchQuery) : true;
        b.draw(ctx, matches);
      });

      ctx.restore();

      animationRef.current = requestAnimationFrame(simulate);
    };

    simulate();

    return () => {
      window.removeEventListener('resize', handleResize);
      canvas.removeEventListener('wheel', handleWheelEvent);
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [gravityType, searchQuery, zoomScale, speedMultiplier]);

  // Pointer event listeners (Inverse-transformed for zoom)
  const getCanvasMousePos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const clientY = e.clientY - rect.top;
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;
    return {
      x: (clientX - w / 2) / zoomScale + w / 2,
      y: (clientY - h / 2) / zoomScale + h / 2
    };
  };

  const handlePointerDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getCanvasMousePos(e);
    const bubbles = bubblesRef.current;

    // Find clicked bubble
    const hit = bubbles.find(b => Math.hypot(b.x - x, b.y - y) < b.radius);
    if (hit) {
      dragRef.current = {
        bubble: hit,
        offsetX: x - hit.x,
        offsetY: y - hit.y
      };
      dragStartRef.current = { x, y };
      hasMovedRef.current = false;
      hit.isDragged = true;
      hit.vx = 0;
      hit.vy = 0;
    } else {
      dragStartRef.current = null;
      hasMovedRef.current = false;
    }
  };

  const handlePointerMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getCanvasMousePos(e);
    const drag = dragRef.current;

    if (drag) {
      // Check if mouse moved significantly to count as drag
      if (dragStartRef.current) {
        const dist = Math.hypot(x - dragStartRef.current.x, y - dragStartRef.current.y);
        if (dist > 5) {
          hasMovedRef.current = true;
        }
      }
      // Perform drag movement
      drag.bubble.x = x - drag.offsetX;
      drag.bubble.y = y - drag.offsetY;
      drag.bubble.vx = 0;
      drag.bubble.vy = 0;
      setHoverPos({ x: e.clientX + 15, y: e.clientY + 15 });
    } else {
      // Perform hover tracking
      const bubbles = bubblesRef.current;
      let matchedHover = false;

      bubbles.forEach((b) => {
        const dist = Math.hypot(b.x - x, b.y - y);
        if (dist < b.radius) {
          b.isHovered = true;
          setHoveredData(b.data);
          setHoverPos({ x: e.clientX + 15, y: e.clientY + 15 });
          matchedHover = true;
        } else {
          b.isHovered = false;
        }
      });

      if (!matchedHover) {
        setHoveredData(null);
      }
    }
  };

  const handlePointerUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    if (drag) {
      drag.bubble.isDragged = false;
      const { x, y } = getCanvasMousePos(e);
      drag.bubble.vx = (x - (drag.bubble.x + drag.offsetX)) * 0.15;
      drag.bubble.vy = (y - (drag.bubble.y + drag.offsetY)) * 0.15;

      // Click to analyze ONLY if it did not move much (simple click/tap)
      if (!hasMovedRef.current) {
        onAnalyzeTicker(drag.bubble.data.symbol);
      }

      dragRef.current = null;
      dragStartRef.current = null;
      hasMovedRef.current = false;
    }
  };

  const resetSimulationPhysics = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;

    bubblesRef.current.forEach((b) => {
      b.x = w / 2 + (Math.random() - 0.5) * 160;
      b.y = h / 2 + (Math.random() - 0.5) * 160;
      b.vx = (Math.random() - 0.5) * 2;
      b.vy = (Math.random() - 0.5) * 2;
    });
  };

  // Sort and filter table list (Applies both global search + advanced dropdown selections)
  const filteredAndSortedList = useMemo(() => {
    let list = [...filteredAssets];
    if (searchQuery) {
      list = list.filter(
        c => c.symbol.toLowerCase().includes(searchQuery.toLowerCase()) || 
             c.name.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }
    return list.sort((a, b) => {
      // Sort on RAW numbers. `marketCap`/`turnover` read the raw fields rather
      // than the display strings, so the order matches the values shown.
      let aVal: number;
      let bVal: number;
      if (sortField === 'marketCap') {
        aVal = a.marketCapRaw;
        bVal = b.marketCapRaw;
      } else if (sortField === 'turnover') {
        aVal = a.turnover;
        bVal = b.turnover;
      } else if (sortField === 'rank') {
        aVal = a.rank;
        bVal = b.rank;
      } else if (sortField === 'symbol') {
        return sortOrder === 'asc'
          ? a.symbol.localeCompare(b.symbol)
          : b.symbol.localeCompare(a.symbol);
      } else {
        aVal = a[sortField];
        bVal = b[sortField];
      }

      if (aVal < bVal) return sortOrder === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortOrder === 'asc' ? 1 : -1;
      return 0;
    });
  }, [filteredAssets, searchQuery, sortField, sortOrder]);

  // Paginate table list slice
  const paginatedList = useMemo(() => {
    const startIndex = (currentPage - 1) * itemsPerPage;
    return filteredAndSortedList.slice(startIndex, startIndex + itemsPerPage);
  }, [filteredAndSortedList, currentPage, itemsPerPage]);

  const totalPages = useMemo(() => {
    return Math.max(1, Math.ceil(filteredAndSortedList.length / itemsPerPage));
  }, [filteredAndSortedList, itemsPerPage]);

  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const filterRef = useRef<HTMLSelectElement>(null);
  usePageShortcuts(rootRef, [
    { id: 'bubbles.search', label: 'Search assets', keys: 'S', run: () => searchRef.current?.focus() },
    { id: 'bubbles.filters', label: 'Focus sector filter', keys: 'Shift+F', run: () => filterRef.current?.focus() },
  ]);

  const toggleSort = (field: typeof sortField) => {
    if (sortField === field) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('desc'); // Default to high-to-low
    }
  };

  return (
    <>
      {loading && <TopLoader />}
      <div ref={rootRef} data-keyboard-scope="Market bubbles" className="flex-1 w-full px-4 md:px-8 py-6 space-y-6 flex flex-col pb-20 select-none overflow-y-auto">
        
        {/* Title Header Section */}
        <PageHeader
          icon={Orbit}
          title="Market Bubbles"
          description="Live turnover map from JDDS — every bubble is a real priced instrument, sized by 24h traded value."
          size="lg"
          iconClassName="animate-spin-slow"
          className="animate-fade-in-up pb-4 border-border/20 shrink-0"
          actions={
            <div className="flex items-center justify-end gap-3 flex-wrap">
            {/* Market Selector — the same market list the heatmaps use. */}
            <div className="flex items-center gap-2 glass-card-subtle p-1.5 rounded-3xl border border-border/40 shrink-0">
              <span className="text-[10px] uppercase font-bold text-muted-foreground/80 px-2 tracking-wider">Market:</span>
              <select
                value={selectedMarket}
                onChange={e => handleMarketChange(e.target.value)}
                className="bg-background border border-border/60 hover:border-primary/50 rounded-3xl px-3 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary outline-none transition-all cursor-pointer font-semibold"
                title="Select the market to map"
              >
                {HEATMAP_MARKETS.map(m => (
                  <option key={m.id} value={m.id}>{m.country} — {m.index}</option>
                ))}
              </select>
            </div>

            {/* How many of the market's most-traded instruments to draw */}
            <div className="flex items-center gap-2 glass-card-subtle p-1.5 rounded-3xl border border-border/40 shrink-0">
              <span className="text-[10px] uppercase font-bold text-muted-foreground/80 px-2 tracking-wider">Top:</span>
              <select
                value={topN}
                onChange={e => setTopN(Number(e.target.value))}
                className="bg-background border border-border/60 hover:border-primary/50 rounded-3xl px-3 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary outline-none transition-all cursor-pointer font-semibold"
                title="Draw the N most-traded instruments in this market"
              >
                {[20, 40, 60, 100, 140, 220].map(n => (
                  <option key={n} value={n} className="bg-[#121212] text-foreground">
                    Top {n} (by turnover)
                  </option>
                ))}
              </select>
            </div>

            {/* Search tool */}
            <div className="relative w-64 shrink-0">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
              <input
                ref={searchRef}
                type="text"
                placeholder="Search / Highlight Asset..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value.toUpperCase())}
                className="w-full glass-card-subtle border border-border/40 rounded-xl pl-9 pr-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary placeholder:text-muted-foreground/60 transition-all font-mono"
              />
            </div>
            </div>
          }
        />

        {/* Filters Banner (Row 1) */}
        <div className="flex flex-wrap items-center gap-4 glass-card-subtle border border-white/5 rounded-2xl p-4 shrink-0 text-xs">
          
          {/* Sector Category Filter */}
          <div className="flex items-center gap-2 border-r border-white/5 pr-4">
            <Filter size={12} className="text-muted-foreground" />
            <span className="text-muted-foreground font-semibold">Sector:</span>
            <select
              ref={filterRef}
              value={selectedSector}
              onChange={e => setSelectedSector(e.target.value)}
              className="bg-black/40 border border-white/10 rounded-lg px-2.5 py-1 text-[11px] font-mono text-foreground focus:outline-none focus:border-primary/50 cursor-pointer"
            >
              {sectorsList.map(sec => (
                <option key={sec} value={sec} className="bg-[#121212] text-foreground">
                  {sec === 'All' ? 'All Sectors' : sec}
                </option>
              ))}
            </select>
          </div>

          {/* Performance Threshold Filter */}
          <div className="flex items-center gap-2 border-r border-white/5 pr-4">
            <span className="text-muted-foreground font-semibold">Performance:</span>
            <select
              value={selectedPerformance}
              onChange={e => setSelectedPerformance(e.target.value)}
              className="bg-black/40 border border-white/10 rounded-lg px-2.5 py-1 text-[11px] font-mono text-foreground focus:outline-none focus:border-primary/50 cursor-pointer"
            >
              <option value="All" className="bg-[#121212] text-foreground">All Ranges</option>
              <option value="gainers" className="bg-[#121212] text-primary">Gainers (&gt; 0%)</option>
              <option value="bigGainers" className="bg-[#121212] text-primary font-bold">Big Gainers (&gt; 5%)</option>
              <option value="losers" className="bg-[#121212] text-rose-400">Losers (&lt; 0%)</option>
              <option value="bigLosers" className="bg-[#121212] text-rose-400 font-bold">Big Losers (&lt; -5%)</option>
            </select>
          </div>

          {/* Rank Range Filter */}
          <div className="flex items-center gap-2 border-r border-white/5 pr-4">
            <TrendingUp size={12} className="text-muted-foreground" />
            <span className="text-muted-foreground font-semibold">Rank Tier:</span>
            <select
              value={selectedRankTier}
              onChange={e => setSelectedRankTier(e.target.value)}
              className="bg-black/40 border border-white/10 rounded-lg px-2.5 py-1 text-[11px] font-mono text-foreground focus:outline-none focus:border-primary/50 cursor-pointer"
            >
              <option value="All" className="bg-[#121212] text-foreground">All Ranks</option>
              <option value="top10" className="bg-[#121212] text-foreground">Top 10 (Mega)</option>
              <option value="top50" className="bg-[#121212] text-foreground">Top 50</option>
              <option value="top100" className="bg-[#121212] text-foreground">Top 100</option>
              <option value="mid" className="bg-[#121212] text-foreground">Ranks 101-200</option>
              <option value="small" className="bg-[#121212] text-foreground">Ranks 201+</option>
            </select>
          </div>

          {/* Traded-value (turnover) filter — the market-currency figure. */}
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground font-semibold">Traded value:</span>
            <select
              value={selectedVolumeTier}
              onChange={e => setSelectedVolumeTier(e.target.value)}
              className="bg-black/40 border border-white/10 rounded-lg px-2.5 py-1 text-[11px] font-mono text-foreground focus:outline-none focus:border-primary/50 cursor-pointer"
            >
              <option value="All" className="bg-[#121212] text-foreground">All Ranges</option>
              <option value="ultra" className="bg-[#121212] text-foreground">Ultra High (&gt; 1B)</option>
              <option value="high" className="bg-[#121212] text-foreground">High (100M – 1B)</option>
              <option value="medium" className="bg-[#121212] text-foreground">Medium (10M – 100M)</option>
              <option value="low" className="bg-[#121212] text-foreground">Low (&lt; 10M)</option>
            </select>
          </div>
        </div>

        {/* Physics Controls Banner (Row 2) */}
        <div className="flex flex-wrap items-center justify-between gap-4 glass-card-subtle border border-white/5 rounded-2xl p-4 shrink-0 text-xs">
          <div className="flex flex-wrap items-center gap-6">
            
            {/* Split Mode Grouping */}
            <div className="flex items-center gap-2 border-r border-white/5 pr-4">
              <span className="text-muted-foreground font-semibold">Physics Layout:</span>
              <select
                value={gravityType}
                onChange={e => setGravityType(e.target.value as 'single' | 'performers' | 'rank')}
                className="bg-black/40 border border-white/10 rounded-lg px-2.5 py-1 text-[11px] font-mono text-foreground focus:outline-none focus:border-primary/50 cursor-pointer"
              >
                <option value="single" className="bg-[#121212] text-foreground">Single Center Pool</option>
                <option value="performers" className="bg-[#121212] text-foreground">Gainers vs Losers Split</option>
                <option value="rank" className="bg-[#121212] text-foreground">Top 30 Tier vs Mid/Small Caps</option>
              </select>
            </div>

            {/* Sizing Metric */}
            <div className="flex items-center gap-2 border-r border-white/5 pr-4">
              <span className="text-muted-foreground font-semibold">Size By:</span>
              <div className="flex bg-black/40 rounded-lg p-0.5 border border-white/5">
                {[
                  { key: 'turnover', label: 'Traded value', hint: 'Size by 24h traded value (turnover) — comparable across instruments.' },
                  { key: 'marketCap', label: 'Mkt Cap', hint: 'Size by market capitalisation where JDDS has it.' },
                  { key: 'change', label: '% Change', hint: 'Size by absolute 24h percent change.' },
                ].map(opt => (
                  <button
                    key={opt.key}
                    onClick={() => setSizeMetric(opt.key as 'marketCap' | 'turnover' | 'change')}
                    title={opt.hint}
                    className={`px-3 py-1 rounded-md text-[10px] font-mono cursor-pointer transition-all ${
                      sizeMetric === opt.key 
                        ? 'bg-accent text-foreground border border-border/30' 
                        : 'text-muted-foreground hover:text-foreground border border-transparent'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Bubble size scale slider */}
            <div className="flex items-center gap-2 border-r border-white/5 pr-4">
              <Sliders size={12} className="text-muted-foreground" />
              <span className="text-muted-foreground font-semibold">Bubble Scale:</span>
              <input
                type="range"
                min="0.5"
                max="2.0"
                step="0.05"
                value={bubbleSizeMultiplier}
                onChange={e => setBubbleSizeMultiplier(parseFloat(e.target.value))}
                className="w-20 md:w-28 accent-primary cursor-pointer h-1 rounded-lg bg-white/10"
              />
              <span className="font-mono text-muted-foreground text-[10px] min-w-[28px]">
                {Math.round(bubbleSizeMultiplier * 100)}%
              </span>
            </div>

            {/* Physics Drift speed slider */}
            <div className="flex items-center gap-2 border-r border-white/5 pr-4">
              <Gauge size={12} className="text-muted-foreground" />
              <span className="text-muted-foreground font-semibold">Drift Speed:</span>
              <input
                type="range"
                min="0.2"
                max="2.0"
                step="0.1"
                value={speedMultiplier}
                onChange={e => setSpeedMultiplier(parseFloat(e.target.value))}
                className="w-20 md:w-28 accent-primary cursor-pointer h-1 rounded-lg bg-white/10"
              />
              <span className="font-mono text-muted-foreground text-[10px] min-w-[28px]">
                {speedMultiplier.toFixed(1)}x
              </span>
            </div>

            {/* Zoom controls */}
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground font-semibold">Scale:</span>
              <div className="flex items-center bg-black/40 rounded-lg p-0.5 border border-white/5 gap-1">
                <button
                  onClick={() => setZoomScale(prev => Math.max(0.3, prev - 0.15))}
                  className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-white/5 cursor-pointer transition-all"
                  title="Zoom Out"
                >
                  <ZoomOut size={12} />
                </button>
                <span className="px-1.5 text-[10px] font-mono text-primary font-bold min-w-[36px] text-center">
                  {Math.round(zoomScale * 100)}%
                </span>
                <button
                  onClick={() => setZoomScale(prev => Math.min(2.5, prev + 0.15))}
                  className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-white/5 cursor-pointer transition-all"
                  title="Zoom In"
                >
                  <ZoomIn size={12} />
                </button>
                <button
                  onClick={() => setZoomScale(1.4)}
                  className="px-2 py-0.5 rounded text-[9px] font-mono text-muted-foreground hover:text-foreground hover:bg-white/5 cursor-pointer transition-all border-l border-white/5"
                  title="Reset Zoom"
                >
                  Reset
                </button>
              </div>
            </div>

          </div>

          {/* Reset Physics */}
          <div className="flex items-center gap-2">
            <button
              onClick={resetSimulationPhysics}
              className="flex items-center gap-1.5 bg-black/30 hover:bg-black/60 border border-white/5 text-muted-foreground hover:text-foreground px-3.5 py-1.5 rounded-lg font-mono text-[10px] cursor-pointer transition-all"
            >
              <RefreshCw size={11} /> Reset Physics
            </button>
          </div>
        </div>

        {/* Live Canvas Box */}
        <div className="h-[55vh] min-h-[320px] w-full glass-card border border-white/5 rounded-3xl relative overflow-hidden shrink-0 sm:h-[500px] sm:max-h-[500px]">
          {loading && rawList.length === 0 && (
            <div className="absolute inset-0 flex flex-col items-center justify-center z-10 bg-[#050505]/80">
              <Orbit className="text-white/5 w-16 h-16 animate-spin-slow mb-4" />
              <Skeleton className="h-3 w-48" />
            </div>
          )}

          {/* No priced instruments for this market — say so instead of drawing a
              board of invented bubbles. */}
          {!loading && unavailable && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 px-6 text-center">
              <Orbit className="text-muted-foreground/20 w-14 h-14" />
              <p className="max-w-[36ch] text-xs italic text-amber-400/80">
                No priced instruments for {marketLabel} in JDDS yet — nothing to measure.
              </p>
              <p className="text-[10px] text-muted-foreground/60">
                Pick another market, or load this one from Settings › Market Data.
              </p>
            </div>
          )}

          <canvas
            ref={canvasRef}
            onMouseDown={handlePointerDown}
            onMouseMove={handlePointerMove}
            onMouseUp={handlePointerUp}
            onMouseLeave={handlePointerUp}
            className="w-full h-full cursor-grab active:cursor-grabbing block"
          />

          {/* Ambient center instruction — only over a live board. */}
          {rawList.length > 0 && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20 text-[9px] font-mono tracking-widest text-muted-foreground select-none uppercase">
              Drag to throw • Click or use details table to query AI • Wheel to zoom
            </div>
          )}
        </div>

        {/* Volume Analytics — whole-market turnover, not just the bubbles drawn */}
        {volumeSummary ? (
          <VolumeAnalyticsPanel summary={volumeSummary} marketLabel={marketLabel} />
        ) : (
          !loading && rawList.length > 0 && (
            <div className="glass-card border border-white/5 rounded-3xl p-5 shrink-0">
              <p className="text-[11px] italic text-muted-foreground/70">
                Volume Analytics unavailable — JDDS reports no traded volume for {marketLabel}.
              </p>
            </div>
          )
        )}

        {/* Market Details Table */}
        <div className="glass-card border border-white/5 rounded-3xl p-6 space-y-4 shrink-0">
          <div className="flex items-center justify-between border-b border-white/5 pb-3">
            <h2 className="font-serif text-lg font-semibold text-foreground">Market Details Table</h2>
            <span className="text-[10px] text-muted-foreground font-mono bg-white/5 px-2.5 py-1 rounded-full">
              Showing {filteredAndSortedList.length} instruments
            </span>
          </div>

          <div className="overflow-x-auto w-full">
            {loading && rawList.length === 0 ? (
              <div className="space-y-2.5">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-4 h-12 border-b border-white/5">
                    <Skeleton className="h-4 w-8" />
                    <Skeleton className="h-4 w-16" />
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-4 w-20 ml-auto" />
                    <Skeleton className="h-4 w-20" />
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-8 w-24 rounded-lg" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-4">
                <table className="w-full text-left text-xs font-mono border-collapse">
                  <thead>
                    <tr className="border-b border-white/5 text-muted-foreground/80 text-[10px]">
                      <th onClick={() => toggleSort('rank')} className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors">
                        <div className="flex items-center gap-1.5">Rank <ArrowUpDown size={10} /></div>
                      </th>
                      <th onClick={() => toggleSort('symbol')} className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors">
                        <div className="flex items-center gap-1.5">Symbol <ArrowUpDown size={10} /></div>
                      </th>
                      <th className="py-3 px-4">Name</th>
                      <th onClick={() => toggleSort('price')} className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors text-right">
                        <div className="flex items-center justify-end gap-1.5">Price <ArrowUpDown size={10} /></div>
                      </th>
                      <th onClick={() => toggleSort('changePercent')} className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors text-right">
                        <div className="flex items-center justify-end gap-1.5">24h Change <ArrowUpDown size={10} /></div>
                      </th>
                      <th onClick={() => toggleSort('marketCap')} className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors text-right">
                        <div className="flex items-center justify-end gap-1.5">Market Cap <ArrowUpDown size={10} /></div>
                      </th>
                      <th onClick={() => toggleSort('turnover')} className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors text-right">
                        <div className="flex items-center justify-end gap-1.5">24h Traded Value <ArrowUpDown size={10} /></div>
                      </th>
                      <th className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5" title="Raw reported volume: shares, or quote notional for crypto.">
                          {isNotionalVolume(selectedMarket) ? 'Notional' : 'Shares'}
                        </div>
                      </th>
                      <th className="py-3 px-4 text-center">AI Inquire</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedList.length > 0 ? (
                      paginatedList.map((c) => {
                        const isPositive = c.changePercent >= 0;
                        return (
                          <tr key={c.symbol} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors group">
                            <td className="py-3.5 px-4 text-muted-foreground/80">#{c.rank}</td>
                            <td className="py-3.5 px-4 font-bold text-primary tracking-wider">{c.symbol}</td>
                            <td className="py-3.5 px-4 text-muted-foreground font-sans truncate max-w-[150px]">{c.name}</td>
                            <td className="py-3.5 px-4 text-right font-semibold">
                              {formatPrice(c.price, currency)}
                            </td>
                            <td className={`py-3.5 px-4 text-right font-semibold ${isPositive ? 'text-primary' : 'text-rose-400'}`}>
                              {isPositive ? '+' : ''}{c.changePercent.toFixed(2)}%
                            </td>
                            <td className="py-3.5 px-4 text-right text-muted-foreground">
                              {c.marketCapRaw > 0 ? formatTurnover(c.marketCapRaw, currency) : '—'}
                            </td>
                            <td className="py-3.5 px-4 text-right font-semibold">{formatTurnover(c.turnover, currency)}</td>
                            <td className="py-3.5 px-4 text-right text-muted-foreground">{formatCompact(c.volumeRaw)}</td>
                            <td className="py-1 px-4 text-center">
                              <button
                                onClick={() => onAnalyzeTicker(c.symbol)}
                                className="inline-flex items-center gap-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 px-3 py-1.5 rounded-lg text-[10px] cursor-pointer font-semibold transition-all group-hover:scale-105"
                              >
                                <Sparkles size={11} /> Ask AI
                              </button>
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan={9} className="py-8 text-center text-muted-foreground/60">
                          No matching instruments found
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>

                {/* Table Pagination Controls Footer */}
                <div className="flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-white/5 pt-4 text-xs font-mono text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <span>Rows per page:</span>
                    <select
                      value={itemsPerPage}
                      onChange={e => {
                        setItemsPerPage(parseInt(e.target.value));
                        setCurrentPage(1);
                      }}
                      className="bg-black/40 border border-white/10 rounded px-2.5 py-1 text-[11px] font-mono text-foreground focus:outline-none cursor-pointer"
                    >
                      {[10, 25, 50, 100, 220].map(size => (
                        <option key={size} value={size} className="bg-[#121212] text-foreground">
                          {size}
                        </option>
                      ))}
                      {![10, 25, 50, 100, 220].includes(topN) && (
                        <option value={topN} className="bg-[#121212] text-foreground">
                          {topN}
                        </option>
                      )}
                    </select>
                    <span className="ml-2 text-[11px]">
                      Showing {Math.min(filteredAndSortedList.length, (currentPage - 1) * itemsPerPage + 1)}-
                      {Math.min(filteredAndSortedList.length, currentPage * itemsPerPage)} of {filteredAndSortedList.length} instruments
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                      disabled={currentPage === 1}
                      className="px-3 py-1.5 rounded-lg border border-white/5 bg-black/20 hover:bg-black/40 disabled:opacity-40 disabled:hover:bg-black/20 disabled:cursor-not-allowed transition-all cursor-pointer"
                    >
                      Previous
                    </button>
                    <span className="px-3 py-1 bg-white/5 rounded-lg text-foreground text-[11px]">
                      Page {currentPage} of {totalPages}
                    </span>
                    <button
                      onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                      disabled={currentPage === totalPages}
                      className="px-3 py-1.5 rounded-lg border border-white/5 bg-black/20 hover:bg-black/40 disabled:opacity-40 disabled:hover:bg-black/20 disabled:cursor-not-allowed transition-all cursor-pointer"
                    >
                      Next
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Floating Tooltip Detail Card */}
        {hoveredData && (
          <div
            style={{
              position: 'fixed',
              left: `${hoverPos.x}px`,
              top: `${hoverPos.y}px`,
              zIndex: 9999,
            }}
            className="w-56 p-4 rounded-xl border border-border/50 glass-card-strong text-foreground shadow-2xl pointer-events-none text-left flex flex-col gap-2 transition-all duration-100 animate-fade-in"
          >
            <div className="flex items-center justify-between border-b border-border/20 pb-1.5">
              <span className="font-mono text-sm font-bold tracking-wider text-primary">{hoveredData.symbol}</span>
              <span
                className={`font-mono text-xs font-semibold px-2 py-0.5 rounded-full ${
                  hoveredData.changePercent >= 0
                    ? 'bg-emerald-500/10 text-primary border border-primary/20'
                    : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                }`}
              >
                {hoveredData.changePercent >= 0 ? '+' : ''}
                {hoveredData.changePercent}%
              </span>
            </div>

            <div className="space-y-1 text-xs">
              <p className="text-muted-foreground font-semibold truncate leading-tight">{hoveredData.name}</p>
              <p className="text-[9px] uppercase tracking-wider text-muted-foreground/60">{hoveredData.sector} · Rank #{hoveredData.rank}</p>
              <div className="flex justify-between mt-1 text-[11px]">
                <span className="text-muted-foreground">Price:</span>
                <span className="font-mono font-semibold">{formatPrice(hoveredData.price, currency)}</span>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-muted-foreground">Traded value:</span>
                <span className="font-mono font-semibold text-primary">{formatTurnover(hoveredData.turnover, currency)}</span>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-muted-foreground">Mkt Cap:</span>
                <span className="font-mono font-semibold">
                  {hoveredData.marketCapRaw > 0 ? formatTurnover(hoveredData.marketCapRaw, currency) : '—'}
                </span>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-muted-foreground">24h {isNotionalVolume(selectedMarket) ? 'notional' : 'shares'}:</span>
                <span className="font-mono font-semibold">{formatCompact(hoveredData.volumeRaw)}</span>
              </div>
            </div>
            
            <div className="border-t border-border/20 pt-1.5 flex items-center gap-1.5 text-[9px] font-semibold text-primary font-sans">
              <Sparkles size={10} /> Click bubble to query with AI
            </div>
          </div>
        )}

      </div>
    </>
  );
}
