// ── Intelligence analytics — deterministic market intelligence ───────────────
// Pure functions that derive market regime, "what changed", opportunities, and
// market drivers from the SAME data the widgets already consume (indices,
// overview, news). No LLM, no randomness — every output is reproducible from
// the inputs (spec §35: use deterministic analytics for change detection).

export type Regime =
  | 'Risk On'
  | 'Risk Off'
  | 'Trending Bull'
  | 'Trending Bear'
  | 'Range'
  | 'High Volatility'
  | 'Transition';

export interface RegimeFactors {
  breadth: number;      // % of indices advancing (0-100)
  momentum: number;     // avg % change of indices
  volatility: number;   // dispersion of index changes (proxy)
  riskOn: boolean;
}

export interface RegimeResult {
  regime: Regime;
  factors: RegimeFactors;
  reasons: string[];
}

/** Compute the market regime from index data. */
export function computeRegime(indices: { changePercent: number }[]): RegimeResult {
  if (indices.length === 0) {
    return { regime: 'Range', factors: { breadth: 50, momentum: 0, volatility: 0, riskOn: true }, reasons: ['No index data'] };
  }
  const changes = indices.map(i => i.changePercent);
  const advancing = changes.filter(c => c > 0).length;
  const breadth = (advancing / changes.length) * 100;
  const momentum = changes.reduce((a, b) => a + b, 0) / changes.length;
  const volatility = Math.sqrt(changes.reduce((a, b) => a + (b - momentum) ** 2, 0) / changes.length);
  const riskOn = breadth >= 50 && momentum >= 0;

  const reasons: string[] = [];
  let regime: Regime;
  if (volatility > 1.5) {
    regime = 'High Volatility';
    reasons.push(`High dispersion (${volatility.toFixed(1)}%) across indices`);
  } else if (riskOn && momentum > 0.3) {
    regime = 'Trending Bull';
    reasons.push(`Broad advance (${breadth.toFixed(0)}% up) with momentum +${momentum.toFixed(2)}%`);
  } else if (!riskOn && momentum < -0.3) {
    regime = 'Trending Bear';
    reasons.push(`Broad decline (${(100 - breadth).toFixed(0)}% down) with momentum ${momentum.toFixed(2)}%`);
  } else if (Math.abs(momentum) < 0.15) {
    regime = 'Range';
    reasons.push(`Indices flat (avg ${momentum.toFixed(2)}%)`);
  } else {
    regime = riskOn ? 'Risk On' : 'Risk Off';
    reasons.push(riskOn ? 'Risk-on tilt (positive breadth)' : 'Risk-off tilt (negative breadth)');
  }
  return { regime, factors: { breadth, momentum, volatility, riskOn }, reasons };
}

export interface ChangeItem {
  label: string;
  value: string;
  direction: 'up' | 'down' | 'flat';
  severity: 'positive' | 'negative' | 'neutral';
}

/** "What changed" — compare current index state to a previous snapshot. */
export function computeWhatChanged(
  current: { name: string; changePercent: number }[],
  previous: { name: string; changePercent: number }[] | null,
): ChangeItem[] {
  const items: ChangeItem[] = [];
  const prevMap = new Map((previous ?? []).map(p => [p.name, p.changePercent]));
  for (const c of current) {
    const prev = prevMap.get(c.name);
    if (prev === undefined) continue;
    const delta = c.changePercent - prev;
    if (Math.abs(delta) < 0.05) continue;
    items.push({
      label: c.name,
      value: `${c.changePercent > 0 ? '+' : ''}${c.changePercent.toFixed(2)}%`,
      direction: delta > 0 ? 'up' : 'down',
      severity: delta > 0 ? 'positive' : 'negative',
    });
  }
  return items.slice(0, 8);
}

export interface Opportunity {
  symbol: string;
  name: string;
  type: string;
  score: number;
  checks: string[];
  risks: string[];
}

/** Opportunity scanner — deterministic conditions over the overview universe. */
export function scanOpportunities(stocks: { symbol: string; name: string; changePct: number }[]): Opportunity[] {
  const out: Opportunity[] = [];
  for (const s of stocks) {
    const checks: string[] = [];
    const risks: string[] = [];
    let score = 50;
    if (s.changePct > 3) { checks.push('Strong momentum'); score += 20; }
    else if (s.changePct > 1) { checks.push('Positive momentum'); score += 10; }
    if (s.changePct > 5) risks.push('Extended — pullback risk');
    if (s.changePct < -3) { checks.push('Oversold bounce candidate'); score += 10; risks.push('Downtrend intact'); }
    if (score > 50) {
      out.push({
        symbol: s.symbol,
        name: s.name,
        type: s.changePct > 0 ? 'Momentum' : 'Mean Reversion',
        score: Math.min(99, score),
        checks,
        risks,
      });
    }
  }
  return out.sort((a, b) => b.score - a.score).slice(0, 6);
}

export interface Driver {
  name: string;
  change: number;
  direction: 'up' | 'down';
}

/** Market drivers — rank what's moving by absolute change. */
export function computeDrivers(indices: { name: string; changePercent: number }[]): Driver[] {
  return [...indices]
    .map(i => ({ name: i.name, change: i.changePercent, direction: i.changePercent >= 0 ? 'up' as const : 'down' as const }))
    .sort((a, b) => Math.abs(b.change) - Math.abs(a.change))
    .slice(0, 6);
}
