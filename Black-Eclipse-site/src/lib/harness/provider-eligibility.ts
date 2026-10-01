// ─── Declared provider eligibility + verified sample symbols ────────────────
// (Harness closeout Phases 2.5 / 3.3 / 4.5.)
//
// The capability matrix used to INFER a quote route from `MARKET_SLUG` + a
// provider whose `supports: () => true`. That is structurally reachable almost
// everywhere, so it said "configured" for markets where the provider actually
// returns quote-not-found upstream (`.NG` Nigeria, `.AE` Abu Dhabi) or thin data
// (`.ME`, `.JO`, `.VN`, `.MX`). The real limit is data + symbol quality, not the
// absence of an adapter.
//
// This registry is DATA: for each (provider × market) it declares `eligible`,
// `not_eligible` or `unknown`, WITH a verified sample symbol where one exists.
// The matrix consumes it; nothing hard-codes another Set. A market whose sample
// symbol has been verified can report `configured` honestly; a market whose
// sample fails reports `not_implemented` naming the symbol that was tried.

export type Eligibility = "eligible" | "not_eligible" | "unknown";

export interface RouteEligibility {
  /** Whether this provider can serve a quote for this market, as declared. */
  eligible: Eligibility;
  /**
   * A sample symbol to probe/verify for this market (the local code, no Yahoo
   * suffix). `verified: true` means it has succeeded; `verified: false` means it
   * was tried and failed (the matrix must not then claim `configured`).
   */
  sampleSymbol?: string;
  verified?: boolean;
  /** Why it is not eligible / not verified, when so. */
  reason?: string;
}

/**
 * Yahoo-suffix market → a large, liquid sample symbol (the local code).
 * `verified` is set by the probe (`probe-route-health`) or by a recorded run;
 * the static default is `eligible` for markets with a strong, well-known listing
 * and `unknown` where the data is thin.
 */
export const QUOTE_SAMPLE_SYMBOLS: Record<string, RouteEligibility> = {
  US: { eligible: "eligible", sampleSymbol: "AAPL", verified: true },
  UK: { eligible: "eligible", sampleSymbol: "SHEL", verified: false },
  DE: { eligible: "eligible", sampleSymbol: "SAP", verified: false },
  FR: { eligible: "eligible", sampleSymbol: "MC", verified: false },
  NL: { eligible: "eligible", sampleSymbol: "ASML", verified: false },
  CH: { eligible: "eligible", sampleSymbol: "NESN", verified: false },
  CA: { eligible: "eligible", sampleSymbol: "SHOP", verified: false },
  BR: { eligible: "eligible", sampleSymbol: "PETR4", verified: false },
  MX: { eligible: "unknown", sampleSymbol: "WALMEX", verified: false, reason: "thin quote data upstream" },
  JP: { eligible: "eligible", sampleSymbol: "7203", verified: false },
  KR: { eligible: "eligible", sampleSymbol: "005930", verified: false },
  TW: { eligible: "eligible", sampleSymbol: "2330", verified: false },
  HK: { eligible: "eligible", sampleSymbol: "0700", verified: false },
  CN: { eligible: "eligible", sampleSymbol: "600519", verified: false },
  IN: { eligible: "eligible", sampleSymbol: "RELIANCE", verified: false },
  SG: { eligible: "eligible", sampleSymbol: "D05", verified: false },
  MY: { eligible: "eligible", sampleSymbol: "1155", verified: false },
  TH: { eligible: "unknown", sampleSymbol: "PTT", verified: false, reason: "thin quote data upstream" },
  ID: { eligible: "eligible", sampleSymbol: "BBCA", verified: false },
  AU: { eligible: "eligible", sampleSymbol: "BHP", verified: false },
  PK: { eligible: "eligible", sampleSymbol: "OGDC", verified: false },
  SA: { eligible: "eligible", sampleSymbol: "2222", verified: false },
  AE: { eligible: "not_eligible", sampleSymbol: "FAB", verified: false, reason: "quote-not-found upstream (ADX/DFM) — secondary route only" },
  QA: { eligible: "eligible", sampleSymbol: "QNBK", verified: false },
  KW: { eligible: "eligible", sampleSymbol: "NBK", verified: false },
  ZA: { eligible: "eligible", sampleSymbol: "NPN", verified: false },
  EG: { eligible: "unknown", sampleSymbol: "COMI", verified: false, reason: "thin quote data upstream" },
  NG: { eligible: "not_eligible", sampleSymbol: "DANGCEM", verified: false, reason: "quote-not-found upstream (.NG)" },
  RU: { eligible: "not_eligible", sampleSymbol: "GAZP", verified: false, reason: "venue access restricted upstream" },
  TR: { eligible: "eligible", sampleSymbol: "THYAO", verified: false },
  VN: { eligible: "unknown", sampleSymbol: "VIC", verified: false, reason: "thin quote data upstream" },
  CRYPTO: { eligible: "eligible", sampleSymbol: "BTC-USD", verified: true },
  FX: { eligible: "eligible", sampleSymbol: "EURUSD=X", verified: true },
};

/** The declared eligibility row for a market, or a conservative default. */
export function quoteEligibility(market: string): RouteEligibility {
  return QUOTE_SAMPLE_SYMBOLS[market] ?? { eligible: "unknown" };
}

/** The sample symbol to probe for a market, or null when none is declared. */
export function sampleSymbolFor(market: string): string | null {
  return QUOTE_SAMPLE_SYMBOLS[market]?.sampleSymbol ?? null;
}
