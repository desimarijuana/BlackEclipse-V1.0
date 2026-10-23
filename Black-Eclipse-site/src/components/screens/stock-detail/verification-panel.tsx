'use client';

import { ExternalLink, RefreshCw, ShieldAlert, ShieldCheck } from '@/lib/icons';
import { SectionShell } from '@/components/screens/company/sections';
import { cn } from '@/lib/utils';
import { useStockVerification } from '@/lib/stock-intelligence/use-stock-verification';
import type {
  VerificationCheck,
  VerificationState,
} from '@/lib/stock-intelligence/verification';

const STATE_STYLE: Record<VerificationState, string> = {
  VERIFIED: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
  CORROBORATED: 'border-sky-400/30 bg-sky-400/10 text-sky-300',
  UNVERIFIED: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
  CONFLICTED: 'border-rose-400/30 bg-rose-400/10 text-rose-300',
  UNAVAILABLE: 'border-border/30 bg-muted/20 text-muted-foreground',
};

const STATE_LABEL: Record<VerificationState, string> = {
  VERIFIED: 'Verified',
  CORROBORATED: 'Corroborated',
  UNVERIFIED: 'Single source',
  CONFLICTED: 'Conflict',
  UNAVAILABLE: 'Unavailable',
};

function StateChip({ state }: { state: VerificationState }) {
  return (
    <span className={cn('rounded-md border px-1.5 py-0.5 text-[9px] font-mono font-bold uppercase tracking-wide', STATE_STYLE[state])}>
      {STATE_LABEL[state]}
    </span>
  );
}

function CheckRow({ check }: { check: VerificationCheck }) {
  const official = check.evidence.find((item) => item.official) ?? check.evidence[0];
  return (
    <div className="rounded-xl border border-border/30 glass-card-subtle p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-serif text-xs font-bold">{check.label}</h3>
          <p className="mt-0.5 text-[10px] leading-relaxed text-muted-foreground">{check.detail}</p>
        </div>
        <StateChip state={check.state} />
      </div>
      {official && (
        <a
          href={official.url}
          target="_blank"
          rel="noreferrer noopener"
          className="mt-2 flex items-start gap-1.5 text-[10px] text-muted-foreground/80 hover:text-foreground"
        >
          <ExternalLink size={10} className="mt-0.5 shrink-0" />
          <span className="min-w-0 truncate">{official.title} · {official.host}</span>
        </a>
      )}
    </div>
  );
}

export function SourceVerificationPanel({
  symbol,
  name,
  market,
  price,
  enabled = true,
}: {
  symbol: string;
  name?: string | null;
  market: string;
  price?: number | null;
  enabled?: boolean;
}) {
  const { data, loading, error, refresh } = useStockVerification({
    symbol, market, name, price, enabled,
  });

  if (!enabled) return null;

  return (
    <SectionShell
      icon={<ShieldCheck size={14} className="text-primary" />}
      title="Source verification"
      subtitle="official sources first · search pointers are never evidence"
      right={
        <button
          type="button"
          onClick={refresh}
          className="flex items-center gap-1 rounded-md border border-border/30 px-1.5 py-0.5 text-[9px] font-mono text-muted-foreground hover:text-foreground"
        >
          <RefreshCw size={10} className={cn(loading && 'animate-spin')} /> verify
        </button>
      }
    >
      {loading && (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {[0, 1, 2, 3].map((key) => (
            <div key={key} className="h-20 animate-pulse rounded-xl border border-border/30 glass-card-subtle" />
          ))}
        </div>
      )}
      {!loading && error && (
        <div className="flex items-start gap-2 rounded-xl border border-dashed border-border/30 px-3 py-4">
          <ShieldAlert size={14} className="mt-0.5 shrink-0 text-amber-400" />
          <p className="text-[11px] leading-relaxed text-muted-foreground">{error}</p>
        </div>
      )}
      {!loading && !error && data && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <StateChip state={data.overall} />
            <span className="text-[10px] text-muted-foreground">
              {data.companyName ?? data.symbol} · {data.market}
            </span>
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {data.checks.map((check) => (
              <CheckRow key={check.id} check={check} />
            ))}
          </div>
          {data.warnings.length > 0 && (
            <p className="text-[10px] leading-relaxed text-muted-foreground/60">{data.warnings.join(' · ')}</p>
          )}
        </>
      )}
    </SectionShell>
  );
}
