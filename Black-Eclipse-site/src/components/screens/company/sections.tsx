'use client';

// ── Company detail sections (Workstream E) ───────────────────────────────────
// Presentational sections for the single-page company intelligence experience.
// They receive already-fetched/derived data (hooks and deterministic engines are
// driven by the parent) so a stock detail page never starts duplicate requests.
// Nothing here fabricates a value or a citation.

import {
  RefreshCw, ExternalLink, Newspaper, ShieldAlert, AlertTriangle,
  CheckCircle2, HelpCircle, BookOpen, Activity, TrendingUp, Landmark,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { TechnicalSnapshot } from '@/lib/company/technical';
import type { RiskEntry } from '@/lib/company/risk';
import type { Officer } from '@/lib/fundamentals/types';
import type { CompanyNewsState } from '@/lib/company/use-company-news';
import type { CompanyResearchState } from '@/lib/company/use-company-research';

// ── Section shell ────────────────────────────────────────────────────────────
export function SectionShell({
  icon, title, subtitle, right, children,
}: {
  icon?: React.ReactNode;
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-border/40 glass-card p-4 md:p-5 space-y-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          {icon}
          <h2 className="font-serif text-sm font-bold">{title}</h2>
          {subtitle && <span className="text-[10px] font-mono text-muted-foreground">{subtitle}</span>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

function chip(tone: 'ok' | 'warn' | 'bad' | 'muted', text: string) {
  const map = {
    ok: 'border-emerald-400/30 text-emerald-400',
    warn: 'border-amber-400/30 text-amber-400',
    bad: 'border-rose-400/30 text-rose-400',
    muted: 'border-border/40 text-muted-foreground',
  };
  return <span className={cn('rounded border px-1.5 py-0.5 text-[9px] font-mono uppercase', map[tone])}>{text}</span>;
}

function num(v: number | null | undefined, digits = 2, suffix = ''): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return `${v.toFixed(digits)}${suffix}`;
}

type ClaimRow = { id?: string; text?: string; kind?: string; status?: string; confidence?: number; issues?: string | null };
type SourceRow = { sourceId?: string; canonicalUrl?: string; domain?: string; publisher?: string; publishedAt?: string; sourceType?: string };

// ── Section B + K: AI research brief / conclusion ────────────────────────────
export function AiResearchSection({
  research, variant = 'brief',
}: {
  research: CompanyResearchState & { refresh: () => void };
  variant?: 'brief' | 'conclusion';
}) {
  const { detail, status, running, error, state, startedAt } = research;
  const claims = (detail?.claims ?? []) as ClaimRow[];
  const sources = (detail?.sources ?? []) as SourceRow[];
  const conflicts = (detail?.conflicts ?? []) as unknown[];

  const synth = parseSynthesis(detail?.run?.answer);
  const conclusionKeys = ['partially', 'not established', 'conflict', 'gap', 'excluded', 'citation'];
  const sections = variant === 'conclusion'
    ? synth.sections.filter((s) => conclusionKeys.some((k) => s.title.toLowerCase().includes(k)))
    : synth.sections;

  const sourceCount = status?.sourceCount ?? sources.length;
  const evidenceCount = status?.evidenceCount ?? findingsCount(detail);
  const title = variant === 'brief' ? 'AI Company Intelligence Brief' : 'AI Research Conclusion';

  return (
    <SectionShell
      icon={<BookOpen size={14} className="text-primary" />}
      title={title}
      subtitle={startedAt ? `updated ${new Date(startedAt).toLocaleString()}` : undefined}
      right={
        <div className="flex items-center gap-2">
          {state && chip(state === 'COMPLETED' ? 'ok' : state === 'FAILED' || state === 'CANCELLED' ? 'bad' : state === 'PARTIAL' ? 'warn' : 'muted', state.toLowerCase())}
          {typeof sourceCount === 'number' && <span className="text-[10px] font-mono text-muted-foreground">{sourceCount} source{sourceCount === 1 ? '' : 's'}</span>}
          <button
            onClick={research.refresh}
            disabled={running}
            className="flex items-center gap-1 rounded-md border border-border/40 px-2 py-1 text-[10px] font-bold text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw size={11} /> {running ? 'Researching…' : 'Refresh'}
          </button>
        </div>
      }
    >
      {error && (
        <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-300">
          <AlertTriangle size={12} className="inline mr-1" />
          Research unavailable: {error}. Showing only verified market and filings data. You can retry above.
        </div>
      )}

      {/* Coverage subhead — assembled by the engine (coverage, source counts). */}
      {synth.meta.length > 0 && variant === 'brief' && (
        <p className="text-[11px] leading-relaxed text-muted-foreground border-l-2 border-primary/30 pl-2.5">
          {synth.meta.join(' · ')}
        </p>
      )}

      {/* Structured synthesis — titled sections instead of a wall of text. */}
      {!running && sections.length > 0 && (
        <div className="space-y-3">
          {sections.map((s) => (
            <div key={s.title}>
              <h3 className={cn('text-[10px] font-bold uppercase tracking-wider mb-1', toneText(s.tone))}>
                {s.title}
              </h3>
              <ul className="space-y-1">
                {s.items.map((it, i) => (
                  <li key={i} className="flex gap-2 text-[12px] leading-relaxed text-foreground/90">
                    <span className={cn('mt-[7px] h-1 w-1 rounded-full shrink-0', toneDot(s.tone))} />
                    <span>{it}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {running && (
        <div className="space-y-2" aria-busy="true">
          {[90, 75, 60].map((w, i) => (
            <div key={i} className="h-3 rounded bg-muted/30 animate-pulse" style={{ width: `${w}%` }} />
          ))}
          <p className="text-[10px] text-muted-foreground font-mono">
            Retrieving and validating sources…{typeof status?.progress === 'number' ? ` ${Math.round(status.progress)}%` : ''}
          </p>
        </div>
      )}

      {!running && detail && claims.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] font-mono text-muted-foreground">
          <span>{claims.length} findings</span>
          <span>{evidenceCount ?? 0} evidence items</span>
          {conflicts.length > 0 && (
            <span className="text-amber-400">
              {conflicts.length} conflict{conflicts.length === 1 ? '' : 's'} flagged
            </span>
          )}
        </div>
      )}

      {!running && detail && claims.length === 0 && !error && (
        <div className="rounded-xl border border-border/30 glass-card-subtle px-3 py-2 text-[11px] text-muted-foreground">
          <BookOpen size={12} className="inline mr-1" />
          Research reached state <span className="font-mono">{state ?? 'unknown'}</span> with no verified claims for this company.
          Coverage gaps are shown rather than filled with unverified text.
        </div>
      )}

      {!running && !detail && !error && (
        <p className="text-[11px] text-muted-foreground">Research has not produced a result yet.</p>
      )}

      {sources.length > 0 && (
        <details className="rounded-xl border border-border/30 bg-background/30 overflow-hidden">
          <summary className="flex items-center justify-between gap-2 cursor-pointer select-none list-none px-3 py-2 text-[11px] font-semibold text-muted-foreground hover:text-foreground transition-colors">
            <span className="flex items-center gap-1.5">
              <ExternalLink size={11} className="text-primary" /> Sources ({sources.length})
            </span>
            <span className="text-[10px] font-mono opacity-70">view</span>
          </summary>
          <ul className="border-t border-border/20 px-3 py-2 space-y-1 max-h-64 overflow-y-auto">
            {sources.slice(0, 40).map((s) => (
              <li key={s.sourceId} className="text-[11px] flex items-center gap-2">
                <a href={s.canonicalUrl || '#'} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1 text-foreground/90 hover:text-primary truncate">
                  <ExternalLink size={10} className="shrink-0" /> {s.publisher || s.domain || safeHost(s.canonicalUrl)}
                </a>
                <span className="ml-auto shrink-0 text-[9px] text-muted-foreground font-mono">
                  {s.sourceType ?? ''}{s.publishedAt ? ` · ${s.publishedAt.slice(0, 10)}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </SectionShell>
  );
}

function findingsCount(detail: CompanyResearchState['detail']): number | null {
  if (!detail) return null;
  const ev = detail.evidence as unknown[];
  return Array.isArray(ev) ? ev.length : null;
}

function safeHost(url?: string): string {
  if (!url) return 'source';
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url.slice(0, 40); }
}

// The engine's synthesized answer is STRUCTURED text (not free prose):
//   Research: <objective>
//   Coverage: <status> — N sources, M evidence item(s), P primary.
//   Findings (evidence-backed):
//   - ...
//   Partially supported (verify before relying on):
//   - ...
//   Not established / conflicting (removed from findings):
//   - [STATUS] reason
//   Conflicts / Gaps / Excluded / Citation issues ...
// This parser turns it into titled sections so the brief reads as a proper
// document with headings instead of a wall of text.
export type SynthTone = 'ok' | 'warn' | 'bad' | 'muted' | 'info';
export interface SynthSection { title: string; items: string[]; tone: SynthTone }
export interface Synthesis { meta: string[]; sections: SynthSection[] }

function toneForHeading(title: string): SynthTone {
  const t = title.toLowerCase();
  if (t.includes('conflict') || t.includes('not established') || t.includes('citation')) return 'bad';
  if (t.includes('partially')) return 'warn';
  if (t.includes('finding') || t.includes('evidence-backed')) return 'ok';
  if (t.includes('gap') || t.includes('excluded')) return 'muted';
  return 'info';
}

export function parseSynthesis(answer: string | null | undefined): Synthesis {
  if (!answer) return { meta: [], sections: [] };
  const meta: string[] = [];
  const sections: SynthSection[] = [];
  let current: SynthSection | null = null;
  for (const rawLine of answer.split('\n')) {
    const l = rawLine.trim();
    if (!l) continue;
    if (l.startsWith('- ')) {
      if (!current) { current = { title: 'Summary', items: [], tone: 'info' }; sections.push(current); }
      current.items.push(l.slice(2).trim());
      continue;
    }
    // A trailing colon (and no leading dash) marks a heading — except the two
    // leading metadata lines (Research / Coverage), which stay as a subhead.
    if (l.endsWith(':') && !/^(research|coverage):/i.test(l)) {
      current = { title: l.replace(/:$/, ''), items: [], tone: toneForHeading(l) };
      sections.push(current);
      continue;
    }
    meta.push(l);
  }
  return { meta, sections };
}

function toneText(tone: SynthTone): string {
  return tone === 'ok' ? 'text-emerald-400'
    : tone === 'warn' ? 'text-amber-400'
      : tone === 'bad' ? 'text-rose-400'
        : tone === 'muted' ? 'text-muted-foreground'
          : 'text-foreground';
}
function toneDot(tone: SynthTone): string {
  return tone === 'ok' ? 'bg-emerald-400'
    : tone === 'warn' ? 'bg-amber-400'
      : tone === 'bad' ? 'bg-rose-400'
        : 'bg-muted-foreground/60';
}

// ── Section G: news ──────────────────────────────────────────────────────────
export function CompanyNewsSection({ news }: { news: CompanyNewsState & { refresh: () => void } }) {
  return (
    <SectionShell
      icon={<Newspaper size={14} className="text-primary" />}
      title="Recent news & material events"
      subtitle={news.lastIngestAt ? `feed updated ${new Date(news.lastIngestAt).toLocaleString()}` : undefined}
      right={<button onClick={news.refresh} className="flex items-center gap-1 rounded-md border border-border/40 px-2 py-1 text-[10px] font-bold text-muted-foreground hover:text-foreground"><RefreshCw size={11} /> Refresh</button>}
    >
      {news.loading && (
        <div className="space-y-2" aria-busy="true">{[80, 65, 55].map((w, i) => <div key={i} className="h-3 rounded bg-muted/30 animate-pulse" style={{ width: `${w}%` }} />)}</div>
      )}
      {!news.loading && news.error && <p className="text-[11px] text-amber-300">{news.error}</p>}
      {!news.loading && !news.error && news.items.length === 0 && (
        <p className="text-[11px] text-muted-foreground">No recent coverage found in the ingested feed for this instrument.</p>
      )}
      <ul className="space-y-2.5">
        {news.items.map((n) => (
          <li key={n.id} className="border-b border-border/10 pb-2">
            <a href={n.url || '#'} target="_blank" rel="noreferrer" className="text-[12px] font-semibold hover:text-primary inline-flex items-start gap-1">
              {n.headline} {n.url && <ExternalLink size={10} className="mt-1 shrink-0" />}
            </a>
            {n.summary && <p className="text-[11px] text-muted-foreground mt-0.5">{n.summary}</p>}
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[9px] font-mono text-muted-foreground">
              <span>{n.source}</span>
              <span>· {new Date(n.publishedAt).toLocaleString()}</span>
              {n.sourceCount > 1 && <span>· {n.sourceCount} outlets</span>}
              <span className={cn(
                n.sentiment === 'bullish' ? 'text-emerald-400' : n.sentiment === 'bearish' ? 'text-rose-400' : 'text-muted-foreground',
              )}>· {n.sentiment}</span>
            </div>
          </li>
        ))}
      </ul>
    </SectionShell>
  );
}

// ── Section I: technical analysis ────────────────────────────────────────────
export function TechnicalSection({ tech }: { tech: TechnicalSnapshot }) {
  const rows: Array<[string, string, string]> = [
    ['Trend', tech.trend, tech.sma50 != null ? `Last ${num(tech.last)} vs SMA50 ${num(tech.sma50)}` : 'insufficient data'],
    ['RSI (14)', num(tech.rsi14, 1), `State: ${tech.rsiState}`],
    ['MACD', tech.macd != null ? num(tech.macd, 3) : '—', `Signal ${num(tech.macdSignal, 3)} · ${tech.macdState}`],
    ['Volatility (ann.)', num(tech.volatilityPct, 1, '%'), `${tech.bars} bars`],
    ['ATR (14)', num(tech.atr14, 2), 'Average true range'],
    ['Max drawdown', num(tech.maxDrawdownPct, 1, '%'), 'Observed window'],
    ['Momentum 1W / 1M / 3M', `${num(tech.return1w, 1, '%')} / ${num(tech.return1m, 1, '%')} / ${num(tech.return3m, 1, '%')}`, 'Simple period returns'],
    ['Volume trend', tech.volumeTrend == null ? '—' : `${tech.volumeTrend.toFixed(2)}×`, 'Recent 10 vs 50-bar average'],
    ['Support / Resistance', `${num(tech.support)} / ${num(tech.resistance)}`, '20-bar close min / max'],
  ];
  return (
    <SectionShell
      icon={<Activity size={14} className="text-primary" />}
      title="Technical analysis"
      subtitle={tech.asOf ? `as of ${tech.asOf} · ${tech.bars} bars` : undefined}
      right={<span className="text-[9px] font-mono text-muted-foreground">observed, not a forecast</span>}
    >
      {tech.bars === 0 ? (
        <p className="text-[11px] text-muted-foreground">No historical series available for technical analysis.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2">
          {rows.map(([k, v, note]) => (
            <div key={k} className="flex items-baseline justify-between border-b border-border/10 py-1">
              <span className="text-[11px] text-muted-foreground">{k}</span>
              <span className="text-right">
                <span className="font-mono text-[12px] font-bold">{v}</span>
                <span className="block text-[9px] text-muted-foreground/70">{note}</span>
              </span>
            </div>
          ))}
        </div>
      )}
      <p className="text-[9px] text-muted-foreground/70">Computed deterministically from the fetched OHLCV series. Conditions are observed, not predictions.</p>
    </SectionShell>
  );
}

// ── Section J: risk ──────────────────────────────────────────────────────────
export function RiskSection({ risks }: { risks: RiskEntry[] }) {
  return (
    <SectionShell
      icon={<ShieldAlert size={14} className="text-primary" />}
      title="Risk analysis"
      subtitle={`${risks.length} factor${risks.length === 1 ? '' : 's'}`}
      right={<span className="text-[9px] font-mono text-muted-foreground">documented thresholds</span>}
    >
      {risks.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">No computable risk factors from the available data.</p>
      ) : (
        <ul className="space-y-2.5">
          {risks.map((r) => (
            <li key={r.id} className="border-b border-border/10 pb-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[12px] font-semibold flex items-center gap-2">
                  {r.tone === 'positive' ? <CheckCircle2 size={12} className="text-emerald-400" />
                    : r.tone === 'negative' ? <AlertTriangle size={12} className="text-rose-400" />
                      : r.tone === 'warning' ? <AlertTriangle size={12} className="text-amber-400" />
                        : <HelpCircle size={12} className="text-muted-foreground" />}
                  {r.label}
                </span>
                <span className="font-mono text-[12px] font-bold">{r.value}</span>
              </div>
              <p className="text-[10px] text-muted-foreground mt-0.5">{r.basis}</p>
              {r.evidence && <p className="text-[10px] text-amber-300/90 mt-0.5">{r.evidence}</p>}
            </li>
          ))}
        </ul>
      )}
    </SectionShell>
  );
}

// ── Section F: leadership ────────────────────────────────────────────────────
export function LeadershipSection({ officers, companyName }: { officers: Officer[]; companyName: string }) {
  return (
    <SectionShell
      icon={<Landmark size={14} className="text-primary" />}
      title="Leadership & management"
      subtitle={companyName}
      right={<span className="text-[9px] font-mono text-muted-foreground">provider-disclosed</span>}
    >
      {officers.length === 0 ? (
        <p className="text-[11px] text-muted-foreground">
          No executive names are disclosed by the configured fundamentals providers for this instrument.
          The AI brief above surfaces dated leadership evidence when the research run retrieves it.
        </p>
      ) : (
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          {officers.map((o, i) => (
            <li key={`${o.name}-${i}`} className="flex items-baseline justify-between border-b border-border/10 py-1">
              <span className="min-w-0">
                <span className="text-[12px] font-semibold truncate">{o.name}</span>
                <span className="block text-[10px] text-muted-foreground truncate">{o.title}</span>
              </span>
              <span className="text-right shrink-0 ml-2">
                {o.age != null && <span className="block text-[10px] font-mono text-muted-foreground">age {o.age}</span>}
                {o.totalPay != null && (
                  <span className="block text-[10px] font-mono text-muted-foreground">
                    {o.totalPay >= 1e6 ? `${(o.totalPay / 1e6).toFixed(1)}M` : Math.round(o.totalPay)} pay
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-[9px] text-muted-foreground/70">
        Names and titles are provider-reported and can lag an appointment. Verify current officeholders against the latest filing before relying on them.
      </p>
    </SectionShell>
  );
}

// ── Valuation / peers note (Section H) ───────────────────────────────────────
export function ValuationNote() {
  return (
    <div className="rounded-xl border border-border/30 glass-card-subtle px-3 py-2 text-[10px] text-muted-foreground flex items-start gap-2">
      <TrendingUp size={12} className="text-primary mt-0.5 shrink-0" />
      <span>A low multiple does not by itself mean a stock is undervalued. Compare against the company&apos;s own history and verified peers above; peer sets are shown only when the fundamentals provider supplies them.</span>
    </div>
  );
}
