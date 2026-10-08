"use client";

// ── Market Data Layer console ────────────────────────────────────────────────
// The operator surface for the Market Data Layer: providers, per-provider
// health, DECLARED-vs-OBSERVED rate limits (live quota), the real-time stream
// state, the cache and recent data-quality findings. Rendered inside the
// existing "Data & providers" settings area — no new design system, no store.
//
// Everything is read from the SAME Python `/market/*` routes the agent tools
// use, via the front-door proxy. Credentials are shown only as presence.

import { useCallback, useEffect, useState } from "react";
import { Activity, AlertCircle, Check, Gauge, Loader2, Radio, RefreshCcw, Timer } from "@/lib/icons";
import { cn } from "@/lib/utils";
import {
  fetchMarketHealth,
  fetchMarketProviders,
  fetchMarketQuality,
  fetchMarketStream,
  type MarketHealth,
  type MarketProviderRow,
  type MarketQualityEvent,
  type MarketStreamSnapshot,
} from "@/lib/harness/market-client";
import { Panel } from "./settings-ui";

const REFRESH_MS = 15_000;

export function MarketDataConsole() {
  const [providers, setProviders] = useState<MarketProviderRow[]>([]);
  const [health, setHealth] = useState<MarketHealth | null>(null);
  const [stream, setStream] = useState<MarketStreamSnapshot | null>(null);
  const [quality, setQuality] = useState<MarketQualityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [p, h, s, q] = await Promise.all([
        fetchMarketProviders().catch(() => null),
        fetchMarketHealth().catch(() => null),
        fetchMarketStream().catch(() => null),
        fetchMarketQuality(20).catch(() => null),
      ]);
      if (p?.providers) setProviders(p.providers);
      setHealth(h);
      setStream(s);
      setQuality(q?.events ?? []);
    } catch {
      setError("Could not reach the market data layer.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  const rateLimits = health?.providerMetrics?.rateLimits ?? {};
  const providerStats = health?.providerMetrics?.providers ?? {};

  return (
    <Panel className="p-5 md:p-6" data-anchor="market-data">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <Activity className="h-4 w-4 text-muted-foreground" />
            Market Data Layer
          </h3>
          <p className="mt-1 max-w-2xl text-[10px] leading-relaxed text-muted-foreground">
            Quotes, OHLCV, order books, trades, funding, open interest, options, FX, bonds and
            real-time streams — routed across providers, quality-checked, and provenance-carrying.
            Rate limits show <span className="text-foreground/80">declared</span> vs the{" "}
            <span className="text-foreground/80">observed</span> live quota.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2 py-1 text-[10px] text-muted-foreground hover:bg-white/5 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCcw className="h-3 w-3" />}
          Refresh
        </button>
      </div>

      {error && (
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-[10px] text-amber-400/90">
          <AlertCircle className="h-3 w-3" /> {error}
        </div>
      )}

      {health && !health.available && (
        <div className="mt-3 rounded-lg border border-white/10 glass-card-subtle px-3 py-2 text-[10px] text-muted-foreground">
          The market data layer is unavailable{health.reason ? `: ${health.reason}` : "."}
        </div>
      )}

      {health?.available && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">
            <Stat label="Requests" value={String(health.metrics?.requests ?? 0)} />
            <Stat label="Cache hits" value={String(health.metrics?.cacheHits ?? 0)} />
            <Stat label="Provider calls" value={String(health.metrics?.providerCalls ?? 0)} />
            <Stat label="Rate-limited" value={String(health.metrics?.rateLimited ?? 0)} tone={(health.metrics?.rateLimited ?? 0) > 0 ? "warn" : undefined} />
          </div>

          <Section title="Rate limits — declared vs observed" icon={<Gauge className="h-3 w-3" />}>
            {Object.keys(rateLimits).length === 0 ? (
              <Empty>No provider has been called yet.</Empty>
            ) : (
              <div className="space-y-2">
                {Object.entries(rateLimits).map(([provider, rl]) => (
                  <div key={provider} className="rounded-xl border border-white/10 glass-card-subtle px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium">{provider}</span>
                      <span className="text-[10px] text-muted-foreground">
                        effective {rl.effectiveRequestsPerMinute ?? "—"}/min
                        {rl.cooldownRemainingS > 0 && ` · cooldown ${rl.cooldownRemainingS}s`}
                      </span>
                    </div>
                    <div className="mt-1 grid grid-cols-2 gap-2 text-[10px] text-muted-foreground">
                      <span>declared: {rl.declared.requestsPerMinute ?? "—"}/min · {rl.declared.concurrency} conc</span>
                      <span>
                        observed: {rl.observed.remaining != null ? `${rl.observed.remaining} left` : "—"}
                        {rl.observed.used != null ? ` (${rl.observed.used} used)` : ""}
                      </span>
                    </div>
                    {providerStats[provider] && (
                      <div className="mt-0.5 text-[10px] text-muted-foreground/70">
                        {providerStats[provider].calls} call(s) · avg {providerStats[provider].avgLatencyMs}ms · max {providerStats[provider].maxLatencyMs}ms
                        {rl.throttled429 > 0 && ` · ${rl.throttled429} throttle(s)`}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title="Providers" icon={<Check className="h-3 w-3" />}>
            {providers.length === 0 ? (
              <Empty>No providers registered.</Empty>
            ) : (
              <div className="space-y-1.5">
                {providers.map((p) => {
                  const h = health.persistedHealth?.find((r) => r.provider === p.id) as Record<string, unknown> | undefined;
                  return (
                    <div key={p.id} className="flex items-center gap-2 rounded-lg border border-white/10 glass-card-subtle px-3 py-1.5">
                      <span className={cn(
                        "rounded-md border px-1.5 py-0.5 text-[9px] uppercase tracking-wide",
                        p.implemented ? "border-emerald-400/20 text-emerald-400/90" : "border-white/10 text-muted-foreground",
                      )}>
                        {p.implemented ? "live" : "declared"}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-xs">{p.label}</span>
                      {p.streaming && <Radio className="h-3 w-3 text-sky-400/80" />}
                      <span className="hidden truncate text-[10px] text-muted-foreground md:block">
                        {p.capabilities.slice(0, 4).join(", ")}{p.capabilities.length > 4 ? "…" : ""}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        {p.configured === true ? "key ✓" : p.credentialRef ? "key ✗" : "keyless"}
                        {h && Number(h.failures) > 0 ? ` · ${h.failures} fail` : ""}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </Section>

          <Section title="Real-time stream" icon={<Radio className="h-3 w-3" />}>
            {!stream?.available ? (
              <Empty>{stream?.reason ?? "Streaming is not available."}</Empty>
            ) : (
              <div className="text-[10px] text-muted-foreground">
                <div className="flex flex-wrap gap-3">
                  <span>state: <span className="text-foreground/80">{stream.state}</span></span>
                  <span>provider: {stream.provider}</span>
                  <span>subscriptions: {stream.subscriptions?.length ?? 0}</span>
                  <span>events: {stream.metrics?.events ?? 0}</span>
                  <span>reconnects: {stream.metrics?.reconnects ?? 0}</span>
                  <span>deduped: {stream.metrics?.deduped ?? 0}</span>
                  <span>gaps: {stream.metrics?.sequenceGaps ?? 0}</span>
                </div>
                {(stream.subscriptions ?? []).map((s) => (
                  <div key={s.id} className="mt-1 inline-flex items-center gap-2 rounded border border-white/10 px-2 py-0.5">
                    <Timer className="h-3 w-3" /> {s.symbols.join(", ")} · {s.eventTypes.join("/")} · q{s.queueDepth}
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title="Recent data-quality findings" icon={<AlertCircle className="h-3 w-3" />}>
            {quality.length === 0 ? (
              <Empty>No quality findings recorded.</Empty>
            ) : (
              <div className="space-y-1">
                {quality.slice(0, 6).map((e) => (
                  <div key={e.id} className="flex items-start gap-2 text-[10px] text-muted-foreground">
                    <span className={cn("mt-0.5 rounded px-1", e.severity === "invalid" ? "bg-red-400/10 text-red-400/90" : "bg-amber-400/10 text-amber-400/90")}>
                      {e.kind}
                    </span>
                    <span className="truncate">{e.symbol} · {e.provider}: {e.detail}</span>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </>
      )}
    </Panel>
  );
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="mt-4">
      <p className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {icon} {title}
      </p>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div className="rounded-xl border border-white/10 glass-card-subtle px-3 py-2">
      <p className="text-[9px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn("mt-0.5 text-sm font-medium tabular-nums", tone === "warn" && "text-amber-400/90")}>{value}</p>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] text-muted-foreground/70">{children}</p>;
}
