// ── The safe scalar expression evaluator ──────────────────────────────────────
// The SINGLE evaluator behind declarative `simulation` outputs. It is a small,
// recursive-descent expression language mirroring the approach of the Python
// stats formula engine (`python/harness/stats/formula.py`): no `eval`, no
// `Function`, no property access, no I/O — only a fixed operator set and a
// closed function whitelist over scalar numbers.
//
// It is SERVER-SAFE on purpose (no React, no DOM, no network) — the same shape as
// `lib/response/icon-vocabulary.ts` — so the renderer, the validation bridge and
// any non-React producer can share one implementation.
//
// Determinism: a division by zero, a non-finite intermediate, or a domain error
// yields `null` (an UNAVAILABLE figure), never `Infinity`/`NaN`. Results are
// rounded explicitly at the format boundary, so a displayed number is stable.

export class EvalError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
    this.name = 'EvalError';
  }
}

export const MAX_EXPRESSION_LEN = 500;
export const MAX_TOKENS = 256;
export const MAX_NODES = 128;

type Ast =
  | ['num', number]
  | ['var', string]
  | ['unary', '-' | '+', Ast]
  | ['bin', string, Ast, Ast]
  | ['call', string, Ast[]];

type Token = { kind: 'NUMBER' | 'IDENT' | 'OP' | '(' | ')' | ',' | 'EOF'; value: string | number; pos: number };

const COMPARE_OPS = new Set(['<', '>', '<=', '>=', '==', '!=']);
const ADD_OPS = new Set(['+', '-', ...COMPARE_OPS]);

function tokenize(text: string): Token[] {
  if (text.length > MAX_EXPRESSION_LEN) throw new EvalError('TOO_LONG', 'expression is too long');
  const tokens: Token[] = [];
  let i = 0;
  const n = text.length;
  while (i < n) {
    const c = text[i];
    if (/\s/.test(c)) {
      i++;
      continue;
    }
    if (c >= '0' && c <= '9') {
      let j = i;
      while (j < n && /[0-9.]/.test(text[j])) j++;
      tokens.push({ kind: 'NUMBER', value: Number(text.slice(i, j)), pos: i });
      i = j;
      continue;
    }
    if (/[A-Za-z_]/.test(c)) {
      let j = i;
      while (j < n && /[A-Za-z0-9_]/.test(text[j])) j++;
      tokens.push({ kind: 'IDENT', value: text.slice(i, j), pos: i });
      i = j;
      continue;
    }
    const two = text.slice(i, i + 2);
    if (COMPARE_OPS.has(two)) {
      tokens.push({ kind: 'OP', value: two, pos: i });
      i += 2;
      continue;
    }
    if ('+-*/^<>'.includes(c)) {
      tokens.push({ kind: 'OP', value: c, pos: i });
      i++;
      continue;
    }
    if (c === '(' || c === ')' || c === ',') {
      tokens.push({ kind: c, value: c, pos: i });
      i++;
      continue;
    }
    throw new EvalError('BAD_CHAR', `unexpected character ${JSON.stringify(c)} at ${i}`);
  }
  if (tokens.length > MAX_TOKENS) throw new EvalError('TOO_COMPLEX', 'expression has too many tokens');
  tokens.push({ kind: 'EOF', value: null as unknown as number, pos: n });
  return tokens;
}

class Parser {
  private i = 0;
  private nodes = 0;
  constructor(private readonly tokens: Token[]) {}

  private peek(): Token {
    return this.tokens[this.i];
  }
  private next(): Token {
    return this.tokens[this.i++];
  }
  private count(): void {
    if (++this.nodes > MAX_NODES) throw new EvalError('TOO_COMPLEX', 'expression is too deeply nested');
  }

  parse(): Ast {
    const node = this.expr();
    if (this.peek().kind !== 'EOF') {
      throw new EvalError('TRAILING', `unexpected token ${JSON.stringify(this.peek().value)}`);
    }
    return node;
  }
  private expr(): Ast {
    let node = this.term();
    while (this.peek().kind === 'OP' && ADD_OPS.has(String(this.peek().value))) {
      const op = String(this.next().value);
      this.count();
      node = ['bin', op, node, this.term()];
    }
    return node;
  }
  private term(): Ast {
    let node = this.unary();
    while (this.peek().kind === 'OP' && (this.peek().value === '*' || this.peek().value === '/')) {
      const op = String(this.next().value);
      this.count();
      node = ['bin', op, node, this.unary()];
    }
    return node;
  }
  private unary(): Ast {
    if (this.peek().kind === 'OP' && (this.peek().value === '-' || this.peek().value === '+')) {
      const op = this.next().value as '-' | '+';
      this.count();
      return ['unary', op, this.unary()];
    }
    return this.power();
  }
  private power(): Ast {
    const node = this.primary();
    if (this.peek().kind === 'OP' && this.peek().value === '^') {
      this.next();
      this.count();
      return ['bin', '^', node, this.unary()];
    }
    return node;
  }
  private primary(): Ast {
    const tok = this.peek();
    if (tok.kind === 'NUMBER') {
      this.next();
      this.count();
      return ['num', tok.value as number];
    }
    if (tok.kind === 'IDENT') {
      const name = String(this.next().value);
      if (this.peek().kind === '(') {
        this.next();
        const args: Ast[] = [];
        if (this.peek().kind !== ')') {
          args.push(this.expr());
          while (this.peek().kind === ',') {
            this.next();
            args.push(this.expr());
          }
        }
        if (this.peek().kind !== ')') throw new EvalError('PAREN', `missing ')' after ${name}()`);
        this.next();
        this.count();
        return ['call', name, args];
      }
      this.count();
      return ['var', name];
    }
    if (tok.kind === '(') {
      this.next();
      const node = this.expr();
      if (this.peek().kind !== ')') throw new EvalError('PAREN', "missing closing ')'");
      this.next();
      return node;
    }
    throw new EvalError('SYNTAX', `unexpected token ${JSON.stringify(tok.value)}`);
  }
}

/** The closed function whitelist. Each takes fixed arity (min/max checked). */
type Fn = { min: number; max: number; fn: (args: number[]) => number };
const FUNCTIONS: Record<string, Fn> = {
  abs: { min: 1, max: 1, fn: ([x]) => Math.abs(x) },
  sqrt: { min: 1, max: 1, fn: ([x]) => Math.sqrt(x) },
  floor: { min: 1, max: 1, fn: ([x]) => Math.floor(x) },
  ceil: { min: 1, max: 1, fn: ([x]) => Math.ceil(x) },
  sign: { min: 1, max: 1, fn: ([x]) => Math.sign(x) },
  round: { min: 1, max: 2, fn: ([x, n = 0]) => roundTo(x, Math.trunc(n)) },
  clamp: { min: 3, max: 3, fn: ([x, lo, hi]) => Math.min(Math.max(x, lo), hi) },
  pow: { min: 2, max: 2, fn: ([a, b]) => Math.pow(a, b) },
  min: { min: 1, max: Infinity, fn: (args) => Math.min(...args) },
  max: { min: 1, max: Infinity, fn: (args) => Math.max(...args) },
  sum: { min: 1, max: Infinity, fn: (args) => args.reduce((a, b) => a + b, 0) },
  avg: { min: 1, max: Infinity, fn: (args) => args.reduce((a, b) => a + b, 0) / args.length },
  if: { min: 3, max: 3, fn: ([c, a, b]) => (c !== 0 ? a : b) },
};

export const EVAL_FUNCTIONS = Object.keys(FUNCTIONS).sort();

function roundTo(value: number, digits: number): number {
  const factor = Math.pow(10, digits);
  // Round half away from zero, so a display figure is stable and predictable.
  return Math.sign(value) * Math.round(Math.abs(value) * factor) / factor;
}

/** Parse an expression, throwing `EvalError` on any problem. */
export function parseExpression(expr: string): Ast {
  if (typeof expr !== 'string' || expr.trim() === '') throw new EvalError('EMPTY', 'expression is empty');
  return new Parser(tokenize(expr)).parse();
}

function collect(node: Ast, vars: Set<string>, fns: Set<string>): void {
  switch (node[0]) {
    case 'var':
      vars.add(node[1]);
      break;
    case 'call':
      fns.add(node[1]);
      node[2].forEach((a) => collect(a, vars, fns));
      break;
    case 'bin':
      collect(node[2], vars, fns);
      collect(node[3], vars, fns);
      break;
    case 'unary':
      collect(node[2], vars, fns);
      break;
  }
}

/** Validate an expression without evaluating: known functions, known variables. */
export function validateExpression(
  expr: string,
  knownVariables?: Iterable<string>,
): { ok: boolean; error?: string; variables: string[]; functions: string[] } {
  let ast: Ast;
  try {
    ast = parseExpression(expr);
  } catch (error) {
    return { ok: false, error: error instanceof EvalError ? error.message : String(error), variables: [], functions: [] };
  }
  const vars = new Set<string>();
  const fns = new Set<string>();
  collect(ast, vars, fns);
  const unknownFn = [...fns].filter((name) => !(name in FUNCTIONS));
  if (unknownFn.length) return { ok: false, error: `unknown function(s): ${unknownFn.join(', ')}`, variables: [...vars], functions: [...fns] };
  if (knownVariables) {
    const known = new Set(knownVariables);
    const unknownVar = [...vars].filter((name) => !known.has(name));
    if (unknownVar.length) return { ok: false, error: `unknown variable(s): ${unknownVar.join(', ')}`, variables: [...vars], functions: [...fns] };
  }
  return { ok: true, variables: [...vars], functions: [...fns] };
}

function evalNode(node: Ast, vars: Record<string, number>): number | null {
  switch (node[0]) {
    case 'num':
      return Number.isFinite(node[1]) ? node[1] : null;
    case 'var': {
      const value = vars[node[1]];
      return typeof value === 'number' && Number.isFinite(value) ? value : null;
    }
    case 'unary': {
      const v = evalNode(node[2], vars);
      if (v == null) return null;
      return node[1] === '-' ? -v : v;
    }
    case 'bin': {
      const a = evalNode(node[2], vars);
      const b = evalNode(node[3], vars);
      if (a == null || b == null) return null;
      const op = node[1];
      let out: number;
      switch (op) {
        case '+': out = a + b; break;
        case '-': out = a - b; break;
        case '*': out = a * b; break;
        case '/': if (b === 0) return null; out = a / b; break;
        case '^': out = Math.pow(a, b); break;
        case '<': return a < b ? 1 : 0;
        case '>': return a > b ? 1 : 0;
        case '<=': return a <= b ? 1 : 0;
        case '>=': return a >= b ? 1 : 0;
        case '==': return a === b ? 1 : 0;
        case '!=': return a !== b ? 1 : 0;
        default: return null;
      }
      return Number.isFinite(out) ? out : null;
    }
    case 'call': {
      const spec = FUNCTIONS[node[1]];
      if (!spec) return null;
      const args = node[2].map((a) => evalNode(a, vars));
      if (args.length < spec.min || args.length > spec.max || args.some((v) => v == null)) return null;
      const out = spec.fn(args as number[]);
      return Number.isFinite(out) ? out : null;
    }
  }
}

/**
 * Evaluate an expression over scalar variables. Returns `null` for a
 * division-by-zero, a non-finite result, an unknown name, or any parse error —
 * the UNAVAILABLE case — and never throws at the compute boundary.
 */
export function evaluateExpression(expr: string, vars: Record<string, number>): number | null {
  let ast: Ast;
  try {
    ast = parseExpression(expr);
  } catch {
    return null;
  }
  try {
    return evalNode(ast, vars);
  } catch {
    return null;
  }
}

export interface FormatSpec {
  precision?: number;
  format?: 'number' | 'currency' | 'percent';
  unit?: string;
}

/** Format a value for display (used by the renderer and the fallback projection). */
export function formatSimulationValue(value: number | null, spec: FormatSpec = {}): string {
  if (value == null) return '—';
  const { format = 'number', unit } = spec;
  const precision = spec.precision ?? (format === 'currency' ? 2 : format === 'percent' ? 2 : 4);
  const rounded = roundTo(value, precision);
  if (format === 'percent') return `${rounded.toFixed(precision)}%`;
  if (format === 'currency') return `$${rounded.toLocaleString('en-US', { minimumFractionDigits: precision, maximumFractionDigits: precision })}`;
  const text = rounded.toFixed(precision);
  return unit ? `${text}${unit}` : text;
}
