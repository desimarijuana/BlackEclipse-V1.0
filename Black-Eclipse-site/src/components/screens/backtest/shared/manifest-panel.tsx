'use client';

// ── Run manifest & reproduction ─────────────────────────────────────────────
// Shows the content-hashed record behind an experiment and can re-run it from
// that record. The browser computes nothing: it renders the runtime's verdict.

import React, { useCallback, useEffect, useState } from 'react';
import {
  backtestClient,
  type ReproduceResult,
  type RunManifest,
} from '@/lib/backtest/backtest-client';
import { Loader2, RefreshCw, ShieldCheck } from '@/lib/icons';

export interface ManifestPanelProps {
  experimentId: string | null;
  className?: string;
}

function shortHash(value?: string | null): string {
  if (!value) return '—';
  return value.length > 16 ? `${value.slice(0, 12)}…${value.slice(-4)}` : value;
}

export function ManifestPanel({ experimentId, className }: ManifestPanelProps) {
  const [manifest, setManifest] = useState<RunManifest | null>(null);
  const [repro, setRepro] = useState<ReproduceResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setManifest(null);
    setRepro(null);
    setError(null);
    if (!experimentId) return;
    let active = true;
    void backtestClient
      .getManifest(experimentId)
      .then((m) => active && setManifest(m))
      .catch((e: unknown) => active && setError(e instanceof Error ? e.message : 'manifest unavailable'));
    return () => { active = false; };
  }, [experimentId]);

  const reproduce = useCallback(async () => {
    if (!experimentId || busy) return;
    setBusy(true);
    setError(null);
    try {
      setRepro(await backtestClient.reproduce(experimentId));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'reproduction failed');
    } finally {
      setBusy(false);
    }
  }, [experimentId, busy]);

  if (!experimentId) return null;

  const bars = manifest?.data?.series
    ? Object.values(manifest.data.series).reduce((sum, s) => sum + (s.bars ?? 0), 0)
    : 0;

  return (
    <div className={`glass-card rounded-2xl p-4 ${className ?? ''}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-primary" />
        <h2 className="text-sm font-semibold">Reproducibility</h2>
        <span className="font-mono text-[10px] text-muted-foreground">
          manifest · data fingerprint · re-run
        </span>
        <button
          type="button"
          onClick={() => void reproduce()}
          disabled={busy}
          className="glass-card-subtle ml-auto inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
          Reproduce
        </button>
      </div>

      {error ? <p className="text-xs text-destructive">{error}</p> : null}

      {manifest ? (
        <div className="grid gap-2 text-[11px] sm:grid-cols-2">
          <Row label="Digest" value={shortHash(manifest.digest)} mono />
          <Row label="Engine" value={manifest.engineVersion ?? '—'} mono />
          <Row label="Code" value={shortHash(manifest.codeVersion)} mono />
          <Row label="Bars" value={String(bars)} mono />
          <Row
            label="Strategies"
            value={(manifest.strategies ?? []).map((s) => `${s.id ?? '?'}@${s.version ?? '?'}`).join(', ') || '—'}
          />
          <Row
            label="Symbols"
            value={(manifest.data?.symbols ?? []).join(', ') || '—'}
          />
        </div>
      ) : !error ? (
        <p className="text-xs text-muted-foreground">Loading manifest…</p>
      ) : null}

      {repro ? (
        <div
          className={`mt-3 rounded-xl border px-3 py-2 text-[11px] ${
            repro.verdict === 'REPRODUCED'
              ? 'border-emerald-500/30 bg-emerald-500/5 text-emerald-300'
              : 'border-amber-500/30 bg-amber-500/5 text-amber-300'
          }`}
        >
          <p className="font-semibold">{repro.verdict}</p>
          <p className="mt-0.5 opacity-80">
            {repro.comparison.compared} metrics compared ·{' '}
            {repro.comparison.differences.length} difference(s) · data fingerprint{' '}
            {repro.dataFingerprintMatch ? 'matched' : 'changed'}
          </p>
          {repro.comparison.differences.slice(0, 4).map((d) => (
            <p key={d.metric} className="mt-1 font-mono">
              {d.metric}: {String(d.expected)} → {String(d.actual)}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className={`truncate text-right ${mono ? 'font-mono' : ''}`} title={value}>{value}</span>
    </div>
  );
}
