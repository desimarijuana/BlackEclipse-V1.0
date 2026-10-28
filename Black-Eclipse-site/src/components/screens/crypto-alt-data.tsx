'use client';

// Crypto / on-chain / alt-data panel for the Market Overview crypto tab.
//
// Reads the SAME read-only front door the dashboard widgets use
// (`/api/crypto/alt-data` → the market adapters). Every card renders an honest
// UNAVAILABLE note when a provider/key is absent; nothing is invented.

import { useEffect, useState } from 'react';

type Alt = { status?: string; error?: string; [key: string]: unknown };

const fmt = (n?: number | null, d = 2) =>
  n == null || !Number.isFinite(n) ? '—' : n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });

const fmtUsd = (n?: number | null) => {
  if (n == null || !Number.isFinite(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
};

async function get(params: Record<string, string>): Promise<Alt> {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`/api/crypto/alt-data?${qs}`, { cache: 'no-store' });
  return (await res.json()) as Alt;
}

function Card({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl glass-card border border-white/10 dark:border-white/5 p-4 flex flex-col min-h-[180px]">
      <div className="flex items-center justify-between border-b border-border/10 pb-2 mb-2">
        <h3 className="font-serif text-sm font-semibold text-foreground">{title}</h3>
        {hint && <span className="font-mono text-[9px] text-muted-foreground/70">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="flex flex-1 items-center justify-center text-center text-xs text-muted-foreground/70 italic">{children}</p>;
}

const rowTone = (n: number) => (n > 0 ? 'text-emerald-400' : n < 0 ? 'text-rose-400' : 'text-muted-foreground');

function LiquidationsCard() {
  const [rows, setRows] = useState<Array<{ symbol: string; total: number | null; long: number | null; short: number | null }>>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    Promise.all(['BTC', 'ETH', 'SOL'].map(async (symbol) => {
      const d = await get({ capability: 'liquidations', symbol, exchange: 'Binance' });
      return { symbol, total: d.status === 'OK' && typeof d.totalUsd === 'number' ? d.totalUsd : null, long: d.status === 'OK' && typeof d.longUsd === 'number' ? d.longUsd : null, short: d.status === 'OK' && typeof d.shortUsd === 'number' ? d.shortUsd : null };
    })).then((next) => { if (alive) { setRows(next); setLoading(false); } }).catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  const ok = rows.filter((r) => r.total != null);
  return (
    <Card title="Liquidations" hint="24H · BINANCE">
      {loading ? <Note>Loading liquidations…</Note> : ok.length === 0 ? <Note>UNAVAILABLE — CoinGlass key not configured.</Note> : (
        <div className="flex flex-1 flex-col gap-2">
          {ok.map((r) => {
            const longPct = r.total && r.long != null ? (r.long / r.total) * 100 : 50;
            return (
              <div key={r.symbol}>
                <div className="flex items-center justify-between text-xs">
                  <span className="font-mono font-bold">{r.symbol}</span>
                  <span className="font-mono">{fmtUsd(r.total)}</span>
                </div>
                <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-accent/40">
                  <div className="h-full bg-emerald-400/70" style={{ width: `${Math.max(0, Math.min(100, longPct))}%` }} />
                </div>
                <div className="mt-0.5 flex justify-between font-mono text-[9px] text-muted-foreground">
                  <span className="text-emerald-400/80">L {fmtUsd(r.long)}</span>
                  <span className="text-rose-400/80">S {fmtUsd(r.short)}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

function LongShortCard() {
  const [rows, setRows] = useState<Array<{ symbol: string; longPercent: number | null; shortPercent: number | null; ratio: number | null }>>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    Promise.all(['BTC', 'ETH', 'SOL'].map(async (symbol) => {
      const d = await get({ capability: 'long_short', symbol, exchange: 'Binance', interval: '1h', limit: '1' });
      return { symbol, longPercent: d.status === 'OK' && typeof d.longPercent === 'number' ? d.longPercent : null, shortPercent: d.status === 'OK' && typeof d.shortPercent === 'number' ? d.shortPercent : null, ratio: d.status === 'OK' && typeof d.longShortRatio === 'number' ? d.longShortRatio : null };
    })).then((next) => { if (alive) { setRows(next); setLoading(false); } }).catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  const ok = rows.filter((r) => r.ratio != null);
  return (
    <Card title="Long / Short" hint="ACCOUNTS · 1H">
      {loading ? <Note>Loading long/short…</Note> : ok.length === 0 ? <Note>UNAVAILABLE — CoinGlass key not configured.</Note> : (
        <div className="flex flex-1 flex-col gap-2">
          {ok.map((r) => (
            <div key={r.symbol} className="flex items-center justify-between text-xs">
              <span className="font-mono font-bold">{r.symbol}</span>
              <span className="flex items-center gap-2 font-mono">
                <span className="text-emerald-400/80">{fmt(r.longPercent)}%</span>
                <span className="text-muted-foreground/50">/</span>
                <span className="text-rose-400/80">{fmt(r.shortPercent)}%</span>
                <span className={rowTone((r.ratio ?? 1) - 1)}>{fmt(r.ratio)}x</span>
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function TvlCard() {
  const [rows, setRows] = useState<Array<{ symbol: string; tvl: number | null; change: number | null }>>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    Promise.all(['AAVE', 'UNI', 'LDO', 'MKR', 'CRV', 'GMX'].map(async (symbol) => {
      const d = await get({ capability: 'tvl', symbol });
      return { symbol, tvl: d.status === 'OK' && typeof d.tvlUsd === 'number' ? d.tvlUsd : null, change: d.status === 'OK' && typeof d.change24hPct === 'number' ? d.change24hPct : null };
    })).then((next) => { if (alive) { setRows(next); setLoading(false); } }).catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  const ok = rows.filter((r) => r.tvl != null);
  return (
    <Card title="DeFi TVL" hint="DEFILLAMA">
      {loading ? <Note>Loading TVL…</Note> : ok.length === 0 ? <Note>UNAVAILABLE — DefiLlama did not answer.</Note> : (
        <div className="flex flex-1 flex-col gap-1">
          {ok.map((r) => (
            <div key={r.symbol} className="flex items-center justify-between text-xs py-0.5">
              <span className="font-mono font-bold">{r.symbol}</span>
              <span className="flex items-center gap-2 font-mono">
                <span>{fmtUsd(r.tvl)}</span>
                {r.change != null && <span className={`w-14 text-right ${rowTone(r.change)}`}>{r.change > 0 ? '+' : ''}{fmt(r.change)}%</span>}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export function CryptoAltData() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
      <LiquidationsCard />
      <LongShortCard />
      <TvlCard />
    </div>
  );
}
