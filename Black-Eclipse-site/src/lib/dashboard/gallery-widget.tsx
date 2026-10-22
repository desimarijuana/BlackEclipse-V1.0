'use client';

// ── The gallery — published strategies, with the grade they earned ───────────
// A local catalogue of FROZEN, graded strategies. Each record carries the spec
// it published with, the grade its evidence earned and the report it came
// from. Browse them, favourite them, clone one back into the quant store.
//
// It is not a community of strangers, and it does not pretend to be: it is
// your own catalogue of strategies you have validated.

import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Star } from '@/lib/icons';
import { cn } from '@/lib/utils';

interface PublishedEntry {
  id: string;
  name: string;
  description: string;
  grade: string | null;
  score: number | null;
  summary: string;
  symbols: string[];
  favourites: number;
  clones: number;
  createdAt: string;
}

export function GalleryWidget() {
  const [entries, setEntries] = useState<PublishedEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/harness/gallery');
      const payload = (await res.json().catch(() => ({}))) as {
        entries?: PublishedEntry[];
        error?: string;
      };
      if (!res.ok) {
        setError(payload.error ?? `the gallery returned ${res.status}`);
        return;
      }
      setEntries(payload.entries ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'the gallery is unavailable');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = useCallback(
    async (id: string, action: 'favourite' | 'clone') => {
      setBusy(id);
      setNote(null);
      try {
        const res = await fetch(`/api/harness/gallery/${encodeURIComponent(id)}/${action}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: action === 'clone' ? JSON.stringify({}) : undefined,
        });
        const payload = (await res.json().catch(() => ({}))) as {
          summary?: string;
          error?: string;
          detail?: { message?: string };
        };
        if (!res.ok) {
          setNote(payload.error ?? payload.detail?.message ?? 'the action failed');
          return;
        }
        setNote(payload.summary ?? 'done');
        await load();
      } catch (err) {
        setNote(err instanceof Error ? err.message : 'the action failed');
      } finally {
        setBusy(null);
      }
    },
    [load],
  );

  return (
    <div className="flex h-full flex-col gap-2 p-3">
      <div className="flex items-center gap-2">
        <Star className="h-3.5 w-3.5 text-primary" />
        <span className="text-[11px] font-semibold text-foreground">Gallery</span>
        <span className="ml-auto font-mono text-[9px] text-muted-foreground">
          {loading ? 'loading…' : `${entries.length} published`}
        </span>
      </div>

      {error && <p className="font-mono text-[9px] text-rose-300">{error}</p>}
      {!error && !loading && entries.length === 0 && (
        <p className="font-mono text-[9px] text-muted-foreground">
          Nothing published yet. Publish a strategy with the agent to start the
          catalogue.
        </p>
      )}

      <div className="min-h-0 flex-1 space-y-1 overflow-y-auto scrollbar-hide">
        {entries.map((entry) => (
          <div key={entry.id} className="rounded-lg border border-white/10 px-2 py-1.5">
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-[10px] text-foreground">
                {entry.name}
              </span>
              {entry.grade && (
                <span className="shrink-0 rounded border border-primary/40 bg-primary/10 px-1 font-mono text-[9px] text-primary">
                  {entry.grade}
                </span>
              )}
            </div>
            {entry.summary && (
              <p className="mt-0.5 text-[9px] leading-relaxed text-muted-foreground">
                {entry.summary}
              </p>
            )}
            <div className="mt-1 flex items-center gap-2">
              <span className="font-mono text-[8px] text-muted-foreground">
                ★ {entry.favourites} · ⧉ {entry.clones}
                {entry.symbols.length > 0 ? ` · ${entry.symbols.join(' ')}` : ''}
              </span>
              <button
                type="button"
                onClick={() => void act(entry.id, 'favourite')}
                disabled={busy === entry.id}
                className={cn(
                  'ml-auto rounded border border-white/15 px-1.5 py-0.5 text-[9px]',
                  'text-muted-foreground transition hover:text-foreground disabled:opacity-40',
                )}
              >
                Favourite
              </button>
              <button
                type="button"
                onClick={() => void act(entry.id, 'clone')}
                disabled={busy === entry.id}
                className={cn(
                  'rounded border border-primary/40 px-1.5 py-0.5 text-[9px] text-primary',
                  'transition disabled:opacity-40',
                )}
              >
                {busy === entry.id ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : 'Clone'}
              </button>
            </div>
          </div>
        ))}
      </div>

      {note && <p className="font-mono text-[9px] text-muted-foreground">{note}</p>}

      <p className="text-[8px] leading-relaxed text-muted-foreground/70">
        Published records are frozen: the spec, the grade its evidence earned and the
        report it came from. Cloning copies the spec into a new strategy; the
        original is untouched.
      </p>
    </div>
  );
}
