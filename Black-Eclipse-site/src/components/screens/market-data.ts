// Market screener demo data — extracted into its own module to reduce
// the compiler's per-module memory footprint (the component file is very large).

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
  ytdReturn: number;
  expenseRatio: number;
  rating: number;
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
  { name: 'S&P 500', symbol: 'SPX', price: 5304.72, change: 42.10, changePercent: 0.80, sparkline: [5260, 5280, 5275, 5290, 5304.72] },
  { name: 'Nasdaq Composite', symbol: 'IXIC', price: 16920.72, change: 182.20, changePercent: 1.09, sparkline: [16700, 16820, 16780, 16850, 16920.72] },
  { name: 'Dow Jones', symbol: 'DJI', price: 39069.59, change: -88.10, changePercent: -0.22, sparkline: [39200, 39150, 39180, 39020, 39069.59] },
  { name: 'Russell 2000', symbol: 'RUT', price: 2068.32, change: 11.45, changePercent: 0.56, sparkline: [2050, 2062, 2055, 2060, 2068.32] },
  { name: 'Bitcoin', symbol: 'BTC', price: 67840.00, change: 1420.00, changePercent: 2.14, sparkline: [66200, 66800, 67200, 67000, 67840.0] },
  { name: 'Gold', symbol: 'GC=F', price: 2348.80, change: -12.40, changePercent: -0.52, sparkline: [2365, 2360, 2355, 2358, 2348.8] },
];

export const SECTOR_PERFORMANCE = [
  { name: 'Information Technology', change: 1.84 },
  { name: 'Communication Services', change: 1.25 },
  { name: 'Health Care', change: 0.88 },
  { name: 'Financials', change: 0.42 },
  { name: 'Materials', change: 0.15 },
  { name: 'Energy', change: -0.12 },
  { name: 'Industrials', change: -0.34 },
  { name: 'Consumer Staples', change: -0.45 },
  { name: 'Real Estate', change: -0.72 },
  { name: 'Utilities', change: -0.85 },
  { name: 'Consumer Discretionary', change: -1.12 },
];

export const ETFS_DATA: ETFItem[] = [
  { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', category: 'Large Blend', price: 529.44, changePercent: 0.81, volume: '62.4M', aum: '502B', expenseRatio: '0.09%' },
  { symbol: 'QQQ', name: 'Invesco QQQ Trust Series 1', category: 'Large Growth', price: 458.20, changePercent: 1.12, volume: '41.8M', aum: '254B', expenseRatio: '0.20%' },
  { symbol: 'VOO', name: 'Vanguard S&P 500 ETF', category: 'Large Blend', price: 486.50, changePercent: 0.82, volume: '8.2M', aum: '430B', expenseRatio: '0.03%' },
  { symbol: 'IWM', name: 'iShares Russell 2000 ETF', category: 'Small Blend', price: 205.32, changePercent: 0.56, volume: '24.1M', aum: '58B', expenseRatio: '0.19%' },
  { symbol: 'DIA', name: 'SPDR Dow Jones Industrial Average ETF', category: 'Large Value', price: 390.68, changePercent: -0.22, volume: '3.1M', aum: '32B', expenseRatio: '0.16%' },
  { symbol: 'ARKK', name: 'ARK Innovation ETF', category: 'Mid-Cap Growth', price: 43.15, changePercent: 2.45, volume: '9.4M', aum: '6.8B', expenseRatio: '0.75%' },
];

export const NEW_STOCKS_DATA: NewStockItem[] = [
  { symbol: 'RDDT', name: 'Reddit, Inc.', ipoDate: 'Mar 2024', price: 58.40, changePercent: 3.12, volume: '4.8M', marketCap: '9.4B', ipoPrice: 34.00 },
  { symbol: 'ARM', name: 'ARM Holdings plc', ipoDate: 'Sep 2023', price: 124.50, changePercent: 5.82, volume: '11.2M', marketCap: '128B', ipoPrice: 51.00 },
  { symbol: 'ALAB', name: 'Astera Labs, Inc.', ipoDate: 'Mar 2024', price: 74.20, changePercent: -1.45, volume: '1.9M', marketCap: '11.6B', ipoPrice: 36.00 },
  { symbol: 'KVUE', name: 'Kenvue Inc.', ipoDate: 'May 2023', price: 20.15, changePercent: 0.42, volume: '12.4M', marketCap: '38.5B', ipoPrice: 22.00 },
  { symbol: 'BIRK', name: 'Birkenstock Holding plc', ipoDate: 'Oct 2023', price: 48.60, changePercent: -0.85, volume: '800K', marketCap: '9.1B', ipoPrice: 46.00 },
];

export const BLUE_CHIPS_DATA: BlueChipItem[] = [
  { symbol: 'BRK.B', name: 'Berkshire Hathaway Inc.', dividendYield: 'None', price: 408.20, changePercent: 0.42, volume: '3.1M', marketCap: '886B', peRatio: '18.5', safetyRating: 'AAA' },
  { symbol: 'JNJ', name: 'Johnson & Johnson', dividendYield: '3.12%', price: 154.50, changePercent: 0.25, volume: '6.4M', marketCap: '372B', peRatio: '15.4', safetyRating: 'AAA' },
  { symbol: 'PG', name: 'Procter & Gamble Co.', dividendYield: '2.42%', price: 165.80, changePercent: -0.15, volume: '5.2M', marketCap: '398B', peRatio: '24.2', safetyRating: 'AAA' },
  { symbol: 'WMT', name: 'Walmart Inc.', dividendYield: '1.38%', price: 65.40, changePercent: 0.62, volume: '14.8M', marketCap: '525B', peRatio: '28.1', safetyRating: 'AA+' },
  { symbol: 'XOM', name: 'Exxon Mobil Corp.', dividendYield: '3.25%', price: 114.20, changePercent: -0.85, volume: '15.4M', marketCap: '456B', peRatio: '12.8', safetyRating: 'AA+' },
  { symbol: 'HD', name: 'Home Depot Inc.', dividendYield: '2.54%', price: 348.50, changePercent: 0.12, volume: '3.8M', marketCap: '346B', peRatio: '22.4', safetyRating: 'AA+' },
];

export const TOP_GAINERS = [
  { symbol: 'NVDA', name: 'NVIDIA Corp.', price: 1096.50, changePercent: 4.60 },
  { symbol: 'LLY', name: 'Eli Lilly & Co.', price: 818.50, changePercent: 2.10 },
  { symbol: 'NFLX', name: 'Netflix Inc.', price: 645.20, changePercent: 1.96 },
  { symbol: 'AAPL', name: 'Apple Inc.', price: 189.84, changePercent: 1.25 },
  { symbol: 'AMZN', name: 'Amazon.com, Inc.', price: 182.15, changePercent: 1.08 },
];

export const TOP_LOSERS = [
  { symbol: 'TSLA', name: 'Tesla Inc.', price: 178.50, changePercent: -2.35 },
  { symbol: 'META', name: 'Meta Platforms', price: 475.40, changePercent: -1.70 },
  { symbol: 'UNH', name: 'UnitedHealth Group', price: 494.60, changePercent: -1.30 },
  { symbol: 'AMD', name: 'Advanced Micro Devices', price: 166.30, changePercent: -1.83 },
  { symbol: 'MSFT', name: 'Microsoft Corp.', price: 429.20, changePercent: -0.42 },
];

export function getSimulatedDashboard(country: string) {
  let indices: IndexCard[] = [];
  let sectors: SectorPerformance[] = [];
  let shifters: { gainers: ShifterItem[]; losers: ShifterItem[] } = { gainers: [], losers: [] };

  if (country === 'CRYPTO' || country === 'Crypto') {
    indices = [
      { name: "Bitcoin", symbol: "BTC", price: 67840.0, change: 1420.0, changePercent: 2.14, sparkline: [66200, 66800, 67200, 67000, 67840] },
      { name: "Ethereum", symbol: "ETH", price: 3500.2, change: 82.5, changePercent: 2.41, sparkline: [3400, 3420, 3450, 3480, 3500.2] },
      { name: "Solana", symbol: "SOL", price: 168.4, change: 6.2, changePercent: 3.82, sparkline: [160, 162, 165, 164, 168.4] },
      { name: "Binance Coin", symbol: "BNB", price: 585.5, change: 12.1, changePercent: 2.11, sparkline: [570, 575, 580, 578, 585.5] },
      { name: "Ripple", symbol: "XRP", price: 0.52, change: 0.015, changePercent: 2.97, sparkline: [0.50, 0.51, 0.50, 0.51, 0.52] },
      { name: "Dogecoin", symbol: "DOGE", price: 0.154, change: 0.008, changePercent: 5.48, sparkline: [0.142, 0.145, 0.148, 0.150, 0.154] }
    ];
    sectors = [
      { name: "Layer 1", change: 2.85 },
      { name: "DeFi", change: 1.45 },
      { name: "Stablecoins", change: 0.0 },
      { name: "Meme Coins", change: 8.5 },
      { name: "Exchange Tokens", change: -1.2 },
      { name: "Layer 2", change: 1.8 }
    ];
    shifters = {
      gainers: [
        { symbol: 'DOGE', name: 'Dogecoin', price: 0.154, changePercent: 5.48 },
        { symbol: 'SOL', name: 'Solana', price: 168.40, changePercent: 3.82 },
        { symbol: 'ETH', name: 'Ethereum', price: 3500.20, changePercent: 2.41 }
      ],
      losers: [
        { symbol: 'BNB', name: 'Binance Coin', price: 585.50, changePercent: -1.20 },
        { symbol: 'XRP', name: 'Ripple', price: 0.52, changePercent: -0.45 },
        { symbol: 'BTC', name: 'Bitcoin', price: 67840.00, changePercent: -0.15 }
      ]
    };
  } else {
    indices = [
      { name: 'S&P 500', symbol: 'SPX', price: 5304.72, change: 42.10, changePercent: 0.80, sparkline: [5260, 5280, 5275, 5290, 5304.72] },
      { name: 'Nasdaq Composite', symbol: 'IXIC', price: 16920.72, change: 182.20, changePercent: 1.09, sparkline: [16700, 16820, 16780, 16850, 16920.72] },
      { name: 'Dow Jones', symbol: 'DJI', price: 39069.59, change: -88.10, changePercent: -0.22, sparkline: [39200, 39150, 39180, 39020, 39069.59] },
      { name: 'Russell 2000', symbol: 'RUT', price: 2068.32, change: 11.45, changePercent: 0.56, sparkline: [2050, 2062, 2055, 2060, 2068.32] },
      { name: 'Bitcoin', symbol: 'BTC', price: 67840.00, change: 1420.00, changePercent: 2.14, sparkline: [66200, 66800, 67200, 67000, 67840.0] },
      { name: 'Gold', symbol: 'GC=F', price: 2348.80, change: -12.40, changePercent: -0.52, sparkline: [2365, 2360, 2355, 2358, 2348.8] }
    ];
    sectors = [
      { name: 'Information Technology', change: 1.84 },
      { name: 'Communication Services', change: 1.25 },
      { name: 'Health Care', change: 0.88 },
      { name: 'Financials', change: 0.42 },
      { name: 'Materials', change: 0.15 },
      { name: 'Energy', change: -0.12 },
      { name: 'Industrials', change: -0.34 },
      { name: 'Consumer Staples', change: -0.45 },
      { name: 'Real Estate', change: -0.72 },
      { name: 'Utilities', change: -0.85 },
      { name: 'Consumer Discretionary', change: -1.12 }
    ];
    shifters = {
      gainers: [
        { symbol: 'NVDA', name: 'NVIDIA Corp.', price: 1096.50, changePercent: 4.60 },
        { symbol: 'LLY', name: 'Eli Lilly & Co.', price: 818.50, changePercent: 2.10 },
        { symbol: 'NFLX', name: 'Netflix Inc.', price: 645.20, changePercent: 1.96 }
      ],
      losers: [
        { symbol: 'TSLA', name: 'Tesla Inc.', price: 178.50, changePercent: -2.35 },
        { symbol: 'META', name: 'Meta Platforms', price: 475.40, changePercent: -1.70 },
        { symbol: 'UNH', name: 'UnitedHealth Group', price: 494.60, changePercent: -1.30 }
      ]
    };
  }

  return { indices, sectors, shifters };
}

export function getRegionalEtfs(country: string): ETFItem[] {
  const data: Record<string, ETFItem[]> = {
    USA: [
      { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', category: 'Large Blend', price: 529.44, changePercent: 0.81, volume: '62.4M', aum: '502B', expenseRatio: '0.09%' },
      { symbol: 'QQQ', name: 'Invesco QQQ Trust Series 1', category: 'Large Growth', price: 458.20, changePercent: 1.12, volume: '41.8M', aum: '254B', expenseRatio: '0.20%' },
      { symbol: 'VOO', name: 'Vanguard S&P 500 ETF', category: 'Large Blend', price: 486.50, changePercent: 0.82, volume: '8.2M', aum: '430B', expenseRatio: '0.03%' },
      { symbol: 'IWM', name: 'iShares Russell 2000 ETF', category: 'Small Blend', price: 205.32, changePercent: 0.56, volume: '24.1M', aum: '58B', expenseRatio: '0.19%' },
      { symbol: 'DIA', name: 'SPDR Dow Jones Industrial ETF', category: 'Large Value', price: 390.68, changePercent: -0.22, volume: '3.1M', aum: '32B', expenseRatio: '0.16%' },
      { symbol: 'ARKK', name: 'ARK Innovation ETF', category: 'Mid-Cap Growth', price: 43.15, changePercent: 2.45, volume: '9.4M', aum: '6.8B', expenseRatio: '0.75%' }
    ],
    India: [
      { symbol: 'NIFTYBEES', name: 'Nippon India ETF Nifty BeES', category: 'Large Blend', price: 246.50, changePercent: 0.74, volume: '1.8M', aum: '2.4B', expenseRatio: '0.12%' },
      { symbol: 'JUNIORBEES', name: 'Nippon India ETF Junior BeES', category: 'Mid Blend', price: 584.20, changePercent: 0.85, volume: '0.5M', aum: '0.8B', expenseRatio: '0.15%' },
      { symbol: 'GILTBEES', name: 'Nippon India ETF Gilt BeES', category: 'Government Bond', price: 112.40, changePercent: 0.10, volume: '0.3M', aum: '0.5B', expenseRatio: '0.14%' },
      { symbol: 'BANKBEES', name: 'Nippon India ETF Bank BeES', category: 'Financial Services', price: 488.50, changePercent: 0.25, volume: '1.2M', aum: '1.5B', expenseRatio: '0.13%' }
    ],
    Pakistan: [
      { symbol: 'NITGBF-ETF', name: 'NIT Government Bond ETF', category: 'Income Fund', price: 10.42, changePercent: 0.40, volume: '0.2M', aum: '12M', expenseRatio: '0.40%' },
      { symbol: 'UBLPET-ETF', name: 'UBL Pakistan Enterprise ETF', category: 'Equity Fund', price: 15.20, changePercent: 0.82, volume: '0.4M', aum: '8M', expenseRatio: '0.50%' },
      { symbol: 'MZNP-ETF', name: 'Meezan Pakistan ETF', category: 'Shariah Equity', price: 12.10, changePercent: 1.05, volume: '0.5M', aum: '10M', expenseRatio: '0.45%' }
    ]
  };
  return data[country] || data['USA'];
}

export function getRegionalNewListings(country: string): NewStockItem[] {
  const data: Record<string, NewStockItem[]> = {
    USA: [
      { symbol: 'RDDT', name: 'Reddit, Inc.', ipoDate: 'Mar 2024', price: 58.40, changePercent: 3.12, volume: '4.8M', marketCap: '9.4B', ipoPrice: 34.00 },
      { symbol: 'ARM', name: 'ARM Holdings plc', ipoDate: 'Sep 2023', price: 124.50, changePercent: 5.82, volume: '11.2M', marketCap: '128B', ipoPrice: 51.00 },
      { symbol: 'ALAB', name: 'Astera Labs, Inc.', ipoDate: 'Mar 2024', price: 74.20, changePercent: -1.45, volume: '1.9M', marketCap: '11.6B', ipoPrice: 36.00 },
      { symbol: 'KVUE', name: 'Kenvue Inc.', ipoDate: 'May 2023', price: 20.15, changePercent: 0.42, volume: '12.4M', marketCap: '38.5B', ipoPrice: 22.00 },
      { symbol: 'BIRK', name: 'Birkenstock Holding plc', ipoDate: 'Oct 2023', price: 48.60, changePercent: -0.85, volume: '800K', marketCap: '9.1B', ipoPrice: 46.00 }
    ],
    India: [
      { symbol: 'PREMIER.NS', name: 'Premier Energies Ltd', ipoDate: 'Sep 2024', price: 890.50, changePercent: 4.80, volume: '2.5M', marketCap: '4.2B', ipoPrice: 450.00 },
      { symbol: 'TATATECH.NS', name: 'Tata Technologies Ltd', ipoDate: 'Nov 2023', price: 1045.20, changePercent: -0.95, volume: '1.2M', marketCap: '5.6B', ipoPrice: 500.00 },
      { symbol: 'JSWINFRA.NS', name: 'JSW Infrastructure Ltd', ipoDate: 'Oct 2023', price: 254.10, changePercent: 1.15, volume: '0.8M', marketCap: '3.1B', ipoPrice: 119.00 }
    ],
    Pakistan: [
      { symbol: 'SECURE-LP', name: 'Secure Logistics Group', ipoDate: 'Apr 2024', price: 18.50, changePercent: 1.12, volume: '0.4M', marketCap: '45M', ipoPrice: 12.00 },
      { symbol: 'SYM-LP', name: 'Symmetry Group Limited', ipoDate: 'Aug 2023', price: 5.40, changePercent: 2.30, volume: '0.8M', marketCap: '12M', ipoPrice: 4.25 }
    ]
  };
  return data[country] || data['USA'];
}

export function getRegionalBlueChips(country: string): BlueChipItem[] {
  const data: Record<string, BlueChipItem[]> = {
    USA: [
      { symbol: 'BRK.B', name: 'Berkshire Hathaway Inc.', dividendYield: 'None', price: 408.20, changePercent: 0.42, volume: '3.1M', marketCap: '886B', peRatio: '18.5', safetyRating: 'AAA' },
      { symbol: 'JNJ', name: 'Johnson & Johnson', dividendYield: '3.12%', price: 154.50, changePercent: 0.25, volume: '6.4M', marketCap: '372B', peRatio: '15.4', safetyRating: 'AAA' },
      { symbol: 'PG', name: 'Procter & Gamble Co.', dividendYield: '2.42%', price: 165.80, changePercent: -0.15, volume: '5.2M', marketCap: '398B', peRatio: '24.2', safetyRating: 'AAA' },
      { symbol: 'WMT', name: 'Walmart Inc.', dividendYield: '1.38%', price: 65.40, changePercent: 0.62, volume: '14.8M', marketCap: '525B', peRatio: '28.1', safetyRating: 'AA+' },
      { symbol: 'XOM', name: 'Exxon Mobil Corp.', dividendYield: '3.25%', price: 114.20, changePercent: -0.85, volume: '15.4M', marketCap: '456B', peRatio: '12.8', safetyRating: 'AA+' }
    ],
    India: [
      { symbol: 'RELIANCE.NS', name: 'Reliance Industries', dividendYield: '0.35%', price: 2854.50, changePercent: 0.95, volume: '5.2M', marketCap: '230B', peRatio: '25.4', safetyRating: 'AAA' },
      { symbol: 'TCS.NS', name: 'Tata Consultancy Services', dividendYield: '1.25%', price: 3820.20, changePercent: 1.45, volume: '2.1M', marketCap: '170B', peRatio: '28.2', safetyRating: 'AAA' },
      { symbol: 'HDFCBANK.NS', name: 'HDFC Bank Ltd', dividendYield: '1.10%', price: 1485.40, changePercent: 0.25, volume: '12.4M', marketCap: '135B', peRatio: '18.5', safetyRating: 'AAA' },
      { symbol: 'INFY.NS', name: 'Infosys Ltd', dividendYield: '2.40%', price: 1430.50, changePercent: 1.15, volume: '6.2M', marketCap: '78B', peRatio: '24.2', safetyRating: 'AA+' }
    ],
    Pakistan: [
      { symbol: 'SYS.KA', name: 'Systems Limited', dividendYield: '2.10%', price: 420.50, changePercent: 2.10, volume: '0.8M', marketCap: '0.5B', peRatio: '14.2', safetyRating: 'AA+' },
      { symbol: 'LUCK.KA', name: 'Lucky Cement', dividendYield: '3.40%', price: 785.40, changePercent: 0.85, volume: '1.2M', marketCap: '1.1B', peRatio: '9.2', safetyRating: 'AAA' },
      { symbol: 'ENGRO.KA', name: 'Engro Corporation', dividendYield: '8.50%', price: 345.20, changePercent: 1.50, volume: '1.5M', marketCap: '1.2B', peRatio: '7.4', safetyRating: 'AAA' },
      { symbol: 'FFC.KA', name: 'Fauji Fertilizer Company', dividendYield: '9.20%', price: 168.40, changePercent: 0.40, volume: '2.4M', marketCap: '0.8B', peRatio: '6.8', safetyRating: 'AA+' }
    ]
  };
  return data[country] || data['USA'];
}

export function getRegionalFunds(country: string): FundItem[] {
  const data: Record<string, FundItem[]> = {
    USA: [
      { symbol: 'VFIAX', name: 'Vanguard 500 Index Admiral', category: 'Large Blend', nav: 488.24, changePercent: 0.81, ytdReturn: 11.24, expenseRatio: 0.04, rating: 5, aum: '1.1T' },
      { symbol: 'AGTHX', name: 'American Funds Growth Fund', category: 'Large Growth', nav: 68.42, changePercent: 1.45, ytdReturn: 13.80, expenseRatio: 0.62, rating: 4, aum: '260B' },
      { symbol: 'VGTSX', name: 'Vanguard Total Intl Stock', category: 'Foreign Large Blend', nav: 21.50, changePercent: 0.30, ytdReturn: 6.42, expenseRatio: 0.17, rating: 4, aum: '420B' }
    ],
    India: [
      { symbol: 'SBI-BLUE', name: 'SBI Bluechip Fund Growth', category: 'Large Growth', nav: 82.50, changePercent: 0.74, ytdReturn: 14.20, expenseRatio: 0.85, rating: 5, aum: '5.2B' },
      { symbol: 'HDFC-MID', name: 'HDFC Mid-Cap Opportunities', category: 'Mid Growth', nav: 142.60, changePercent: 0.95, ytdReturn: 18.50, expenseRatio: 0.75, rating: 5, aum: '8.4B' },
      { symbol: 'NIPPON-SM', name: 'Nippon India Small Cap Fund', category: 'Small Growth', nav: 154.20, changePercent: 1.10, ytdReturn: 22.40, expenseRatio: 0.90, rating: 4, aum: '6.5B' }
    ],
    Pakistan: [
      { symbol: 'MCB-CMO', name: 'MCB Cash Management Optimizer', category: 'Money Market', nav: 104.50, changePercent: 0.40, ytdReturn: 21.50, expenseRatio: 0.60, rating: 5, aum: '150M' },
      { symbol: 'MEEZAN-SF', name: 'Al Meezan Shariah Stock Fund', category: 'Islamic Equity', nav: 88.20, changePercent: 0.85, ytdReturn: 32.40, expenseRatio: 1.50, rating: 4, aum: '85M' },
      { symbol: 'NBP-SF', name: 'NBP Balanced Stock Fund', category: 'Balanced Fund', nav: 22.40, changePercent: 0.50, ytdReturn: 24.80, expenseRatio: 1.20, rating: 4, aum: '62M' }
    ]
  };
  return data[country] || data['USA'];
}

export function getRegionalDividendStocks(country: string): BlueChipItem[] {
  const data: Record<string, BlueChipItem[]> = {
    USA: [
      { symbol: 'KO', name: 'The Coca-Cola Co.', dividendYield: '3.10%', price: 61.20, changePercent: 0.45, volume: '11.2M', marketCap: '265B', peRatio: '24.2', safetyRating: 'AAA' },
      { symbol: 'PEP', name: 'PepsiCo Inc.', dividendYield: '2.95%', price: 168.40, changePercent: 0.20, volume: '5.4M', marketCap: '231B', peRatio: '22.8', safetyRating: 'AAA' },
      { symbol: 'MO', name: 'Altria Group Inc.', dividendYield: '8.45%', price: 44.50, changePercent: -0.65, volume: '9.2M', marketCap: '78B', peRatio: '9.4', safetyRating: 'AA' },
      { symbol: 'T', name: 'AT&T Inc.', dividendYield: '6.20%', price: 17.85, changePercent: -0.15, volume: '32.4M', marketCap: '128B', peRatio: '8.5', safetyRating: 'A+' }
    ],
    India: [
      { symbol: 'ITC.NS', name: 'ITC Limited', dividendYield: '3.80%', price: 425.20, changePercent: 0.65, volume: '8.5M', marketCap: '65B', peRatio: '24.5', safetyRating: 'AAA' },
      { symbol: 'COALINDIA.NS', name: 'Coal India Ltd', dividendYield: '6.15%', price: 448.40, changePercent: 1.10, volume: '9.4M', marketCap: '32B', peRatio: '8.4', safetyRating: 'AA+' },
      { symbol: 'PFC.NS', name: 'Power Finance Corp', dividendYield: '4.80%', price: 382.50, changePercent: 1.85, volume: '12.4M', marketCap: '18B', peRatio: '7.2', safetyRating: 'AA+' }
    ],
    Pakistan: [
      { symbol: 'EFERT.KA', name: 'Engro Fertilizers', dividendYield: '14.20%', price: 154.50, changePercent: 0.95, volume: '2.5M', marketCap: '0.8B', peRatio: '6.4', safetyRating: 'AA+' },
      { symbol: 'FFC.KA', name: 'Fauji Fertilizer Company', dividendYield: '12.80%', price: 168.40, changePercent: 0.40, volume: '2.4M', marketCap: '0.8B', peRatio: '6.8', safetyRating: 'AA+' },
      { symbol: 'HUBC.KA', name: 'Hub Power Company', dividendYield: '11.50%', price: 124.50, changePercent: 1.10, volume: '3.1M', marketCap: '0.6B', peRatio: '5.2', safetyRating: 'AA+' }
    ]
  };
  return data[country] || data['USA'];
}
