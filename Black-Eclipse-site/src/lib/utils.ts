import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(...inputs))
}

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
    let coin = cleanSym;
    if (coin.endsWith('USDT')) coin = coin.slice(0, -4);
    else if (coin.endsWith('USD')) coin = coin.slice(0, -3);
    else if (coin.endsWith('-USD')) coin = coin.slice(0, -4);
    else if (coin.endsWith('-USDT')) coin = coin.slice(0, -5);
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

  // Pakistani Indices & FX
  if (cleanSym === 'KSE100') return 'PSX:KSE100';
  if (cleanSym === 'KSE30') return 'PSX:KSE30';
  if (cleanSym === 'KMI30') return 'PSX:KMI30';
  if (cleanSym === 'PKR=X') return 'FX_IDC:USDPKR';

  // FX pairs (Yahoo "=X" style) → TradingView FX_IDC
  if (cleanSym.endsWith('=X')) {
    const pair = cleanSym.replace('=X', '');
    return `FX_IDC:${pair}`;
  }

  // Chinese Indices & FX
  if (cleanSym === 'SSEC') return 'SSE:000001';
  if (cleanSym === 'CSI300') return 'SSE:000300';
  if (cleanSym === 'HSI') return 'HSI:HSI';
  if (cleanSym === 'CNY=X') return 'FX_IDC:USDCNY';

  // Taiwan
  if (cleanSym === 'TWII') return 'TWSE:TAIEX';
  if (cleanSym === 'TWD=X') return 'FX_IDC:USDTWD';

  // Netherlands / EUR
  if (cleanSym === 'AEX') return 'AEX:AEX';
  if (cleanSym === 'AMX') return 'AEX:AMX';
  if (cleanSym === 'EUR=X') return 'FX_IDC:EURUSD';

  // Switzerland / CHF
  if (cleanSym === 'SSMI') return 'SIX:SMI';
  if (cleanSym === 'SPI') return 'SIX:SPI';
  if (cleanSym === 'CHF=X') return 'FX_IDC:USDCHF';

  // Suffix/Exchange mappings
  if (cleanSym.endsWith('.NS')) {
    return `NSE:${cleanSym.replace('.NS', '')}`;
  }
  if (cleanSym.endsWith('.KA')) {
    return `PSX:${cleanSym.replace('.KA', '')}`;
  }
  if (cleanSym.endsWith('.AS')) {
    return `EURONEXT:${cleanSym.replace('.AS', '')}`;
  }
  if (cleanSym.endsWith('.SW')) {
    return `SIX:${cleanSym.replace('.SW', '')}`;
  }
  if (cleanSym.endsWith('.SS')) {
    return `SSE:${cleanSym.replace('.SS', '')}`;
  }
  if (cleanSym.endsWith('.TW')) {
    return `TWSE:${cleanSym.replace('.TW', '')}`;
  }

  // Market-qualified resolution: prefix the symbol with its exchange so
  // numeric/ambiguous tickers resolve on TradingView (HKEX:1, TSE:1301,
  // PSX:786, SZSE:000001, TADAWUL:1010, ...). Yahoo-style suffixes are
  // stripped first (.TW/.SS/.T/.KS/.HK/.SI/.AX/.L/.DE/.TO/.NS...).
  if (market && MARKET_TV_EXCHANGE[market]) {
    const bare = cleanSym.replace(/\.(PSX|NS|KA|AS|SW|SS|BJ|SZ|TW|T|KS|KQ|HK|SI|KL|AX|L|DE|PA|AS|TO|SA|MX|ME|IS|JK|BK|VN|NG|CA|JO|SR|AE|EG|TO)$/, '');
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
