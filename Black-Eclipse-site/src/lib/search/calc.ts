// ── In-palette calculator & unit conversion ─────────────────────────────────
// A tiny, dependency-free evaluator that runs entirely offline. It handles two
// shapes the command palette recognizes inline:
//
//   "12 * 4 + 8"          → arithmetic
//   "100 usd in eur"      → currency/unit conversion (indicative rates)
//
// This is deliberately NOT a general expression parser — it is a safe, shunting
// -yard style evaluator over numbers and + - * / % ( ) with a fixed, local
// exchange table. No eval(), no network.

export interface CalcResult {
  /** The formatted answer, e.g. "56" or "92.10 EUR". */
  display: string;
  /** Raw numeric value. */
  value: number;
  /** What kind of computation produced this (drives the row icon/subtitle). */
  kind: 'arithmetic' | 'conversion';
}

// Indicative rates relative to USD. Offline + deterministic by design; labeled
// "indicative" in the UI so it is never mistaken for a live quote.
const USD_RATES: Record<string, number> = {
  usd: 1,
  eur: 0.92,
  gbp: 0.79,
  jpy: 156.4,
  chf: 0.88,
  cad: 1.36,
  aud: 1.51,
  nzd: 1.64,
  cny: 7.24,
  inr: 83.4,
  pkr: 278.5,
  aed: 3.67,
  sar: 3.75,
  try: 32.3,
  zar: 18.6,
  brl: 5.15,
  mxn: 17.1,
  sgd: 1.35,
  hkd: 7.81,
  krw: 1370,
  sek: 10.5,
  nok: 10.6,
  dkk: 6.85,
  pln: 3.95,
  rub: 90.0,
};

const CURRENCY_SYMBOL: Record<string, string> = {
  usd: '$', eur: '€', gbp: '£', jpy: '¥',
};

function fmt(n: number): string {
  if (!Number.isFinite(n)) return '—';
  if (Number.isInteger(n)) return n.toLocaleString();
  const abs = Math.abs(n);
  const digits = abs < 1 ? 4 : abs < 1000 ? 2 : 2;
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

// ── Conversion ──────────────────────────────────────────────────────────────

const CONVERSION_RE =
  /^\s*([0-9][0-9,.]*)\s*([a-z]{3})?\s*(?:in|to|into|as)\s*([a-z]{3})\s*$/i;

function tryConversion(raw: string): CalcResult | null {
  const m = raw.trim().match(CONVERSION_RE);
  if (!m) return null;
  const amount = Number(m[1].replace(/,/g, ''));
  if (!Number.isFinite(amount)) return null;
  const from = (m[2] || 'usd').toLowerCase();
  const to = m[3].toLowerCase();
  if (!(from in USD_RATES) || !(to in USD_RATES)) return null;

  const usd = amount / USD_RATES[from];
  const value = usd * USD_RATES[to];
  const sym = CURRENCY_SYMBOL[to];
  const display = sym ? `${sym}${fmt(value)}` : `${fmt(value)} ${to.toUpperCase()}`;
  return { display, value, kind: 'conversion' };
}

// ── Arithmetic ──────────────────────────────────────────────────────────────

const ARITHMETIC_RE = /^[\d\s+\-*/%().,]+$/;

/** Tokenize + evaluate with the shunting-yard algorithm (no eval). */
function tryArithmetic(raw: string): CalcResult | null {
  const expr = raw.trim();
  // Require at least one operator so a bare number stays a normal search term.
  if (!ARITHMETIC_RE.test(expr) || !/[+\-*/%]/.test(expr)) return null;

  const tokens = expr.replace(/,/g, '').match(/\d+\.?\d*|[+\-*/%()]/g);
  if (!tokens) return null;

  const prec: Record<string, number> = { '+': 1, '-': 1, '*': 2, '/': 2, '%': 2 };
  const output: (number | string)[] = [];
  const ops: string[] = [];

  for (const t of tokens) {
    if (/^\d/.test(t)) {
      output.push(Number(t));
    } else if (t === '(') {
      ops.push(t);
    } else if (t === ')') {
      while (ops.length && ops[ops.length - 1] !== '(') output.push(ops.pop()!);
      if (!ops.length) return null;
      ops.pop();
    } else {
      while (ops.length && prec[ops[ops.length - 1]] >= prec[t]) output.push(ops.pop()!);
      ops.push(t);
    }
  }
  while (ops.length) {
    const op = ops.pop()!;
    if (op === '(') return null;
    output.push(op);
  }

  const stack: number[] = [];
  for (const t of output) {
    if (typeof t === 'number') {
      stack.push(t);
      continue;
    }
    const b = stack.pop();
    const a = stack.pop();
    if (a === undefined || b === undefined) return null;
    switch (t) {
      case '+': stack.push(a + b); break;
      case '-': stack.push(a - b); break;
      case '*': stack.push(a * b); break;
      case '/': stack.push(b === 0 ? NaN : a / b); break;
      case '%': stack.push(b === 0 ? NaN : a % b); break;
    }
  }
  if (stack.length !== 1) return null;
  const value = stack[0];
  if (!Number.isFinite(value)) return null;
  return { display: fmt(value), value, kind: 'arithmetic' };
}

/** Try to evaluate a query as a conversion or an arithmetic expression. */
export function evaluateCalc(raw: string): CalcResult | null {
  if (!raw) return null;
  return tryConversion(raw) ?? tryArithmetic(raw);
}

/** Exposed for tests — the local rate table is indicative, USD-based. */
export const __USD_RATES = USD_RATES;
