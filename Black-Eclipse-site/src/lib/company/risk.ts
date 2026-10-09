// ── Deterministic company risk synthesis (Workstream E, Section J) ───────────
// Every risk is a function of real inputs: the price series (via the technical
// snapshot) and reported statement periods. Tones follow DOCUMENTED thresholds
// stated in each entry's `basis`, so nothing is an arbitrary score. When an
// input is missing the entry is omitted, never guessed.

import type { FundamentalInsight, FundamentalPeriod } from '@/lib/fundamentals/types';
import type { TechnicalSnapshot } from './technical';

export type RiskTone = 'positive' | 'warning' | 'negative' | 'neutral';

export interface RiskEntry {
  id: string;
  label: string;
  /** Formatted value, e.g. "38.2%". */
  value: string;
  tone: RiskTone;
  /** Why it is relevant + the exact basis/threshold used. */
  basis: string;
  evidence?: string;
}

export interface CompanyRiskInput {
  technical: TechnicalSnapshot;
  /** Reported fiscal periods (may be empty). */
  periods: FundamentalPeriod[];
  beta: number | null;
  avgVolume: number | null;
  /** Statement-derived insights from the fundamentals layer. */
  insights: FundamentalInsight[];
}

function coerceNum(v: unknown): number | null {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Coefficient of variation (stdev/|mean|) of net income across periods. */
function earningsVariability(periods: FundamentalPeriod[]): number | null {
  const xs = periods.map((p) => coerceNum(p.netIncome)).filter((v): v is number => v != null);
  if (xs.length < 3) return null;
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  if (mean === 0) return null;
  const sd = Math.sqrt(xs.reduce((a, x) => a + (x - mean) ** 2, 0) / (xs.length - 1));
  return +(sd / Math.abs(mean)).toFixed(2);
}

export function computeCompanyRisk(input: CompanyRiskInput): RiskEntry[] {
  const out: RiskEntry[] = [];
  const { technical, periods, beta, avgVolume, insights } = input;
  const latest = periods[periods.length - 1];

  // ── Market risk (from the actual series) ──
  if (technical.volatilityPct != null) {
    const v = technical.volatilityPct;
    out.push({
      id: 'volatility',
      label: 'Historical volatility',
      value: `${v.toFixed(1)}%`,
      tone: v < 20 ? 'positive' : v <= 40 ? 'neutral' : 'negative',
      basis: `Annualized stdev of daily returns over ${technical.bars} bars. Low <20%, high >40%.`,
    });
  }
  if (technical.maxDrawdownPct != null) {
    const d = technical.maxDrawdownPct;
    out.push({
      id: 'drawdown',
      label: 'Maximum drawdown',
      value: `${d.toFixed(1)}%`,
      tone: d > -15 ? 'positive' : d >= -35 ? 'warning' : 'negative',
      basis: 'Largest peak-to-trough decline in the observed window. Low >-15%, high <-35%.',
    });
  }
  if (beta != null && Number.isFinite(beta)) {
    out.push({
      id: 'beta',
      label: 'Beta',
      value: beta.toFixed(2),
      tone: beta < 0.8 ? 'positive' : beta <= 1.5 ? 'neutral' : 'negative',
      basis: 'Reported market sensitivity. <0.8 defensive, >1.5 amplified.',
    });
  }

  // ── Balance-sheet / fundamental risk (from reported periods) ──
  if (latest) {
    const debt = coerceNum(latest.totalDebt);
    const equity = coerceNum(latest.totalEquity);
    if (debt != null && equity != null && equity > 0) {
      const de = +(debt / equity).toFixed(2);
      out.push({
        id: 'leverage',
        label: 'Leverage (debt / equity)',
        value: `${de.toFixed(2)}×`,
        tone: de < 0.5 ? 'positive' : de < 1.5 ? 'neutral' : 'negative',
        basis: `Total debt ÷ equity for ${latest.endDate}. Low <0.5×, high ≥1.5×.`,
      });
      const ebitda = coerceNum(latest.ebitda);
      if (ebitda != null && ebitda > 0 && debt != null) {
        const netDebt = coerceNum(latest.netDebt) ?? debt;
        const nd = +(netDebt / ebitda).toFixed(2);
        out.push({
          id: 'net-debt-ebitda',
          label: 'Net debt / EBITDA',
          value: `${nd.toFixed(2)}×`,
          tone: nd < 2 ? 'positive' : nd <= 4 ? 'warning' : 'negative',
          basis: `Net debt ÷ EBITDA for ${latest.endDate}. Low <2×, high >4×.`,
        });
      }
    }

    const fcf = coerceNum(latest.freeCashFlow);
    if (fcf != null) {
      const prior = periods.length >= 2 ? coerceNum(periods[periods.length - 2].freeCashFlow) : null;
      const trend = prior != null ? (fcf >= prior ? 'grew' : 'fell') : '';
      out.push({
        id: 'cash-flow',
        label: 'Free cash flow',
        value: `${fcf < 0 ? '-' : ''}${Math.abs(fcf) >= 1e9 ? `${(Math.abs(fcf) / 1e9).toFixed(2)}B` : Math.abs(fcf) >= 1e6 ? `${(Math.abs(fcf) / 1e6).toFixed(1)}M` : fcf.toFixed(0)}`,
        tone: fcf > 0 ? 'positive' : 'negative',
        basis: `Reported free cash flow for ${latest.endDate}${trend ? `; ${trend} vs prior period` : ''}. Positive = self-funding.`,
      });
    }
  }

  const ev = earningsVariability(periods);
  if (ev != null) {
    out.push({
      id: 'earnings-variability',
      label: 'Earnings variability',
      value: `${ev.toFixed(2)}×`,
      tone: ev < 0.2 ? 'positive' : ev < 0.5 ? 'warning' : 'negative',
      basis: `Coefficient of variation of net income across ${periods.length} periods. Stable <0.2, volatile >0.5.`,
    });
  }

  if (avgVolume != null && avgVolume > 0) {
    out.push({
      id: 'liquidity',
      label: 'Liquidity (avg volume)',
      value: avgVolume >= 1e6 ? `${(avgVolume / 1e6).toFixed(1)}M` : `${Math.round(avgVolume)}`,
      tone: avgVolume >= 1e6 ? 'positive' : avgVolume >= 1e5 ? 'warning' : 'negative',
      basis: 'Average daily share volume. Thin liquidity (<100k) raises slippage and exit risk.',
    });
  }

  // ── Statement-derived warnings already computed by the fundamentals layer ──
  for (const insight of insights) {
    if (insight.tone !== 'warning' && insight.tone !== 'negative') continue;
    out.push({
      id: `insight-${insight.id}`,
      label: insight.title,
      value: insight.tone === 'negative' ? 'elevated' : 'watch',
      tone: insight.tone === 'negative' ? 'negative' : 'warning',
      basis: 'Derived from the reported statements by the fundamentals engine.',
      evidence: insight.detail,
    });
  }

  return out;
}
