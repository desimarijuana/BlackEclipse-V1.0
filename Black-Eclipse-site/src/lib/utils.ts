import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(...inputs))
}

// Exchange suffixes Yahoo appends to a bare ticker (AAPL.US, RELIANCE.NS,
// OGDC.PSX, 0001.HK, 7203.T, ...). Single source of truth — the previous
// alternation was duplicated (with drifting lists) here and in the quote /
// price-history routes, and contained duplicate branches (`.AS` and `.TO`
// appeared twice) plus a `.L` branch that a longer suffix could shadow.
const EXCHANGE_SUFFIXES = [
  'PSX', 'NS', 'BO', 'KA', 'AS', 'SW', 'SS', 'SZ', 'BJ',
  'TW', 'T', 'KS', 'KQ', 'HK', 'SI', 'KL', 'AX', 'L',
  'DE', 'PA', 'TO', 'SA', 'MX', 'ME', 'IS', 'JK', 'BK',
  'VN', 'NG', 'CA', 'JO', 'SR', 'AE', 'EG', 'US',
] as const;

// Longest-first so `.SW` is not read as `.S` etc.; anchored to the end so a
// legitimate ticker (AT&T's "T", a symbol ending "CO") is never truncated.
const EXCHANGE_SUFFIX_RE = new RegExp(`\\.(${[...EXCHANGE_SUFFIXES].sort((a, b) => b.length - a.length).join('|')})$`, 'i');

/** Strip a trailing Yahoo exchange suffix: "OGDC.PSX" → "OGDC", "0001.HK" → "0001". */
export function stripExchangeSuffix(symbol: string): string {
  return symbol.trim().toUpperCase().replace(EXCHANGE_SUFFIX_RE, '');
}

// Yahoo suffix → TradingView exchange prefix, for suffix-only resolution (no
// `market` argument). `.NS`/`.KA`/etc. keep their dedicated mappings; this
// closes the gaps that previously fell through as unresolvable raw strings.
const SUFFIX_TV_EXCHANGE: Record<string, string> = {
  NS: 'NSE', BO: 'BSE', KA: 'PSX', PSX: 'PSX',
  AS: 'EURONEXT', SW: 'SIX', SS: 'SSE', SZ: 'SZSE', BJ: 'BSE',
  TW: 'TWSE', T: 'TSE', KS: 'KRX', KQ: 'KRX',
  HK: 'HKEX', SI: 'SGX', KL: 'MYX', AX: 'ASX', L: 'LSE',
  DE: 'GETTEX', PA: 'EURONEXT', TO: 'TSX', SA: 'TADAWUL',
  MX: 'BMV', IS: 'BIST', JK: 'IDX', BK: 'SET', VN: 'HOSE',
  US: 'NASDAQ',
};

// Market id → TradingView exchange prefix (verified against scanner results).
// Passing the REAL exchange is the fix for symbols that don't resolve on
// TradingView (numeric tickers like "000006", "786", "1", "1301" are
// ambiguous without their exchange prefix).
const MARKET_TV_EXCHANGE: Record<string, string> = {
  PK: 'PSX',
  HK: 'HKEX',
  JP: 'TSE',
  KR: 'KRX',
  TW: 'TWSE',
  CN: 'SSE', // refined per-prefix below (SZSE for 0/3-prefix codes)
  SA: 'TADAWUL',
  SG: 'SGX',
  AU: 'ASX',
  CA: 'TSX',
  TR: 'BIST',
  DE: 'GETTEX',
  FR: 'EURONEXT',
  IN: 'NSE', // refined per-symbol (BSE-listed fall back below)
};

export function getTradingViewSymbol(
  symbol: string,
  isCrypto?: boolean,
  market?: string
): string {
  if (!symbol) return 'NASDAQ:AAPL';

  const cleanSym = symbol.trim().toUpperCase();

  if (isCrypto) {
    // Order matters: the longest / most specific suffix must be stripped
    // first or it is unreachable. "-USDT" before "-USD" before "USDT" before
    // "USD"; the old order tested bare "USD" before "-USD", so "BTC-USD"
    // became the invalid pair "BINANCE:BTC-USDT".
    let coin = cleanSym;
    if (coin.endsWith('-USDT')) coin = coin.slice(0, -5);
    else if (coin.endsWith('-USD')) coin = coin.slice(0, -4);
    else if (coin.endsWith('USDT')) coin = coin.slice(0, -4);
    else if (coin.endsWith('USD')) coin = coin.slice(0, -3);
    coin = coin.replace(/-+$/, ''); // tolerate "BTC-" style leftovers
    if (!coin) return 'BINANCE:BTCUSDT';
    return `BINANCE:${coin}USDT`;
  }

  const cryptoSymbols = new Set([
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "AVAX", "DOGE", "DOT", "TRX",
    "LINK", "MATIC", "SHIB", "LTC", "BCH", "UNI", "NEAR", "ICP", "FIL", "XLM",
    "FTM", "INJ", "SUI", "OP", "MKR", "THETA"
  ]);

  if (cryptoSymbols.has(cleanSym)) {
    return `BINANCE:${cleanSym}USDT`;
  }

  // Custom Index Mappings
  if (cleanSym === 'SPX' || cleanSym === '^SPX' || cleanSym === '^GSPC' || cleanSym === 'GSPC') return 'SP:SPX';
  if (cleanSym === 'IXIC' || cleanSym === '^IXIC') return 'NASDAQ:IXIC';
  if (cleanSym === 'DJI' || cleanSym === '^DJI') return 'DJ:DJI';
  if (cleanSym === 'RUT' || cleanSym === '^RUT') return 'INDEX:RUT';
  if (cleanSym === 'BTC' || cleanSym === 'BTCUSD') return 'BINANCE:BTCUSDT';
  if (cleanSym === 'GC=F' || cleanSym === 'GOLD') return 'TVC:GOLD';
  if (cleanSym === 'SI=F') return 'TVC:SILVER';
  if (cleanSym === 'CL=F') return 'TVC:USOIL';
  if (cleanSym === 'BZ=F') return 'TVC:UKOIL';
  if (cleanSym === 'NG=F') return 'TVC:NATGAS';
  if (cleanSym === 'HG=F') return 'COMEX:HG1!';
  if (cleanSym === 'PL=F') return 'TVC:PLATINUM';
  if (cleanSym === 'PA=F') return 'TVC:PALLADIUM';
  if (cleanSym === 'ZW=F') return 'CBOT:ZW1!';
  if (cleanSym === 'ZC=F') return 'CBOT:ZC1!';
  if (cleanSym === 'ZS=F') return 'CBOT:ZS1!';
  if (cleanSym === 'KC=F') return 'ICEUS:KC1!';
  if (cleanSym === 'CC=F') return 'ICEUS:CC1!';
  if (cleanSym === 'SB=F') return 'ICEUS:SB1!';
  if (cleanSym === 'CT=F') return 'ICEUS:CT1!';
  if (cleanSym === 'LE=F') return 'CME:LE1!';
  if (cleanSym === 'ALI=F') return 'COMEX:ALI1!';

  // Indian Indices
  if (cleanSym === '^NSEI' || cleanSym === 'NSEI') return 'NSE:NIFTY';
  if (cleanSym === '^BSESN' || cleanSym === 'BSESN') return 'BSE:SENSEX';
  if (cleanSym === '^NIFTYIT') return 'NSE:NIFTY_IT';
  if (cleanSym === '^NSEBANK') return 'NSE:BANKNIFTY';

  // Pakistani Indices
  if (cleanSym === 'KSE100') return 'PSX:KSE100';
  if (cleanSym === 'KSE30') return 'PSX:KSE30';
  if (cleanSym === 'KMI30') return 'PSX:KMI30';

  // Chinese, Taiwanese, Dutch and Swiss indices (FX handled below).
  if (cleanSym === 'SSEC') return 'SSE:000001';
  if (cleanSym === 'CSI300') return 'SSE:000300';
  if (cleanSym === 'HSI') return 'HSI:HSI';
  if (cleanSym === 'TWII') return 'TWSE:TAIEX';
  if (cleanSym === 'AEX') return 'AEX:AEX';
  if (cleanSym === 'AMX') return 'AEX:AMX';
  if (cleanSym === 'SSMI') return 'SIX:SMI';
  if (cleanSym === 'SPI') return 'SIX:SPI';

  // Curated FX pairs — MUST be checked before the generic "=X" branch below,
  // which otherwise turned "EUR=X" into "FX_IDC:EUR" (not a pair) and made
  // these explicit mappings unreachable dead code.
  const FX_PAIRS: Record<string, string> = {
    'EUR=X': 'FX_IDC:EURUSD',
    'GBP=X': 'FX_IDC:GBPUSD',
    'JPY=X': 'FX_IDC:USDJPY',
    'PKR=X': 'FX_IDC:USDPKR',
    'CNY=X': 'FX_IDC:USDCNY',
    'TWD=X': 'FX_IDC:USDTWD',
    'CHF=X': 'FX_IDC:USDCHF',
    'INR=X': 'FX_IDC:USDINR',
    'CAD=X': 'FX_IDC:USDCAD',
    'AUD=X': 'FX_IDC:AUDUSD',
  };
  if (FX_PAIRS[cleanSym]) return FX_PAIRS[cleanSym];

  // FX pairs (Yahoo "=X" style) → TradingView FX_IDC
  if (cleanSym.endsWith('=X')) {
    const pair = cleanSym.slice(0, -2);
    return `FX_IDC:${pair}`;
  }
  // Suffix/Exchange mappings — resolve a Yahoo-suffixed ticker on its own,
  // without needing the caller to pass `market`. Previously only .NS/.KA/.AS/
  // .SW/.SS/.TW were handled here; "0001.HK", "7203.T" or "CSPX.L" fell
  // through and returned a raw string TradingView cannot resolve.
  const suffixExchange = SUFFIX_TV_EXCHANGE[cleanSym.split('.').pop() ?? ''];
  if (suffixExchange) {
    return `${suffixExchange}:${stripExchangeSuffix(cleanSym)}`;
  }

  // Market-qualified resolution: prefix the symbol with its exchange so
  // numeric/ambiguous tickers resolve on TradingView (HKEX:1, TSE:1301,
  // PSX:786, SZSE:000001, TADAWUL:1010, ...). Yahoo-style suffixes are
  // stripped first via the shared helper (.TW/.SS/.T/.KS/.HK/.SI/.AX/.L/...).
  if (market && MARKET_TV_EXCHANGE[market]) {
    const bare = stripExchangeSuffix(cleanSym);
    let exchange = MARKET_TV_EXCHANGE[market];
    // China: 6xxxxx → Shanghai, 0/3xxxxx → Shenzhen, 4/8xxxxx → Beijing.
    if (market === 'CN') {
      if (/^(0|3)/.test(bare)) exchange = 'SZSE';
      else if (/^(4|8)/.test(bare)) exchange = 'BSE';
      else exchange = 'SSE';
    }
    // India: keep NSE default; BSE-only tickers are rare in JDDS.
    return `${exchange}:${bare}`;
  }

  // Fallback defaults
  // For crypto
  if (cleanSym.includes('USDT') || (cleanSym.includes('USD') && (cleanSym.startsWith('BTC') || cleanSym.startsWith('ETH') || cleanSym.startsWith('SOL')))) {
    return `BINANCE:${cleanSym}`;
  }

  return cleanSym;
}
