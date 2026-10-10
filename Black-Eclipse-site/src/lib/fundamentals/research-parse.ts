// ── Research → structured financial facts (fundamentals fallback) ────────────
// When no filings provider has data, Eclipse runs the web-research engine and
// gets back verified text (findings/claims). This module deterministically pulls
// the standard financial line items out of that text so the UI can show real
// numbers (with their source text) instead of only sentences.
//
// It is intentionally conservative: a fact is emitted only when a known metric
// keyword and a parseable number appear in the SAME segment, and the metric is
// rescaled from words (million/billion) or suffixes (M/B/K) to a base value. It
// NEVER invents a number — no number, no fact.

export type FactUnit = 'currency' | 'percent' | 'ratio' | 'number';

export interface FinancialFact {
  key: string;
  label: string;
  value: number;
  unit: FactUnit;
  /** The source sentence the value was extracted from (evidence). */
  raw: string;
}

// Metric keyword → canonical key/label/unit. First match wins; longer/more
// specific keys are listed first so "operating income" beats "income".
const METRICS: Array<{ key: string; label: string; unit: FactUnit; re: RegExp }> = [
  { key: 'grossMargin', label: 'Gross margin', unit: 'percent', re: /\bgross margin|gross profit margin\b/i },
  { key: 'operatingMargin', label: 'Operating margin', unit: 'percent', re: /\boperating margin|operating profit margin\b/i },
  { key: 'netMargin', label: 'Net margin', unit: 'percent', re: /\bnet (profit )?margin\b/i },
  { key: 'freeCashFlow', label: 'Free cash flow', unit: 'currency', re: /\bfree cash flow\b|\bfcf\b/i },
  { key: 'operatingCashFlow', label: 'Operating cash flow', unit: 'currency', re: /\boperating cash flow|cash (flow )?from operations\b/i },
  { key: 'grossProfit', label: 'Gross profit', unit: 'currency', re: /\bgross profit\b/i },
  { key: 'operatingIncome', label: 'Operating income', unit: 'currency', re: /\boperating (income|profit)\b|\bebit\b/i },
  { key: 'ebitda', label: 'EBITDA', unit: 'currency', re: /\bebitda\b/i },
  { key: 'netIncome', label: 'Net income', unit: 'currency', re: /\bnet (income|profit)\b|profit for the (year|period)\b|\bbottom[- ]?line\b/i },
  { key: 'eps', label: 'EPS', unit: 'ratio', re: /\b(earnings per share|diluted eps|basic eps|eps)\b/i },
  { key: 'revenue', label: 'Revenue', unit: 'currency', re: /\b(revenue|sales|turnover|top[- ]?line)\b/i },
  { key: 'totalDebt', label: 'Total debt', unit: 'currency', re: /\btotal debt\b/i },
  { key: 'netDebt', label: 'Net debt', unit: 'currency', re: /\bnet debt\b/i },
  { key: 'cash', label: 'Cash', unit: 'currency', re: /\bcash (and (cash )?equivalents|balance|position)\b/i },
  { key: 'totalAssets', label: 'Total assets', unit: 'currency', re: /\btotal assets\b/i },
  { key: 'totalEquity', label: 'Total equity', unit: 'currency', re: /\btotal (equity|shareholders.? equity)\b/i },
  { key: 'capex', label: 'Capital expenditure', unit: 'currency', re: /\b(capital expenditure|capex)\b/i },
  { key: 'dividendYield', label: 'Dividend yield', unit: 'percent', re: /\bdividend yield\b/i },
  { key: 'roe', label: 'Return on equity', unit: 'percent', re: /\breturn on equity|\broe\b/i },
  { key: 'roa', label: 'Return on assets', unit: 'percent', re: /\breturn on assets|\broa\b/i },
  { key: 'debtToEquity', label: 'Debt / equity', unit: 'ratio', re: /\bdebt[- ]to[- ]equity\b/i },
  { key: 'currentRatio', label: 'Current ratio', unit: 'ratio', re: /\bcurrent ratio\b/i },
  { key: 'marketCap', label: 'Market cap', unit: 'currency', re: /\bmarket (cap|capitalization)\b/i },
  { key: 'peRatio', label: 'P/E', unit: 'ratio', re: /\b(p\/e|price[- ]to[- ]earnings|pe ratio)\b/i },
];

const SCALES: Array<[RegExp, number]> = [
  [/\btrillion\b/i, 1e12], [/\bbillion\b|\bbn\b/i, 1e9],
  [/\bmillion\b|\bmn\b/i, 1e6], [/\bthousand\b/i, 1e3],
  [/\bt\b/, 1e12], [/\bb\b/, 1e9], [/\bm\b/, 1e6], [/\bk\b/, 1e3],
];

/** Parse the first number in `s`, applying a word/suffix scale. */
export function parseNumber(s: string): { value: number; scaled: boolean } | null {
  const m = s.match(/(-?\d[\d,]*(?:\.\d+)?)\s*(trillion|billion|million|thousand|[bnmk])?\b/i);
  if (!m) return null;
  const base = Number(m[1].replace(/,/g, ''));
  if (!Number.isFinite(base)) return null;
  let value = base;
  let scaled = false;
  const tail = (m[2] ?? '').toLowerCase();
  if (tail) {
    const scale = SCALES.find(([re]) => re.test(tail));
    if (scale) { value = base * scale[1]; scaled = true; }
  }
  return { value, scaled };
}

/** Split a block of text into segments (sentences / bullet lines). */
function segments(text: string): string[] {
  return text
    .split(/\n|(?<=[.;])\s+/)
    .map((s) => s.replace(/^[-•*]\s*/, '').trim())
    .filter((s) => s.length >= 8);
}

/**
 * Extract financial facts from research text. Returns at most one fact per
 * metric key (the first confidently parseable occurrence).
 */
export function parseFinancialFacts(text: string | null | undefined): FinancialFact[] {
  if (!text) return [];
  const out: FinancialFact[] = [];
  const seen = new Set<string>();
  for (const seg of segments(text)) {
    for (const metric of METRICS) {
      if (seen.has(metric.key) || !metric.re.test(seg)) continue;
      const num = parseNumber(seg);
      if (!num) continue;
      // A percentage metric must carry a '%' or the word "percent" nearby, else
      // we could misread a currency figure as a margin.
      if (metric.unit === 'percent' && !/%|percent/i.test(seg)) continue;
      const unit: FactUnit = metric.unit;
      seen.add(metric.key);
      out.push({ key: metric.key, label: metric.label, value: num.value, unit, raw: seg });
      break; // one metric per segment
    }
  }
  return out;
}
