import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function getTradingViewSymbol(symbol: string, isCrypto?: boolean): string {
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

  // Fallback defaults
  // For crypto
  if (cleanSym.includes('USDT') || (cleanSym.includes('USD') && (cleanSym.startsWith('BTC') || cleanSym.startsWith('ETH') || cleanSym.startsWith('SOL')))) {
    return `BINANCE:${cleanSym}`;
  }

  return cleanSym;
}
