'use client';

import { useState } from 'react';
import {
  ArrowUpRight,
  Bell,
  Coins,
  Gauge,
  Globe,
  Layers,
  Shield,
  TrendingDown,
  TrendingUp,
} from '@/lib/icons';
import { createQuickAlert } from '@/lib/alerts/quick-alert';
import { navigateTo } from '@/lib/sdk/navigate';
import { cn } from '@/lib/utils';
import type { HomeData } from '@/lib/dashboard/use-home-data';
import type { SectorTone } from '@/lib/dashboard/home-model';
import {
  ChangeText,
  formatAge,
  formatCompactMoney,
  formatPct,
  HomeCard,
  TONE_TEXT,
  UnavailableNote,
  WeightBar,
  toneForChange,
} from './home-primitives';

function Title({ title, right }: { title: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-3">
      <h3 className="text-sm font-medium tracking-tight text-foreground">{title}</h3>
      {right}
    </div>
  );
}

function Cta({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:bg-white/[0.04] hover:text-foreground"
    >
      {label}
      <ArrowUpRight size={11} />
    </button>
  );
}

export function PnlAttributionCard({ data }: { data: HomeData }) {
  const { gainers, losers, net } = data.attribution;
  const empty = gainers.length === 0 && losers.length === 0;
  return (
    <HomeCard>
      <Title
        title="What moved your book"
        right={<span className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">today</span>}
      />
      {data.positionsLoading ? (
        <div className="mt-4 h-16 animate-pulse rounded-xl bg-white/[0.03]" />
      ) : empty ? (
        <UnavailableNote className="mt-4">No priced holdings to attribute today.</UnavailableNote>
      ) : (
        <>
          <p className="mt-3 text-[11px] text-muted-foreground">
            Net today:{' '}
            <span className={cn('font-medium', TONE_TEXT[toneForChange(net)])}>{formatCompactMoney(net, data.displayCurrency)}</span>
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              {gainers.map((row) => (
                <button key={row.symbol} type="button" onClick={() => navigateTo({ tab: 'chart', params: { symbol: row.symbol } })} className="flex w-full items-center justify-between gap-2 text-left text-[11px]">
                  <span className="inline-flex min-w-0 items-center gap-1.5"><TrendingUp size={11} className="shrink-0 text-emerald-400" /><span className="truncate text-foreground/90">{row.symbol}</span></span>
                  <span className="shrink-0 tabular-nums text-emerald-400">+{formatCompactMoney(row.contribution, data.displayCurrency).replace('-', '')}</span>
                </button>
              ))}
              {gainers.length === 0 && <p className="text-[10px] text-muted-foreground/50">No gainers</p>}
            </div>
            <div className="space-y-1.5">
              {losers.map((row) => (
                <button key={row.symbol} type="button" onClick={() => navigateTo({ tab: 'chart', params: { symbol: row.symbol } })} className="flex w-full items-center justify-between gap-2 text-left text-[11px]">
                  <span className="inline-flex min-w-0 items-center gap-1.5"><TrendingDown size={11} className="shrink-0 text-rose-400" /><span className="truncate text-foreground/90">{row.symbol}</span></span>
                  <span className="shrink-0 tabular-nums text-rose-400">{formatCompactMoney(row.contribution, data.displayCurrency)}</span>
                </button>
              ))}
              {losers.length === 0 && <p className="text-[10px] text-muted-foreground/50">No losers</p>}
            </div>
          </div>
        </>
      )}
      <div className="mt-2"><Cta label="Open portfolio" onClick={() => navigateTo({ tab: 'portfolio' })} /></div>
    </HomeCard>
  );
}

export function ActionListCard({ data }: { data: HomeData }) {
  const [alerted, setAlerted] = useState<Record<string, 'ok' | 'err'>>({});
  const rows = data.actionList.slice(0, 6);
  const setAlert = async (symbol: string) => {
    const result = await createQuickAlert(symbol, 3);
    setAlerted((prev) => ({ ...prev, [symbol]: result.ok ? 'ok' : 'err' }));
  };
  return (
    <HomeCard>
      <Title
        title="Needs a look"
        right={<span className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">{data.actionList.length} flagged</span>}
      />
      {data.historyLoading ? (
        <div className="mt-4 h-16 animate-pulse rounded-xl bg-white/[0.03]" />
      ) : rows.length === 0 ? (
        <UnavailableNote className="mt-4">Nothing urgent: no holding is near support, falling, or reporting this week.</UnavailableNote>
      ) : (
        <div className="mt-3 divide-y divide-white/5">
          {rows.map((row) => (
            <div key={row.symbol} className="flex items-center gap-3 py-2">
              <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', row.severity === 'high' ? 'bg-rose-400' : row.severity === 'medium' ? 'bg-zinc-300' : 'bg-white/30')} />
              <button type="button" onClick={() => navigateTo({ tab: 'chart', params: { symbol: row.symbol } })} className="min-w-0 flex-1 text-left">
                <span className="block text-[12px] font-medium text-foreground">{row.symbol}</span>
                <span className="block truncate text-[10px] text-muted-foreground/70">{row.reason}</span>
              </button>
              <button
                type="button"
                onClick={() => void setAlert(row.symbol)}
                title="Create a ±3% alert"
                className="shrink-0 rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-white/[0.06] hover:text-foreground"
              >
                {alerted[row.symbol] === 'ok' ? <span className="text-[9px] text-emerald-400">set</span> : <Bell size={12} />}
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="mt-2"><Cta label="Open portfolio" onClick={() => navigateTo({ tab: 'portfolio' })} /></div>
    </HomeCard>
  );
}

export function MarketSessionsCard({ data }: { data: HomeData }) {
  const open = data.sessions.filter((session) => session.status === 'open').length;
  return (
    <HomeCard>
      <Title
        title="Market sessions"
        right={<span className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/50">{open} open now</span>}
      />
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        {data.sessions.map((session) => (
          <div key={session.name} className="flex items-center gap-2 text-[11px]">
            <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', session.status === 'open' ? 'bg-emerald-400' : 'bg-white/25')} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-foreground/80">{session.name}</span>
              <span className="block text-[9px] text-muted-foreground/60">{session.localTime} · {session.hours}</span>
            </span>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[9px] text-muted-foreground/45">Local exchange hours in each market&apos;s own time zone. Weekends are closed; holidays are not checked.</p>
    </HomeCard>
  );
}

export function RiskCard({ data }: { data: HomeData }) {
  const risk = data.risk;
  return (
    <HomeCard>
      <Title title="Portfolio risk" right={<Gauge size={14} className="text-white/50" />} />
      {data.holdingsCount === 0 || risk.sample === 0 ? (
        <UnavailableNote className="mt-4">Risk metrics need at least one holding with ~30 sessions of history.</UnavailableNote>
      ) : (
        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded-xl bg-white/[0.025] px-3 py-2.5">
            <p className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/60">Volatility</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-foreground">{risk.volatilityPct == null ? '—' : `${risk.volatilityPct.toFixed(1)}%`}</p>
            <p className="text-[9px] text-muted-foreground/50">annualised</p>
          </div>
          <div className="rounded-xl bg-white/[0.025] px-3 py-2.5">
            <p className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/60">Max drawdown</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-rose-400">{risk.maxDrawdownPct == null ? '—' : `${risk.maxDrawdownPct.toFixed(1)}%`}</p>
            <p className="text-[9px] text-muted-foreground/50">recent window</p>
          </div>
          <div className="rounded-xl bg-white/[0.025] px-3 py-2.5">
            <p className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/60">Beta</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-foreground">{risk.beta == null ? '—' : risk.beta.toFixed(2)}</p>
            <p className="text-[9px] text-muted-foreground/50">vs benchmark</p>
          </div>
          <div className="rounded-xl bg-white/[0.025] px-3 py-2.5">
            <p className="text-[9px] uppercase tracking-[0.14em] text-muted-foreground/60">Top weight</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-foreground">{formatPct(risk.concentrationPct)}</p>
            <p className="text-[9px] text-muted-foreground/50">single name</p>
          </div>
        </div>
      )}
      <p className="mt-3 text-[9px] text-muted-foreground/45">Computed from your holdings&apos; daily closes; not a forecast.</p>
    </HomeCard>
  );
}

export function FxExposureCard({ data }: { data: HomeData }) {
  const slices = data.fxExposure;
  return (
    <HomeCard>
      <Title title="Currency exposure" right={<Coins size={14} className="text-white/50" />} />
      {slices.length === 0 ? (
        <UnavailableNote className="mt-4">No priced holdings to split by currency.</UnavailableNote>
      ) : (
        <div className="mt-3 space-y-2">
          {slices.slice(0, 5).map((slice, index) => (
            <div key={slice.currency}>
              <div className="flex items-center justify-between gap-2 text-[10px]">
                <span className="text-muted-foreground">{slice.currency}</span>
                <span className="tabular-nums text-foreground/80">{formatPct(slice.weightPct)} · {formatCompactMoney(slice.value, 'USD')}</span>
              </div>
              <WeightBar className="mt-1" value={slice.weightPct} color={['rgba(255,255,255,0.95)', 'rgba(255,255,255,0.7)', 'rgba(255,255,255,0.5)', 'rgba(255,255,255,0.34)', 'rgba(255,255,255,0.22)'][index % 5]} />
            </div>
          ))}
          {slices[0]?.currency === 'USD' && slices.length === 1 && (
            <p className="text-[10px] text-muted-foreground/60">Fully USD — no foreign-exchange translation risk in the book.</p>
          )}
        </div>
      )}
    </HomeCard>
  );
}

const ROTATION_TONE: Record<SectorTone, string> = {
  leading: 'text-emerald-400',
  improving: 'text-zinc-300',
  weakening: 'text-zinc-400',
  lagging: 'text-rose-400',
};

export function SectorRotationCard({ data }: { data: HomeData }) {
  return (
    <HomeCard>
      <Title title="Sector rotation" right={<Layers size={14} className="text-white/50" />} />
      {data.rotation.every((group) => group.count === 0) ? (
        <UnavailableNote className="mt-4">Sector rotation is unavailable for this scope.</UnavailableNote>
      ) : (
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {data.rotation.map((group) => (
            <div key={group.tone} className="rounded-xl bg-white/[0.025] px-3 py-2.5">
              <p className={cn('text-[10px] font-medium uppercase tracking-[0.1em]', ROTATION_TONE[group.tone])}>{group.label}</p>
              <p className="mt-1 text-lg font-semibold tabular-nums text-foreground">{group.count}</p>
              <p className="mt-0.5 line-clamp-2 text-[9px] text-muted-foreground/60">{group.sectors.join(', ') || '—'}</p>
            </div>
          ))}
        </div>
      )}
    </HomeCard>
  );
}

export function RelativePerformanceCard({ data }: { data: HomeData }) {
  const benchmarkCloses = data.benchmark?.closes ?? [];
  const period = 21;
  const benchReturn = benchmarkCloses.length > period
    ? benchmarkCloses[benchmarkCloses.length - 1] / benchmarkCloses[benchmarkCloses.length - 1 - period] - 1
    : null;
  const rows = data.holdings
    .filter((holding) => holding.closes.length > period && benchReturn != null)
    .map((holding) => {
      const closes = holding.closes;
      const ret = closes[closes.length - 1] / closes[closes.length - 1 - period] - 1;
      return { holding, relative: (ret - (benchReturn ?? 0)) * 100 };
    })
    .sort((a, b) => b.relative - a.relative);
  return (
    <HomeCard>
      <Title title="Relative to benchmark" right={<Globe size={14} className="text-white/50" />} />
      {rows.length === 0 ? (
        <UnavailableNote className="mt-4">Relative performance needs holding history and a benchmark.</UnavailableNote>
      ) : (
        <div className="mt-3 divide-y divide-white/5">
          {rows.slice(0, 6).map((row) => (
            <button key={row.holding.symbol} type="button" onClick={() => navigateTo({ tab: 'chart', params: { symbol: row.holding.symbol } })} className="flex w-full items-center gap-3 py-2 text-left">
              <span className="min-w-0 flex-1"><span className="text-[12px] text-foreground">{row.holding.symbol}</span></span>
              <ChangeText value={row.relative} className="text-[11px]" />
            </button>
          ))}
        </div>
      )}
      <p className="mt-2 text-[9px] text-muted-foreground/45">~1 month vs {data.benchmark?.label ?? 'benchmark'}. Positive means ahead.</p>
    </HomeCard>
  );
}

export function AlertsStripCard({ data }: { data: HomeData }) {
  return (
    <HomeCard>
      <Title title="Alerts" right={<Bell size={14} className="text-white/50" />} />
      <div className="mt-3 flex items-center gap-5">
        <div><p className="text-lg font-semibold tabular-nums text-foreground">{data.activeAlerts}</p><p className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/60">active</p></div>
        <div><p className="text-lg font-semibold tabular-nums text-foreground">{data.alerts.length}</p><p className="text-[9px] uppercase tracking-[0.12em] text-muted-foreground/60">total</p></div>
      </div>
      <div className="mt-3 space-y-1.5">
        {data.recentAlerts.length === 0 ? (
          <p className="rounded-lg bg-white/[0.02] px-2.5 py-2 text-[10px] text-muted-foreground">No alerts have fired yet. Use the bell on a flagged holding to create a ±3% alert.</p>
        ) : (
          data.recentAlerts.map((alert) => (
            <div key={alert.id} className="flex items-center gap-2 text-[11px]">
              <span className="min-w-0 flex-1 truncate text-foreground/85">{alert.name}</span>
              <span className="shrink-0 text-[9px] text-muted-foreground/60">{alert.lastFiredAt ? formatAge(alert.lastFiredAt) : alert.status}</span>
            </div>
          ))
        )}
      </div>
      <div className="mt-2"><Cta label="View alerts" onClick={() => navigateTo({ tab: 'alerts' })} /></div>
    </HomeCard>
  );
}

export function DataFreshness({ data }: { data: HomeData }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 text-[9px] uppercase tracking-[0.12em] text-muted-foreground/40">
      <span>JDDS · {data.updatedAt ? formatAge(data.updatedAt) : 'connecting'}</span>
      <span>Earnings · {data.earningsSource}</span>
      <span>Quotes · {data.displayCurrency}</span>
      <span>{data.holdingsCount} holdings</span>
    </div>
  );
}

export function AlertsShortcutHint() {
  return (
    <span className="inline-flex items-center gap-1 text-[9px] uppercase tracking-[0.12em] text-muted-foreground/40">
      <Shield size={10} /> J/K navigate · Enter open · A alert · R refresh · / search
    </span>
  );
}
