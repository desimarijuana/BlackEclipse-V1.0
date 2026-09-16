'use client';

// ── Investor Eye — Saved Views ───────────────────────────────────────────────
// A saved "intelligence posture": layers + time window + projection + metric.
// Lets a user keep e.g. "Red Sea shipping watch" or "Energy & sanctions" and
// return to it in one click.
//
// Restores VIEW STATE only — never data — so a saved view can't resurrect a
// stale observation.

import { useState } from 'react';
import { Bookmark, Plus, Trash2, X } from 'lucide-react';
import { useInvestorEyeStore } from '@/lib/investor-eye/store';
import { cn } from '@/lib/utils';

export function SavedViews() {
  const views = useInvestorEyeStore((s) => s.views);
  const saveView = useInvestorEyeStore((s) => s.saveView);
  const applyView = useInvestorEyeStore((s) => s.applyView);
  const deleteView = useInvestorEyeStore((s) => s.deleteView);

  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');

  const submit = () => {
    if (!name.trim()) return;
    saveView(name);
    setName('');
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-semibold text-muted-foreground hover:text-foreground cursor-pointer"
        title="Saved views (layers + window presets)"
        aria-expanded={open}
      >
        <Bookmark size={12} />
        <span className="hidden sm:inline">Views</span>
        {views.length > 0 && (
          <span className="rounded-sm bg-primary/20 px-1 font-mono text-[9px] text-foreground">{views.length}</span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-40 mt-1 w-64 glass-card-strong rounded-xl border border-white/10 p-2">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Saved views</span>
            <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground cursor-pointer" aria-label="Close saved views">
              <X size={11} />
            </button>
          </div>

          <div className="flex items-center gap-1.5">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
              placeholder="Save current as…"
              className="min-w-0 flex-1 rounded-lg border border-border/40 bg-background/60 px-2 py-1.5 text-[10px] text-foreground outline-none focus:border-primary/40"
            />
            <button
              onClick={submit}
              disabled={!name.trim()}
              className="rounded-lg border border-primary/30 bg-primary/15 px-2 py-1.5 text-[10px] font-semibold text-foreground disabled:opacity-40 cursor-pointer"
              aria-label="Save view"
            >
              <Plus size={11} />
            </button>
          </div>

          <div className="mt-2 max-h-56 space-y-1 overflow-y-auto scrollbar-hide">
            {views.length === 0 && (
              <div className="py-2 text-center text-[10px] italic text-muted-foreground/70">
                No saved views yet.
              </div>
            )}
            {views.map((v) => (
              <div key={v.id} className="flex items-center gap-1 rounded-lg border border-border/20 px-2 py-1.5">
                <button
                  onClick={() => { applyView(v.id); setOpen(false); }}
                  className="min-w-0 flex-1 text-left cursor-pointer"
                >
                  <div className="truncate text-[10px] font-medium text-foreground">{v.name}</div>
                  <div className="truncate font-mono text-[9px] text-muted-foreground/70">
                    {v.activeLayers.length} layers · {v.timeRange} · {v.mapMode}
                  </div>
                </button>
                <button
                  onClick={() => deleteView(v.id)}
                  className={cn('shrink-0 rounded-md p-1 text-muted-foreground hover:text-rose-400 cursor-pointer')}
                  aria-label={`Delete view ${v.name}`}
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
