'use client';

// ── Crypto on-chain / alt-data widgets ───────────────────────────────────────
// These read the SAME read-only front door the agent's adapters use
// (`/api/crypto/alt-data`). An UNAVAILABLE envelope renders as an honest note,
// never as a zero. Kept in their own module so `widgets.tsx` stays within the
// source-size budget.

import React, { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

type AltDataResult = { status?: string; error?: string; [key: string]: unknown };

const tone = (n: number) => (n > 0 ? 'text-emerald-400' : n < 0 ? 'text-rose-400' : 'text-muted-foreground');
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

function WidgetHeader({ title, hint }: { title: string; hint?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
      <h3 className="font-serif text-sm font-semibold text-foreground truncate">{title}</h3>
      {hint && <span className="font-mono text-[9px] text-muted-foreground/70 shrink-0">{hint}</span>}
    </div>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-1 items-center justify-center py-8 text-center">
      <p className="text-xs text-muted-foreground/70 italic">{children}</p>
    </div>
  );
}

const TVL_PROTOCOLS = ['AAVE', 'UNI', 'LDO', 'MKR', 'CRV', 'GMX'];

export function CryptoTvlWidget() {
  const [rows, setRows] = useState<Array<{ symbol: string; tvlUsd: number | null; change?: number | null }>>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    Promise.all(
      TVL_PROTOCOLS.map(async (symbol) => {
        const res = await fetch(`/api/crypto/alt-data?capability=tvl&symbol=${symbol}`, { cache: 'no-store' });
        const data = (await res.json()) as AltDataResult;
        const ok = data.status === 'OK';
        return {
          symbol,
          tvlUsd: ok && typeof data.tvlUsd === 'number' ? data.tvlUsd : null,
          change: ok && typeof data.change24hPct === 'number' ? data.change24hPct : null,
        };
      }),
    )
      .then((next) => { if (alive) { setRows(next); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  const answered = rows.filter((r) => r.tvlUsd != null);
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="DeFi TVL" hint="DEFILLAMA" />
      {loading ? <EmptyNote>Loading TVL…</EmptyNote> : answered.length === 0 ? (
        <EmptyNote>TVL unavailable — no protocol answered.</EmptyNote>
      ) : (
        <div className="flex flex-1 flex-col gap-1">
          {answered.map((r) => (
            <div key={r.symbol} className="flex items-center justify-between text-xs py-0.5">
              <span className="font-mono font-bold text-foreground">{r.symbol}</span>
              <span className="flex items-center gap-2">
                <span className="font-mono text-foreground">{fmtUsd(r.tvlUsd)}</span>
                {r.change != null && (
                  <span className={cn('font-mono w-14 text-right', tone(r.change))}>
                    {r.change > 0 ? '+' : ''}{fmt(r.change)}%
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const LIQ_COINS = ['BTC', 'ETH', 'SOL'];

export function CryptoLiquidationsWidget() {
  const [rows, setRows] = useState<Array<{ symbol: string; total: number | null; long: number | null; short: number | null }>>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    Promise.all(
      LIQ_COINS.map(async (symbol) => {
        const res = await fetch(`/api/crypto/alt-data?capability=liquidations&symbol=${symbol}&exchange=Binance`, { cache: 'no-store' });
        const data = (await res.json()) as AltDataResult;
        const ok = data.status === 'OK';
        return {
          symbol,
          total: ok && typeof data.totalUsd === 'number' ? data.totalUsd : null,
          long: ok && typeof data.longUsd === 'number' ? data.longUsd : null,
          short: ok && typeof data.shortUsd === 'number' ? data.shortUsd : null,
        };
      }),
    )
      .then((next) => { if (alive) { setRows(next); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  const answered = rows.filter((r) => r.total != null);
  return (
    <div className="flex h-full flex-col p-4">
      <WidgetHeader title="Liquidations" hint="24H · BINANCE" />
      {loading ? <EmptyNote>Loading liquidations…</EmptyNote> : answered.length === 0 ? (
        <EmptyNote>Liquidations unavailable — CoinGlass key not configured.</EmptyNote>
      ) : (
        <div className="flex flex-1 flex-col gap-1.5">
          {answered.map((r) => {
            const longPct = r.total && r.long != null ? (r.long / r.total) * 100 : 50;
            return (
              <div key={r.symbol} className="text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-foreground">{r.symbol}</span>
                  <span className="font-mono text-foreground">{fmtUsd(r.total)}</span>
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
    </div>
  );
}
