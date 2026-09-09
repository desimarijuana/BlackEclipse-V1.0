'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Search, Sparkles, Orbit, RefreshCw, ZoomIn, ZoomOut, ArrowUpDown, Filter, Gauge, Sliders, TrendingUp } from 'lucide-react';
import { TopLoader } from '@/components/ui/top-loader';
import { Skeleton } from '@/components/ui/skeleton';

interface BubbleData {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  marketCap: string;
  volume: string;
  sector?: string;
  rank?: number;
  circulatingSupply?: string;
  ath?: string;
}

const DEMO_CRYPTOS: BubbleData[] = [
  { symbol: 'BTC', name: 'Bitcoin', price: 67840, changePercent: 2.14, marketCap: '1.32T', volume: '42.1B', sector: 'Layer 1', rank: 1, circulatingSupply: '19.7M', ath: '$73,750' },
  { symbol: 'ETH', name: 'Ethereum', price: 3500.2, changePercent: 2.41, marketCap: '420.1B', volume: '18.5B', sector: 'Layer 1', rank: 2, circulatingSupply: '120.1M', ath: '$4,878' },
  { symbol: 'USDT', name: 'Tether', price: 1.0, changePercent: 0.01, marketCap: '112.3B', volume: '68.4B', sector: 'Stablecoin', rank: 3, circulatingSupply: '112.3B', ath: '$1.10' },
  { symbol: 'BNB', name: 'BNB', price: 585.5, changePercent: 2.11, marketCap: '90.2B', volume: '2.3B', sector: 'Layer 1', rank: 4, circulatingSupply: '153.9M', ath: '$686' },
  { symbol: 'SOL', name: 'Solana', price: 168.4, changePercent: 3.82, marketCap: '77.4B', volume: '4.1B', sector: 'Layer 1', rank: 5, circulatingSupply: '459.2M', ath: '$260' },
  { symbol: 'XRP', name: 'XRP', price: 0.53, changePercent: -0.84, marketCap: '29.1B', volume: '1.4B', sector: 'Payments', rank: 6, circulatingSupply: '55.0B', ath: '$3.40' },
  { symbol: 'USDC', name: 'USD Coin', price: 1.0, changePercent: 0.0, marketCap: '32.2B', volume: '7.2B', sector: 'Stablecoin', rank: 7, circulatingSupply: '32.2B', ath: '$1.17' },
  { symbol: 'ADA', name: 'Cardano', price: 0.45, changePercent: -1.32, marketCap: '16.0B', volume: '0.4B', sector: 'Layer 1', rank: 8, circulatingSupply: '35.5B', ath: '$3.09' },
  { symbol: 'DOGE', name: 'Dogecoin', price: 0.16, changePercent: 1.12, marketCap: '23.1B', volume: '1.8B', sector: 'Meme', rank: 9, circulatingSupply: '143.9B', ath: '$0.73' },
  { symbol: 'AVAX', name: 'Avalanche', price: 35.6, changePercent: 2.8, marketCap: '13.9B', volume: '0.6B', sector: 'Layer 1', rank: 10, circulatingSupply: '391.2M', ath: '$146' },
  { symbol: 'DOT', name: 'Polkadot', price: 6.9, changePercent: 0.42, marketCap: '9.8B', volume: '0.3B', sector: 'Layer 1', rank: 11, circulatingSupply: '1.4B', ath: '$55' },
  { symbol: 'LINK', name: 'Chainlink', price: 14.2, changePercent: 1.9, marketCap: '8.4B', volume: '0.5B', sector: 'Oracle', rank: 12, circulatingSupply: '587M', ath: '$52' },
  { symbol: 'TRX', name: 'TRON', price: 0.13, changePercent: -0.2, marketCap: '11.4B', volume: '0.4B', sector: 'Layer 1', rank: 13, circulatingSupply: '88.0B', ath: '$0.23' },
  { symbol: 'MATIC', name: 'Polygon', price: 0.72, changePercent: 0.95, marketCap: '7.1B', volume: '0.4B', sector: 'Layer 2', rank: 14, circulatingSupply: '9.9B', ath: '$2.92' },
  { symbol: 'LTC', name: 'Litecoin', price: 84.3, changePercent: -0.5, marketCap: '6.3B', volume: '0.5B', sector: 'Payments', rank: 15, circulatingSupply: '74.5M', ath: '$410' },
];

const DEMO_PSX: BubbleData[] = [
  { symbol: 'LUCK', name: 'Lucky Cement', price: 1120.5, changePercent: 1.85, marketCap: '412.3B', volume: '12.4M', sector: 'Materials', rank: 1, circulatingSupply: 'N/A', ath: 'N/A' },
  { symbol: 'HUBC', name: 'Hub Power Company', price: 128.4, changePercent: 0.92, marketCap: '148.2B', volume: '8.1M', sector: 'Utilities', rank: 2, circulatingSupply: 'N/A', ath: 'N/A' },
  { symbol: 'ENGRO', name: 'Engro Corporation', price: 385.2, changePercent: -0.64, marketCap: '201.5B', volume: '5.3M', sector: 'Materials', rank: 3, circulatingSupply: 'N/A', ath: 'N/A' },
  { symbol: 'FFC', name: 'Fauji Fertilizer', price: 342.8, changePercent: 1.12, marketCap: '435.1B', volume: '6.7M', sector: 'Materials', rank: 4, circulatingSupply: 'N/A', ath: 'N/A' },
  { symbol: 'OGDC', name: 'Oil & Gas Development', price: 142.6, changePercent: 0.45, marketCap: '612.8B', volume: '9.2M', sector: 'Energy', rank: 5, circulatingSupply: 'N/A', ath: 'N/A' },
  { symbol: 'SYS', name: 'Systems Limited', price: 645.9, changePercent: 2.34, marketCap: '190.4B', volume: '3.8M', sector: 'Technology', rank: 6, circulatingSupply: 'N/A', ath: 'N/A' },
  { symbol: 'MCB', name: 'MCB Bank', price: 268.3, changePercent: 0.78, marketCap: '318.6B', volume: '4.5M', sector: 'Financials', rank: 7, circulatingSupply: 'N/A', ath: 'N/A' },
  { symbol: 'MARI', name: 'Mari Petroleum', price: 2850.0, changePercent: -1.25, marketCap: '380.2B', volume: '1.9M', sector: 'Energy', rank: 8, circulatingSupply: 'N/A', ath: 'N/A' },
];

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
      fillColor = 'rgba(122, 255, 120, 0.12)';
      strokeColor = 'rgba(122, 255, 120, 0.35)';
      labelColor = '#7aff78';
    } else if (this.data.changePercent < 0) {
      // Translucent crimson red outline
      fillColor = 'rgba(255, 74, 74, 0.12)';
      strokeColor = 'rgba(255, 74, 74, 0.35)';
      labelColor = '#ff4a4a';
    }

    ctx.fillStyle = fillColor;
    ctx.strokeStyle = strokeColor;

    // Frosted-glass effect: blur the bubble body so the backdrop bleeds through
    ctx.filter = this.isHovered ? 'blur(1.5px)' : 'blur(2.5px)';

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

    ctx.fill();
    ctx.stroke();

    // Render Text Labels (Proportional monospace ratios)
    ctx.filter = 'none';
    ctx.shadowBlur = 0;
    ctx.globalAlpha = matchesSearch ? 1.0 : 0.12;
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    if (this.radius > 26) {
      ctx.font = `bold ${Math.max(9, Math.min(15, this.radius * 0.32))}px monospace`;
      ctx.fillText(this.data.symbol, this.x, this.y - 5);
      
      ctx.font = `600 ${Math.max(8, Math.min(11, this.radius * 0.22))}px monospace`;
      const pct = (this.data.changePercent >= 0 ? '+' : '') + this.data.changePercent.toFixed(2) + '%';
      ctx.fillStyle = labelColor;
      ctx.fillText(pct, this.x, this.y + 10);
    } else if (this.radius > 13) {
      ctx.font = `bold ${Math.max(8, Math.min(11, this.radius * 0.45))}px monospace`;
      ctx.fillText(this.data.symbol, this.x, this.y);
    }

    ctx.restore();
  }
}

interface MarketBubblesProps {
  onAnalyzeTicker: (ticker: string) => void;
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

interface MarketOption {
  id: string;
  label: string;
  isCrypto: boolean;
  pricedCount: number;
}

export function MarketBubbles({ onAnalyzeTicker }: MarketBubblesProps) {
  
  // Basic query filters
  const [searchQuery, setSearchQuery] = useState('');
  // Goal of this screen: compare which stock moves the most volume — default to volume sizing.
  const [sizeMetric, setSizeMetric] = useState<'marketCap' | 'volume' | 'change'>('volume');
  const [gravityType, setGravityType] = useState<'single' | 'performers' | 'rank'>('single');
  const [loading, setLoading] = useState(false);
  const [rawList, setRawList] = useState<BubbleData[]>([]);
  // Markets available in JDDS (loaded from /api/markets) + selected market.
  const [markets, setMarkets] = useState<MarketOption[]>([]);
  const [selectedMarket, setSelectedMarket] = useState<string>('CRYPTO');

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
  const [sortField, setSortField] = useState<'rank' | 'symbol' | 'price' | 'changePercent' | 'marketCap' | 'volume'>('rank');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

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

  // Helper: robust parsing of metric strings to numbers
  const parseVal = (val: unknown): number => {
    if (typeof val === 'number') return val;
    if (!val) return 0;
    const str = String(val).toUpperCase().trim();
    const mult = str.endsWith('T') ? 1e12 : str.endsWith('B') ? 1e9 : str.endsWith('M') ? 1e6 : str.endsWith('K') ? 1e3 : 1;
    const num = parseFloat(str.replace(/[TBMK$,]/g, ''));
    return isNaN(num) ? 0 : num * mult;
  };

  // Load bubble data for the selected market from JDDS via /api/stocks.
  // silent=true skips the TopLoader (background 20s poll over live bubbles).
  const loadMarketData = async (market: string, silent = false) => {
    if (!silent) setLoading(true);
    const isCrypto = market.toUpperCase() === 'CRYPTO';
    try {
      // For equities markets, only show stocks (not ETFs/funds/bonds). Markets
      // without securityType metadata skip this filter server-side anyway.
      const typeParam = isCrypto ? '' : '&type=Stock';
      // Order by volume so the most-traded asset leads — that's the point of
      // this screen. /api/stocks maps the market id straight to JDDS.
      const res = await fetch(`/api/stocks?country=${encodeURIComponent(market)}${typeParam}&sort=volume&limit=100`);
      const data = await res.json();
      const fallback = markets.find(m => m.id === market)?.isCrypto ? DEMO_CRYPTOS : DEMO_PSX;
      if (data && Array.isArray(data.stocks) && data.stocks.length > 0) {
        const mapped: BubbleData[] = (data.stocks as Array<Record<string, unknown>>)
          .filter(s => typeof s.price === 'number' && (s.price as number) > 0)
          .map(s => ({
            symbol: String(s.symbol ?? ''),
            name: String(s.name ?? ''),
            price: (s.price as number) || 0,
            changePercent: (s.changePercent as number) || 0,
            marketCap: (s.marketCap as string) || 'N/A',
            volume: (s.volume as string) || 'N/A',
            sector: (s.sector as string) || 'Other',
            rank: (s.rank as number) || 999,
            circulatingSupply: (s.circulatingSupply as string) || 'N/A',
            ath: (s.ath as string) || 'N/A',
          }));
        // If the market returned no priced stocks yet, fall back to demo data so bubbles still render.
        if (mapped.length > 0) {
          setRawList(mapped);
        } else if (!silent || rawList.length === 0) {
          setRawList(isCrypto ? DEMO_CRYPTOS : fallback);
        }
      } else if (!silent || rawList.length === 0) {
        setRawList(isCrypto ? DEMO_CRYPTOS : fallback);
      }
    } catch (e) {
      // Transient failures (dev recompile, brief network drop) must not wipe
      // live bubbles with demo data — only initial loads take the fallback.
      if (silent) {
        console.warn('[bubbles] poll fetch failed, keeping current data', e);
      } else {
        console.error('Failed to load market bubble data', e);
        setRawList(isCrypto ? DEMO_CRYPTOS : DEMO_PSX);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  };

  // Load which countries/markets exist in JDDS and populate the selector.
  useEffect(() => {
    let cancelled = false;
    const loadMarkets = async () => {
      try {
        const res = await fetch('/api/markets');
        if (!res.ok) return;
        const data = await res.json();
        if (!Array.isArray(data.markets)) return;
        // Only offer markets that actually have priced data in JDDS; crypto first.
        const usable = (data.markets as Array<Record<string, unknown>>)
          .filter(m => m.enabled && (m.assetCount as number) > 0)
          .map((m): MarketOption => ({
            id: String(m.id),
            label: m.isCrypto ? `Global Crypto (${m.pricedCount})` : `${m.country} — ${m.exchange} (${m.pricedCount})`,
            isCrypto: !!m.isCrypto,
            pricedCount: (m.pricedCount as number) ?? 0,
          }))
          .sort((a: MarketOption, b: MarketOption) =>
            a.isCrypto === b.isCrypto ? b.pricedCount - a.pricedCount : a.isCrypto ? -1 : 1);
        if (!cancelled && usable.length > 0) {
          setMarkets(usable);
          setSelectedMarket(prev => (usable.some((m: MarketOption) => m.id === prev) ? prev : usable[0].id));
        }
      } catch (e) {
        console.error('Failed to load JDDS markets', e);
      }
    };
    loadMarkets();
    return () => { cancelled = true; };
  }, []);

  // Switch market and reload data.
  const handleMarketChange = (market: string) => {
    setSelectedMarket(market);
    setSearchQuery('');
    setSelectedSector('All');
    setSelectedPerformance('All');
    setSelectedRankTier('All');
    setSelectedVolumeTier('All');
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

      // Volume Range filter
      const volNum = parseVal(c.volume);
      if (selectedVolumeTier === 'ultra' && volNum < 1e9) return false;
      if (selectedVolumeTier === 'high' && (volNum < 1e8 || volNum >= 1e9)) return false;
      if (selectedVolumeTier === 'medium' && (volNum < 1e7 || volNum >= 1e8)) return false;
      if (selectedVolumeTier === 'low' && volNum >= 1e7) return false;
      
      return true;
    });
  }, [rawList, selectedSector, selectedPerformance, selectedRankTier, selectedVolumeTier]);

  // Sync new data into existing physics objects to keep trajectory
  const syncBubbles = (cryptos: BubbleData[]) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const width = canvas.width / window.devicePixelRatio;
    const height = canvas.height / window.devicePixelRatio;

    // Calculate dynamic scaling factors
    const maxMC = Math.max(...cryptos.map(c => parseVal(c.marketCap)), 1);
    const maxVol = Math.max(...cryptos.map(c => parseVal(c.volume)), 1);
    const maxChange = Math.max(...cryptos.map(c => Math.abs(c.changePercent)), 1);

    const getTargetRadius = (c: BubbleData) => {
      let relativeValue = 0.5;
      if (sizeMetric === 'marketCap') {
        relativeValue = parseVal(c.marketCap) / maxMC;
      } else if (sizeMetric === 'volume') {
        relativeValue = parseVal(c.volume) / maxVol;
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
        updated.push(prev);
      } else {
        // Spawn scattered around center
        const x = width / 2 + (Math.random() - 0.5) * 160;
        const y = height / 2 + (Math.random() - 0.5) * 160;
        updated.push(new PhysicsBubble(x, y, radius, c));
      }
    });

    bubblesRef.current = updated;
  };

  // Sync physics objects when lists, metrics, or sizes change
  useEffect(() => {
    if (rawList.length > 0) {
      syncBubbles(filteredAssets);
    }
    // syncBubbles is stable per-render and reads current state internally.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sizeMetric, rawList, filteredAssets, bubbleSizeMultiplier]);

  // Init live poll — initial load shows the loader, refreshes are silent.
  useEffect(() => {
    loadMarketData(selectedMarket);
    const interval = setInterval(() => loadMarketData(selectedMarket, true), 20000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMarket]);

  // Reset page position to 1 when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, selectedSector, selectedPerformance, selectedRankTier, selectedVolumeTier]);

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

      // Handle circle-to-circle collisions
      for (let i = 0; i < bubbles.length; i++) {
        for (let j = i + 1; j < bubbles.length; j++) {
          const b1 = bubbles[i];
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
      let aVal: string | number = a[sortField] ?? 0;
      let bVal: string | number = b[sortField] ?? 0;

      if (sortField === 'marketCap' || sortField === 'volume') {
        aVal = parseVal(aVal);
        bVal = parseVal(bVal);
      } else if (sortField === 'rank') {
        aVal = a.rank ?? 999;
        bVal = b.rank ?? 999;
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
      <div className="flex-1 w-full max-w-7xl mx-auto px-4 md:px-8 py-6 space-y-6 flex flex-col pb-20 select-none overflow-y-auto">
        
        {/* Title Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/20 pb-4 shrink-0">
          <div>
            <h1 className="font-serif text-3xl md:text-4xl font-medium tracking-tight text-foreground flex items-center gap-3">
              <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
                <Orbit className="text-primary animate-spin-slow" size={30} />
              </span>
              Market Bubbles
            </h1>
            <p className="text-muted-foreground text-xs mt-1">
              Interactive fluid-physics bubble catalog. Select a market, then customize sizing, scale, and filters.
            </p>
          </div>

          <div className="flex items-center justify-end gap-3 flex-wrap ml-auto">
            {/* Market Selector — populated from markets loaded in JDDS */}
            <div className="flex items-center gap-2 bg-accent/40 p-1.5 rounded-3xl border border-border/40 backdrop-blur-md shrink-0">
              <span className="text-[10px] uppercase font-bold text-muted-foreground/80 px-2 tracking-wider">Market:</span>
              <select
                value={selectedMarket}
                onChange={e => handleMarketChange(e.target.value)}
                className="bg-background border border-border/60 hover:border-primary/50 rounded-3xl px-3 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary outline-none transition-all cursor-pointer font-semibold"
                title="Select country / market to load bubble data from JDDS"
              >
                {markets.length > 0 ? (
                  markets.map(m => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))
                ) : (
                  <>
                    <option value="CRYPTO">Global Crypto</option>
                    <option value="US">United States</option>
                    <option value="PK">Pakistan (PSX)</option>
                  </>
                )}
              </select>
            </div>

            {/* Search tool */}
            <div className="relative w-64 shrink-0">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
              <input
                type="text"
                placeholder="Search / Highlight Asset..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value.toUpperCase())}
                className="w-full bg-[#0f0f0f]/40 border border-border/40 rounded-xl pl-9 pr-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-primary placeholder:text-muted-foreground/60 transition-all font-mono"
              />
            </div>
          </div>
        </div>

        {/* Filters Banner (Row 1) */}
        <div className="flex flex-wrap items-center gap-4 bg-[#0f0f0f]/40 border border-white/5 rounded-2xl p-4 shrink-0 text-xs">
          
          {/* Sector Category Filter */}
          <div className="flex items-center gap-2 border-r border-white/5 pr-4">
            <Filter size={12} className="text-muted-foreground" />
            <span className="text-muted-foreground font-semibold">Sector:</span>
            <select
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

          {/* Volume 24h Filter */}
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground font-semibold">24h Vol:</span>
            <select
              value={selectedVolumeTier}
              onChange={e => setSelectedVolumeTier(e.target.value)}
              className="bg-black/40 border border-white/10 rounded-lg px-2.5 py-1 text-[11px] font-mono text-foreground focus:outline-none focus:border-primary/50 cursor-pointer"
            >
              <option value="All" className="bg-[#121212] text-foreground">All Volumes</option>
              <option value="ultra" className="bg-[#121212] text-foreground">Ultra High (&gt; $1B)</option>
              <option value="high" className="bg-[#121212] text-foreground">High ($100M - $1B)</option>
              <option value="medium" className="bg-[#121212] text-foreground">Medium ($10M - $100M)</option>
              <option value="low" className="bg-[#121212] text-foreground">Low (&lt; $10M)</option>
            </select>
          </div>
        </div>

        {/* Physics Controls Banner (Row 2) */}
        <div className="flex flex-wrap items-center justify-between gap-4 bg-[#0f0f0f]/40 border border-white/5 rounded-2xl p-4 shrink-0 text-xs">
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
                  { key: 'marketCap', label: 'Mkt Cap' },
                  { key: 'volume', label: 'Volume' },
                  { key: 'change', label: '% Change' }
                ].map(opt => (
                  <button
                    key={opt.key}
                    onClick={() => setSizeMetric(opt.key as 'marketCap' | 'volume' | 'change')}
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
        <div className="h-[500px] w-full bg-[#050505]/40 backdrop-blur-3xl border border-white/5 rounded-3xl relative overflow-hidden shrink-0">
          {loading && rawList.length === 0 && (
            <div className="absolute inset-0 flex flex-col items-center justify-center z-10 bg-[#050505]/80">
              <Orbit className="text-white/5 w-16 h-16 animate-spin-slow mb-4" />
              <Skeleton className="h-3 w-48" />
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

          {/* Ambient center instruction */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20 text-[9px] font-mono tracking-widest text-muted-foreground select-none uppercase">
            Drag to throw • Click or use details table to query AI • Wheel to zoom
          </div>
        </div>

        {/* Detailed Crypto Statistics Table */}
        <div className="bg-[#050505]/40 border border-white/5 rounded-3xl p-6 backdrop-blur-3xl space-y-4 shrink-0">
          <div className="flex items-center justify-between border-b border-white/5 pb-3">
            <h2 className="font-serif text-lg font-semibold text-foreground">Market Details Table</h2>
            <span className="text-[10px] text-muted-foreground font-mono bg-white/5 px-2.5 py-1 rounded-full">
              Showing {filteredAndSortedList.length} assets
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
                      <th onClick={() => toggleSort('volume')} className="py-3 px-4 cursor-pointer hover:text-foreground transition-colors text-right">
                        <div className="flex items-center justify-end gap-1.5">24h Volume <ArrowUpDown size={10} /></div>
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
                            <td className="py-3.5 px-4 text-muted-foreground/80">#{c.rank || 999}</td>
                            <td className="py-3.5 px-4 font-bold text-primary tracking-wider">{c.symbol}</td>
                            <td className="py-3.5 px-4 text-muted-foreground font-sans truncate max-w-[150px]">{c.name}</td>
                            <td className="py-3.5 px-4 text-right font-semibold">
                              {bubbleCurrencyFor(selectedMarket) === '$' ? '$' : `${bubbleCurrencyFor(selectedMarket)} `}{c.price >= 1 ? c.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : c.price.toFixed(4)}
                            </td>
                            <td className={`py-3.5 px-4 text-right font-semibold ${isPositive ? 'text-primary' : 'text-rose-400'}`}>
                              {isPositive ? '+' : ''}{c.changePercent.toFixed(2)}%                            </td>
                            <td className="py-3.5 px-4 text-right">{c.marketCap}</td>
                            <td className="py-3.5 px-4 text-right text-muted-foreground">{c.volume}</td>
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
                        <td colSpan={8} className="py-8 text-center text-muted-foreground/60">
                          No matching assets found
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
                      {[10, 25, 50, 100].map(size => (
                        <option key={size} value={size} className="bg-[#121212] text-foreground">
                          {size}
                        </option>
                      ))}
                    </select>
                    <span className="ml-2 text-[11px]">
                      Showing {Math.min(filteredAndSortedList.length, (currentPage - 1) * itemsPerPage + 1)}-
                      {Math.min(filteredAndSortedList.length, currentPage * itemsPerPage)} of {filteredAndSortedList.length} assets
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
            className="w-56 p-4 rounded-xl border border-border/50 bg-background/95 text-foreground backdrop-blur-2xl shadow-2xl pointer-events-none text-left flex flex-col gap-2 transition-all duration-100 animate-fade-in"
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
              <div className="flex justify-between mt-1 text-[11px]">
                <span className="text-muted-foreground">Price:</span>
                <span className="font-mono font-semibold">{bubbleCurrencyFor(selectedMarket) === '$' ? '$' : `${bubbleCurrencyFor(selectedMarket)} `}{hoveredData.price >= 1 ? hoveredData.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : hoveredData.price.toFixed(4)}</span>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-muted-foreground">Mkt Cap:</span>
                <span className="font-mono font-semibold">{hoveredData.marketCap}</span>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-muted-foreground">24h Vol:</span>
                <span className="font-mono font-semibold">{hoveredData.volume}</span>
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
