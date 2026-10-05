"use client";

// ── Contextual provider list ────────────────────────────────────────────────
// A compact slice of the provider catalog, rendered INSIDE the settings section
// that configures it. APIs live where you would look for them:
//
//   AI / LLM       → AI & LLM
//   Investor Eye   → Market, fundamentals, economics, crypto, news, earnings
//   Market Data    → Market price sources
//   News           → News providers
//   Data Sources   → Your own data (the wizard)
//
// The full catalog is still one request (`GET /api/providers`); it is cached at
// module scope so rendering it in several sections costs one fetch.
//
// Every row now answers "why does this exist and who uses it?" via the provider
// directory (`lib/providers/directory`): purpose, used-by features, and cost
// tier. Honesty rules are unchanged: a row only says "connected" when the
// gating env var is really set, and an action button never claims to have saved
// a key — env-gated providers route to the section that sets it.

import { useEffect, useState } from "react";
import { Check, ChevronDown, Loader2, Plus, Wrench } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useCommandStore } from "@/lib/search/store";
import { providerMeta, TIER_LABEL } from "@/lib/providers/directory";
import type { CatalogProvider, ProviderCatalog, ProviderCategory } from "@/lib/connectors/catalog";

const EMPTY_CATALOG: ProviderCatalog = { categories: [], envFlags: {}, totals: { providers: 0, connected: 0, custom: 0 } };

let cached: Promise<ProviderCatalog> | null = null;
// Every mounted consumer subscribes, so a forced reload (e.g. after a failed
// fetch) updates all of them — the retry button actually re-renders.
const subscribers = new Set<(c: ProviderCatalog) => void>();

/** Fetch the catalog once per page load. Pass `force` to refetch and notify. */
export function loadProviderCatalog(force = false): Promise<ProviderCatalog> {
  if (!cached || force) {
    cached = fetch("/api/providers")
      .then((r) => r.json())
      .catch(() => EMPTY_CATALOG);
    if (force) {
      void cached.then((c) => subscribers.forEach((fn) => fn(c)));
    }
  }
  return cached;
}

export function useProviderCatalog(): ProviderCatalog | null {
  const [catalog, setCatalog] = useState<ProviderCatalog | null>(null);
  useEffect(() => {
    const set = (c: ProviderCatalog) => setCatalog(c);
    subscribers.add(set);
    let live = true;
    void loadProviderCatalog()
      .then((c) => {
        if (live) set(c);
      })
      .catch(() => {
        // A failed fetch must leave the hook in a terminal state, not spin
        // forever. An empty catalog renders the honest "no providers" state.
        if (live) set(EMPTY_CATALOG);
      });
    return () => {
      live = false;
      subscribers.delete(set);
    };
  }, []);
  return catalog;
}

/**
 * Route a provider to where it is configured. Env-gated providers cannot be
 * saved from the browser, so this navigates rather than pretending to save.
 * Settings is a modal, so navigation goes through the destination bus.
 */
function goConfigure(provider: CatalogProvider, onOpenWizard?: () => void) {
  if (provider.configure.target === "wizard") {
    onOpenWizard?.();
    return;
  }
  if (provider.configure.target === "ai" || provider.configure.target === "investor-eye") {
    useCommandStore.getState().dispatch({
      tab: "settings",
      subroute: `settings.${provider.configure.target}`,
    });
  }
}

function ProviderRow({
  provider,
  onOpenWizard,
}: {
  provider: CatalogProvider;
  onOpenWizard?: () => void;
}) {
  const available = provider.status === "builtin" || provider.status === "connected";
  const actionable = !available && provider.configure.target !== "none";
  const meta = providerMeta(provider.id, provider.category);

  return (
    <div className="px-4 py-3 hover:bg-accent/20 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium text-foreground flex items-center gap-1.5 flex-wrap">
            <span className="truncate">{provider.name}</span>
            {provider.recommended && (
              <span className="px-1.5 py-0.5 rounded-full text-[8px] font-bold border border-primary/30 bg-primary/10 text-primary shrink-0">
                RECOMMENDED
              </span>
            )}
            <span className="text-[8px] font-bold uppercase tracking-wider text-muted-foreground/70 shrink-0">
              {TIER_LABEL[meta.tier]}
            </span>
          </p>
          {/* Purpose — "what is this API?" */}
          <p className="text-[10px] text-primary/90 mt-0.5">{meta.purpose}</p>
          <p className="text-[10px] text-muted-foreground truncate" title={provider.description}>
            {provider.description}
          </p>
          {/* Used-by — "which feature uses it?" */}
          {meta.usedBy.length > 0 && (
            <p className="text-[9px] text-muted-foreground/70 mt-1">
              Used by: {meta.usedBy.join(", ")}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {provider.status === "not_configured" && provider.envVar && (
            <span className="text-[9px] text-amber-400/90 font-mono hidden sm:inline">needs {provider.envVar}</span>
          )}
          {available ? (
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span className="text-[9px] uppercase tracking-wider text-muted-foreground">
                {provider.status === "builtin" ? "Built-in" : "Key set"}
              </span>
            </span>
          ) : actionable ? (
            <Button
              variant="outline"
              size="sm"
              className="cursor-pointer rounded-xl text-[10px] h-7 px-2.5"
              onClick={() => goConfigure(provider, onOpenWizard)}
            >
              {provider.configure.target === "wizard" ? (
                <Plus className="w-3 h-3 mr-1" />
              ) : (
                <Wrench className="w-3 h-3 mr-1" />
              )}
              {provider.configure.target === "wizard" ? "Add" : "Configure"}
            </Button>
          ) : (
            <span className="text-[9px] uppercase tracking-wider text-muted-foreground">Off</span>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Render the catalog slice for one or more categories.
 *
 * @param categories  Which parts of the catalog to show.
 * @param collapsible Start collapsed (for long lists like economics).
 * @param searchable  Show a filter box (worth it only for long lists).
 * @param onOpenWizard Called when a provider's action is "open the wizard".
 * @param title       Override the section heading (e.g. "Fundamental data providers").
 */
export function ProviderList({
  categories,
  collapsible = false,
  searchable = false,
  onOpenWizard,
  title,
}: {
  categories: ProviderCategory[];
  collapsible?: boolean;
  searchable?: boolean;
  onOpenWizard?: () => void;
  title?: string;
}) {
  const catalog = useProviderCatalog();
  const [open, setOpen] = useState(!collapsible);
  const [filter, setFilter] = useState("");

  if (!catalog) {
    return (
      <div className="flex items-center gap-2 px-4 py-3 text-[10px] text-muted-foreground">
        <Loader2 className="w-3 h-3 animate-spin" /> Loading providers…
      </div>
    );
  }

  const groups = catalog.categories.filter((c) => categories.includes(c.id));
  const total = groups.reduce((n, g) => n + g.providers.length, 0);
  const available = groups.reduce((n, g) => n + g.connectedCount, 0);
  if (groups.length === 0) return null;

  const needle = filter.trim().toLowerCase();
  const matches = (p: CatalogProvider) =>
    !needle || p.name.toLowerCase().includes(needle) || p.description.toLowerCase().includes(needle);

  return (
    <div className="rounded-2xl border border-border/20 glass-card overflow-hidden">
      <button
        className={cn(
          "w-full px-4 py-3 flex items-center justify-between gap-3",
          collapsible && "cursor-pointer hover:bg-accent/20 transition-colors"
        )}
        onClick={() => collapsible && setOpen((v) => !v)}
      >
        <div className="text-left">
          <p className="text-[10px] uppercase tracking-[0.15em] font-bold text-primary">
            {title ?? (groups.length === 1 ? groups[0].label : "Providers")}
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5">
            {available} of {total} available
          </p>
        </div>
        {collapsible && (
          <ChevronDown
            size={14}
            className={cn("text-muted-foreground shrink-0 transition-transform", open && "rotate-180")}
          />
        )}
      </button>

      {open && (
        <>
          {searchable && (
            <div className="px-4 pb-2.5 border-t border-border/10 pt-3">
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter providers…"
                className="w-full h-8 rounded-lg border border-border/30 bg-transparent px-3 text-[11px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/40"
              />
            </div>
          )}
          <div className="divide-y divide-border/10 border-t border-border/10 max-h-[26rem] overflow-y-auto scrollbar-hide">
            {groups.flatMap((group) =>
              group.providers.filter(matches).map((provider) => (
                <ProviderRow key={provider.id} provider={provider} onOpenWizard={onOpenWizard} />
              ))
            )}
            {needle && groups.every((g) => g.providers.filter(matches).length === 0) && (
              <p className="px-4 py-4 text-[10px] text-muted-foreground">No providers match “{filter}”.</p>
            )}
          </div>
          <p className="px-4 py-2.5 border-t border-border/10 text-[9px] text-muted-foreground flex items-center gap-1.5">
            <Check className="w-3 h-3 text-primary shrink-0" />
            Key-gated providers are set with an environment variable or the encrypted vault; this list links you to the right screen.
          </p>
        </>
      )}
    </div>
  );
}
