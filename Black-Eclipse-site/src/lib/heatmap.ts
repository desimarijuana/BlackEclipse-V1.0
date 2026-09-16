// ── Market heatmap metadata ──────────────────────────────────────────────────
// Country → headline index labels for the treemap heatmap. Pure data, shared
// by the /api/heatmap route (server) and the widget (client) so both agree on
// the same market list and labels. Never fabricates prices — only describes
// which JDDS market / index a heatmap view maps to.

export interface HeatmapMarket {
  /** Canonical JDDS market id (US, PK, IN, ...). */
  id: string;
  /** Human-readable country / market name. */
  country: string;
  /** Headline index for this market (S&P 500, Nifty 50, ...). */
  index: string;
  /** Yahoo ticker for the headline index (used to look up IndexQuote rows). */
  indexSymbol?: string;
}

export const HEATMAP_MARKETS: HeatmapMarket[] = [
  { id: 'US', country: 'United States', index: 'S&P 500', indexSymbol: '^GSPC' },
  { id: 'CRYPTO', country: 'Global Crypto', index: 'Top Assets' },
  { id: 'FOREX', country: 'Forex', index: 'Major Pairs' },
  { id: 'COMMODITIES', country: 'Commodities', index: 'Futures' },
  { id: 'IN', country: 'India', index: 'Nifty 50', indexSymbol: '^NSEI' },
  { id: 'CN', country: 'China', index: 'Shanghai Composite', indexSymbol: '000001.SS' },
  { id: 'TW', country: 'Taiwan', index: 'TAIEX Weighted', indexSymbol: '^TWII' },
  { id: 'HK', country: 'Hong Kong', index: 'Hang Seng', indexSymbol: '^HSI' },
  { id: 'JP', country: 'Japan', index: 'Nikkei 225', indexSymbol: '^N225' },
  { id: 'KR', country: 'South Korea', index: 'KOSPI', indexSymbol: '^KS11' },
  { id: 'SG', country: 'Singapore', index: 'Straits Times', indexSymbol: '^STI' },
  { id: 'MY', country: 'Malaysia', index: 'FTSE Bursa KLCI', indexSymbol: '^KLSE' },
  { id: 'AU', country: 'Australia', index: 'S&P/ASX 200', indexSymbol: '^AXJO' },
  { id: 'UK', country: 'United Kingdom', index: 'FTSE 100', indexSymbol: '^FTSE' },
  { id: 'DE', country: 'Germany', index: 'DAX', indexSymbol: '^GDAXI' },
  { id: 'FR', country: 'France', index: 'CAC 40', indexSymbol: '^FCHI' },
  { id: 'NL', country: 'Netherlands', index: 'AEX', indexSymbol: '^AEX' },
  { id: 'CA', country: 'Canada', index: 'S&P/TSX Composite', indexSymbol: '^GSPTSE' },
  { id: 'BR', country: 'Brazil', index: 'Ibovespa', indexSymbol: '^BVSP' },
  { id: 'MX', country: 'Mexico', index: 'IPC Mexico', indexSymbol: '^MXX' },
  { id: 'SA', country: 'Saudi Arabia', index: 'Tadawul All Share', indexSymbol: '^TASI.SR' },
  { id: 'AE', country: 'United Arab Emirates', index: 'DFM General', indexSymbol: '^DFMGI' },
  { id: 'ZA', country: 'South Africa', index: 'JSE All Share', indexSymbol: '^JALSH' },
  { id: 'EG', country: 'Egypt', index: 'EGX 30', indexSymbol: '^EGX30' },
  { id: 'NG', country: 'Nigeria', index: 'NGX All Share', indexSymbol: '^NGXALLSH' },
  { id: 'RU', country: 'Russia', index: 'MOEX Russia', indexSymbol: '^IMOEX.ME' },
  { id: 'TR', country: 'Turkey', index: 'BIST 100', indexSymbol: '^XU100' },
  { id: 'ID', country: 'Indonesia', index: 'Jakarta Composite', indexSymbol: '^JKSE' },
  { id: 'TH', country: 'Thailand', index: 'SET Index', indexSymbol: '^SET.BK' },
  { id: 'VN', country: 'Vietnam', index: 'VN Index', indexSymbol: '^VNINDEX' },
  { id: 'PK', country: 'Pakistan', index: 'KSE 100', indexSymbol: '^KSE100' },
];

export function heatmapMeta(market: string): HeatmapMarket {
  return (
    HEATMAP_MARKETS.find(m => m.id === market) ?? {
      id: market,
      country: market,
      index: market,
    }
  );
}

export interface HeatmapStock {
  symbol: string;
  name: string;
  sector: string;
  price: number;
  /** Percent change, already in percent units (e.g. 1.84 = +1.84%). */
  changePct: number;
  /**
   * Tile-size value: the market's raw market cap COMPRESSED for the treemap so
   * a mega-cap cannot flatten every other tile. Use `rawMarketCap` to display
   * the true figure.
   */
  marketCap: number;
  /** The true, uncompressed market cap (what the tooltip shows). */
  rawMarketCap?: number;
  /** Fallback size metric (24h volume) when market cap is missing. */
  volume: number;
}

export interface HeatmapSector {
  name: string;
  /** Cap-weighted percent change for the sector. */
  change: number;
  /** Tile-size total (compressed) of the sector's constituents. */
  marketCap: number;
  /** The sector's true, uncompressed market cap. */
  rawMarketCap?: number;
  stocks: HeatmapStock[];
}

export interface HeatmapPayload {
  market: string;
  country: string;
  indexName: string;
  currency: string;
  asOf: string;
  /** Number of stocks included in the heatmap. */
  live: number;
  /** Cap-weighted percent change across all included stocks. */
  change: number;
  sectors: HeatmapSector[];
  /** True when no priced data was available for the market. */
  empty?: boolean;
  /**
   * Whole-market traded-volume analysis, computed over EVERY priced asset in
   * the market (not just the `limit` tiles shown). Absent for feed markets
   * (FOREX/COMMODITIES), where no real traded volume exists.
   */
  volume?: VolumeSummary;
}

// ── Traded-volume analysis ───────────────────────────────────────────────────
// A "proper" volume measure has to be honest about units: JDDS stores crypto
// volume as quote-currency NOTIONAL (Binance `quoteVolume`, already in USD) but
// equity volume as a SHARE COUNT (TradingView / yfinance). Summing share counts
// across differently-priced stocks is dimensionally meaningless, so for
// share-based markets we derive TURNOVER (shares × price = traded value in the
// market's own currency), which IS comparable across instruments. Crypto
// turnover is the notional volume itself — multiplying it by price would double
// count.

/** True when the market's stored `volume` is already quote-currency notional. */
export function isNotionalVolume(market: string): boolean {
  return market === 'CRYPTO';
}

/**
 * Traded value for one instrument, in the market's currency.
 * Notional markets: volume is already value. Share markets: shares × price.
 */
export function turnoverFor(volume: number, price: number, market: string): number {
  if (!(volume > 0)) return 0;
  return isNotionalVolume(market) ? volume : volume * price;
}

/** How the market reports volume, so the UI can label the unit truthfully. */
export type VolumeUnit = 'notional' | 'shares';

/** One instrument's contribution to market turnover. */
export interface VolumeContributor {
  symbol: string;
  name: string;
  sector: string;
  /** Raw stored volume (shares, or quote notional for crypto). */
  volume: number;
  price: number;
  /** Traded value in the market currency (see `turnoverFor`). */
  turnover: number;
  /** Percent of the market's total turnover, 0–100. */
  sharePct: number;
  changePct: number;
}

/**
 * A turnover band. Bands are defined by an instrument's CONTRIBUTION SHARE of
 * market turnover rather than an absolute amount, so they stay meaningful
 * across currencies (USD vs PKR vs IDR) and market sizes.
 */
export interface VolumeTier {
  label: string;
  /** Inclusive lower bound as a fraction of market turnover, e.g. 0.10 = 10%. */
  minShare: number;
  count: number;
  turnover: number;
  /** Percent of market turnover held by this band. */
  sharePct: number;
}

export interface VolumeSummary {
  unit: VolumeUnit;
  /** Currency the turnover figures are expressed in. */
  currency: string;
  /** Priced instruments with volume > 0 that contributed. */
  instruments: number;
  /** Every priced instrument in the market (contributors + zero-volume rows). */
  marketAssets: number;
  /** Sum of raw stored volume (shares, or quote notional for crypto). */
  totalVolume: number;
  /** Sum of traded value in the market currency. */
  turnover: number;
  averageTurnover: number;
  /** Median turnover — robust to a single dominant instrument. */
  medianTurnover: number;
  maxTurnover: number;
  /** Leading instruments by turnover. */
  top: VolumeContributor[];
  /** Percent of market turnover held by the top 10 instruments. */
  top10SharePct: number;
  /**
   * Herfindahl–Hirschman Index (0–10000) over instrument turnover shares.
   * >2500 = highly concentrated, 1500–2500 = moderate, <1500 = competitive.
   */
  hhi: number;
  tiers: VolumeTier[];
}

/** Minimal per-instrument input to `summarizeVolume`. */
export interface VolumeInput {
  symbol: string;
  name: string;
  sector: string;
  price: number;
  volume: number;
  changePct: number;
}

const TIER_BANDS: Array<{ label: string; minShare: number }> = [
  { label: 'Dominant (≥10%)', minShare: 0.10 },
  { label: 'Major (2–10%)', minShare: 0.02 },
  { label: 'Notable (0.5–2%)', minShare: 0.005 },
  { label: 'Minor (<0.5%)', minShare: 0 },
];

/** How many contributors the summary carries. */
export const VOLUME_TOP_N = 12;

/**
 * Aggregate a market's traded volume into a turnover profile. Pure so it can be
 * unit-tested and shared by the API route and any client that already holds the
 * rows. Returns null when no instrument has positive volume — callers render an
 * UNAVAILABLE state rather than a zeroed-out panel that looks like real data.
 */
export function summarizeVolume(
  rows: VolumeInput[],
  market: string,
  currency: string,
): VolumeSummary | null {
  const withVolume = rows.filter(r => r.volume > 0 && r.price > 0);
  if (withVolume.length === 0) return null;

  const contributors: VolumeContributor[] = withVolume.map(r => ({
    symbol: r.symbol,
    name: r.name,
    sector: r.sector,
    volume: r.volume,
    price: r.price,
    turnover: turnoverFor(r.volume, r.price, market),
    sharePct: 0,
    changePct: r.changePct,
  }));

  const totalVolume = contributors.reduce((a, c) => a + c.volume, 0);
  const turnover = contributors.reduce((a, c) => a + c.turnover, 0);
  if (!(turnover > 0)) return null;

  for (const c of contributors) c.sharePct = (c.turnover / turnover) * 100;

  const sorted = [...contributors].sort((a, b) => b.turnover - a.turnover);
  const top = sorted.slice(0, VOLUME_TOP_N);

  // Median on the full distribution (not the truncated top list).
  const values = sorted.map(c => c.turnover).sort((a, b) => a - b);
  const mid = Math.floor(values.length / 2);
  const medianTurnover = values.length % 2 === 0
    ? (values[mid - 1] + values[mid]) / 2
    : values[mid];

  const top10SharePct = sorted.slice(0, 10).reduce((a, c) => a + c.sharePct, 0);
  // HHI in whole points: Σ(share%)². Shares are % so this lands in 0–10000.
  const hhi = contributors.reduce((a, c) => a + c.sharePct * c.sharePct, 0);

  const tiers: VolumeTier[] = TIER_BANDS.map((band, i) => {
    // Bands are contiguous: [this.minShare, nextHigherBand.minShare).
    const upper = i === 0 ? Infinity : TIER_BANDS[i - 1].minShare;
    const members = contributors.filter(c => {
      const f = c.turnover / turnover;
      return f >= band.minShare && f < upper;
    });
    const bandTurnover = members.reduce((a, c) => a + c.turnover, 0);
    return {
      label: band.label,
      minShare: band.minShare,
      count: members.length,
      turnover: bandTurnover,
      sharePct: (bandTurnover / turnover) * 100,
    };
  });

  return {
    unit: isNotionalVolume(market) ? 'notional' : 'shares',
    currency,
    instruments: contributors.length,
    marketAssets: rows.length,
    totalVolume,
    turnover,
    averageTurnover: turnover / contributors.length,
    medianTurnover,
    maxTurnover: sorted[0]?.turnover ?? 0,
    top,
    top10SharePct,
    hhi,
    tiers,
  };
}
