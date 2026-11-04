"use client";

// High Alert band for the News tab.
//
// Shows the strongest market-moving stories (deterministic importance score)
// and upcoming high-impact macro releases. Each card explains WHY it was
// flagged and offers a compact "trade check" — signal, corroboration and what
// would invalidate the read. It is decision support, never a trade instruction.

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Bell,
  CheckCircle2,
  Clock,
  Sparkles,
} from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { NewsItem } from "./market-news";

export interface HighAlertItem extends NewsItem {
  importance: number;
  alertLevel: "critical" | "high" | "medium" | "low";
  importanceReasons: string[];
  isBreaking: boolean;
  confidence: "high" | "medium" | "low";
  direction: "bullish" | "bearish" | "neutral";
  horizon: "intraday" | "days" | "macro";
  invalidates: string[];
  affected: string[];
}

interface UpcomingEvent {
  id: string;
  title: string;
  country: string;
  date: string;
  minutesUntil: number;
  importance: "high" | "medium" | "low";
  forecast: string | null;
  previous: string | null;
}

interface NewsHighAlertsProps {
  watchlist: string[];
  portfolio: string[];
  active: boolean;
  /** Bump to force an immediate re-scan (manual refresh). */
  refreshKey?: number;
  onDiscuss?: (item: NewsItem) => void;
}

const LEVEL_STYLE: Record<
  HighAlertItem["alertLevel"],
  { label: string; badge: string; accent: string; glow: string }
> = {
  critical: {
    label: "CRITICAL",
    badge: "bg-rose-500/15 text-rose-300 border-rose-500/40",
    accent: "border-rose-500/30 dark:border-rose-500/20",
    glow: "bg-rose-500",
  },
  high: {
    label: "HIGH ALERT",
    badge: "bg-amber-400/15 text-amber-300 border-amber-400/40",
    accent: "border-amber-400/25 dark:border-amber-400/15",
    glow: "bg-amber-400",
  },
  medium: {
    label: "WATCH",
    badge: "bg-sky-400/10 text-sky-300 border-sky-400/30",
    accent: "border-sky-400/20",
    glow: "bg-sky-400",
  },
  low: {
    label: "LOW",
    badge: "bg-neutral-500/10 text-neutral-300 border-neutral-500/30",
    accent: "border-border/20",
    glow: "bg-neutral-400",
  },
};

function ageLabel(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "recent";
  const mins = Math.max(0, Math.floor((Date.now() - ts) / 60_000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function untilLabel(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

function directionLabel(d: HighAlertItem["direction"]): string {
  if (d === "bullish") return "Bullish bias";
  if (d === "bearish") return "Bearish bias";
  return "Neutral";
}

export function NewsHighAlerts({
  watchlist,
  portfolio,
  active,
  refreshKey = 0,
  onDiscuss,
}: NewsHighAlertsProps) {
  const [alerts, setAlerts] = useState<HighAlertItem[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [actingId, setActingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const watchKey = watchlist.join(",");
  const portfolioKey = portfolio.join(",");

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "5", hours: "24" });
      if (watchKey) params.set("tickers", watchKey);
      if (portfolioKey) params.set("portfolio", portfolioKey);
      const res = await fetch(`/api/news/alerts?${params.toString()}`, { cache: "no-store" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.error || `API ${res.status}`);
      setAlerts(Array.isArray(data.alerts) ? data.alerts : []);
      setUpcoming(Array.isArray(data.upcoming) ? data.upcoming : []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "High-alert scan unavailable");
    } finally {
      setLoading(false);
    }
  }, [watchKey, portfolioKey]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 60_000);
    return () => clearInterval(id);
  }, [active, load]);

  const setPriceAlert = async (item: HighAlertItem) => {
    if (!item.ticker) return;
    setActingId(item.id);
    setNotice(null);
    try {
      const direction = item.sentiment === "bearish" ? "down" : "up";
      const res = await fetch("/api/news/alert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker: item.ticker, direction, movePct: 2 }),
      });
      const data = await res.json().catch(() => ({}));
      setNotice(
        res.ok
          ? `Price watch created for ${item.ticker} (${direction} ≥ 2%).`
          : data?.error || "Could not create the price watch.",
      );
    } catch {
      setNotice("Could not create the price watch.");
    } finally {
      setActingId(null);
    }
  };

  if (loading) {
    return (
      <div className="w-full rounded-2xl border border-border/10 glass-card p-4">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] font-bold text-muted-foreground">
          <AlertTriangle size={12} className="text-amber-400" /> Scanning for high-alert news…
        </div>
      </div>
    );
  }

  if (error && alerts.length === 0 && upcoming.length === 0) {
    return (
      <div className="w-full rounded-2xl border border-border/10 glass-card-subtle px-4 py-3 text-[11px] font-mono text-muted-foreground">
        High-alert scan unavailable — {error}
      </div>
    );
  }

  if (alerts.length === 0 && upcoming.length === 0) return null;

  const nextEvent = upcoming[0];

  return (
    <section className="w-full space-y-3" aria-label="High alert news">
      <div className="flex items-center gap-2 px-1">
        <AlertTriangle size={14} className="text-amber-400" />
        <h2 className="text-[11px] font-bold uppercase tracking-[0.18em] text-foreground">
          High Alert
        </h2>
        <span className="text-[10px] font-mono text-muted-foreground">
          market-moving stories · deterministic, not advice
        </span>
      </div>

      {nextEvent && (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-400/[0.06] p-4 flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex items-center gap-2 shrink-0">
            <span className="flex size-8 items-center justify-center rounded-lg border border-amber-400/30 bg-amber-400/10">
              <Clock size={15} className="text-amber-300" />
            </span>
            <div>
              <p className="text-[9px] font-bold uppercase tracking-[0.16em] text-amber-300">
                High-impact release · {nextEvent.country}
              </p>
              <p className="text-xs font-semibold text-foreground">{nextEvent.title}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] text-muted-foreground sm:ml-auto">
            <span className="text-foreground font-bold">in {untilLabel(nextEvent.minutesUntil)}</span>
            {nextEvent.forecast && <span>forecast {nextEvent.forecast}</span>}
            {nextEvent.previous && <span>prev {nextEvent.previous}</span>}
            <span>Volatility often rises around this release.</span>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {alerts.map((item) => {
          const style = LEVEL_STYLE[item.alertLevel] ?? LEVEL_STYLE.high;
          const expanded = expandedId === item.id;
          return (
            <article
              key={item.id}
              className={cn(
                "relative overflow-hidden rounded-2xl border glass-card p-4 sm:p-5 transition-all",
                style.accent,
              )}
            >
              <div
                className={cn(
                  "pointer-events-none absolute -right-10 -top-12 size-40 rounded-full blur-[60px] opacity-20",
                  style.glow,
                )}
              />
              <div className="relative z-10 space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest",
                      style.badge,
                    )}
                  >
                    <span className={cn("size-1.5 rounded-full", style.glow)} /> {style.label}
                  </span>
                  {item.isBreaking && (
                    <span className="rounded-full border border-rose-500/40 bg-rose-500/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-rose-300">
                      Breaking
                    </span>
                  )}
                  <span className="text-[10px] font-mono text-muted-foreground">{item.source}</span>
                  <span className="text-[10px] font-mono text-muted-foreground">{ageLabel(item.timestamp)}</span>
                  <span className="ml-auto text-[10px] font-mono text-muted-foreground">
                    score {item.importance} · {item.confidence} confidence
                  </span>
                </div>

                <h3 className="text-sm sm:text-base font-semibold leading-snug text-foreground">
                  {item.url ? (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:text-primary transition-colors"
                    >
                      {item.headline}
                    </a>
                  ) : (
                    item.headline
                  )}
                </h3>

                {item.summary && (
                  <p className="text-[11px] leading-relaxed text-muted-foreground line-clamp-2">
                    {item.summary}
                  </p>
                )}

                <div className="flex flex-wrap items-center gap-1.5">
                  {item.importanceReasons.slice(0, 5).map((reason) => (
                    <span
                      key={reason}
                      className="rounded-md border border-border/40 bg-accent/40 px-2 py-0.5 text-[9px] font-mono text-muted-foreground"
                    >
                      {reason}
                    </span>
                  ))}
                  {(item.affected.length > 0 ? item.affected : item.ticker ? [item.ticker] : []).map((sym) => (
                    <span
                      key={sym}
                      className="rounded-md border border-primary/25 bg-primary/10 px-2 py-0.5 text-[9px] font-extrabold font-mono text-primary"
                    >
                      {sym}
                    </span>
                  ))}
                  {item.region && item.region !== "GLOBAL" && (
                    <span className="text-[9px] font-mono text-muted-foreground/70">{item.region}</span>
                  )}
                </div>

                {expanded && (
                  <div className="rounded-xl border border-border/30 bg-background/40 p-3 space-y-2.5">
                    <div className="flex items-center gap-1.5">
                      <AlertTriangle size={11} className="text-amber-400" />
                      <span className="text-[9px] font-bold uppercase tracking-[0.16em] text-foreground">
                        Trade check
                      </span>
                      <span className="text-[9px] font-mono text-muted-foreground">
                        signal, not advice
                      </span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono text-[10px]">
                      <div>
                        <span className="block text-[8px] uppercase tracking-wider text-muted-foreground">Bias</span>
                        <span className="text-foreground font-semibold">{directionLabel(item.direction)}</span>
                      </div>
                      <div>
                        <span className="block text-[8px] uppercase tracking-wider text-muted-foreground">Confidence</span>
                        <span className="text-foreground font-semibold capitalize">{item.confidence}</span>
                      </div>
                      <div>
                        <span className="block text-[8px] uppercase tracking-wider text-muted-foreground">Horizon</span>
                        <span className="text-foreground font-semibold capitalize">{item.horizon}</span>
                      </div>
                      <div>
                        <span className="block text-[8px] uppercase tracking-wider text-muted-foreground">Corroboration</span>
                        <span className="text-foreground font-semibold">{item.sourceCount ?? 1} source{(item.sourceCount ?? 1) > 1 ? "s" : ""}</span>
                      </div>
                    </div>
                    {item.invalidates.length > 0 && (
                      <p className="text-[10px] leading-relaxed text-muted-foreground">
                        <span className="font-bold text-foreground/80">What would change this: </span>
                        {item.invalidates[0]}
                      </p>
                    )}
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-2 border-t border-border/30 pt-3">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setExpandedId(expanded ? null : item.id)}
                    className="h-8 rounded-lg px-3 text-[11px] cursor-pointer"
                  >
                    {expanded ? "Hide check" : "Trade check"}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => setPriceAlert(item)}
                    disabled={!item.ticker || actingId === item.id}
                    title={item.ticker ? `Create a price watch for ${item.ticker}` : "No ticker resolved for this story"}
                    className="h-8 rounded-lg px-3 text-[11px] inline-flex items-center gap-1.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <Bell size={11} /> {item.ticker ? `Alert ${item.ticker}` : "No ticker"}
                  </Button>
                  {onDiscuss && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onDiscuss(item)}
                      className="h-8 rounded-lg px-3 text-[11px] inline-flex items-center gap-1.5 cursor-pointer"
                    >
                      <Sparkles size={11} /> Ask AI
                    </Button>
                  )}
                  {item.url && (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="h-8 inline-flex items-center gap-1 rounded-lg border border-border/40 px-3 text-[11px] font-semibold text-muted-foreground hover:text-foreground transition-colors"
                    >
                      Source <ArrowUpRight size={11} />
                    </a>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {notice && (
        <div className="flex items-center gap-1.5 px-1 text-[10px] font-mono text-muted-foreground">
          <CheckCircle2 size={11} className="text-emerald-400" /> {notice}
        </div>
      )}
    </section>
  );
}
