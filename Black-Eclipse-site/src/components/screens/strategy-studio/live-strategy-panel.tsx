'use client';

// ── Live strategy trial (Strategy Studio) ───────────────────────────────────
// The governed bridge from a saved, approved strategy to the existing broker
// layer. The operator arms the live connection, creates a capped mandate, then
// runs one signal at a time. The broker stays the source of truth.

import React, { useCallback, useEffect, useState } from 'react';
import { backtestClient } from '@/lib/backtest/backtest-client';
import { listBrokerConnections, type BrokerConnection } from '@/lib/harness/clients/trading-client';
import { Loader2, Radio } from '@/lib/icons';

export interface LiveStrategyPanelProps {
  strategyId?: string;
  version?: string;
  symbol: string;
  onError?: (message: string | null) => void;
}

export function LiveStrategyPanel({ strategyId, version, symbol, onError }: LiveStrategyPanelProps) {
  const [connections, setConnections] = useState<BrokerConnection[]>([]);
  const [connectionId, setConnectionId] = useState('');
  const [maxMargin, setMaxMargin] = useState('500');
  const [maxOrders, setMaxOrders] = useState('5');
  const [ttlSeconds, setTtlSeconds] = useState('3600');
  const [volume, setVolume] = useState('0.01');
  const [stopPoints, setStopPoints] = useState('100');
  const [takePoints, setTakePoints] = useState('200');
  const [phrase, setPhrase] = useState('');
  const [trial, setTrial] = useState<Record<string, unknown> | null>(null);
  const [signal, setSignal] = useState<Record<string, unknown> | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    void listBrokerConnections()
      .then((rows) => {
        const live = rows.filter((row) => row.mode === 'live');
        setConnections(live);
        if (live[0]) setConnectionId(live[0].id);
      })
      .catch(() => setConnections([]));
  }, []);

  useEffect(() => {
    setPhrase(strategyId && version ? `LIVE TRIAL ${strategyId} ${version}` : '');
  }, [strategyId, version]);

  const run = useCallback(async (kind: string, work: () => Promise<void>) => {
    if (busy) return;
    setBusy(kind);
    onError?.(null);
    try { await work(); } catch (e) {
      onError?.(e instanceof Error ? e.message : `${kind} failed`);
    } finally { setBusy(null); }
  }, [busy, onError]);

  const prepare = useCallback(() => run('prepare', async () => {
    if (!strategyId || !version) throw new Error('save the strategy first');
    const row = await backtestClient.livePrepare({
      strategyId, version, connectionId,
      symbols: [symbol.toUpperCase()], timeframe: 'H1',
      volume: Number(volume),
      stopLossPoints: Number(stopPoints),
      takeProfitPoints: Number(takePoints),
      maxOrders: Number(maxOrders),
      maxMargin: Number(maxMargin), ttlSeconds: Number(ttlSeconds),
      confirmation: phrase,
      note: 'Strategy Studio live trial',
    });
    setTrial(row);
    setSignal(null);
    setResult(null);
  }), [connectionId, maxMargin, maxOrders, phrase, run, strategyId, symbol, ttlSeconds, version, volume]);

  const trialId = String(trial?.id ?? '');

  const checkSignal = useCallback(() => run('signal', async () => {
    if (!trialId) throw new Error('prepare a trial first');
    const body = await backtestClient.liveSignal(trialId, symbol.toUpperCase());
    setSignal(body.signal);
  }), [run, symbol, trialId]);

  const runOnce = useCallback(() => run('run', async () => {
    if (!trialId) throw new Error('prepare a trial first');
    const body = await backtestClient.liveRun(trialId, {
      symbol: symbol.toUpperCase(), volume: Number(volume),
    });
    setResult(body);
    if (body.signal) setSignal(body.signal as Record<string, unknown>);
  }), [run, symbol, trialId, volume]);

  const showResults = useCallback(() => run('results', async () => {
    if (!trialId) throw new Error('prepare a trial first');
    setResult(await backtestClient.liveResults(trialId));
  }), [run, trialId]);

  const stop = useCallback(() => run('stop', async () => {
    if (!trialId) throw new Error('prepare a trial first');
    const body = await backtestClient.liveStop(trialId);
    setTrial(body.trial);
  }), [run, trialId]);

  const approved = Boolean(strategyId && version);

  return (
    <div className="glass-card rounded-2xl p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Radio className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Live strategy trial</h2>
        <span className="font-mono text-[10px] text-muted-foreground">
          arm · mandate · signal · order · results
        </span>
      </div>

      {!approved ? (
        <p className="text-[11px] text-muted-foreground">
          Save and approve the strategy first. A live trial needs approved evidence and a recorded backtest.
        </p>
      ) : (
        <>
          <div className="mb-2 grid gap-2 sm:grid-cols-2">
            <label className="text-[11px] text-muted-foreground">
              Live connection
              <select
                value={connectionId}
                onChange={(event) => setConnectionId(event.target.value)}
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs"
              >
                <option value="">Select a live connection</option>
                {connections.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.label} · {row.armedUntil ? 'armed' : 'not armed'}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-[11px] text-muted-foreground">
              Volume
              <input value={volume} onChange={(e) => setVolume(e.target.value)}
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs" />
            </label>
            <label className="text-[11px] text-muted-foreground">
              Stop points
              <input value={stopPoints} onChange={(e) => setStopPoints(e.target.value)}
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs" />
            </label>
            <label className="text-[11px] text-muted-foreground">
              Take points
              <input value={takePoints} onChange={(e) => setTakePoints(e.target.value)}
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs" />
            </label>
            <label className="text-[11px] text-muted-foreground">
              Max margin
              <input value={maxMargin} onChange={(e) => setMaxMargin(e.target.value)}
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs" />
            </label>
            <label className="text-[11px] text-muted-foreground">
              Max orders
              <input value={maxOrders} onChange={(e) => setMaxOrders(e.target.value)}
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs" />
            </label>
            <label className="text-[11px] text-muted-foreground">
              TTL seconds
              <input value={ttlSeconds} onChange={(e) => setTtlSeconds(e.target.value)}
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs" />
            </label>
            <label className="text-[11px] text-muted-foreground">
              Confirmation phrase
              <input value={phrase} onChange={(e) => setPhrase(e.target.value)}
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-2 py-1.5 text-xs" />
            </label>
          </div>

          <div className="mb-2 flex flex-wrap gap-2">
            <button type="button" onClick={prepare} disabled={busy !== null || !connectionId}
              className="rounded-lg bg-primary/20 px-3 py-1.5 text-[11px] disabled:opacity-50">
              {busy === 'prepare' ? <Loader2 className="mr-1 inline h-3 w-3 animate-spin" /> : null}
              Prepare trial
            </button>
            <button type="button" onClick={checkSignal} disabled={busy !== null || !trialId}
              className="rounded-lg border border-white/10 px-3 py-1.5 text-[11px] disabled:opacity-50">
              Check signal
            </button>
            <button type="button" onClick={runOnce} disabled={busy !== null || !trialId}
              className="rounded-lg border border-white/10 px-3 py-1.5 text-[11px] disabled:opacity-50">
              Run once
            </button>
            <button type="button" onClick={showResults} disabled={busy !== null || !trialId}
              className="rounded-lg border border-white/10 px-3 py-1.5 text-[11px] disabled:opacity-50">
              Results
            </button>
            <button type="button" onClick={stop} disabled={busy !== null || !trialId}
              className="rounded-lg border border-red-400/30 px-3 py-1.5 text-[11px] text-red-300 disabled:opacity-50">
              Stop
            </button>
          </div>

          {trial ? (
            <p className="text-[10px] text-muted-foreground">
              {String(trial.status)} · mandate {String(trial.mandateId ?? '—')} · orders {String(trial.ordersUsed ?? 0)}
              /{String(trial.maxOrders ?? '—')}
            </p>
          ) : null}
          {signal ? (
            <p className="mt-1 text-[10px]">
              Signal: <span className="font-mono">{String(signal.signal)}</span> → {String(signal.action)}
              {' '}· {String(signal.reason ?? '')}
            </p>
          ) : null}
          {result ? (
            <p className="mt-1 text-[10px] text-muted-foreground">
              {String(result.message ?? '')}
              {result.openPnl !== undefined ? ` · open P&L ${String(result.openPnl)}` : ''}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
