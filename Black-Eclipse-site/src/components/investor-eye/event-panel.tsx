'use client';

// ── Investor Eye — Event Dossier ─────────────────────────────────────────────
// The detail view for one event. Its job is to answer, in order:
//
//   WHAT happened  → headline + description (real text, or an explicit reason)
//   WHO            → named actors from the provider
//   WHERE / WHEN   → place, coordinates, and HOW precise that is
//   WHY IT MATTERS → relevance reasons (inferred, labelled as such)
//   WHAT'S EXPOSED → channels / commodities / sectors (potential, not causal)
//   WHAT THE MARKET DID → measured reaction (real closes)
//   WHERE IT CAME FROM  → every source, with links
//
// Every inferred line is labelled. Absence is stated rather than filled in:
// a GDELT event genuinely has no headline, so the panel says so instead of
// dressing up its actor string as reporting.

import { useEffect, useState } from 'react';
import { X, ExternalLink, MapPin, Loader2 } from 'lucide-react';
import { severityColor } from '@/lib/investor-eye/layers';
import { actorTypeLabel } from '@/lib/investor-eye/cameo';
import { countryByIso2, countryByIso3 } from '@/lib/investor-eye/countries';
import { GEO_METHOD_LABEL } from '@/lib/investor-eye/geo-resolve';
import { formatUtc, formatDateTime, formatEventTitle, timeInZone } from '@/lib/investor-eye/format';
import { useDisplayTimeZone } from '@/lib/timezone';
import type { EventEntityRef, NormalizedEvent, SourceRef } from '@/lib/investor-eye/types';
import { AnaloguesPanel } from './analogues-panel';
import { ReactionPanel } from './reaction-panel';
import { ExplainPanel } from './explain-panel';
import { SituationPanel } from './situation-panel';
import { cn } from '@/lib/utils';

interface EventPanelProps {
  event: NormalizedEvent;
  onClose: () => void;
  onSelectCountry?: (iso2: string) => void;
}

export function EventPanel({ event, onClose, onSelectCountry }: EventPanelProps) {
  // Recover a real headline once, at the panel level, so the header and the
  // "What happened" block agree rather than one fetching independently.
  const article = useArticleMeta(event);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <Header event={event} onClose={onClose} headline={article.headline} />

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-3 scrollbar-hide">
        <WhatHappened event={event} article={article} />
        {event.actors && event.actors.length > 0 && <Actors event={event} />}
        <WhereAndWhen event={event} onSelectCountry={onSelectCountry} />
        <SituationPanel eventId={event.id ?? event.dedupKey} hours={168} />
        <TypeDetail event={event} />
        <Observed event={event} />

        {event.relevanceReasons && event.relevanceReasons.length > 0 && (
          <Block title="Why it matters" hint="Derived from the event text — potential relevance, not a causal claim.">
            <div className="flex flex-wrap gap-1">
              {event.relevanceReasons.map((r) => (
                <span key={r} className="glass-card-subtle rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                  {r}
                </span>
              ))}
            </div>
          </Block>
        )}

        {(event.channels.length > 0 || event.commodities.length > 0 || event.sectors.length > 0) && (
          <Block title="Potential exposure" hint="Derived from the event text — not a causal claim.">
            {event.channels.length > 0 && <Row label="Economic channels" value={event.channels.join(', ')} />}
            {event.commodities.length > 0 && <Row label="Commodities" value={event.commodities.join(', ')} />}
            {event.sectors.length > 0 && <Row label="Sectors" value={event.sectors.join(', ')} />}
          </Block>
        )}

        {/* What the market actually did after this event (real stored closes). */}
        <ReactionPanel eventId={event.id ?? event.dedupKey} symbol={event.securities[0]} />

        {/* The AI analyst, where the question is asked. Grounded in this record. */}
        <ExplainPanel eventId={event.id ?? event.dedupKey} />

        <Entities eventId={event.id} />
        <Evidence sources={event.sources} sourceCount={event.sourceCount} />
        <EventTimeline event={event} />

        <AnaloguesPanel
          eventId={event.id ?? event.dedupKey}
          eventType={event.eventType}
          symbol={event.securities[0]}
        />

        <div className="rounded-lg border border-border/30 px-2.5 py-2 text-[10px] leading-relaxed text-muted-foreground/80">
          Confidence is internal data quality (how well the event is corroborated and located), not a
          probability that the event is true. Market interpretations are never shown as facts.
        </div>
      </div>
    </div>
  );
}

// ── Header ───────────────────────────────────────────────────────────────────

/**
 * Lazily recover a real headline for an event whose provider publishes none.
 *
 * GDELT links the article but supplies no text, so this reads the article's Open
 * Graph metadata on first open. Server-side cached, so the network cost is paid
 * once per URL, ever. Resolves to `headline: undefined` when there is nothing
 * usable — the UI then states that honestly instead of inventing text.
 */
function useArticleMeta(event: NormalizedEvent) {
  const id = event.id ?? event.dedupKey;
  const hasOwnText = Boolean(event.headline);
  const hasSourceUrl = event.sources.some((s) => s.url);
  const [state, setState] = useState<{
    loading: boolean; headline?: string; description?: string; note?: string; siteName?: string;
  }>({ loading: false });

  useEffect(() => {
    if (hasOwnText || !hasSourceUrl) {
      setState({ loading: false });
      return;
    }
    let cancelled = false;
    setState({ loading: true });
    fetch(`/api/investor-eye/article?id=${encodeURIComponent(id)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((json: ArticleResponse | null) => {
        if (cancelled) return;
        setState({
          loading: false,
          headline: json?.available ? json.headline : undefined,
          description: json?.available ? json.description ?? undefined : undefined,
          note: json?.available ? undefined : json?.note,
          siteName: json?.siteName ?? undefined,
        });
      })
      .catch(() => { if (!cancelled) setState({ loading: false }); });
    return () => { cancelled = true; };
  }, [id, hasOwnText, hasSourceUrl]);

  return {
    ...state,
    headline: event.headline ?? state.headline,
    description: event.description ?? state.description,
    /** True when the text came from the article rather than the event record. */
    fromArticle: !event.headline && Boolean(state.headline),
  };
}

function Header({ event, onClose, headline }: { event: NormalizedEvent; onClose: () => void; headline?: string }) {
  return (
    <div className="flex items-start justify-between gap-2 border-b border-border/10 px-4 py-3">
      <div className="min-w-0">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: severityColor(event.severity) }} />
          <span className="text-[10px] font-mono uppercase tracking-wide text-muted-foreground">
            {event.eventType.replace(/_/g, ' ')} · {event.severity}
          </span>
          <SourceBadge count={event.sourceCount} outlets={event.sources.length > 0 ? new Set(event.sources.map((s) => s.name)).size : undefined} />
        </div>
        <div className="text-sm font-semibold leading-snug text-foreground">
          {headline ?? formatEventTitle(event.title, event.placeName)}
        </div>
      </div>
      <button
        onClick={onClose}
        className="shrink-0 rounded-lg p-1 text-muted-foreground hover:bg-accent hover:text-foreground cursor-pointer"
        aria-label="Close event panel"
      >
        <X size={14} />
      </button>
    </div>
  );
}

/**
 * Corroboration badge. Uses the number of DISTINCT OUTLETS where we have them,
 * because since the article-identity fix one article can back several captured
 * sources — a raw count would overstate corroboration.
 */
function SourceBadge({ count, outlets }: { count: number; outlets?: number }) {
  const n = outlets ?? count;
  const level = n >= 3 ? 'confirmed' : n === 2 ? 'corroborated' : 'single source';
  const style =
    n >= 3
      ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
      : n === 2
        ? 'border-sky-500/25 bg-sky-500/10 text-sky-300'
        : 'border-border/40 text-muted-foreground';
  return (
    <span
      className={cn('rounded-sm border px-1.5 py-0.5 text-[9px] font-mono', style)}
      title={
        outlets !== undefined && outlets !== count
          ? `${outlets} distinct outlet(s) across ${count} captured source(s)`
          : `${count} independent source(s) reported this`
      }
    >
      {level} · {n}
    </span>
  );
}

// ── What happened ────────────────────────────────────────────────────────────

type ArticleState = ReturnType<typeof useArticleMeta>;

function WhatHappened({ event, article }: { event: NormalizedEvent; article: ArticleState }) {
  const [showRaw, setShowRaw] = useState(false);
  const { headline, description, loading, fromArticle, note, siteName } = article;

  // Avoid printing the same sentence twice when a feed repeats title=summary.
  const body = description && description !== headline ? description : undefined;

  return (
    <Block
      title="What happened"
      hint={
        event.headline ? 'Headline as published by the reporting source.'
          : fromArticle ? `Headline read from the linked article${siteName ? ` (${siteName})` : ''}.`
            : undefined
      }
    >
      {headline ? (
        <>
          {body
            ? <p className="text-[11px] leading-relaxed text-muted-foreground">{body}</p>
            : <p className="text-[11px] leading-relaxed text-muted-foreground">Reported under the headline above.</p>}
        </>
      ) : loading ? (
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/70">
          <Loader2 size={11} className="animate-spin" /> Reading the linked article…
        </div>
      ) : (
        <div className="space-y-1">
          <div className="text-[10px] italic text-muted-foreground/70">
            No article headline available for this event.
          </div>
          <div className="text-[10px] leading-relaxed text-muted-foreground/60">
            {note
              ?? (event.actors?.length
                ? 'This event comes from a structured feed that publishes coded events without headlines. The actors and codes below are its own record.'
                : 'Open a source below to read the reporting.')}
          </div>
          {/* The raw provider string is available on request, but not primary —
              it reads as a code fragment, not a sentence. */}
          <button
            onClick={() => setShowRaw((v) => !v)}
            className="text-[9px] text-primary/80 hover:text-primary hover:underline cursor-pointer"
          >
            {showRaw ? 'hide the raw event record' : "show the source's raw event record"}
          </button>
          {showRaw && (
            <div className="rounded-md border border-border/25 px-2 py-1 font-mono text-[9px] leading-relaxed text-muted-foreground">
              {event.title}
            </div>
          )}
        </div>
      )}
    </Block>
  );
}

interface ArticleResponse {
  available: boolean;
  note?: string;
  headline?: string;
  description?: string | null;
  titleSource?: string;
  siteName?: string | null;
  cached?: boolean;
}

// ── Actors ───────────────────────────────────────────────────────────────────

function Actors({ event }: { event: NormalizedEvent }) {
  return (
    <Block title="Actors" hint="Named by the reporting source.">
      <div className="space-y-1">
        {event.actors!.map((a, i) => {
          const type = actorTypeLabel(a.typeCode);
          // GDELT's actor country codes are 3-letter ISO3; resolve to a name so
          // the actor reads as "Iran" rather than "IRN".
          const country = a.countryCode ? countryByIso3(a.countryCode) : undefined;
          return (
            <div key={`${a.name}-${i}`} className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate text-[11px] font-medium text-foreground">{a.name}</span>
              <span className="flex shrink-0 items-center gap-1">
                {type && (
                  <span className="rounded-sm border border-border/40 px-1 font-mono text-[9px] text-muted-foreground">
                    {type}
                  </span>
                )}
                {a.countryCode && (
                  <span className="font-mono text-[9px] text-muted-foreground/70">{country?.name ?? a.countryCode}</span>
                )}
              </span>
            </div>
          );
        })}
      </div>
      {event.providerCodes?.cameoRoot && (
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px] text-muted-foreground/60">
          <span className="font-mono">CAMEO {event.providerCodes.cameoRoot}</span>
          {event.providerCodes.goldstein !== undefined && (
            <span className="font-mono">Goldstein {event.providerCodes.goldstein}</span>
          )}
          <span>· provider codes, shown verbatim</span>
        </div>
      )}
    </Block>
  );
}

// ── Where & when ─────────────────────────────────────────────────────────────

function WhereAndWhen({ event, onSelectCountry }: { event: NormalizedEvent; onSelectCountry?: (iso2: string) => void }) {
  const tz = useDisplayTimeZone();
  const method = event.geoMethod ? GEO_METHOD_LABEL[event.geoMethod] : undefined;
  return (
    <Block title="Where & when" hint={`Times in ${tz}.`}>
      {event.placeName && (
        <div className="mb-1 flex items-start gap-1.5 text-[11px] text-foreground">
          <MapPin size={11} className="mt-0.5 shrink-0 text-muted-foreground" />
          <span className="min-w-0">{event.placeName}</span>
        </div>
      )}
      <Row label="First detected" value={formatDateTime(event.publishedAt, tz)} />
      {event.lastUpdated && <Row label="Last updated" value={formatDateTime(event.lastUpdated, tz)} />}
      {typeof event.lat === 'number' && typeof event.lon === 'number' && (
        <Row label="Coordinates" value={`${event.lat.toFixed(3)}, ${event.lon.toFixed(3)}`} />
      )}
      {method && (
        <div className="mt-0.5 text-[9px] italic text-muted-foreground/60">location: {method}</div>
      )}
      {event.countries.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {event.countries.map((c) => (
            <button
              key={c}
              onClick={() => onSelectCountry?.(c)}
              className="glass-card-subtle rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] font-mono text-foreground hover:border-primary/30 cursor-pointer"
              title={`Open ${countryByIso2(c)?.name ?? c} intelligence`}
            >
              {countryByIso2(c)?.name ?? c}
            </button>
          ))}
        </div>
      )}
    </Block>
  );
}

// ── Observed ─────────────────────────────────────────────────────────────────

function Observed({ event }: { event: NormalizedEvent }) {
  return (
    <Block title="Observed">
      <Row label="Sources" value={String(event.sourceCount)} />
      {event.relevance !== undefined && (
        <Row label="Relevance" value={`${Math.round(event.relevance * 100)}%`} />
      )}
      <Row label="Data confidence" value={event.confidence.toFixed(2)} />
      <Row label="Primary source" value={event.primarySource} />
      {event.securities.length > 0 && <Row label="Securities" value={event.securities.join(', ')} />}
    </Block>
  );
}

// ── Entities (from the already-persisted EventEntity links) ──────────────────

function Entities({ eventId }: { eventId?: string }) {
  const [entities, setEntities] = useState<EventEntityRef[] | null>(null);

  useEffect(() => {
    // Only persisted events have entity links; an unpersisted event has no id.
    if (!eventId) { setEntities(null); return; }
    let cancelled = false;
    setEntities(null);
    fetch(`/api/investor-eye/events/${encodeURIComponent(eventId)}`)
      .then((r) => (r.ok ? r.json() : { entities: [] }))
      .then((json: { entities?: EventEntityRef[] }) => {
        if (!cancelled) setEntities(json.entities ?? []);
      })
      // Entity links are an enhancement. A miss (or an event not yet persisted)
      // must not surface as a console error — we simply omit the section.
      .catch(() => { if (!cancelled) setEntities([]); });
    return () => { cancelled = true; };
  }, [eventId]);

  // Entities are an enhancement: absent, we simply don't render a section.
  if (!entities || entities.length === 0) return null;

  const grouped = entities.reduce<Record<string, EventEntityRef[]>>((acc, e) => {
    (acc[e.kind] ??= []).push(e);
    return acc;
  }, {});

  return (
    <Block title="Linked entities" hint="Stored links from this event to countries, commodities and securities.">
      <div className="space-y-1">
        {Object.entries(grouped).map(([kind, refs]) => (
          <div key={kind} className="flex items-start gap-2">
            <span className="w-16 shrink-0 text-[9px] uppercase tracking-wide text-muted-foreground/70">{kind}</span>
            <div className="flex flex-wrap gap-1">
              {refs.slice(0, 10).map((r) => (
                <span key={`${kind}-${r.entityId}`} className="glass-card-subtle rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                  {r.name}
                </span>
              ))}
              {refs.length > 10 && (
                <span className="text-[9px] text-muted-foreground/60">+{refs.length - 10}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </Block>
  );
}

// ── Evidence ─────────────────────────────────────────────────────────────────

function Evidence({ sources, sourceCount }: { sources: SourceRef[]; sourceCount: number }) {
  // Corroboration means INDEPENDENT outlets. After the article-identity fix one
  // article can legitimately back several rows, so the honest measure is the
  // number of distinct outlets, not the raw source count.
  const outlets = [...new Set(sources.map((s) => s.name))];
  const distinctUrls = new Set(sources.map((s) => s.url).filter(Boolean));
  const hint =
    outlets.length > 1
      ? `${outlets.length} distinct outlets reported this.`
      : sources.length > 1
        ? 'Multiple citations of the same article — one outlet.'
        : 'Single outlet. Not independently corroborated.';

  return (
    <Block title="Sources" hint={hint}>
      {sources.length === 0 ? (
        <div className="text-[10px] italic text-muted-foreground/70">No source list captured.</div>
      ) : (
        <div className="space-y-1.5">
          {sources.slice(0, 12).map((s, i) => (
            <div key={`${s.id}-${i}`} className="flex items-baseline justify-between gap-2">
              <div className="min-w-0">
                <span className="text-[10px] font-medium text-foreground">{s.name}</span>
                {s.publishedAt && (
                  <span className="ml-1 font-mono text-[9px] text-muted-foreground/60">{formatUtc(s.publishedAt)}</span>
                )}
              </div>
              {s.url ? (
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex shrink-0 items-center gap-0.5 text-[9px] text-primary hover:underline"
                  title={s.url}
                >
                  open <ExternalLink size={9} />
                </a>
              ) : null}
            </div>
          ))}
          {sources.length > 12 && (
            <div className="text-[9px] text-muted-foreground/60">+{sources.length - 12} more sources</div>
          )}
          {/* Provider counts vs what we actually captured — never let a large
              number imply corroboration we did not verify. */}
          {sourceCount > sources.length && (
            <div className="text-[9px] text-muted-foreground/60">
              The provider counted {sourceCount} sources; {sources.length} were individually captured
              {distinctUrls.size > 0 ? ` (${distinctUrls.size} distinct article${distinctUrls.size === 1 ? '' : 's'})` : ''}.
            </div>
          )}
        </div>
      )}
    </Block>
  );
}

// ── Type-specific detail ─────────────────────────────────────────────────────
// The same dossier serves every event type; only the emphasis changes. A
// natural disaster leads with magnitude, an energy event leads with the
// commodity, a conflict leads with the actor dyad — all from real fields.

function TypeDetail({ event }: { event: NormalizedEvent }) {
  const rows: Array<{ label: string; value: string }> = [];

  // USGS encodes magnitude in the title ("M 4.5 - ...") — read it back rather
  // than storing a parallel field.
  if (event.eventType === 'natural_disaster') {
    const m = event.title.match(/\bM\s*([0-9]+\.[0-9]+)\b/);
    if (m) rows.push({ label: 'Magnitude', value: m[1] });
  }

  if (event.actors && event.actors.length === 2) {
    rows.push({ label: 'Actor dyad', value: `${event.actors[0].name} → ${event.actors[1].name}` });
  }

  if (event.commodities.length > 0) {
    rows.push({ label: 'Commodities', value: event.commodities.join(', ') });
  }

  if (rows.length === 0) return null;

  return (
    <Block title="Detail">
      {rows.map((r) => <Row key={r.label} label={r.label} value={r.value} />)}
    </Block>
  );
}

// ── Event timeline ───────────────────────────────────────────────────────────
// How the story developed: first detection → each source's own timestamp →
// last update. Drawn only from real timestamps.

function EventTimeline({ event }: { event: NormalizedEvent }) {
  const tz = useDisplayTimeZone();
  const stamps: Array<{ label: string; iso: string }> = [];
  if (event.firstSeen) stamps.push({ label: 'First ingested', iso: event.firstSeen });
  for (const s of event.sources) {
    if (s.publishedAt) stamps.push({ label: s.name, iso: s.publishedAt });
  }
  if (event.lastUpdated) stamps.push({ label: 'Last updated', iso: event.lastUpdated });

  // De-duplicate by (label, timestamp) and sort chronologically.
  const seen = new Set<string>();
  const ordered = stamps
    .filter((s) => {
      const k = `${s.label}|${s.iso}`;
      if (seen.has(k)) return false;
      seen.add(k);
      return !Number.isNaN(Date.parse(s.iso));
    })
    .sort((a, b) => Date.parse(a.iso) - Date.parse(b.iso));

  if (ordered.length < 2) return null;

  return (
    <Block title="Timeline" hint="Source timestamps, earliest first.">
      <div className="space-y-1">
        {ordered.slice(0, 8).map((s, i) => (
          <div key={`${s.label}-${s.iso}-${i}`} className="flex items-baseline gap-2">
            <span className="w-20 shrink-0 font-mono text-[9px] text-muted-foreground/70">
              {timeInZone(s.iso, tz)}
            </span>
            <span className="min-w-0 flex-1 truncate text-[10px] text-muted-foreground">{s.label}</span>
          </div>
        ))}
      </div>
    </Block>
  );
}

// ── Shared primitives ────────────────────────────────────────────────────────

function Block({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{title}</div>
      {hint && <div className="mb-1 text-[9px] italic text-muted-foreground/70">{hint}</div>}
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-0.5">
      <span className="text-[10px] text-muted-foreground">{label}</span>
      <span className="text-right text-[10px] font-medium text-foreground">{value}</span>
    </div>
  );
}
