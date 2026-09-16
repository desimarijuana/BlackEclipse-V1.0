'use client';

// ── Investor Eye — Company panel (Phase 2.6 fix) ─────────────────────────────
// Opened by clicking a company pin on the map (previously a dead click). Shows
// the stored attributes only — HQ country, sector, and the event relationships
// the graph derived for that company. No invented supply chains (spec §34).

import { useMemo } from 'react';
import { X } from 'lucide-react';
import { useTopic } from '@/lib/workspace/data-hub';
import { IE_GRAPH_TOPIC } from '@/lib/investor-eye/topics';
import { countryByIso2 } from '@/lib/investor-eye/countries';
import type { CompanyPoint, RelationshipGraph } from '@/lib/investor-eye/types';
import { formatPct } from '@/lib/investor-eye/format';
import { cn } from '@/lib/utils';

export function CompanyPanel({
  company,
  onClose,
  onSelectCountry,
}: {
  company: CompanyPoint;
  onClose: () => void;
  onSelectCountry?: (iso2: string) => void;
}) {
  const graphTopic = useTopic<RelationshipGraph>(IE_GRAPH_TOPIC);
  const country = countryByIso2(company.iso2);

  // Relationships the graph already derived for this company (stored data).
  const relations = useMemo(() => {
    if (!graphTopic.data) return [];
    const nodeId = `company:${company.symbol}`;
    return graphTopic.data.links
      .filter((l) => l.source === nodeId || l.target === nodeId)
      .map((l) => {
        const otherId = l.source === nodeId ? l.target : l.source;
        const other = graphTopic.data?.nodes.find((n) => n.id === otherId);
        return { relation: l.relation, relationClass: l.relationClass, other };
      })
      .slice(0, 8);
  }, [graphTopic.data, company.symbol]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-start justify-between gap-2 border-b border-border/10 px-4 py-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-foreground">{company.name}</div>
          <div className="text-[10px] font-mono uppercase tracking-wide text-muted-foreground">
            {company.symbol}
            {company.sector ? ` · ${company.sector}` : ''}
          </div>
        </div>
        <button
          onClick={onClose}
          className="shrink-0 rounded-lg p-1 text-muted-foreground hover:bg-accent hover:text-foreground cursor-pointer"
          aria-label="Close company panel"
        >
          <X size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4 scrollbar-hide">
        <Block title="Profile">
          <Row label="HQ country" value={country?.name ?? company.iso2} />
          <Row label="Sector" value={company.sector ?? '—'} />
          {company.changePct !== undefined && (
            <Row
              label="Change"
              value={formatPct(company.changePct)}
              valueClass={company.changePct >= 0 ? 'text-emerald-400' : 'text-red-400'}
            />
          )}
        </Block>

        <Block title="Related entities" hint="Derived from stored relationships — not an inferred supply chain.">
          {relations.length === 0 ? (
            <div className="text-[10px] italic text-muted-foreground/70">
              No relationships derived for this company yet.
            </div>
          ) : (
            <div className="space-y-1">
              {relations.map((r, i) => (
                <button
                  key={i}
                  onClick={() => {
                    if (r.other?.kind === 'country' && r.other.iso2) onSelectCountry?.(r.other.iso2);
                  }}
                  className={cn(
                    'flex w-full items-center justify-between gap-2 rounded-lg border border-border/20 px-2 py-1 text-left',
                    r.other?.kind === 'country' && 'hover:border-primary/30 cursor-pointer',
                  )}
                >
                  <span className="truncate text-[10px] text-foreground/90">{r.other?.name ?? '—'}</span>
                  <span className="shrink-0 text-[9px] font-mono text-muted-foreground">
                    {r.relation} · {r.relationClass.toLowerCase()}
                  </span>
                </button>
              ))}
            </div>
          )}
        </Block>

        {country?.marketId && (
          <Block title="Market">
            <div className="text-[10px] text-muted-foreground">
              Linked JDDS market: <span className="font-mono text-foreground">{country.marketId}</span>
            </div>
          </Block>
        )}
      </div>
    </div>
  );
}

function Block({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{title}</div>
      {hint && <div className="mb-1 text-[9px] italic text-muted-foreground/70">{hint}</div>}
      {children}
    </div>
  );
}

function Row({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-0.5">
      <span className="text-[10px] text-muted-foreground">{label}</span>
      <span className={cn('text-right text-[10px] font-medium text-foreground', valueClass)}>{value}</span>
    </div>
  );
}
