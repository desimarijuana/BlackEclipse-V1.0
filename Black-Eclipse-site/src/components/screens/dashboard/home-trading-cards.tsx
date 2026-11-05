'use client';

// Home dashboard — Trading section.
// Read-only mirror of the broker the user connected in Settings: equity,
// today's P&L, open positions, working orders, margin-based risk and the
// journal edge. Never places/closes/cancels anything (those gates live in
// the broker console and Quick Trade). Every number is either
// broker-reported or computed from broker-reported numbers; missing data
// renders an honest empty state, never a fabricated zero.

import {
  Activity,
  ArrowUpRight,
  BookOpen,
  Briefcase,
  Gauge,
  History,
  Wallet,
} from '@/lib/icons';
import { navigateTo } from '@/lib/sdk/navigate';
import { openSettingsSection } from '@/lib/investor-eye/navigation';
import { cn } from '@/lib/utils';
import type { BrokerWorkingOrder } from '@/lib/harness/trading-client';
import { useTradingHomeData } from '@/lib/dashboard/use-trading-home-data';
import { marginHealth, type MarginHealth } from '@/lib/dashboard/trading-home-model';
import {
  formatAge,
  formatMoney,
  AreaSpark,
  DivergingBarRow,
  HomeCard,
  SymbolChip,
  UnavailableNote,
  WeightBar,
  shortDate,
} from './home-primitives';

const PNL_UP = 'text-emerald-400';
const PNL_DOWN = 'text-rose-400';
const pnlTone = (value: number) => (value > 0 ? PNL_UP : value < 0 ? PNL_DOWN : 'text-muted-foreground');
const fmtSigned = (value: number, currency = 'USD') =>
  `${value >= 0 ? '+' : '−'}${formatMoney(Math.abs(value), currency)}`;

function Title({ title, right }: { title: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-3">
      <h3 className="text-sm font-medium tracking-tight text-foreground">{title}</h3>
      {right}
    </div>
  );
}

function ModeBadge({ mode, armed }: { mode: string; armed: boolean }) {
  const isReal = mode === 'real';
  const isContest = mode === 'contest';
  return (
    <div className="flex items-center gap-1.5">
      {armed && (
        <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-amber-300">
          Live armed
        </span>
      )}
      <span
        className={cn(
          'rounded-full border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.14em]',
          isReal
            ? 'border-rose-400/30 bg-rose-400/10 text-rose-300'
            : isContest
              ? 'border-sky-400/30 bg-sky-400/10 text-sky-300'
              : 'border-sky-400/30 bg-sky-400/10 text-sky-300',
        )}
      >
        {isReal ? 'Live' : isContest ? 'Contest' : mode === 'demo' ? 'Demo' : 'Unknown'}
      </span>
    </div>
  );
}

function TileHeader({ icon, label, right }: { icon: React.ReactNode; label: string; right?: React.ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between gap-2">
      <p className="inline-flex items-center gap-1.5 text-[9px] font-medium uppercase tracking-[0.16em] text-muted-foreground/70">
        <span className="text-white/40">{icon}</span>
        {label}
      </p>
      {right && <div className="shrink-0 text-[9px] text-muted-foreground/60">{right}</div>}
    </div>
  );
}

const MARGIN_HEALTH_LABEL: Record<MarginHealth, { label: string; className: string }> = {
  healthy: { label: 'Healthy', className: 'text-emerald-400' },
  watch: { label: 'Watch', className: 'text-amber-300' },
  danger: { label: 'Danger', className: 'text-rose-400' },
  unavailable: { label: 'n/a', className: 'text-muted-foreground' },
};

function orderTypeLabel(type: string): string {
  // Broker type strings differ per platform ("buy limit", "sell_stop", …) — show, don't reinterpret.
  return type.replace(/_/g, ' ');
}

/** Render a YYYY-MM-DD day key without the UTC-midnight shift. */
function dayLabel(day: string | null): string {
  return day ? shortDate(`${day}T12:00:00`) : '—';
}

/** Render a YYYY-MM month key as "Oct '25". */
function monthLabel(month: string): string {
  const date = new Date(`${month}-01T12:00:00`);
  if (Number.isNaN(date.getTime())) return month;
  return `${date.toLocaleDateString('en-US', { month: 'short' })} '${String(date.getFullYear()).slice(2)}`;
}

/** Compact margin-usage ring (percent of equity posted as margin). */
function UsageRing({ pct, color }: { pct: number | null; color: string }) {
  const size = 62;
  const thickness = 7;
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const value = pct == null || !Number.isFinite(pct) ? 0 : Math.max(0, Math.min(100, pct));
  return (
    <div className="relative inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={thickness} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - value / 100)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[11px] font-semibold tabular-nums text-foreground">
          {pct == null || !Number.isFinite(pct) ? '—' : `${pct.toFixed(0)}%`}
        </span>
        <span className="text-[7px] uppercase tracking-[0.14em] text-muted-foreground/60">used</span>
      </div>
    </div>
  );
}

function OrderRow({ order }: { order: BrokerWorkingOrder }) {
  return (
    <li className="flex items-center gap-2 py-1.5">
      <SymbolChip symbol={order.symbol} />
      <span className="min-w-0 flex-1 truncate text-[10px] capitalize text-muted-foreground">
        {orderTypeLabel(order.type)}
      </span>
      <span className="shrink-0 tabular-nums text-[10px] text-foreground/80">
        {order.volumeCurrent} @ {order.openPrice}
      </span>
    </li>
  );
}

export function TradingCard() {
  const data = useTradingHomeData();
  const { connection, account, error, loading } = data;

  // ── No connection yet, but the read failed/timed out: say why, honestly. ──
  if (!connection && error) {
    return (
      <HomeCard>
        <Title title="Trading" right={<Wallet size={14} className="text-white/50" />} />
        <div className="mt-4 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2.5 text-[11px] leading-relaxed text-amber-200/90">
          {error}
        </div>
        <div className="mt-2 flex items-center gap-2 text-[9px] text-muted-foreground/50">
          <button type="button" onClick={() => void data.refresh()} className="underline decoration-white/20 underline-offset-2 hover:text-foreground">
            Try again
          </button>
          <span>·</span>
          <button type="button" onClick={() => openSettingsSection('trading')} className="underline decoration-white/20 underline-offset-2 hover:text-foreground">
            Broker settings
          </button>
        </div>
      </HomeCard>
    );
  }

  // ── No broker configured: one slim, honest call to action. ──────────────
  if (!connection) {
    return (
      <HomeCard>
        <Title title="Trading" right={<Wallet size={14} className="text-white/50" />} />
        {loading ? (
          <div className="mt-4 space-y-2" aria-hidden>
            {[0, 1, 2].map((row) => (
              <div key={row} className="h-6 animate-pulse rounded-lg bg-white/[0.04]" />
            ))}
          </div>
        ) : (
          <UnavailableNote
            className="mt-4"
            action={
              <button
                type="button"
                onClick={() => openSettingsSection('trading')}
                className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-white/[0.06] px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-foreground transition-colors hover:bg-white/[0.1]"
              >
                Connect
                <ArrowUpRight size={11} />
              </button>
            }
          >
            No broker connected. Link MetaTrader 5 (read-only) in Settings to see equity, today&rsquo;s
            P&amp;L, open positions and margin risk here.
          </UnavailableNote>
        )}
      </HomeCard>
    );
  }

  // ── Connection configured, but the read failed: say why, honestly. ───────
  if (error && !account) {
    return (
      <HomeCard>
        <Title title="Trading" right={<Wallet size={14} className="text-white/50" />} />
        <div className="mt-4 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2.5 text-[11px] leading-relaxed text-amber-200/90">
          Broker read failed: {error}
        </div>
        <p className="mt-2 text-[9px] text-muted-foreground/50">
          Eclipse never fabricates account data — fix the connection and this card fills in.{' '}
          <button type="button" onClick={() => openSettingsSection('trading')} className="underline decoration-white/20 underline-offset-2 hover:text-foreground">
            Broker settings
          </button>
        </p>
      </HomeCard>
    );
  }

  const currency = account?.currency ?? 'USD';
  const armed = Boolean(connection.armedUntil && Date.parse(connection.armedUntil) > Date.now());
  const marginHealthState = marginHealth(data.exposure.marginLevel);
  const marginHealthMeta = MARGIN_HEALTH_LABEL[marginHealthState];
  const ringColor =
    marginHealthState === 'danger' ? '#fb7185' : marginHealthState === 'watch' ? '#fbbf24' : marginHealthState === 'healthy' ? '#34d399' : '#94a3b8';
  const positionsByProfit = [...data.positions].sort((a, b) => Math.abs(b.profit) - Math.abs(a.profit));
  const topPositions = positionsByProfit.slice(0, 4);
  const maxAbsPosition = Math.max(0, ...data.positions.map((position) => Math.abs(position.profit)));
  const topSymbols = data.exposure.bySymbol.slice(0, 3);
  const maxAbsSymbol = Math.max(0, ...data.exposure.bySymbol.map((row) => Math.abs(row.profit)));
  const realizedValues = data.realized.points.map((point) => point.value);
  const realizedLast = realizedValues[realizedValues.length - 1] ?? 0;
  const realizedFlat = data.realized.dealCount > 0 && realizedValues.every((value) => value === realizedValues[0]);
  const realizedStroke = realizedLast >= 0 ? '#34d399' : '#fb7185';
  const journal = data.journal;
  const journalCurveValues = data.journalCurve.map((point) => point.equity);
  const journalCurveStroke = (journalCurveValues[journalCurveValues.length - 1] ?? 0) >= (journalCurveValues[0] ?? 0) ? '#34d399' : '#fb7185';
  const journalDrawdownValues = data.journalCurve.map((point) => -Math.abs(point.drawdown));
  const maxDrawdown = (journal?.equityCurrency ?? []).reduce((max, point) => Math.max(max, point.drawdown), 0);
  const monthlyReturns = (journal?.monthlyReturns ?? []).slice(-12);
  const maxAbsMonthly = Math.max(1, ...monthlyReturns.map((month) => Math.abs(month.netPnl)));
  const journalStats = journal?.performance;
  const journalHasTrades = (journalStats?.totalTrades ?? 0) > 0;
  const profitFactor = journalStats?.profitFactor;
  const profitFactorLabel =
    profitFactor == null || !Number.isFinite(profitFactor)
      ? profitFactor === Infinity
        ? '∞'
        : '—'
      : profitFactor.toFixed(2);

  return (
    <HomeCard accent>
      <Title
        title="Trading"
        right={
          <div className="flex items-center gap-2">
            <ModeBadge mode={account?.mode ?? connection.mode} armed={armed} />
            <button
              type="button"
              onClick={() => openSettingsSection('trading')}
              className="rounded-lg px-2 py-1 text-[9px] font-medium uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground"
            >
              Settings
            </button>
          </div>
        }
      />
      {error && (
        <div className="mt-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-[10px] leading-relaxed text-amber-200/90">
          Partial read failure: {error} — figures below show only what the broker returned.
        </div>
      )}

      {/* ── Account strip: equity · today's P&L · margin ─────────────────── */}
      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div className="rounded-xl bg-white/[0.025] px-3 py-2.5">
          <p className="text-[9px] font-medium uppercase tracking-[0.16em] text-muted-foreground/70">Equity</p>
          <p className="mt-1 truncate text-lg font-semibold tabular-nums text-foreground">
            {account ? formatMoney(account.equity, currency) : '—'}
          </p>
          <p className="mt-0.5 truncate text-[10px] text-muted-foreground/80">
            Balance {account ? formatMoney(account.balance, currency) : '—'} · {connection.label}
          </p>
        </div>
        <div className="rounded-xl bg-white/[0.025] px-3 py-2.5">
          <p className="text-[9px] font-medium uppercase tracking-[0.16em] text-muted-foreground/70">Today · broker-reported</p>
          <p className={cn('mt-1 truncate text-lg font-semibold tabular-nums', pnlTone(data.todayPnl.total))}>
            {fmtSigned(data.todayPnl.total, currency)}
          </p>
          <p className="mt-0.5 truncate text-[10px] text-muted-foreground/80">
            Realized {fmtSigned(data.todayPnl.realized, currency)} · Floating {fmtSigned(data.todayPnl.floating, currency)}
          </p>
        </div>
        <div className="rounded-xl bg-white/[0.025] px-3 py-2.5">
          <p className="text-[9px] font-medium uppercase tracking-[0.16em] text-muted-foreground/70">Margin</p>
          <div className="mt-1 flex items-center gap-3">
            <UsageRing pct={data.exposure.marginUsagePct} color={ringColor} />
            <div className="min-w-0">
              <p className={cn('truncate text-base font-semibold tabular-nums', marginHealthMeta.className)}>
                {data.exposure.marginLevel != null ? `${data.exposure.marginLevel.toFixed(0)}%` : '—'}
              </p>
              <p className="truncate text-[9px] text-muted-foreground/80">{marginHealthMeta.label} level</p>
              <p className="truncate text-[9px] text-muted-foreground/60">
                Free {data.exposure.freeMargin != null ? formatMoney(data.exposure.freeMargin, currency) : '—'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Realized P&L curve (broker deals, last 30 days) ──────────────── */}
      <div className="mt-3 rounded-2xl border border-white/5 bg-white/[0.015] p-3">
        <TileHeader
          icon={<Activity size={11} />}
          label="Realized P&L · last 30 days"
          right={
            <span className={cn('tabular-nums', pnlTone(realizedLast))}>{fmtSigned(realizedLast, currency)}</span>
          }
        />
        {data.realized.dealCount === 0 ? (
          <p className="py-4 text-center text-[11px] italic text-muted-foreground/70">
            No broker deals in the last 30 days.
          </p>
        ) : (
          <>
            <div className="h-20">
              <AreaSpark values={realizedValues} baseline={0} stroke={realizedStroke} />
            </div>
            <div className="mt-1 flex items-center justify-between text-[8px] uppercase tracking-[0.12em] text-muted-foreground/50">
              <span>{dayLabel(data.realized.firstDay)}</span>
              <span>
                {realizedFlat
                  ? `${data.realized.dealCount} ${data.realized.dealCount === 1 ? 'deal' : 'deals'} · no realized P&L in this window`
                  : `${data.realized.dealCount} ${data.realized.dealCount === 1 ? 'deal' : 'deals'} · cumulative · broker-reported`}
              </span>
              <span>{dayLabel(data.realized.lastDay)}</span>
            </div>
          </>
        )}
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-5">
        {/* ── Open positions ─────────────────────────────────────────────── */}
        <div className="rounded-2xl border border-white/5 bg-white/[0.015] p-3 lg:col-span-3">
          <TileHeader
            icon={<Briefcase size={11} />}
            label={`Open positions · ${data.exposure.openCount}`}
            right={
              data.exposure.openCount > 0 ? (
                <span className={cn('tabular-nums', pnlTone(data.exposure.netFloating))}>
                  {fmtSigned(data.exposure.netFloating, currency)}
                </span>
              ) : undefined
            }
          />
          {topPositions.length === 0 ? (
            <p className="py-3 text-center text-[11px] italic text-muted-foreground/70">No open positions.</p>
          ) : (
            <ul className="divide-y divide-white/5">
              {topPositions.map((position) => (
                <li key={position.ticket} className="flex items-center gap-2 py-1.5">
                  <SymbolChip symbol={position.symbol} />
                  <span className={cn('w-6 shrink-0 text-[9px] font-semibold uppercase', position.side === 'buy' ? PNL_UP : PNL_DOWN)}>
                    {position.side === 'buy' ? 'Buy' : 'Sell'}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[10px] tabular-nums text-muted-foreground">
                    {position.volume} @ {position.openPrice}
                  </span>
                  <span className="relative hidden h-1 w-10 shrink-0 rounded-full bg-white/[0.06] sm:block" aria-hidden>
                    <span
                      className={cn('absolute inset-y-0 rounded-full', position.profit >= 0 ? 'left-0 bg-emerald-400/70' : 'right-0 bg-rose-400/70')}
                      style={{ width: `${maxAbsPosition > 0 ? Math.max(8, (Math.abs(position.profit) / maxAbsPosition) * 100) : 0}%` }}
                    />
                  </span>
                  <span className={cn('shrink-0 text-[10px] tabular-nums', pnlTone(position.profit))}>
                    {fmtSigned(position.profit, currency)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {data.positions.length > topPositions.length && (
            <p className="mt-1.5 text-[9px] text-muted-foreground/50">
              +{data.positions.length - topPositions.length} more — manage them in the broker console.
            </p>
          )}
        </div>

        {/* ── Risk & exposure ────────────────────────────────────────────── */}
        <div className="rounded-2xl border border-white/5 bg-white/[0.015] p-3 lg:col-span-2">
          <TileHeader icon={<Gauge size={11} />} label="Risk & exposure" />
          <div className="space-y-2">
            <div>
              <div className="flex items-center justify-between text-[10px]">
                <span className="text-muted-foreground">Margin used</span>
                <span className="tabular-nums text-foreground/80">
                  {data.exposure.marginUsagePct != null ? `${data.exposure.marginUsagePct.toFixed(1)}%` : '—'}
                </span>
              </div>
              <WeightBar
                className="mt-1"
                value={data.exposure.marginUsagePct ?? 0}
                color={marginHealthState === 'danger' ? '#fb7185' : marginHealthState === 'watch' ? '#fbbf24' : 'rgba(255,255,255,0.55)'}
              />
            </div>
            <p className="text-[10px] text-muted-foreground">
              Free margin{' '}
              <span className="tabular-nums text-foreground/80">
                {data.exposure.freeMargin != null ? formatMoney(data.exposure.freeMargin, currency) : '—'}
              </span>
            </p>
            {topSymbols.length > 0 && (
              <div className="space-y-0.5 border-t border-white/5 pt-1.5">
                {topSymbols.map((row) => (
                  <DivergingBarRow
                    key={row.symbol}
                    label={row.symbol}
                    meta={`${row.volume.toFixed(2)} lots`}
                    value={row.profit}
                    maxAbs={maxAbsSymbol}
                    valueLabel={fmtSigned(row.profit, currency)}
                  />
                ))}
              </div>
            )}
            <p className="text-[8px] leading-relaxed text-muted-foreground/45">
              Volume in broker lots — not comparable across symbols. Margin figures are broker-reported.
            </p>
          </div>
        </div>

        {/* ── Working orders ─────────────────────────────────────────────── */}
        <div className="rounded-2xl border border-white/5 bg-white/[0.015] p-3 lg:col-span-3">
          <TileHeader icon={<History size={11} />} label={`Working orders · ${data.orders.length}`} />
          {data.orders.length === 0 ? (
            <p className="py-3 text-center text-[11px] italic text-muted-foreground/70">No working orders.</p>
          ) : (
            <ul className="divide-y divide-white/5">
              {data.orders.slice(0, 4).map((order) => (
                <OrderRow key={order.ticket} order={order} />
              ))}
            </ul>
          )}
          {data.orders.length > 4 && (
            <p className="mt-1.5 text-[9px] text-muted-foreground/50">+{data.orders.length - 4} more in the broker console.</p>
          )}
        </div>

        {/* ── Journal edge ───────────────────────────────────────────────── */}
        <div className="rounded-2xl border border-white/5 bg-white/[0.015] p-3 lg:col-span-2">
          <TileHeader
            icon={<BookOpen size={11} />}
            label="Your edge · journal"
            right={
              <button
                type="button"
                onClick={() => navigateTo({ tab: 'journal' })}
                className="inline-flex items-center gap-0.5 uppercase tracking-[0.12em] transition-colors hover:text-foreground"
              >
                Open
                <ArrowUpRight size={9} />
              </button>
            }
          />
          {data.journalLoading ? (
            <p className="py-3 text-center text-[11px] text-muted-foreground/60">Loading journal…</p>
          ) : !journal || !journalHasTrades ? (
            <p className="py-3 text-center text-[11px] italic text-muted-foreground/70">
              {journal ? 'No journal trades yet — log trades to see your edge.' : 'Journal analytics unavailable.'}
            </p>
          ) : (
            <>
              {journalCurveValues.length >= 2 && (
                <div className="mb-2 h-12">
                  <AreaSpark values={journalCurveValues} stroke={journalCurveStroke} />
                </div>
              )}
              {journalDrawdownValues.length >= 2 && maxDrawdown > 0 && (
                <div className="mb-2">
                  <div className="h-7">
                    <AreaSpark values={journalDrawdownValues} baseline={0} stroke="#fb7185" />
                  </div>
                  <p className="mt-0.5 text-[8px] text-muted-foreground/50">
                    Drawdown · max −{formatMoney(maxDrawdown, currency)}
                  </p>
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <p className="text-[8px] uppercase tracking-[0.14em] text-muted-foreground/60">Win rate</p>
                  <p className="mt-0.5 text-base font-semibold tabular-nums text-foreground">
                    {((journalStats?.winRate ?? 0) * 100).toFixed(0)}%
                  </p>
                </div>
                <div>
                  <p className="text-[8px] uppercase tracking-[0.14em] text-muted-foreground/60">Profit factor</p>
                  <p className="mt-0.5 text-base font-semibold tabular-nums text-foreground">{profitFactorLabel}</p>
                </div>
                <div>
                  <p className="text-[8px] uppercase tracking-[0.14em] text-muted-foreground/60">Net P&amp;L</p>
                  <p className={cn('mt-0.5 text-base font-semibold tabular-nums', pnlTone(journalStats?.netPnl ?? 0))}>
                    {(journalStats?.netPnl ?? 0) >= 0 ? '+' : '−'}
                    {Math.abs(journalStats?.netPnl ?? 0).toFixed(0)}
                  </p>
                </div>
                <div>
                  <p className="text-[8px] uppercase tracking-[0.14em] text-muted-foreground/60">Discipline</p>
                  <p className="mt-0.5 text-base font-semibold tabular-nums text-foreground">
                    {journal?.discipline?.total ?? '—'}
                    <span className="text-[10px] text-muted-foreground/60">/100</span>
                  </p>
                </div>
              </div>
              {monthlyReturns.length > 0 && (
                <div className="mt-2 border-t border-white/5 pt-2">
                  <div className="flex h-5 items-end gap-1">
                    {monthlyReturns.map((month) => {
                      const height = 2 + Math.round((Math.abs(month.netPnl) / maxAbsMonthly) * 14);
                      return (
                        <div
                          key={month.month}
                          className="min-w-0 flex-1"
                          title={`${monthLabel(month.month)} · ${fmtSigned(month.netPnl, currency)} · ${month.trades} trades`}
                        >
                          <div
                            className={cn('w-full rounded-sm', month.netPnl >= 0 ? 'bg-emerald-400/60' : 'bg-rose-400/60')}
                            style={{ height }}
                          />
                        </div>
                      );
                    })}
                  </div>
                  <div className="mt-0.5 flex items-center justify-between text-[8px] uppercase tracking-[0.1em] text-muted-foreground/45">
                    <span>{monthlyReturns[0] ? monthLabel(monthlyReturns[0].month) : ''}</span>
                    <span>Monthly P&amp;L</span>
                    <span>{monthlyReturns[monthlyReturns.length - 1] ? monthLabel(monthlyReturns[monthlyReturns.length - 1].month) : ''}</span>
                  </div>
                </div>
              )}
            </>
          )}
          <p className="mt-2 text-[8px] text-muted-foreground/45">All journal trades · not broker-verified.</p>
        </div>
      </div>

      {/* ── Footer: provenance ───────────────────────────────────────────── */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-white/5 pt-2 text-[9px] text-muted-foreground/50">
        <span className="inline-flex items-center gap-1.5">
          <Activity size={10} />
          Broker-reported via {connection.label} · synced {formatAge(connection.lastSeenAt)}
        </span>
        <span>Read-only — close/modify from the broker console or Quick Trade.</span>
      </div>
    </HomeCard>
  );
}
