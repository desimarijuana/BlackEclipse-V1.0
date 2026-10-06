"use client";

// ── Settings › News › Feeds ─────────────────────────────────────────────────
// The RSS feed list, organised the way the rest of the Settings modal is: what
// is live first, grouped by category, searchable, with an inline "Add feed".
// Replaces the flat 74-row wall that used to live inline in `settings.tsx`.
//
// The parent owns the feed array (it persists via POST /api/settings); this
// panel is presentational plus local search/add state. Adding a feed appends a
// new id; the server merges unknown ids verbatim, so custom feeds round-trip.

import { useMemo, useState } from "react";
import { AlertCircle, Check, Newspaper, Plus, Rss, Search, Trash2, X } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface NewsFeed {
  id: string;
  url: string;
  source: string;
  enabled: boolean;
  category?: string;
  region?: string;
  tier?: number;
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center border rounded-full transition-colors cursor-pointer",
        checked ? "bg-primary/25 border-primary/50" : "bg-muted/60 border-border",
      )}
    >
      <span
        className={cn(
          "inline-block h-3.5 w-3.5 transform rounded-full shadow-sm transition-transform",
          checked ? "translate-x-[18px] bg-primary" : "translate-x-[2px] bg-muted-foreground/70",
        )}
      />
    </button>
  );
}

const TIER_LABEL: Record<number, string> = { 1: "Wire", 2: "Major", 3: "Specialist", 4: "Blog" };

export function NewsFeedsPanel({
  feeds,
  onSave,
  saving,
}: {
  feeds: NewsFeed[];
  onSave: (next: NewsFeed[]) => void;
  saving?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ source: "", url: "", category: "MARKETS" });

  const enabledCount = feeds.filter((f) => f.enabled).length;
  const needle = query.trim().toLowerCase();

  const { live, paused } = useMemo(() => {
    const matches = (f: NewsFeed) => {
      if (!needle) return true;
      return [f.source, f.url, f.category ?? ""].join(" ").toLowerCase().includes(needle);
    };
    const filtered = feeds.filter(matches);
    return {
      live: filtered.filter((f) => f.enabled),
      paused: filtered.filter((f) => !f.enabled),
    };
  }, [feeds, needle]);

  const toggle = (id: string, enabled: boolean) =>
    onSave(feeds.map((f) => (f.id === id ? { ...f, enabled } : f)));

  const remove = (id: string) => onSave(feeds.filter((f) => f.id !== id));

  const addFeed = () => {
    const url = draft.url.trim();
    const source = draft.source.trim() || (() => {
      try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return "Custom feed"; }
    })();
    if (!url || !/^https?:\/\//i.test(url)) return;
    const id = `custom-${Date.now().toString(36)}`;
    onSave([...feeds, { id, url, source, category: draft.category.toUpperCase(), enabled: true }]);
    setDraft({ source: "", url: "", category: "MARKETS" });
    setAdding(false);
  };

  const Row = ({ f }: { f: NewsFeed }) => (
    <div className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-accent/20 transition-colors group">
      <div className="flex items-center gap-3 min-w-0">
        <span
          className={cn(
            "w-2 h-2 rounded-full shrink-0",
            f.enabled ? "bg-primary shadow-[0_0_8px] shadow-primary/60" : "bg-border",
          )}
        />
        <div className="min-w-0">
          <span className="text-[11px] font-medium text-foreground flex items-center gap-1.5 flex-wrap">
            {f.source}
            {f.category && (
              <span className="text-[8px] font-bold uppercase tracking-wider text-muted-foreground/70 border border-border/40 rounded-full px-1.5 py-0.5">
                {f.category}
              </span>
            )}
            {f.tier && (
              <span className="text-[8px] uppercase tracking-wider text-muted-foreground/50">{TIER_LABEL[f.tier]}</span>
            )}
          </span>
          <span className="text-[10px] text-muted-foreground block truncate max-w-[280px] font-mono">{f.url}</span>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className={cn("text-[10px] font-semibold hidden sm:block", f.enabled ? "text-primary" : "text-muted-foreground")}>
          {f.enabled ? "Live" : "Paused"}
        </span>
        <Toggle checked={f.enabled} onChange={(v) => toggle(f.id, v)} />
        <button
          type="button"
          onClick={() => remove(f.id)}
          title="Remove feed"
          className="p-1 rounded-md text-muted-foreground/0 group-hover:text-muted-foreground hover:!text-rose-400 transition-colors cursor-pointer"
        >
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  );

  const GroupHeader = ({ label, count, tone }: { label: string; count: number; tone: "ok" | "muted" }) => (
    <div className="flex items-center gap-2 px-4 pt-3 pb-1">
      {tone === "ok" ? <Check size={11} className="text-primary shrink-0" /> : <AlertCircle size={11} className="text-muted-foreground shrink-0" />}
      <span className={cn("text-[9px] uppercase tracking-[0.15em] font-bold", tone === "ok" ? "text-primary/90" : "text-muted-foreground/70")}>
        {label}
      </span>
      <span className="text-[9px] text-muted-foreground/60">{count}</span>
    </div>
  );

  return (
    <div className="rounded-2xl border border-border/20 glass-card overflow-hidden">
      <div className="px-4 py-3 border-b border-border/10 flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.15em] font-bold text-primary flex items-center gap-1.5">
            <Rss size={11} /> RSS feeds
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5">
            {enabledCount} of {feeds.length} live · toggle, add or remove feeds
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search feeds…"
              className="w-40 h-7 rounded-lg border border-border/30 bg-transparent pl-7 pr-2 text-[10px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/40"
            />
          </div>
          <Button
            size="sm"
            variant={adding ? "outline" : "default"}
            className="cursor-pointer rounded-lg text-[10px] h-7 px-2.5"
            onClick={() => setAdding((v) => !v)}
          >
            {adding ? <X className="w-3 h-3 mr-1" /> : <Plus className="w-3 h-3 mr-1" />}
            {adding ? "Cancel" : "Add feed"}
          </Button>
        </div>
      </div>

      {adding && (
        <div className="border-b border-border/10 bg-white/[0.02] px-4 py-3">
          <div className="grid gap-2 sm:grid-cols-[1fr_1.4fr_auto_auto] items-end">
            <div className="flex flex-col gap-1">
              <label className="text-[9px] uppercase tracking-wider text-muted-foreground">Source</label>
              <Input
                value={draft.source}
                onChange={(e) => setDraft((d) => ({ ...d, source: e.target.value }))}
                placeholder="e.g. Reuters"
                className="h-8 text-xs"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[9px] uppercase tracking-wider text-muted-foreground">RSS URL</label>
              <Input
                value={draft.url}
                autoFocus
                onChange={(e) => setDraft((d) => ({ ...d, url: e.target.value }))}
                onKeyDown={(e) => { if (e.key === "Enter") addFeed(); }}
                placeholder="https://example.com/feed.xml"
                className="h-8 text-xs font-mono"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[9px] uppercase tracking-wider text-muted-foreground">Category</label>
              <Input
                value={draft.category}
                onChange={(e) => setDraft((d) => ({ ...d, category: e.target.value }))}
                className="h-8 text-xs w-28"
              />
            </div>
            <Button
              size="sm"
              className="cursor-pointer rounded-lg text-[11px] h-8"
              disabled={saving || !/^https?:\/\//i.test(draft.url.trim())}
              onClick={addFeed}
            >
              Add
            </Button>
          </div>
          <p className="text-[9px] text-muted-foreground mt-1.5">Feeds are fetched over the network; the server blocks private/localhost URLs.</p>
        </div>
      )}

      {live.length === 0 && paused.length === 0 && (
        <p className="px-4 py-6 text-[10px] text-muted-foreground text-center">
          {needle ? <>No feeds match “{query}”.</> : "No feeds configured."}
        </p>
      )}

      {live.length > 0 && (
        <div className={cn(paused.length > 0 && "border-b border-border/10")}>
          <GroupHeader label="Live" count={live.length} tone="ok" />
          <div className="divide-y divide-border/10">{live.map((f) => <Row key={f.id} f={f} />)}</div>
        </div>
      )}

      {paused.length > 0 && (
        <div>
          <GroupHeader label="Paused" count={paused.length} tone="muted" />
          <div className="divide-y divide-border/10">{paused.map((f) => <Row key={f.id} f={f} />)}</div>
        </div>
      )}

      <p className="px-4 py-2.5 border-t border-border/10 text-[9px] text-muted-foreground flex items-center gap-1.5">
        <Newspaper size={10} className="text-muted-foreground/60" />
        Feeds power the Market News bulletin and Investor Eye sentiment. Changes save automatically.
      </p>
    </div>
  );
}
