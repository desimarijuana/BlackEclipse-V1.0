'use client';

// ── Investor Eye — Portfolio overlay panel (Phase 2) ─────────────────────────
// Reuses the EXISTING portfolio engine (`useAggregatePortfolio`) — no second
// portfolio system. It maps each holding's market to an ISO2 country and posts
// the exposure to `/api/investor-eye/portfolio`, which returns exposure and
// event intersections. Presented strictly as exposure, never as advice.

import { useEffect, useMemo, useState } from 'react';
import { useAggregatePortfolio } from '@/lib/dashboard/portfolio-store';
import { MARKET_ID_MAP } from '@/lib/markets';
import type { ExposureSlice, PortfolioIntersection } from '@/lib/investor-eye/analytics';
import { cn } from '@/lib/utils';

interface PortfolioResponse {
  exposure: { countries: ExposureSlice[]; sectors: ExposureSlice[]; total: number; unmappedWeight: number };
  intersections: PortfolioIntersection[];
  provenance: string;
  disclaimer: string;
}

/** JDDS market id → ISO2 (the gazetteer keys the map on ISO2). */
function iso2ForMarket(marketId: string | undefined): string | undefined {
  if (!marketId) return undefined;
  const mapped = MARKET_ID_MAP[marketId] ?? marketId;
  // CRYPTO/US aliases resolve here; anything not a 2-letter ISO is dropped.
  return /^[A-Z]{2}$/.test(mapped) ? mapped : undefined;
}

export function PortfolioPanel({ onExposureReady }: { onExposureReady?: (rows: Array<{ iso2: string; weight: number }>) => void }) {
  const { stats, quotes } = useAggregatePortfolio();
  const [data, setData] = useState<PortfolioResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const holdings = useMemo(() => {
    const marketBySymbol = new Map(quotes.map((q) => [q.symbol.toUpperCase(), q.marketId]));
    const total = stats.holdings.reduce((sum, h) => sum + (h.valueUsd || 0), 0) || 1;
    return stats.holdings.map((h) => ({
      symbol: h.symbol,
      weight: (h.valueUsd || 0) / total,
      country: iso2ForMarket(marketBySymbol.get(h.symbol.toUpperCase())),
    }));
  }, [stats.holdings, quotes]);

  useEffect(() => {
    let cancelled = false;
    if (holdings.length === 0) {
      setData(null);
      onExposureReady?.([]);
      return;
    }
    setLoading(true);
    fetch('/api/investor-eye/portfolio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ holdings }),
    })
      .then((r) => r.json())
      .then((json: PortfolioResponse) => {
        if (cancelled) return;
        setData(json);
        onExposureReady?.(json.exposure.countries.map((c) => ({ iso2: c.key, weight: c.weight })));
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [holdings, onExposureReady]);

  if (holdings.length === 0) {
    return (
      <Shell>
        <Muted>No holdings found. Add positions in the Portfolio tab to see exposure here.</Muted>
      </Shell>
    );
  }

  return (
    <Shell>
      {loading && !data && <Muted>Computing exposure…</Muted>}
      {data && (
        <>
          <Sub title="Country exposure">
            {data.exposure.countries.length === 0 ? (
              <Muted>No holdings could be mapped to a country.</Muted>
            ) : (
              <div className="space-y-1">
                {data.exposure.countries.slice(0, 6).map((c) => (
                  <div key={c.key} className="flex items-center gap-2 text-[10px]">
                    <span className="w-10 shrink-0 font-mono text-muted-foreground">{c.key}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                      <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, c.weight * 100)}%` }} />
                    </div>
                    <span className="w-10 shrink-0 text-right font-mono text-foreground">{(c.weight * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            )}
          </Sub>

          <Sub title="Sector exposure">
            {data.exposure.sectors.length === 0 ? (
              <Muted>Sector data unavailable for these holdings.</Muted>
            ) : (
              <div className="space-y-1">
                {data.exposure.sectors.slice(0, 6).map((s) => (
                  <div key={s.key} className="flex items-center gap-2 text-[10px]">
                    <span className="w-20 shrink-0 truncate text-muted-foreground">{s.label}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                      <div className="h-full rounded-full bg-accent-foreground/40" style={{ width: `${Math.min(100, s.weight * 100)}%` }} />
                    </div>
                    <span className="w-10 shrink-0 text-right font-mono text-foreground">{(s.weight * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            )}
          </Sub>

          <Sub title={`Events intersecting (${data.intersections.length})`}>
            {data.intersections.length === 0 ? (
              <Muted>No current events intersect this portfolio.</Muted>
            ) : (
              <div className="space-y-1">
                {data.intersections.slice(0, 6).map((x) => (
                  <div key={x.event.id ?? x.event.dedupKey} className="rounded-lg border border-border/20 px-2 py-1">
                    <div className="line-clamp-2 text-[10px] text-foreground/90">{x.event.title}</div>
                    <div className="mt-0.5 flex items-center gap-2 text-[9px] text-muted-foreground">
                      {x.matchedCountries.length > 0 && <span>{x.matchedCountries.join(', ')}</span>}
                      <span className={cn('font-mono', x.exposedWeight > 0.1 ? 'text-amber-400' : 'text-muted-foreground')}>
                        {(x.exposedWeight * 100).toFixed(1)}% exposed
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Sub>

          <div className="text-[9px] italic leading-relaxed text-muted-foreground/60">{data.disclaimer}</div>
        </>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5 px-3 py-2.5">
      <div className="mb-2 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
        Portfolio Exposure
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Sub({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground/80">{title}</div>
      {children}
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <div className="text-[10px] italic text-muted-foreground/70">{children}</div>;
}
