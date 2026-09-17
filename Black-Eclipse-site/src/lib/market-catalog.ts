// ── Market catalog — provider-served instruments that are NOT `Asset` rows ────
// Commodity futures (`GC=F`) and FX pairs (`EURUSD=X`) live outside JDDS: they
// are quote-only instruments served straight from the Yahoo bridge. Their symbol
// lists were duplicated across /api/commodities, /api/forex and the header price
// ribbon; this module is the SINGLE SOURCE OF TRUTH.
//
// Pure data + pure lookups only (no I/O), so it is safe on the server (routes)
// and in the client bundle (the ribbon splits its configured symbols by family).

export interface CommodityDef {
  symbol: string;
  name: string;
  /** Display unit, e.g. `USD/oz`. */
  unit: string;
}

export interface ForexDef {
  symbol: string;
  name: string;
  base: string;
  quote: string;
}

/** Major commodity futures (Yahoo tickers; market "US" appends no suffix). */
export const COMMODITY_CATALOG: CommodityDef[] = [
  { symbol: "GC=F", name: "Gold", unit: "USD/oz" },
  { symbol: "SI=F", name: "Silver", unit: "USD/oz" },
  { symbol: "CL=F", name: "Crude Oil (WTI)", unit: "USD/bbl" },
  { symbol: "BZ=F", name: "Brent Crude", unit: "USD/bbl" },
  { symbol: "NG=F", name: "Natural Gas", unit: "USD/MMBtu" },
  { symbol: "HG=F", name: "Copper", unit: "USD/lb" },
  { symbol: "PL=F", name: "Platinum", unit: "USD/oz" },
  { symbol: "PA=F", name: "Palladium", unit: "USD/oz" },
  { symbol: "ALI=F", name: "Aluminum", unit: "USD/t" },
  { symbol: "ZW=F", name: "Wheat", unit: "USc/bu" },
  { symbol: "ZC=F", name: "Corn", unit: "USc/bu" },
  { symbol: "ZS=F", name: "Soybeans", unit: "USc/bu" },
  { symbol: "KC=F", name: "Coffee", unit: "USc/lb" },
  { symbol: "CC=F", name: "Cocoa", unit: "USD/t" },
  { symbol: "SB=F", name: "Sugar", unit: "USc/lb" },
  { symbol: "CT=F", name: "Cotton", unit: "USc/lb" },
  { symbol: "LE=F", name: "Live Cattle", unit: "USc/lb" },
];

/** Major forex pairs (Yahoo tickers; the bridge passes `=` symbols through). */
export const FOREX_CATALOG: ForexDef[] = [
  { symbol: "EURUSD=X", name: "Euro / US Dollar", base: "EUR", quote: "USD" },
  { symbol: "GBPUSD=X", name: "British Pound / US Dollar", base: "GBP", quote: "USD" },
  { symbol: "USDJPY=X", name: "US Dollar / Japanese Yen", base: "USD", quote: "JPY" },
  { symbol: "USDCHF=X", name: "US Dollar / Swiss Franc", base: "USD", quote: "CHF" },
  { symbol: "AUDUSD=X", name: "Australian Dollar / US Dollar", base: "AUD", quote: "USD" },
  { symbol: "USDCAD=X", name: "US Dollar / Canadian Dollar", base: "USD", quote: "CAD" },
  { symbol: "NZDUSD=X", name: "New Zealand Dollar / US Dollar", base: "NZD", quote: "USD" },
  { symbol: "USDCNY=X", name: "US Dollar / Chinese Yuan", base: "USD", quote: "CNY" },
  { symbol: "USDINR=X", name: "US Dollar / Indian Rupee", base: "USD", quote: "INR" },
  { symbol: "USDPKR=X", name: "US Dollar / Pakistani Rupee", base: "USD", quote: "PKR" },
  { symbol: "USDTRY=X", name: "US Dollar / Turkish Lira", base: "USD", quote: "TRY" },
  { symbol: "USDBRL=X", name: "US Dollar / Brazilian Real", base: "USD", quote: "BRL" },
  { symbol: "USDMXN=X", name: "US Dollar / Mexican Peso", base: "USD", quote: "MXN" },
  { symbol: "USDZAR=X", name: "US Dollar / South African Rand", base: "USD", quote: "ZAR" },
  { symbol: "USDSGD=X", name: "US Dollar / Singapore Dollar", base: "USD", quote: "SGD" },
  { symbol: "USDHKD=X", name: "US Dollar / Hong Kong Dollar", base: "USD", quote: "HKD" },
  { symbol: "USDKRW=X", name: "US Dollar / South Korean Won", base: "USD", quote: "KRW" },
  { symbol: "USDTHB=X", name: "US Dollar / Thai Baht", base: "USD", quote: "THB" },
  { symbol: "USDIDR=X", name: "US Dollar / Indonesian Rupiah", base: "USD", quote: "IDR" },
  { symbol: "USDVND=X", name: "US Dollar / Vietnamese Dong", base: "USD", quote: "VND" },
  { symbol: "USDAED=X", name: "US Dollar / UAE Dirham", base: "USD", quote: "AED" },
  { symbol: "USDSAR=X", name: "US Dollar / Saudi Riyal", base: "USD", quote: "SAR" },
  { symbol: "USDEGP=X", name: "US Dollar / Egyptian Pound", base: "USD", quote: "EGP" },
  { symbol: "USDNGN=X", name: "US Dollar / Nigerian Naira", base: "USD", quote: "NGN" },
  { symbol: "USDRUB=X", name: "US Dollar / Russian Ruble", base: "USD", quote: "RUB" },
  { symbol: "USDPLN=X", name: "US Dollar / Polish Zloty", base: "USD", quote: "PLN" },
  { symbol: "USDSEK=X", name: "US Dollar / Swedish Krona", base: "USD", quote: "SEK" },
  { symbol: "USDNOK=X", name: "US Dollar / Norwegian Krone", base: "USD", quote: "NOK" },
  { symbol: "USDDKK=X", name: "US Dollar / Danish Krone", base: "USD", quote: "DKK" },
  { symbol: "USDHUF=X", name: "US Dollar / Hungarian Forint", base: "USD", quote: "HUF" },
  { symbol: "USDCZK=X", name: "US Dollar / Czech Koruna", base: "USD", quote: "CZK" },
  { symbol: "USDILS=X", name: "US Dollar / Israeli Shekel", base: "USD", quote: "ILS" },
  { symbol: "USDPHP=X", name: "US Dollar / Philippine Peso", base: "USD", quote: "PHP" },
  { symbol: "USDMYR=X", name: "US Dollar / Malaysian Ringgit", base: "USD", quote: "MYR" },
];

const COMMODITY_BY_SYMBOL = new Map(COMMODITY_CATALOG.map((c) => [c.symbol.toUpperCase(), c]));
const FOREX_BY_SYMBOL = new Map(FOREX_CATALOG.map((p) => [p.symbol.toUpperCase(), p]));

/** The commodity definition for a symbol, or undefined. */
export function commodityDef(symbol: string): CommodityDef | undefined {
  return COMMODITY_BY_SYMBOL.get(symbol.trim().toUpperCase());
}

/** The forex definition for a symbol, or undefined. */
export function forexDef(symbol: string): ForexDef | undefined {
  return FOREX_BY_SYMBOL.get(symbol.trim().toUpperCase());
}

/**
 * True when the symbol is served by the commodity or forex feed rather than by
 * JDDS. Consumers use this to route a symbol to the right topic/endpoint.
 */
export function isCatalogSymbol(symbol: string): boolean {
  const s = symbol.trim().toUpperCase();
  return COMMODITY_BY_SYMBOL.has(s) || FOREX_BY_SYMBOL.has(s);
}

/** Display name for any catalog symbol, or undefined when not catalogued. */
export function catalogName(symbol: string): string | undefined {
  return commodityDef(symbol)?.name ?? forexDef(symbol)?.name;
}
