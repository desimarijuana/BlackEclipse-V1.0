'use client';

// ── Manage models dialog ─────────────────────────────────────────────────────
// Opened from the model picker's "Manage models" action. A provider (OpenRouter,
// Ollama, a local server) can list hundreds or thousands of models — far too
// many to pour into a dropdown. This dialog shows the FULL discovered catalog in
// a searchable list with per-model checkboxes, so the operator enables only the
// handful they actually use. Enabled ids are persisted (see `enabled-models.ts`)
// and are what the compact pickers show.
//
// It is a filter, never an allowlist: the runtime still accepts any id and the
// picker keeps a "Custom model id…" entry. Portaled to <body> by the shared
// Dialog, so it is never clipped and sits above the Settings modal (z-[100]).

import { useMemo, useState } from 'react';
import { Check, RefreshCw, Search } from '@/lib/icons';
import { ProviderLogo } from '@/components/providers/provider-logo';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { useEnabledModelsStore } from '@/lib/agent/enabled-models';
import { compareModelRecency } from '@/lib/agent/model-recency';

/** Stable empty reference so the zustand selector never returns a new array. */
const NO_MODELS: string[] = [];

export interface ManageModelsDialogProps {
  providerId: string;
  providerLabel: string;
  /** Every model id the provider currently lists (declared + discovered). */
  allModels: string[];
  /** The currently selected model, kept enabled so the active choice survives. */
  selected?: string;
  /** Runs a fresh live discovery; resolves true on success (new ids merge in). */
  onDiscover?: () => Promise<boolean>;
  canDiscover?: boolean;
  onClose: () => void;
}

export function ManageModelsDialog({
  providerId,
  providerLabel,
  allModels,
  selected,
  onDiscover,
  canDiscover,
  onClose,
}: ManageModelsDialogProps) {
  const [query, setQuery] = useState('');
  const [discovering, setDiscovering] = useState(false);
  const enabled = useEnabledModelsStore((s) => s.providers[providerId] ?? NO_MODELS);
  const setEnabled = useEnabledModelsStore((s) => s.setEnabled);
  const resetProvider = useEnabledModelsStore((s) => s.resetProvider);

  // The working set = every id offered. A freshly discovered id appears here
  // because the parent merges it into `allModels` and re-renders.
  const models = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const m of [...allModels, ...(selected ? [selected] : [])]) {
      if (m && !seen.has(m)) { seen.add(m); out.push(m); }
    }
    return out;
  }, [allModels, selected]);

  const enabledSet = useMemo(() => new Set(enabled), [enabled]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q ? models.filter((m) => m.toLowerCase().includes(q)) : models;
    // Enabled first, then NEWEST first within each group — a newly released
    // model sits at the top of the uncurated section instead of at the bottom.
    return [...list].sort((a, b) => {
      const ea = enabledSet.has(a) ? 0 : 1;
      const eb = enabledSet.has(b) ? 0 : 1;
      if (ea !== eb) return ea - eb;
      const recency = compareModelRecency(a, b);
      if (recency !== 0) return recency;
      return a.localeCompare(b);
    });
  }, [models, query, enabledSet]);

  const toggle = (id: string) => {
    const next = enabledSet.has(id) ? enabled.filter((m) => m !== id) : [...enabled, id];
    setEnabled(providerId, next);
  };

  const enableAllFiltered = () => setEnabled(providerId, Array.from(new Set([...enabled, ...filtered])));
  const clearAll = () => setEnabled(providerId, []);

  const runDiscover = async () => {
    if (!onDiscover || discovering) return;
    setDiscovering(true);
    try {
      await onDiscover();
    } finally {
      setDiscovering(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent
        overlayClassName="z-[130]"
        className="z-[130] w-[calc(100%-1.5rem)] max-w-3xl h-[min(85dvh,720px)] rounded-2xl border border-white/15 dark:border-white/10 glass-card-strong p-0 gap-0 overflow-hidden"
      >
        <DialogTitle className="sr-only">Manage models — {providerLabel}</DialogTitle>

        {/* Header */}
        <div className="flex items-start gap-3 border-b border-border/10 p-5">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05] text-foreground">
            <ProviderLogo provider={providerId} size={20} />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="font-serif text-lg font-semibold text-foreground">Manage models</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {providerLabel} lists <span className="text-foreground/80">{models.length}</span> model{models.length === 1 ? '' : 's'}.
              Enable the ones you want in the picker — {enabled.length} enabled.
            </p>
          </div>
          {canDiscover && onDiscover && (
            <button
              type="button"
              onClick={() => void runDiscover()}
              disabled={discovering}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-border/40 bg-accent/30 px-3 py-1.5 text-[11px] font-bold text-foreground/90 transition-colors hover:border-primary/40 hover:text-primary disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw size={12} className={cn(discovering && 'animate-spin')} />
              {discovering ? 'Discovering…' : 'Discover'}
            </button>
          )}
        </div>

        {/* Search + bulk actions */}
        <div className="flex flex-wrap items-center gap-2 border-b border-border/10 px-5 py-3">
          <div className="relative min-w-[10rem] flex-1">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter models…"
              className="h-9 w-full rounded-xl border border-border/30 bg-transparent pl-8 pr-3 text-xs text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-primary/40"
            />
          </div>
          <button
            type="button"
            onClick={enableAllFiltered}
            className="rounded-xl border border-border/40 bg-accent/20 px-3 py-1.5 text-[11px] font-semibold text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
          >
            Enable {query.trim() ? 'filtered' : 'all'}
          </button>
          <button
            type="button"
            onClick={clearAll}
            className="rounded-xl border border-border/40 bg-accent/20 px-3 py-1.5 text-[11px] font-semibold text-muted-foreground transition-colors hover:text-rose-400 cursor-pointer"
          >
            Clear
          </button>
        </div>

        {/* List */}
        <div className="min-h-0 flex-1 overflow-y-auto p-3 scrollbar-hide">
          {filtered.length === 0 ? (
            <p className="py-12 text-center text-xs text-muted-foreground">
              {models.length === 0
                ? 'No models listed yet — run Discover to fetch this provider’s catalog.'
                : `No models match “${query}”.`}
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map((m) => {
                const on = enabledSet.has(m);
                return (
                  <button
                    key={m}
                    type="button"
                    onClick={() => toggle(m)}
                    aria-pressed={on}
                    className={cn(
                      'flex items-center gap-2 rounded-lg border px-2.5 py-2 text-left text-xs transition-colors cursor-pointer',
                      on
                        ? 'border-white/12 bg-white/[0.06] text-foreground'
                        : 'border-transparent text-muted-foreground hover:bg-accent/40 hover:text-foreground',
                    )}
                  >
                    <span
                      className={cn(
                        'flex h-4 w-4 shrink-0 items-center justify-center rounded border',
                        on ? 'border-primary/50 bg-primary/20 text-primary' : 'border-border/50',
                      )}
                    >
                      {on && <Check size={11} />}
                    </span>
                    <span className="truncate font-mono">{m}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between gap-2 border-t border-border/10 px-5 py-4">
          <button
            type="button"
            onClick={() => resetProvider(providerId)}
            className="rounded-xl px-2 py-1.5 text-[11px] font-semibold text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
            title="Forget this curation and fall back to the declared list"
          >
            Reset to default
          </button>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 px-4 py-2 text-xs font-bold text-primary transition-all hover:bg-primary/25 cursor-pointer"
          >
            Done
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
