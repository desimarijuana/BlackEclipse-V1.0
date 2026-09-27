// Market screener demo data — extracted into its own module to reduce
// the compiler's per-module memory footprint (the component file is very large).
//
// POLICY: demo/fallback rows are PLACEHOLDERS, never simulated market data.
// Every price, change, and percent here is ZERO. When the real API can't be
// reached the UI shows names with empty ("—") values instead of fake numbers.

export interface IndexCard {
  name: string;
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  sparkline: number[];
  /** Currency code or "$" that belongs to this instrument (from /api/indices). */
  currency?: string;
}

export interface SectorPerformance {
  name: string;
  change: number;
}

export interface ShifterItem {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
}

export interface StockItem {
  symbol: string;
  name: string;
  sector: string;
  industry: string;
  /** Security type from the market universe (e.g. 'Common Stock', 'ETF', 'Mutual Fund', 'ADR', ...). */
  securityType?: string;
  /** Asset class (e.g. 'Equity', 'ETF', 'Mutual Fund', 'Derivative'). */
  assetClass?: string;
  country: string;
  price: number;
  changePercent: number;
  volume: string;
  marketCap: string;
  peRatio: string;
  dividendYield: string;
  index: string;
  recommendation: string;
  exchange: string;
  forwardPE: string;
  peg: string;
  ps: string;
  pb: string;
  evEbitda: string;
  grossMargin: string;
  operatingMargin: string;
  netProfitMargin: string;
  insiderOwnership: string;
  institutionalOwnership: string;
  shortFloat: string;
  rsi14: string;
  sma20: string;
  sma50: string;
  sma200: string;
  circulatingSupply?: string;
  totalSupply?: string;
  maxSupply?: string;
  ath?: string;
  atl?: string;
  rank?: number;
  athChangePercent?: number;
  atlChangePercent?: number;
  athDate?: string;
  atlDate?: string;
  marketCapRaw?: number;
  volumeRaw?: number;
  circulatingSupplyRaw?: number;
  maxSupplyRaw?: number;
  /** 52-week trading range (raw numbers) — powers the range slider. */
  fiftyTwoWeekHigh?: number | null;
  fiftyTwoWeekLow?: number | null;
  /** Earnings per share (TTM), formatted. */
  eps?: string;
  /** Day session + richer fundamentals for the stock detail view. */
  dayHigh?: number | null;
  dayLow?: number | null;
  dayOpen?: number | null;
  previousClose?: number | null;
  beta?: string;
  dividendRate?: string;
  fdv?: string;
  /** True when no price exists yet (render '--', click to scrape). */
  priceMissing?: boolean;
  /** 'scraper' (live) | 'csv' (imported historical/API data) | 'tradingview' | null. */
  priceSource?: string | null;
  /** ISO timestamp of the last price update — used to decide auto-refresh. */
  updatedAt?: string | null;
}

export interface FundItem {
  symbol: string;
  name: string;
  category: string;
  nav: number;
  changePercent: number;
  // These metrics are not sourced for JDDS funds yet. `null` renders as N/A —
  // never a fabricated 0, which would read as a real (bad) return/ratio/rating.
  ytdReturn: number | null;
  expenseRatio: number | null;
  rating: number | null;
  aum: string;
}

export interface ETFItem {
  symbol: string;
  name: string;
  category: string;
  price: number;
  changePercent: number;
  volume: string;
  aum: string;
  expenseRatio: string;
}

export interface NewStockItem {
  symbol: string;
  name: string;
  ipoDate: string;
  price: number;
  changePercent: number;
  volume: string;
  marketCap: string;
  ipoPrice: number;
}

export interface BlueChipItem {
  symbol: string;
  name: string;
  dividendYield: string;
  price: number;
  changePercent: number;
  volume: string;
  marketCap: string;
  peRatio: string;
  safetyRating: string;
}

export const INDEX_DATA: IndexCard[] = [
  { name: 'S&P 500', symbol: 'SPX', price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
  { name: 'Nasdaq Composite', symbol: 'IXIC', price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
  { name: 'Dow Jones', symbol: 'DJI', price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
  { name: 'Russell 2000', symbol: 'RUT', price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
  { name: 'Bitcoin', symbol: 'BTC', price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
  { name: 'Gold', symbol: 'GC=F', price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
];

export const SECTOR_PERFORMANCE = [
  { name: 'Information Technology', change: 0 },
  { name: 'Communication Services', change: 0 },
  { name: 'Health Care', change: 0 },
  { name: 'Financials', change: 0 },
  { name: 'Materials', change: 0 },
  { name: 'Energy', change: 0 },
  { name: 'Industrials', change: 0 },
  { name: 'Consumer Staples', change: 0 },
  { name: 'Real Estate', change: 0 },
  { name: 'Utilities', change: 0 },
  { name: 'Consumer Discretionary', change: 0 },
];

export const ETFS_DATA: ETFItem[] = [
  { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', category: 'Large Blend', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
  { symbol: 'QQQ', name: 'Invesco QQQ Trust Series 1', category: 'Large Growth', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
  { symbol: 'VOO', name: 'Vanguard S&P 500 ETF', category: 'Large Blend', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
  { symbol: 'IWM', name: 'iShares Russell 2000 ETF', category: 'Small Blend', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
  { symbol: 'DIA', name: 'SPDR Dow Jones Industrial Average ETF', category: 'Large Value', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
  { symbol: 'ARKK', name: 'ARK Innovation ETF', category: 'Mid-Cap Growth', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
];

export const NEW_STOCKS_DATA: NewStockItem[] = [
  { symbol: 'RDDT', name: 'Reddit, Inc.', ipoDate: 'Mar 2024', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 },
  { symbol: 'ARM', name: 'ARM Holdings plc', ipoDate: 'Sep 2023', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 },
  { symbol: 'ALAB', name: 'Astera Labs, Inc.', ipoDate: 'Mar 2024', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 },
  { symbol: 'KVUE', name: 'Kenvue Inc.', ipoDate: 'May 2023', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 },
  { symbol: 'BIRK', name: 'Birkenstock Holding plc', ipoDate: 'Oct 2023', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 },
];

export const BLUE_CHIPS_DATA: BlueChipItem[] = [
  { symbol: 'BRK.B', name: 'Berkshire Hathaway Inc.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
  { symbol: 'JNJ', name: 'Johnson & Johnson', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
  { symbol: 'PG', name: 'Procter & Gamble Co.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
  { symbol: 'WMT', name: 'Walmart Inc.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
  { symbol: 'XOM', name: 'Exxon Mobil Corp.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
  { symbol: 'HD', name: 'Home Depot Inc.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
];

export const TOP_GAINERS = [
  { symbol: 'NVDA', name: 'NVIDIA Corp.', price: 0, changePercent: 0 },
  { symbol: 'LLY', name: 'Eli Lilly & Co.', price: 0, changePercent: 0 },
  { symbol: 'NFLX', name: 'Netflix Inc.', price: 0, changePercent: 0 },
  { symbol: 'AAPL', name: 'Apple Inc.', price: 0, changePercent: 0 },
  { symbol: 'AMZN', name: 'Amazon.com, Inc.', price: 0, changePercent: 0 },
];

export const TOP_LOSERS = [
  { symbol: 'TSLA', name: 'Tesla Inc.', price: 0, changePercent: 0 },
  { symbol: 'META', name: 'Meta Platforms', price: 0, changePercent: 0 },
  { symbol: 'UNH', name: 'UnitedHealth Group', price: 0, changePercent: 0 },
  { symbol: 'AMD', name: 'Advanced Micro Devices', price: 0, changePercent: 0 },
  { symbol: 'MSFT', name: 'Microsoft Corp.', price: 0, changePercent: 0 },
];

export function getSimulatedDashboard(country: string) {
  let indices: IndexCard[] = [];
  let sectors: SectorPerformance[] = [];
  let shifters: { gainers: ShifterItem[]; losers: ShifterItem[] } = { gainers: [], losers: [] };

  // Zero-valued placeholders — the real dashboard must come from /api/indices.
  if (country === 'CRYPTO' || country === 'Crypto') {
    indices = [
      { name: "Bitcoin", symbol: "BTC", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Ethereum", symbol: "ETH", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Solana", symbol: "SOL", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Binance Coin", symbol: "BNB", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Ripple", symbol: "XRP", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: "Dogecoin", symbol: "DOGE", price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] }
    ];
    sectors = [
      { name: "Layer 1", change: 0 },
      { name: "DeFi", change: 0 },
      { name: "Stablecoins", change: 0 },
      { name: "Meme Coins", change: 0 },
      { name: "Exchange Tokens", change: 0 },
      { name: "Layer 2", change: 0 }
    ];
    shifters = {
      gainers: [
        { symbol: 'DOGE', name: 'Dogecoin', price: 0, changePercent: 0 },
        { symbol: 'SOL', name: 'Solana', price: 0, changePercent: 0 },
        { symbol: 'ETH', name: 'Ethereum', price: 0, changePercent: 0 }
      ],
      losers: [
        { symbol: 'BNB', name: 'Binance Coin', price: 0, changePercent: 0 },
        { symbol: 'XRP', name: 'Ripple', price: 0, changePercent: 0 },
        { symbol: 'BTC', name: 'Bitcoin', price: 0, changePercent: 0 }
      ]
    };
  } else {
    indices = [
      { name: 'S&P 500', symbol: 'SPX', price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: 'Nasdaq Composite', symbol: 'IXIC', price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: 'Dow Jones', symbol: 'DJI', price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: 'Russell 2000', symbol: 'RUT', price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: 'Bitcoin', symbol: 'BTC', price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] },
      { name: 'Gold', symbol: 'GC=F', price: 0, change: 0, changePercent: 0, sparkline: [0, 0, 0, 0, 0] }
    ];
    sectors = [
      { name: 'Information Technology', change: 0 },
      { name: 'Communication Services', change: 0 },
      { name: 'Health Care', change: 0 },
      { name: 'Financials', change: 0 },
      { name: 'Materials', change: 0 },
      { name: 'Energy', change: 0 },
      { name: 'Industrials', change: 0 },
      { name: 'Consumer Staples', change: 0 },
      { name: 'Real Estate', change: 0 },
      { name: 'Utilities', change: 0 },
      { name: 'Consumer Discretionary', change: 0 }
    ];
    shifters = {
      gainers: [
        { symbol: 'NVDA', name: 'NVIDIA Corp.', price: 0, changePercent: 0 },
        { symbol: 'LLY', name: 'Eli Lilly & Co.', price: 0, changePercent: 0 },
        { symbol: 'NFLX', name: 'Netflix Inc.', price: 0, changePercent: 0 }
      ],
      losers: [
        { symbol: 'TSLA', name: 'Tesla Inc.', price: 0, changePercent: 0 },
        { symbol: 'META', name: 'Meta Platforms', price: 0, changePercent: 0 },
        { symbol: 'UNH', name: 'UnitedHealth Group', price: 0, changePercent: 0 }
      ]
    };
  }

  return { indices, sectors, shifters };
}

export function getRegionalEtfs(country: string): ETFItem[] {
  const data: Record<string, ETFItem[]> = {
    USA: [
      { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', category: 'Large Blend', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
      { symbol: 'QQQ', name: 'Invesco QQQ Trust Series 1', category: 'Large Growth', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
      { symbol: 'VOO', name: 'Vanguard S&P 500 ETF', category: 'Large Blend', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
      { symbol: 'IWM', name: 'iShares Russell 2000 ETF', category: 'Small Blend', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
      { symbol: 'DIA', name: 'SPDR Dow Jones Industrial ETF', category: 'Large Value', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
      { symbol: 'ARKK', name: 'ARK Innovation ETF', category: 'Mid-Cap Growth', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' }
    ],
    India: [
      { symbol: 'NIFTYBEES', name: 'Nippon India ETF Nifty BeES', category: 'Large Blend', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
      { symbol: 'JUNIORBEES', name: 'Nippon India ETF Junior BeES', category: 'Mid Blend', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
      { symbol: 'GILTBEES', name: 'Nippon India ETF Gilt BeES', category: 'Government Bond', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
      { symbol: 'BANKBEES', name: 'Nippon India ETF Bank BeES', category: 'Financial Services', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' }
    ],
    Pakistan: [
      { symbol: 'NITGBF-ETF', name: 'NIT Government Bond ETF', category: 'Income Fund', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
      { symbol: 'UBLPET-ETF', name: 'UBL Pakistan Enterprise ETF', category: 'Equity Fund', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' },
      { symbol: 'MZNP-ETF', name: 'Meezan Pakistan ETF', category: 'Shariah Equity', price: 0, changePercent: 0, volume: 'N/A', aum: 'N/A', expenseRatio: 'N/A' }
    ]
  };
  return data[country] || data['USA'];
}

export function getRegionalNewListings(country: string): NewStockItem[] {
  const data: Record<string, NewStockItem[]> = {
    USA: [
      { symbol: 'RDDT', name: 'Reddit, Inc.', ipoDate: 'Mar 2024', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 },
      { symbol: 'ARM', name: 'ARM Holdings plc', ipoDate: 'Sep 2023', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 },
      { symbol: 'ALAB', name: 'Astera Labs, Inc.', ipoDate: 'Mar 2024', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 },
      { symbol: 'KVUE', name: 'Kenvue Inc.', ipoDate: 'May 2023', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 },
      { symbol: 'BIRK', name: 'Birkenstock Holding plc', ipoDate: 'Oct 2023', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 }
    ],
    India: [
      { symbol: 'PREMIER.NS', name: 'Premier Energies Ltd', ipoDate: 'Sep 2024', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 },
      { symbol: 'TATATECH.NS', name: 'Tata Technologies Ltd', ipoDate: 'Nov 2023', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 },
      { symbol: 'JSWINFRA.NS', name: 'JSW Infrastructure Ltd', ipoDate: 'Oct 2023', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 }
    ],
    Pakistan: [
      { symbol: 'SECURE-LP', name: 'Secure Logistics Group', ipoDate: 'Apr 2024', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 },
      { symbol: 'SYM-LP', name: 'Symmetry Group Limited', ipoDate: 'Aug 2023', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', ipoPrice: 0 }
    ]
  };
  return data[country] || data['USA'];
}

export function getRegionalBlueChips(country: string): BlueChipItem[] {
  const data: Record<string, BlueChipItem[]> = {
    USA: [
      { symbol: 'BRK.B', name: 'Berkshire Hathaway Inc.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'JNJ', name: 'Johnson & Johnson', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'PG', name: 'Procter & Gamble Co.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'WMT', name: 'Walmart Inc.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'XOM', name: 'Exxon Mobil Corp.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' }
    ],
    India: [
      { symbol: 'RELIANCE.NS', name: 'Reliance Industries', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'TCS.NS', name: 'Tata Consultancy Services', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'HDFCBANK.NS', name: 'HDFC Bank Ltd', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'INFY.NS', name: 'Infosys Ltd', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' }
    ],
    Pakistan: [
      { symbol: 'SYS.KA', name: 'Systems Limited', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'LUCK.KA', name: 'Lucky Cement', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'ENGRO.KA', name: 'Engro Corporation', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'FFC.KA', name: 'Fauji Fertilizer Company', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' }
    ]
  };
  return data[country] || data['USA'];
}

export function getRegionalFunds(country: string): FundItem[] {
  const data: Record<string, FundItem[]> = {
    USA: [
      { symbol: 'VFIAX', name: 'Vanguard 500 Index Admiral', category: 'Large Blend', nav: 0, changePercent: 0, ytdReturn: 0, expenseRatio: 0, rating: 0, aum: 'N/A' },
      { symbol: 'AGTHX', name: 'American Funds Growth Fund', category: 'Large Growth', nav: 0, changePercent: 0, ytdReturn: 0, expenseRatio: 0, rating: 0, aum: 'N/A' },
      { symbol: 'VGTSX', name: 'Vanguard Total Intl Stock', category: 'Foreign Large Blend', nav: 0, changePercent: 0, ytdReturn: 0, expenseRatio: 0, rating: 0, aum: 'N/A' }
    ],
    India: [
      { symbol: 'SBI-BLUE', name: 'SBI Bluechip Fund Growth', category: 'Large Growth', nav: 0, changePercent: 0, ytdReturn: 0, expenseRatio: 0, rating: 0, aum: 'N/A' },
      { symbol: 'HDFC-MID', name: 'HDFC Mid-Cap Opportunities', category: 'Mid Growth', nav: 0, changePercent: 0, ytdReturn: 0, expenseRatio: 0, rating: 0, aum: 'N/A' },
      { symbol: 'NIPPON-SM', name: 'Nippon India Small Cap Fund', category: 'Small Growth', nav: 0, changePercent: 0, ytdReturn: 0, expenseRatio: 0, rating: 0, aum: 'N/A' }
    ],
    Pakistan: [
      { symbol: 'MCB-CMO', name: 'MCB Cash Management Optimizer', category: 'Money Market', nav: 0, changePercent: 0, ytdReturn: 0, expenseRatio: 0, rating: 0, aum: 'N/A' },
      { symbol: 'MEEZAN-SF', name: 'Al Meezan Shariah Stock Fund', category: 'Islamic Equity', nav: 0, changePercent: 0, ytdReturn: 0, expenseRatio: 0, rating: 0, aum: 'N/A' },
      { symbol: 'NBP-SF', name: 'NBP Balanced Stock Fund', category: 'Balanced Fund', nav: 0, changePercent: 0, ytdReturn: 0, expenseRatio: 0, rating: 0, aum: 'N/A' }
    ]
  };
  return data[country] || data['USA'];
}

export function getRegionalDividendStocks(country: string): BlueChipItem[] {
  const data: Record<string, BlueChipItem[]> = {
    USA: [
      { symbol: 'KO', name: 'The Coca-Cola Co.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'PEP', name: 'PepsiCo Inc.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'MO', name: 'Altria Group Inc.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'T', name: 'AT&T Inc.', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' }
    ],
    India: [
      { symbol: 'ITC.NS', name: 'ITC Limited', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'COALINDIA.NS', name: 'Coal India Ltd', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'PFC.NS', name: 'Power Finance Corp', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' }
    ],
    Pakistan: [
      { symbol: 'EFERT.KA', name: 'Engro Fertilizers', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'FFC.KA', name: 'Fauji Fertilizer Company', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' },
      { symbol: 'HUBC.KA', name: 'Hub Power Company', dividendYield: 'N/A', price: 0, changePercent: 0, volume: 'N/A', marketCap: 'N/A', peRatio: 'N/A', safetyRating: 'N/A' }
    ]
  };
  return data[country] || data['USA'];
}