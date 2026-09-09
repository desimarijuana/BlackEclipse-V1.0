'use client';

// ── CSV Import — parse a trade CSV and bulk-import into the journal ──────────
// Expected columns (case-insensitive): symbol, direction, entry, exit, stopLoss,
// takeProfit, quantity, entryTime, exitTime, session, timeframe, emotion,
// confidence, notes. entryTime/exitTime accept ISO or "YYYY-MM-DD HH:MM".

import React, { useRef, useState } from 'react';
import { Upload, Loader2, X, Check } from 'lucide-react';

interface CsvImportProps {
  onImported: () => void;
}

export function CsvImport({ onImported }: CsvImportProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<{ imported: number; errors: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setImporting(true);
    setError(null);
    setResult(null);
    try {
      const text = await file.text();
      const parsed = parseCsv(text);
      const rows = parsed.map(mapRow).filter((r): r is NonNullable<ReturnType<typeof mapRow>> => r !== null);
      if (rows.length === 0) {
        setError('No valid rows found in the CSV.');
        return;
      }
      const res = await fetch('/api/journal/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Import failed');
      setResult({ imported: data.imported ?? 0, errors: data.errors ?? [] });
      onImported();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to import');
    } finally {
      setImporting(false);
    }
  };

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-accent/30 px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary hover:border-primary/40 transition-all cursor-pointer"
      >
        {open ? <X size={13} /> : <Upload size={13} />} {open ? 'Close' : 'Import CSV'}
      </button>

      {open && (
        <div className="mt-3 rounded-2xl bg-[#0f0f0f]/60 p-4">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.txt"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleFile(f); e.target.value = ''; }}
          />
          <div className="flex items-center gap-3">
            <button
              onClick={() => fileRef.current?.click()}
              disabled={importing}
              className="inline-flex items-center gap-1.5 rounded-lg border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
            >
              {importing ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
              {importing ? 'Importing…' : 'Choose CSV file'}
            </button>
            <span className="text-[10px] text-muted-foreground font-mono">symbol, direction, entry, exit, stopLoss, takeProfit, quantity, entryTime, exitTime, session, timeframe, emotion, confidence, notes</span>
          </div>

          {error && <p className="mt-3 text-xs text-rose-400 font-semibold">{error}</p>}
          {result && (
            <div className="mt-3 rounded-lg bg-white/[0.03] p-3">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-emerald-400">
                <Check size={13} /> Imported {result.imported} trade{result.imported === 1 ? '' : 's'}.
              </p>
              {result.errors.length > 0 && (
                <div className="mt-2 max-h-32 overflow-y-auto">
                  {result.errors.map((e, i) => (
                    <p key={i} className="text-[10px] text-rose-400/80 font-mono">{e}</p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Parse a CSV string into CreateTradeInput rows. */
function parseCsv(text: string): Record<string, string>[] {
  const lines = text.trim().split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) return [];
  const header = lines[0].split(',').map((h) => h.trim().toLowerCase().replace(/^"|"$/g, ''));
  const rows: Record<string, string>[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cells = parseCsvLine(lines[i]);
    const rec: Record<string, string> = {};
    header.forEach((h, idx) => { rec[h] = (cells[idx] ?? '').trim(); });
    rows.push(rec);
  }
  return rows;
}

/** Parse a single CSV line handling quoted fields. */
function parseCsvLine(line: string): string[] {
  const cells: string[] = [];
  let cur = '';
  let inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQ && line[i + 1] === '"') { cur += '"'; i++; }
      else inQ = !inQ;
    } else if (ch === ',' && !inQ) {
      cells.push(cur);
      cur = '';
    } else {
      cur += ch;
    }
  }
  cells.push(cur);
  return cells;
}

/** Map a CSV row to the CreateTradeInput shape, or null if invalid. */
function mapRow(r: Record<string, string>) {
  const num = (v: string | undefined) => (v && v !== '' ? Number(v) : undefined);
  const str = (v: string | undefined) => (v && v !== '' ? v : undefined);
  const direction = (r.direction || r.dir || '').toUpperCase();
  if (direction !== 'LONG' && direction !== 'SHORT') return null;
  const entry = num(r.entry);
  const exit = num(r.exit);
  if (entry == null || exit == null) return null;
  const entryTime = normalizeTime(r.entrytime || r.entry_time || r.entryTime);
  const exitTime = normalizeTime(r.exittime || r.exit_time || r.exitTime);
  if (!entryTime || !exitTime) return null;
  return {
    symbol: (r.symbol || '').toUpperCase(),
    direction,
    entry,
    exit,
    stopLoss: num(r.stoploss || r.stop_loss) ?? null,
    takeProfit: num(r.takeprofit || r.take_profit) ?? null,
    quantity: num(r.quantity || r.qty) ?? 1,
    entryTime,
    exitTime,
    session: str(r.session),
    timeframe: str(r.timeframe || r.tf),
    emotion: str(r.emotion),
    confidence: num(r.confidence) ?? null,
    notes: str(r.notes),
  };
}

/** Normalize a time string to ISO. Accepts ISO or "YYYY-MM-DD HH:MM". */
function normalizeTime(v: string | undefined): string | null {
  if (!v) return null;
  const t = v.trim();
  if (!t) return null;
  // "YYYY-MM-DD HH:MM" -> "YYYY-MM-DDTHH:MM"
  const m = t.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/);
  if (m) return new Date(`${m[1]}T${m[2]}:00`).toISOString();
  const d = new Date(t);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}
