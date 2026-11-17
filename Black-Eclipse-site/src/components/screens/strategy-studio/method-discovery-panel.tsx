'use client';

// ── Method discovery (Strategy Studio) ──────────────────────────────────────
// The front of the funnel: find a method the user understands, scan the actual
// data, turn it into a spec, mine parameterizations, and check whether a setup
// exists right now. Every candidate is labelled as a candidate — evidence still
// has to clear the research gates.

import React, { useCallback, useState } from 'react';
import {
  backtestClient,
  type CurrentSetups,
  type MarketStructure,
  type MethodRecommendation,
  type MineResult,
} from '@/lib/backtest/backtest-client';
import { FlaskConical, Loader2, RefreshCw } from '@/lib/icons';

function inferAsset(symbol: string): string {
  const s = symbol.toUpperCase();
  if (/USDT|USDC|BTC|ETH|SOL|-USD$/.test(s)) return 'crypto';
  if (/^[A-Z]{6}$/.test(s)) return 'fx';
  if (/=F$/.test(s)) return 'futures';
  return 'equities';
}

export interface MethodDiscoveryPanelProps {
  symbol: string;
  symbols?: string[];
  interval: string;
  onUseSpec: (specText: string) => void;
  onError?: (message: string | null) => void;
}

export function MethodDiscoveryPanel({ symbol, symbols, interval, onUseSpec, onError }: MethodDiscoveryPanelProps) {
  const [assetClass, setAssetClass] = useState(() => inferAsset(symbol));
  const [horizon, setHorizon] = useState('swing');
  const [objective, setObjective] = useState('growth');
  const [risk, setRisk] = useState('medium');
  const [recs, setRecs] = useState<MethodRecommendation[]>([]);
  const [structure, setStructure] = useState<MarketStructure | null>(null);
  const [setups, setSetups] = useState<CurrentSetups | null>(null);
  const [mined, setMined] = useState<MineResult | null>(null);
  const [playbook, setPlaybook] = useState<Record<string, unknown> | null>(null);
  const [universe, setUniverse] = useState<Awaited<ReturnType<typeof backtestClient.universeSetups>> | null>(null);
  const [universeMine, setUniverseMine] = useState<Awaited<ReturnType<typeof backtestClient.mineUniverse>> | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const run = useCallback(async (kind: string, work: () => Promise<void>) => {
    if (busy) return;
    setBusy(kind);
    onError?.(null);
    try { await work(); } catch (e) {
      onError?.(e instanceof Error ? e.message : `${kind} failed`);
    } finally { setBusy(null); }
  }, [busy, onError]);

  const recommend = useCallback(() => run('recommend', async () => {
    const result = await backtestClient.recommendMethods({
      assetClass, horizon, objective, riskTolerance: risk,
      symbol, interval, allowShort: true,
    });
    setRecs(result.recommendations);
  }), [run, assetClass, horizon, objective, risk, symbol, interval]);

  const scan = useCallback(() => run('scan', async () => {
    setStructure(await backtestClient.scanStructure({ symbol, interval }));
  }), [run, symbol, interval]);

  const scanSetups = useCallback(() => run('setups', async () => {
    setSetups(await backtestClient.currentSetups({ symbol, interval }));
  }), [run, symbol, interval]);

  const scanWatchlist = useCallback(() => run('universe', async () => {
    const list = (symbols?.length ? symbols : [symbol]).map((s) => s.toUpperCase());
    setUniverse(await backtestClient.universeSetups({ symbols: list, interval }));
  }), [run, symbols, symbol, interval]);

  const mineAcross = useCallback(() => run('mine-universe', async () => {
    const list = (symbols?.length ? symbols : [symbol]).map((s) => s.toUpperCase());
    setUniverseMine(await backtestClient.mineUniverse({
      symbols: list, interval, maxTrials: 6,
    }));
  }), [run, symbols, symbol, interval]);

  const mine = useCallback(() => run('mine', async () => {
    setMined(await backtestClient.mineMethods({
      symbol, interval, maxTrials: 12, oosFraction: 0.3,
    }));
  }), [run, symbol, interval]);

  const showPlaybook = useCallback((methodId: string) => run(`play:${methodId}`, async () => {
    const result = await backtestClient.tradingPlaybook({ methodId, symbol, interval });
    setPlaybook(result.playbook);
  }), [run, symbol, interval]);

  const applyMethod = useCallback((methodId: string) => run(`use:${methodId}`, async () => {
    const result = await backtestClient.synthesizeMethod({ methodId, symbol, interval });
    if (!result.valid) {
      throw new Error(result.issues.map((i) => i.message).join('; ') || 'the method did not validate');
    }
    onUseSpec(JSON.stringify(result.spec, null, 2));
  }), [run, symbol, interval, onUseSpec]);

  return (
    <div className="glass-card rounded-2xl p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <FlaskConical className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Method discovery</h2>
        <span className="font-mono text-[10px] text-muted-foreground">
          find · adapt · invent · scan
        </span>
      </div>

      <div className="grid gap-2 sm:grid-cols-4">
        <Select label="Asset" value={assetClass} onChange={setAssetClass}
          options={['equities', 'fx', 'crypto', 'futures', 'options']} />
        <Select label="Horizon" value={horizon} onChange={setHorizon}
          options={['intraday', 'swing', 'position', 'long-term']} />
        <Select label="Objective" value={objective} onChange={setObjective}
          options={['growth', 'income', 'preservation', 'diversification']} />
        <Select label="Risk" value={risk} onChange={setRisk}
          options={['low', 'medium', 'high']} />
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        <Action onClick={recommend} busy={busy === 'recommend'} label="Recommend methods" />
        <Action onClick={scan} busy={busy === 'scan'} label="Scan this series" />
        <Action onClick={scanSetups} busy={busy === 'setups'} label="Setups now" />
        {(symbols?.length ?? 0) > 1 ? (
          <Action onClick={scanWatchlist} busy={busy === 'universe'} label="Scan watchlist" />
        ) : null}
        <Action onClick={mine} busy={busy === 'mine'} label="Mine candidates" />
        {(symbols?.length ?? 0) > 1 ? (
          <Action onClick={mineAcross} busy={busy === 'mine-universe'} label="Mine universe" />
        ) : null}
      </div>

      {recs.length > 0 ? (
        <div className="mt-3 space-y-1.5">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Method fit — a prior, not an edge
          </p>
          {recs.map((r) => (
            <div key={r.methodId} className="rounded-xl border border-white/5 bg-black/10 px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium">{r.name}</span>
                <span className="font-mono text-[10px] text-muted-foreground">{r.fitPercent}%</span>
                <span className="rounded-full border border-white/10 px-1.5 py-0.5 text-[9px] text-muted-foreground">
                  {r.category}
                </span>
                {r.requires.length ? (
                  <span className="text-[9px] text-amber-300">needs {r.requires.join(', ')}</span>
                ) : (
                  <button type="button" onClick={() => void applyMethod(r.methodId)}
                    disabled={Boolean(busy)}
                    className="glass-card-subtle ml-auto rounded-lg px-2 py-0.5 text-[10px] disabled:opacity-50">
                    Use spec
                  </button>
                )}
                <button type="button" onClick={() => void showPlaybook(r.methodId)}
                  disabled={Boolean(busy)}
                  className="rounded-lg px-1.5 py-0.5 text-[10px] text-muted-foreground disabled:opacity-50">
                  playbook
                </button>
                <button type="button"
                  onClick={() => setExpanded(expanded === r.methodId ? null : r.methodId)}
                  className="rounded-lg px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  why
                </button>
              </div>
              {expanded === r.methodId ? (
                <div className="mt-1.5 space-y-0.5 text-[10px] text-muted-foreground">
                  {r.reasons.map((x) => <p key={x}>+ {x}</p>)}
                  {r.warnings.map((x) => <p key={x} className="text-amber-300/80">! {x}</p>)}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {universeMine ? (
        <div className="mt-3 rounded-xl border border-white/5 bg-black/10 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Universe mine · {universeMine.perSymbol.length} symbols ·{' '}
            {universeMine.failures.length} failed
          </p>
          {universeMine.rankedMethods.length ? (
            <ul className="mt-1 space-y-0.5 text-[10px]">
              {universeMine.rankedMethods.slice(0, 6).map((r) => (
                <li key={r.methodId} className="font-mono">
                  {r.methodId} · {r.support}/{universeMine.perSymbol.length} symbols ·
                  OOS {r.meanOosSharpe === null ? '—' : r.meanOosSharpe.toFixed(2)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-[11px] text-muted-foreground">No method survived across the universe.</p>
          )}
          <p className="mt-1 text-[9px] text-muted-foreground">{universeMine.note}</p>
        </div>
      ) : null}

      {universe ? (
        <div className="mt-3 rounded-xl border border-white/5 bg-black/10 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Watchlist scan · {universe.activeCount} setup(s) across {universe.symbolsWithSetups} of{' '}
            {universe.symbols.length} symbols
          </p>
          {universe.active.length ? (
            <ul className="mt-1 space-y-0.5 font-mono text-[10px]">
              {universe.active.slice(0, 12).map((s) => (
                <li key={`${s.symbol}:${s.methodId}`}>
                  {s.symbol} · {s.methodId} · {s.direction}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-[11px] text-muted-foreground">No active entry conditions.</p>
          )}
          {universe.failures.length ? (
            <p className="mt-1 text-[9px] text-amber-300">
              {universe.failures.length} symbol(s) could not be scanned.
            </p>
          ) : null}
          <p className="mt-1 text-[9px] text-muted-foreground">{universe.note}</p>
        </div>
      ) : null}

      {playbook ? (
        <div className="mt-3 rounded-xl border border-primary/20 bg-primary/5 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Playbook — {String(playbook.name)} on {String(playbook.symbol)}
          </p>
          <div className="mt-1 grid gap-1 text-[10px] sm:grid-cols-2">
            <div>
              <p className="text-muted-foreground">Entry</p>
              {(playbook.entry as string[] | undefined)?.map((x) => <p key={x}>• {x}</p>)}
            </div>
            <div>
              <p className="text-muted-foreground">Exit</p>
              {(playbook.exit as string[] | undefined)?.map((x) => <p key={x}>• {x}</p>)}
            </div>
            <div>
              <p className="text-muted-foreground">Sizing</p>
              <p>{String(playbook.positionSizing)}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Fails when</p>
              {(playbook.whenItFails as string[] | undefined)?.slice(0, 3).map((x) => <p key={x}>• {x}</p>)}
            </div>
          </div>
          <p className="mt-1 text-[9px] text-muted-foreground">{String(playbook.disclaimer)}</p>
        </div>
      ) : null}

      {structure ? (
        <div className="mt-3 rounded-xl border border-white/5 bg-black/10 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            {symbol} · {interval} structure
          </p>
          <p className="mt-0.5 text-xs font-medium">{structure.structure.replace(/_/g, ' ')}</p>
          <div className="mt-1 space-y-0.5 text-[10px] text-muted-foreground">
            {structure.insights.map((x) => <p key={x}>• {x}</p>)}
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground">
            candidates: {structure.candidateMethods.map((c) => c.methodId).join(', ')}
          </p>
        </div>
      ) : null}

      {setups ? (
        <div className="mt-3 rounded-xl border border-white/5 bg-black/10 px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Setups on the latest closed bar
          </p>
          {setups.active.length ? (
            <ul className="mt-1 space-y-0.5 text-[11px]">
              {setups.active.map((s) => (
                <li key={String(s.methodId)}>
                  {String(s.name ?? s.methodId)} — <span className="font-mono">{String(s.direction)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-[11px] text-muted-foreground">No active entry condition.</p>
          )}
          <p className="mt-1 text-[9px] text-muted-foreground">
            A setup is a condition, not an order or a recommendation.
          </p>
        </div>
      ) : null}

      {mined ? (
        <div className="mt-3 rounded-xl border border-white/5 bg-black/10 px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Bounded search · {mined.trialCount} trials
            </p>
            <span className="font-mono text-[10px] text-muted-foreground">
              {mined.isBars} IS / {mined.oosBars} OOS
            </span>
            {mined.deflatedSharpe?.available ? (
              <span className="font-mono text-[10px] text-muted-foreground">
                DSR {mined.deflatedSharpe.deflatedSharpeRatio?.toFixed(3)}
              </span>
            ) : null}
          </div>
          {mined.selected ? (
            <p className="mt-1 text-[11px]">
              Selected <strong>{mined.selected.name ?? mined.selected.methodId}</strong>{' '}
              <span className="font-mono text-[10px] text-muted-foreground">
                OOS Sharpe {String(mined.selected.outOfSample?.sharpe ?? '—')}
              </span>
              <button type="button" onClick={() => void applyMethod(mined.selected!.methodId)}
                className="glass-card-subtle ml-2 rounded-lg px-2 py-0.5 text-[10px]">
                Use spec
              </button>
            </p>
          ) : (
            <p className="mt-1 text-[11px] text-amber-300">No candidate survived the OOS split.</p>
          )}
          <p className="mt-1 text-[9px] text-muted-foreground">
            A candidate is not a validated strategy. Run walk-forward and robustness next.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function Select({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void; options: string[];
}) {
  return (
    <label className="block text-[10px] text-muted-foreground">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="glass-card-subtle mt-0.5 w-full rounded-lg px-2 py-1 text-xs">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  );
}

function Action({ onClick, busy, label }: { onClick: () => void; busy: boolean; label: string }) {
  return (
    <button type="button" onClick={onClick} disabled={busy}
      className="glass-card-subtle inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] disabled:opacity-50">
      {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
      {label}
    </button>
  );
}
