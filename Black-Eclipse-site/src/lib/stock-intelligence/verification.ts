// Deterministic verification rules for stock-search facts. Search results are
// POINTERS, not evidence: a fact is only marked VERIFIED when an official host
// backs it. Two independent reputable results corroborate; snippets can
// corroborate a quote but never make it "verified".

export type VerificationState =
  | 'VERIFIED'
  | 'CORROBORATED'
  | 'UNVERIFIED'
  | 'CONFLICTED'
  | 'UNAVAILABLE';

export type VerificationCheckId = 'identity' | 'listing' | 'filings' | 'quote';

export interface VerificationEvidence {
  title: string;
  url: string;
  snippet: string;
  host: string;
  official: boolean;
}

export interface VerificationCheck {
  id: VerificationCheckId;
  label: string;
  state: VerificationState;
  detail: string;
  evidence: VerificationEvidence[];
}

export interface StockVerificationResponse {
  available: boolean;
  symbol: string;
  market: string;
  companyName: string | null;
  generatedAt: string;
  overall: VerificationState;
  checks: VerificationCheck[];
  warnings: string[];
  reason?: string;
}

export interface SearchResultLike {
  title?: string;
  url?: string;
  snippet?: string;
}

const OFFICIAL_DOMAINS: Record<string, string[]> = {
  US: ['sec.gov', 'nyse.com', 'nasdaq.com', 'otcmarkets.com'],
  IN: ['nseindia.com', 'bseindia.com', 'sebi.gov.in', 'rbi.org.in'],
  UK: ['londonstockexchange.com', 'companieshouse.gov.uk', 'fca.org.uk'],
  AE: ['dfm.ae', 'adx.ae', 'sca.gov.ae'],
  PK: ['psx.com.pk', 'secp.gov.pk', 'sbp.org.pk'],
  SA: ['saudiexchange.sa', 'cma.org.sa'],
  CN: ['sse.com.cn', 'szse.cn', 'csrc.gov.cn'],
  HK: ['hkex.com.hk', 'hkexnews.hk', 'sfc.hk'],
  JP: ['jpx.co.jp', 'edinet-fsa.go.jp', 'fsa.go.jp'],
  KR: ['krx.co.kr', 'kind.krx.co.kr', 'fss.or.kr'],
  TW: ['twse.com.tw', 'tpex.org.tw', 'fsc.gov.tw'],
  DE: ['deutsche-boerse.com', 'bafin.de'],
  FR: ['euronext.com', 'amf-france.org'],
  NL: ['euronext.com', 'afm.nl'],
  CA: ['tmx.com', 'sedar.com', 'osc.ca'],
  AU: ['asx.com.au', 'asic.gov.au'],
  BR: ['b3.com.br', 'cvm.gov.br'],
  MX: ['bmv.com.mx', 'cnbv.gob.mx'],
  SG: ['sgx.com', 'mas.gov.sg'],
  MY: ['bursamalaysia.com', 'sc.com.my'],
  ID: ['idx.co.id', 'ojk.go.id'],
  TH: ['set.or.th', 'sec.or.th'],
  VN: ['hsx.vn', 'hnx.vn', 'ssc.gov.vn'],
  TR: ['borsaistanbul.com', 'spk.gov.tr'],
  ZA: ['jse.co.za', 'fsca.co.za'],
  NG: ['ngxgroup.com', 'sec.gov.ng'],
  EG: ['egx.com.eg', 'fra.gov.eg'],
  CRYPTO: ['sec.gov', 'cftc.gov', 'coinbase.com', 'binance.com'],
  GLOBAL: ['sec.gov', 'worldbank.org', 'imf.org'],
};

export function officialDomainsForMarket(market: string): string[] {
  return OFFICIAL_DOMAINS[market.trim().toUpperCase()] ?? ['sec.gov'];
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./i, '').toLowerCase();
  } catch {
    return '';
  }
}

export function isOfficialHost(host: string, domains: string[]): boolean {
  const clean = host.toLowerCase();
  return domains.some((domain) => clean === domain || clean.endsWith(`.${domain}`));
}

export function normalizeName(value: string | null | undefined): string {
  return (value ?? '')
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/\b(inc|corp|corporation|company|co|ltd|limited|plc|llc|ag|sa|nv|bv|holdings?|group|the)\b/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function nameTokens(name: string | null | undefined): string[] {
  return normalizeName(name)
    .split(' ')
    .filter((token) => token.length >= 3);
}

export function toEvidence(results: SearchResultLike[], domains: string[]): VerificationEvidence[] {
  return results
    .filter((result): result is Required<Pick<SearchResultLike, 'title' | 'url'>> & SearchResultLike =>
      typeof result.url === 'string' && result.url.length > 0,
    )
    .map((result) => {
      const host = hostOf(result.url);
      return {
        title: result.title ?? result.url,
        url: result.url,
        snippet: result.snippet ?? '',
        host,
        official: isOfficialHost(host, domains),
      };
    });
}

function mentionsSymbol(evidence: VerificationEvidence, symbol: string): boolean {
  const needle = symbol.trim().toLowerCase();
  if (!needle) return false;
  const text = `${evidence.title} ${evidence.snippet}`.toLowerCase();
  return new RegExp(`(^|[^a-z0-9])${needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-z0-9]|$)`, 'i').test(text);
}

function mentionsName(evidence: VerificationEvidence, tokens: string[]): boolean {
  if (tokens.length === 0) return false;
  const text = `${evidence.title} ${evidence.snippet}`.toLowerCase();
  const hits = tokens.filter((token) => text.includes(token)).length;
  return hits >= Math.min(2, tokens.length);
}

function extractPrices(text: string): number[] {
  const out: number[] = [];
  const re = /(?:[$€£¥₹]|\b(?:usd|inr|gbp|eur|aed|sar|pkr|jpy|cny|hkd)\b)?\s*(\d{1,7}(?:[.,]\d{1,4})?)/gi;
  for (const match of text.matchAll(re)) {
    const raw = match[1];
    const value = Number(raw.replace(/,/g, ''));
    if (Number.isFinite(value) && value > 0) out.push(value);
  }
  return out;
}

function quoteCorroborated(evidence: VerificationEvidence[], price: number | null): { state: VerificationState; detail: string } {
  if (price == null || !Number.isFinite(price) || price <= 0) {
    return { state: 'UNVERIFIED', detail: 'No provider price was supplied for a cross-check.' };
  }
  for (const item of evidence) {
    const numbers = extractPrices(`${item.title} ${item.snippet}`);
    if (numbers.some((value) => Math.abs(value / price - 1) <= 0.02)) {
      return item.official
        ? { state: 'VERIFIED', detail: `Official source reports a price within 2% of the provider quote (${price}).` }
        : { state: 'CORROBORATED', detail: `Search snippets report a price within 2% of the provider quote (${price}); snippets are not authoritative.` };
    }
  }
  return { state: 'UNVERIFIED', detail: 'No retrieved result independently reports the provider quote.' };
}

export function identityCheck(
  results: SearchResultLike[],
  symbol: string,
  companyName: string | null,
  domains: string[],
): VerificationCheck {
  const evidence = toEvidence(results, domains);
  const tokens = nameTokens(companyName);
  const matches = evidence.filter((item) => mentionsSymbol(item, symbol) || mentionsName(item, tokens));
  const official = matches.filter((item) => item.official);
  if (official.length > 0) {
    return {
      id: 'identity', label: 'Company identity', state: 'VERIFIED',
      detail: `Official source confirms ${symbol}${companyName ? ` / ${companyName}` : ''}.`,
      evidence: official.slice(0, 3),
    };
  }
  if (matches.length >= 2) {
    return {
      id: 'identity', label: 'Company identity', state: 'CORROBORATED',
      detail: 'Two or more independent results reference this symbol/company; no official host was retrieved.',
      evidence: matches.slice(0, 3),
    };
  }
  if (matches.length === 1) {
    return {
      id: 'identity', label: 'Company identity', state: 'UNVERIFIED',
      detail: 'Only one retrieved result references this symbol/company.',
      evidence: matches,
    };
  }
  return {
    id: 'identity', label: 'Company identity', state: 'UNAVAILABLE',
    detail: 'No retrieved result confirmed this symbol/company identity.',
    evidence: evidence.slice(0, 2),
  };
}

export function listingCheck(results: SearchResultLike[], domainResults: SearchResultLike[], symbol: string, market: string, domains: string[]): VerificationCheck {
  const evidence = toEvidence([...domainResults, ...results], domains);
  const official = evidence.filter((item) => item.official && mentionsSymbol(item, symbol));
  if (official.length > 0) {
    return {
      id: 'listing', label: `Listing / ${market}`, state: 'VERIFIED',
      detail: `Official exchange or regulator source references ${symbol}.`,
      evidence: official.slice(0, 3),
    };
  }
  const symbolResults = evidence.filter((item) => mentionsSymbol(item, symbol));
  if (symbolResults.length > 0) {
    return {
      id: 'listing', label: `Listing / ${market}`, state: 'CORROBORATED',
      detail: 'Search results reference the ticker, but no official exchange/regulator page was retrieved.',
      evidence: symbolResults.slice(0, 3),
    };
  }
  return {
    id: 'listing', label: `Listing / ${market}`, state: 'UNVERIFIED',
    detail: 'Could not confirm the listing from retrieved results.',
    evidence: evidence.slice(0, 2),
  };
}

export function filingsCheck(results: SearchResultLike[], domainResults: SearchResultLike[], symbol: string, domains: string[]): VerificationCheck {
  const evidence = toEvidence([...domainResults, ...results], domains);
  const official = evidence.filter((item) => item.official && (mentionsSymbol(item, symbol) || /filing|annual report|10-?k|20-?f|results/i.test(`${item.title} ${item.snippet}`)));
  if (official.length > 0) {
    return {
      id: 'filings', label: 'Filings & reports', state: 'VERIFIED',
      detail: 'An official filing/regulator source was retrieved.',
      evidence: official.slice(0, 3),
    };
  }
  const filingLike = evidence.filter((item) => /filing|annual report|10-?k|20-?f|earnings|results/i.test(`${item.title} ${item.snippet}`));
  if (filingLike.length > 0) {
    return {
      id: 'filings', label: 'Filings & reports', state: 'CORROBORATED',
      detail: 'Filing-like results were retrieved, but not from an official host.',
      evidence: filingLike.slice(0, 3),
    };
  }
  return {
    id: 'filings', label: 'Filings & reports', state: 'UNVERIFIED',
    detail: 'No filing source was retrieved for this symbol.',
    evidence: evidence.slice(0, 2),
  };
}

export function quoteCheck(results: SearchResultLike[], symbol: string, price: number | null, domains: string[]): VerificationCheck {
  const evidence = toEvidence(results, domains).filter((item) => mentionsSymbol(item, symbol) || extractPrices(item.snippet).length > 0);
  const verdict = quoteCorroborated(evidence, price);
  return {
    id: 'quote', label: 'Quote cross-check', state: verdict.state,
    detail: verdict.detail,
    evidence: evidence.slice(0, 3),
  };
}

export function buildVerificationQueries(symbol: string, companyName: string | null, market: string): Record<VerificationCheckId, string> {
  const subject = companyName ? `"${companyName}"` : symbol;
  const domains = officialDomainsForMarket(market);
  const site = domains[0];
  return {
    identity: `${subject} ${symbol} official investor relations`,
    listing: `site:${site} ${symbol} ${companyName ?? ''}`.trim(),
    filings: `${subject} ${symbol} annual report filing ${site}`,
    quote: `${symbol} ${companyName ?? ''} stock price`.trim(),
  };
}

export function overallState(checks: VerificationCheck[]): VerificationState {
  if (checks.some((check) => check.state === 'CONFLICTED')) return 'CONFLICTED';
  if (checks.length > 0 && checks.every((check) => check.state === 'VERIFIED')) return 'VERIFIED';
  if (checks.some((check) => check.state === 'VERIFIED' || check.state === 'CORROBORATED')) return 'CORROBORATED';
  if (checks.length > 0 && checks.every((check) => check.state === 'UNAVAILABLE')) return 'UNAVAILABLE';
  return 'UNVERIFIED';
}
