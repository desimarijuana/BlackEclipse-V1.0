'use client';

import { useEffect, useState } from 'react';
import { SlidersHorizontal, RefreshCw, Globe, Timer, Activity } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TopLoader } from '@/components/ui/top-loader';
import { cn } from '@/lib/utils';

interface SourceHealth {
  source: string;
  market: string;
  _sum: { successCount: number; failCount: number };
  _max: { lastStatus: string };
}

interface NewsFeedHealth {
  id: string;
  source: string;
  category?: string;
  tier?: number;
  enabled: boolean;
  health: {
    status: 'ok' | 'error';
    lastError?: string;
    lastOkAt?: string;
    lastErrorAt?: string;
    durationMs?: number;
    consecutiveFails?: number;
  } | null;
}

interface NewsStatus {
  enabled: boolean;
  intervalMinutes: number;
  lastRunAt: string | null;
  totalItems: number;
  newestItemAt: string | null;
  feeds: NewsFeedHealth[];
  failing: number;
}

interface ScraperStatus {
  markets: string[];
  intervalMinutes: number;
  enabled: boolean;
  mode?: 'auto' | 'off' | 'manual';
  pageSize?: number;
  lastRunAt: string | null;
  nextRunAt: string | null;
  sourceHealth: SourceHealth[];
}

const ALL_MARKETS = [
  { id: 'US', label: 'United States' },
  { id: 'PK', label: 'Pakistan' },
  { id: 'IN', label: 'India' },
  { id: 'CRYPTO', label: 'Crypto' },
];

const INTERVALS = [5, 15, 30, 60];

export function DataSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [status, setStatus] = useState<ScraperStatus | null>(null);
  const [newsStatus, setNewsStatus] = useState<NewsStatus | null>(null);
  const [showFailing, setShowFailing] = useState(false);
  const [markets, setMarkets] = useState<string[]>(['US']);
  const [intervalMinutes, setIntervalMinutes] = useState(15);
  const [message, setMessage] = useState<string | null>(null);

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/scraper');
      const data = await res.json();
      if (data.markets) {
        setMarkets(data.markets);
        setIntervalMinutes(data.intervalMinutes || 15);
      }
      setStatus(data);
    } catch (err) {
      console.error('Failed to load scraper status', err);
    } finally {
      setLoading(false);
    }
    try {
      const nres = await fetch('/api/news/status');
      const ndata = await nres.json();
      if (!ndata.error) setNewsStatus(ndata);
    } catch { /* best-effort */ }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const toggleMarket = (id: string) => {
    setMarkets((prev) =>
      prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id]
    );
  };

  const saveConfig = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const res = await fetch('/api/cron', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intervalMinutes, markets }),
      });
      const data = await res.json();
      if (res.ok) {
        setMessage('Configuration saved. price_scraper is refreshing data...');
        await fetchStatus();
      } else {
        setMessage(data.error || 'Failed to save');
      }
    } catch {
      setMessage('Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const triggerNow = async () => {
    setTriggering(true);
    setMessage(null);
    try {
      await fetch('/api/scraper', { method: 'POST' });
      setMessage('Scrape triggered. Refreshing status...');
      setTimeout(fetchStatus, 2000);
    } catch {
      setMessage('Failed to trigger scrape');
    } finally {
      setTriggering(false);
    }
  };

  if (loading) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 md:px-8 py-8">
        <TopLoader />
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-64 rounded-lg bg-muted/20" />
          <div className="h-32 w-full rounded-2xl bg-muted/10" />
          <div className="h-32 w-full rounded-2xl bg-muted/10" />
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-4xl mx-auto px-4 md:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-border/10 pb-4">
        <SlidersHorizontal className="text-primary w-6 h-6" />
        <div>
          <h1 className="font-serif text-2xl font-semibold tracking-tight text-foreground">Data Settings</h1>
          <p className="text-muted-foreground text-xs mt-0.5">
            Configure which markets price_scraper crawls and how often prices refresh. Scraper mode is controlled from the Market Screener toolbar.
          </p>
        </div>
      </div>

      {/* Market selection */}
      <div className="rounded-2xl border border-border/10 bg-card/40 p-5">
        <div className="flex items-center gap-2 mb-4">
          <Globe className="text-primary w-4 h-4" />
          <h2 className="text-sm font-semibold text-foreground">Markets to Scrape</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {ALL_MARKETS.map((m) => {
            const active = markets.includes(m.id);
            return (
              <button
                key={m.id}
                onClick={() => toggleMarket(m.id)}
                className={cn(
                  'px-4 py-2 rounded-xl text-xs font-medium border transition-all cursor-pointer',
                  active
                    ? 'bg-accent text-foreground border-border/40'
                    : 'bg-transparent text-muted-foreground border-border hover:text-foreground'
                )}
              >
                {m.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Refresh interval */}
      <div className="rounded-2xl border border-border/10 bg-card/40 p-5">
        <div className="flex items-center gap-2 mb-4">
          <Timer className="text-primary w-4 h-4" />
          <h2 className="text-sm font-semibold text-foreground">Refresh Interval</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {INTERVALS.map((m) => (
            <button
              key={m}
              onClick={() => setIntervalMinutes(m)}
              className={cn(
                'px-4 py-2 rounded-xl text-xs font-medium border transition-all cursor-pointer',
                intervalMinutes === m
                  ? 'bg-accent text-foreground border-border/40'
                  : 'bg-transparent text-muted-foreground border-border hover:text-foreground'
              )}
            >
              Every {m} min
            </button>
          ))}
        </div>
      </div>

      {/* Source health */}
      {status?.sourceHealth && status.sourceHealth.length > 0 && (
        <div className="rounded-2xl border border-border/10 bg-card/40 p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="text-primary w-4 h-4" />
            <h2 className="text-sm font-semibold text-foreground">Source Health</h2>
          </div>
          <div className="space-y-2">
            {status.sourceHealth.map((h) => (
              <div key={`${h.source}-${h.market}`} className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground font-mono">
                  {h.source} · {h.market}
                </span>
                <span className="flex items-center gap-2">
                  <span className="text-muted-foreground">
                    {h._sum.successCount}✓ / {h._sum.failCount}✗
                  </span>
                  <span
                    className={cn(
                      'px-2 py-0.5 rounded-full text-[10px]',
                      h._max.lastStatus === 'ok'
                        ? 'bg-emerald-500/15 text-emerald-400'
                        : 'bg-rose-500/15 text-rose-400'
                    )}
                  >
                    {h._max.lastStatus}
                  </span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* News ingestion health */}
      {newsStatus && (
        <div className="rounded-2xl border border-border/10 bg-card/40 p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="text-primary w-4 h-4" />
            <h2 className="text-sm font-semibold text-foreground">News Ingestion</h2>
            <span className={cn(
              'ml-auto px-2 py-0.5 rounded-full text-[10px] font-bold border',
              newsStatus.failing > 0
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            )}>
              {newsStatus.failing > 0 ? `${newsStatus.failing} feeds failing` : 'All feeds healthy'}
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 text-center">
            <div className="p-2.5 rounded-xl bg-accent/20 border border-border/20">
              <p className="text-lg font-bold font-mono text-foreground">{newsStatus.totalItems}</p>
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">articles stored</p>
            </div>
            <div className="p-2.5 rounded-xl bg-accent/20 border border-border/20">
              <p className="text-lg font-bold font-mono text-foreground">
                {newsStatus.feeds.filter((f) => f.health?.status === 'ok').length}/{newsStatus.feeds.length}
              </p>
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">feeds ok</p>
            </div>
            <div className="p-2.5 rounded-xl bg-accent/20 border border-border/20">
              <p className="text-sm font-bold font-mono text-foreground">
                {newsStatus.lastRunAt ? new Date(newsStatus.lastRunAt).toLocaleTimeString() : '—'}
              </p>
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">last ingest</p>
            </div>
            <div className="p-2.5 rounded-xl bg-accent/20 border border-border/20">
              <p className="text-sm font-bold font-mono text-foreground">
                {newsStatus.newestItemAt ? new Date(newsStatus.newestItemAt).toLocaleTimeString() : '—'}
              </p>
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">newest item</p>
            </div>
          </div>
          {newsStatus.failing > 0 && (
            <div>
              <button
                onClick={() => setShowFailing((v) => !v)}
                className="text-[11px] font-bold text-rose-400 hover:text-rose-300 cursor-pointer mb-2"
              >
                {showFailing ? 'Hide' : 'Show'} failing feeds ({newsStatus.failing})
              </button>
              {showFailing && (
                <div className="space-y-1.5">
                  {newsStatus.feeds
                    .filter((f) => f.health?.status === 'error' && (f.health.consecutiveFails ?? 0) >= 3)
                    .map((f) => (
                      <div key={f.id} className="flex items-center justify-between gap-3 text-[11px] font-mono p-2 rounded-lg bg-rose-500/5 border border-rose-500/15">
                        <span className="text-foreground font-bold">{f.source} <span className="text-muted-foreground">T{f.tier ?? '?'}</span></span>
                        <span className="text-rose-400 truncate max-w-[60%]" title={f.health?.lastError}>
                          {f.health?.lastError?.slice(0, 80)} ({f.health?.consecutiveFails}× fails)
                        </span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Status + actions */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="text-xs text-muted-foreground flex items-center gap-3 flex-wrap">
          <span className={cn(
            'px-2 py-0.5 rounded-full text-[10px] font-bold border',
            status?.mode === 'off'
              ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
              : status?.mode === 'manual'
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
          )}>
            {status?.mode === 'off' ? 'Scraper Off' : status?.mode === 'manual' ? 'Manual Mode' : 'Scraper On'}
          </span>
          {status?.pageSize && (
            <span className="px-2 py-0.5 rounded-full bg-accent/20 border border-border/30 font-mono">
              {status.pageSize} stocks/page
            </span>
          )}
          {status?.lastRunAt ? (
            <span>Last run: {new Date(status.lastRunAt).toLocaleTimeString()}</span>
          ) : (
            <span>No scrape run yet</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={triggerNow}
            disabled={triggering}
            className="cursor-pointer"
          >
            <RefreshCw className={cn('w-4 h-4 mr-1', triggering && 'animate-spin')} />
            Refresh Now
          </Button>
          <Button size="sm" onClick={saveConfig} disabled={saving} className="cursor-pointer">
            {saving ? 'Saving...' : 'Save Configuration'}
          </Button>
        </div>
      </div>

      {message && (
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs text-emerald-400">
          {message}
        </div>
      )}
    </div>
  );
}
