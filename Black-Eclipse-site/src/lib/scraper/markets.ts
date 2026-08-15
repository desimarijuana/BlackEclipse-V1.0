// Market metadata + seed symbol universes for price_scraper.
// User picks which markets to scrape; US is the default.

export interface MarketSeed {
  id: string;
  country: string; // 'US', 'PK', 'IN', 'CRYPTO'
  exchange: string;
  timezone: string;
  openHour: number; // 24h local
  closeHour: number;
  isCrypto: boolean;
  symbols: { symbol: string; name: string; sector?: string; industry?: string }[];
}

export const MARKET_SEEDS: MarketSeed[] = [
  {
    id: "US",
    country: "US",
    exchange: "NYSE/NASDAQ",
    timezone: "America/New_York",
    openHour: 9,
    closeHour: 16,
    isCrypto: false,
    symbols: [
      { symbol: "AAPL", name: "Apple Inc.", sector: "Technology", industry: "Consumer Electronics" },
      { symbol: "MSFT", name: "Microsoft Corp.", sector: "Technology", industry: "Software - Infrastructure" },
      { symbol: "NVDA", name: "NVIDIA Corp.", sector: "Technology", industry: "Semiconductors" },
      { symbol: "TSLA", name: "Tesla Inc.", sector: "Consumer Discretionary", industry: "Auto Manufacturers" },
      { symbol: "AMZN", name: "Amazon.com Inc.", sector: "Consumer Discretionary", industry: "Internet Retail" },
      { symbol: "META", name: "Meta Platforms", sector: "Communication Services", industry: "Internet Content" },
      { symbol: "GOOGL", name: "Alphabet Inc.", sector: "Communication Services", industry: "Internet Content" },
      { symbol: "GOOG", name: "Alphabet Inc. (Class C)", sector: "Communication Services", industry: "Internet Content" },
      { symbol: "BRK.B", name: "Berkshire Hathaway", sector: "Financials", industry: "Insurance" },
      { symbol: "LLY", name: "Eli Lilly", sector: "Healthcare", industry: "Drug Manufacturers" },
      { symbol: "AVGO", name: "Broadcom", sector: "Technology", industry: "Semiconductors" },
      { symbol: "JPM", name: "JPMorgan Chase & Co.", sector: "Financials", industry: "Diversified Banks" },
      { symbol: "V", name: "Visa Inc.", sector: "Financials", industry: "Credit Services" },
      { symbol: "JNJ", name: "Johnson & Johnson", sector: "Healthcare", industry: "Drug Manufacturers" },
      { symbol: "XOM", name: "Exxon Mobil", sector: "Energy", industry: "Oil & Gas" },
      { symbol: "WMT", name: "Walmart", sector: "Consumer Staples", industry: "Discount Stores" },
      { symbol: "MA", name: "Mastercard", sector: "Financials", industry: "Credit Services" },
      { symbol: "PG", name: "Procter & Gamble", sector: "Consumer Staples", industry: "Household Products" },
      { symbol: "UNH", name: "UnitedHealth Group", sector: "Healthcare", industry: "Healthcare Plans" },
      { symbol: "HD", name: "Home Depot", sector: "Consumer Discretionary", industry: "Home Improvement" },
      { symbol: "ORCL", name: "Oracle", sector: "Technology", industry: "Software - Infrastructure" },
      { symbol: "COST", name: "Costco Wholesale", sector: "Consumer Staples", industry: "Discount Stores" },
      { symbol: "MRK", name: "Merck & Co.", sector: "Healthcare", industry: "Drug Manufacturers" },
      { symbol: "ABBV", name: "AbbVie", sector: "Healthcare", industry: "Drug Manufacturers" },
      { symbol: "BAC", name: "Bank of America", sector: "Financials", industry: "Diversified Banks" },
      { symbol: "KO", name: "Coca-Cola", sector: "Consumer Staples", industry: "Beverages" },
      { symbol: "PEP", name: "PepsiCo", sector: "Consumer Staples", industry: "Beverages" },
      { symbol: "CSCO", name: "Cisco Systems", sector: "Technology", industry: "Communication Equipment" },
      { symbol: "MCD", name: "McDonald's", sector: "Consumer Discretionary", industry: "Restaurants" },
      { symbol: "AMD", name: "Advanced Micro Devices", sector: "Technology", industry: "Semiconductors" },
      { symbol: "CRM", name: "Salesforce", sector: "Technology", industry: "Software - Application" },
      { symbol: "ADBE", name: "Adobe", sector: "Technology", industry: "Software - Infrastructure" },
      { symbol: "NFLX", name: "Netflix", sector: "Communication Services", industry: "Entertainment" },
      { symbol: "TMO", name: "Thermo Fisher Scientific", sector: "Healthcare", industry: "Diagnostics" },
      { symbol: "ACN", name: "Accenture", sector: "Technology", industry: "Information Technology Services" },
      { symbol: "CVX", name: "Chevron", sector: "Energy", industry: "Oil & Gas" },
      { symbol: "DIS", name: "Walt Disney", sector: "Communication Services", industry: "Entertainment" },
      { symbol: "WFC", name: "Wells Fargo", sector: "Financials", industry: "Diversified Banks" },
      { symbol: "ABT", name: "Abbott Laboratories", sector: "Healthcare", industry: "Medical Devices" },
      { symbol: "DHR", name: "Danaher", sector: "Healthcare", industry: "Diagnostics" },
      { symbol: "INTC", name: "Intel", sector: "Technology", industry: "Semiconductors" },
      { symbol: "CMCSA", name: "Comcast", sector: "Communication Services", industry: "Entertainment" },
      { symbol: "PFE", name: "Pfizer", sector: "Healthcare", industry: "Drug Manufacturers" },
      { symbol: "VZ", name: "Verizon", sector: "Communication Services", industry: "Telecom" },
      { symbol: "T", name: "AT&T", sector: "Communication Services", industry: "Telecom" },
      { symbol: "QCOM", name: "Qualcomm", sector: "Technology", industry: "Semiconductors" },
      { symbol: "NKE", name: "Nike", sector: "Consumer Discretionary", industry: "Apparel" },
      { symbol: "TXN", name: "Texas Instruments", sector: "Technology", industry: "Semiconductors" },
      { symbol: "CAT", name: "Caterpillar", sector: "Industrials", industry: "Farm Machinery" },
      { symbol: "GE", name: "GE Aerospace", sector: "Industrials", industry: "Aerospace & Defense" },
    ],
  },
  {
    id: "PK",
    country: "PK",
    exchange: "PSX",
    timezone: "Asia/Karachi",
    openHour: 9,
    closeHour: 15,
    isCrypto: false,
    symbols: [
      { symbol: "LUCK", name: "Lucky Cement", sector: "Materials", industry: "Construction Materials" },
      { symbol: "HUBC", name: "Hub Power Company", sector: "Utilities", industry: "Electric Utilities" },
      { symbol: "ENGRO", name: "Engro Corporation", sector: "Materials", industry: "Fertilizers" },
      { symbol: "FFC", name: "Fauji Fertilizer", sector: "Materials", industry: "Fertilizers" },
      { symbol: "OGDC", name: "Oil & Gas Development", sector: "Energy", industry: "Oil & Gas" },
      { symbol: "SYS", name: "Systems Limited", sector: "Technology", industry: "Software" },
      { symbol: "MCB", name: "MCB Bank", sector: "Financials", industry: "Banks" },
      { symbol: "MARI", name: "Mari Petroleum", sector: "Energy", industry: "Oil & Gas" },
    ],
  },
  {
    id: "IN",
    country: "IN",
    exchange: "NSE",
    timezone: "Asia/Kolkata",
    openHour: 9,
    closeHour: 15,
    isCrypto: false,
    symbols: [
      { symbol: "RELIANCE", name: "Reliance Industries", sector: "Energy", industry: "Conglomerate" },
      { symbol: "TCS", name: "Tata Consultancy Services", sector: "Technology", industry: "IT Services" },
      { symbol: "HDFCBANK", name: "HDFC Bank", sector: "Financials", industry: "Banks" },
      { symbol: "INFY", name: "Infosys", sector: "Technology", industry: "IT Services" },
      { symbol: "TATAMOTORS", name: "Tata Motors", sector: "Consumer Discretionary", industry: "Autos" },
      { symbol: "ITC", name: "ITC Limited", sector: "Consumer Staples", industry: "Tobacco/Agri" },
      { symbol: "ICICIBANK", name: "ICICI Bank", sector: "Financials", industry: "Banks" },
    ],
  },
  {
    id: "CRYPTO",
    country: "CRYPTO",
    exchange: "Global",
    timezone: "UTC",
    openHour: 0,
    closeHour: 24,
    isCrypto: true,
    symbols: [
      { symbol: "BTC", name: "Bitcoin", sector: "Layer 1", industry: "Layer 1" },
      { symbol: "ETH", name: "Ethereum", sector: "Layer 1", industry: "Layer 1" },
      { symbol: "SOL", name: "Solana", sector: "Layer 1", industry: "Layer 1" },
      { symbol: "BNB", name: "BNB", sector: "Layer 1", industry: "Layer 1" },
      { symbol: "XRP", name: "XRP", sector: "Payments", industry: "Payments" },
      { symbol: "DOGE", name: "Dogecoin", sector: "Meme", industry: "Meme" },
      { symbol: "ADA", name: "Cardano", sector: "Layer 1", industry: "Layer 1" },
      { symbol: "AVAX", name: "Avalanche", sector: "Layer 1", industry: "Layer 1" },
    ],
  },
];

export function getMarketSeed(country: string): MarketSeed | undefined {
  return MARKET_SEEDS.find((m) => m.id === country);
}
