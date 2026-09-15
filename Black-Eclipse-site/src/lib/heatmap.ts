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
}
