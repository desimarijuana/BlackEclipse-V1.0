'use client';

// ── CSV Import — parse a trade CSV and bulk-import into the journal ──────────
// Supports multiple broker/exchange formats (MT4, MT5, Binance, Coinbase,
// generic) with auto-detection, format selection, and template downloads.

import React, { useRef, useState } from 'react';
import { Upload, Loader2, X, Check, Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import { IMPORT_FORMATS, type ImportFormat } from '@/lib/journal/import';

interface CsvImportProps {
  onImported: () => void;
}

export function CsvImport({ onImported }: CsvImportProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [format, setFormat] = useState<ImportFormat>('generic');
  const [result, setResult] = useState<{ imported: number; errors: string[]; format?: ImportFormat; skipped?: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setImporting(true);
    setError(null);
    setResult(null);
    try {
      const text = await file.text();
      const res = await fetch('/api/journal/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, format }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Import failed');
      setResult({ imported: data.imported ?? 0, errors: data.errors ?? [], format: data.format, skipped: data.skipped });
      onImported();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to import');
    } finally {
      setImporting(false);
    }
  };

  const downloadTemplate = () => {
    const a = document.createElement('a');
    a.href = `/api/journal/import?format=${format}`;
    a.download = `blackeclipse-${format}-template.csv`;
    a.click();
  };

  return (
    <div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-accent/30 px-3 py-1.5 text-xs font-bold text-muted-foreground hover:text-primary hover:border-primary/40 transition-all cursor-pointer"
      >
        {open ? <X size={13} /> : <Upload size={13} />} {open ? 'Close' : 'Import'}
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

          {/* Format selector */}
          <div className="mb-3">
            <p className="mb-1.5 text-[9px] uppercase tracking-widest font-bold text-muted-foreground">Source Format</p>
            <div className="flex flex-wrap gap-1.5">
              {IMPORT_FORMATS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setFormat(f.id)}
                  title={f.description}
                  className={cn(
                    'rounded-lg border px-2.5 py-1 text-[10px] font-semibold transition-all cursor-pointer',
                    format === f.id ? 'border-primary/40 bg-primary/15 text-primary' : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:text-foreground',
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-[10px] text-muted-foreground/70">{IMPORT_FORMATS.find((f) => f.id === format)?.description}</p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => fileRef.current?.click()}
              disabled={importing}
              className="inline-flex items-center gap-1.5 rounded-lg border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
            >
              {importing ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
              {importing ? 'Importing…' : 'Choose file'}
            </button>
            <button
              onClick={downloadTemplate}
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-accent/30 px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:text-primary transition-all cursor-pointer"
            >
              <Download size={12} /> Template
            </button>
          </div>

          {error && <p className="mt-3 text-xs text-rose-400 font-semibold">{error}</p>}
          {result && (
            <div className="mt-3 rounded-lg bg-white/[0.03] p-3">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-emerald-400">
                <Check size={13} /> Imported {result.imported} trade{result.imported === 1 ? '' : 's'}
                {result.format ? ` (${result.format})` : ''}
                {result.skipped ? ` · ${result.skipped} skipped` : ''}.
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
