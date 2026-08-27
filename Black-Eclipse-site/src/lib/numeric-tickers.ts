// Real company names for markets whose tickers are pure numeric codes
// (China SSE/SZSE, Korea KRX, Hong Kong, Taiwan). TradingView returns the
// code as the name for these, so the DB stores "600519" as both symbol and
// name — users would see a bare number. This map restores the real name for
// the top instruments actually shown in the overview/screener.
export const NUMERIC_TICKER_NAMES: Record<string, Record<string, string>> = {
  CN: {
    "688825": "CXMT Corporation",
    "601398": "ICBC",
    "601288": "Agricultural Bank of China",
    "601939": "China Construction Bank",
    "601857": "PetroChina",
    "300750": "CATL",
    "601988": "Bank of China",
    "600519": "Kweichow Moutai",
    "600941": "China Mobile",
    "601138": "Foxconn Industrial Internet",
    "000001": "Ping An Bank",
    "000002": "Vanke A",
    "600036": "China Merchants Bank",
    "601318": "Ping An Insurance",
    "601899": "Zijin Mining",
    "600028": "Sinopec",
    "601166": "Industrial Bank",
    "600000": "SPD Bank",
    "600030": "CITIC Securities",
    "000858": "Wuliangye",
  },
  KR: {
    "005930": "Samsung Electronics",
    "005935": "Samsung Electronics P",
    "000660": "SK hynix",
    "402340": "SK Square",
    "009150": "Samsung Electro-Mechanics",
    "009155": "Samsung Electro-Mechanics P",
    "005380": "Hyundai Motor",
    "005385": "Hyundai Motor P",
    "005387": "Hyundai Motor 3P",
    "005389": "Hyundai Motor 4P",
    "051910": "LG Chem",
    "207940": "Samsung Biologics",
    "000270": "Kia",
    "068270": "Celltrion",
    "005490": "POSCO Holdings",
  },
  HK: {
    "700": "Tencent",
    "80700": "Tencent (R)",
    "1398": "ICBC H",
    "5": "HSBC Holdings",
    "1288": "AgBank H",
    "939": "CCB H",
    "857": "PetroChina H",
    "9988": "Alibaba",
    "89988": "Alibaba (R)",
    "3750": "CATL H",
    "941": "China Mobile H",
    "2628": "China Life",
    "3968": "CM Bank H",
    "2318": "Ping An H",
    "1299": "AIA Group",
  },
  TW: {
    "2330": "TSMC",
    "2454": "MediaTek",
    "2308": "Delta Electronics",
    "2317": "Hon Hai Precision",
    "3711": "ASE Technology",
    "2383": "Elite Material",
    "2881": "Fubon Financial",
    "2408": "Nanya Technology",
    "3037": "Unimicron",
    "2303": "UMC",
    "2603": "Evergreen Marine",
    "2313": "Compal Electronics",
    "2891": "CTBC Financial",
    "2882": "Cathay Financial",
    "2327": "Yageo",
  },
};

/** Resolve the display name for a numeric-ticker asset. */
export function displayAssetName(marketId: string, symbol: string, name: string): string {
  const map = NUMERIC_TICKER_NAMES[marketId];
  if (map && map[symbol] && /^\d+$/.test(symbol) && name === symbol) {
    return map[symbol];
  }
  return name;
}
