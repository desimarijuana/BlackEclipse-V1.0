"use client";

// ── Strategy picker (New bot / change strategy) ─────────────────────────────
// A searchable list with evidence, not a 46-option <select>. Reads the shared
// catalog, so an agent-made strategy is here the moment the library refreshes,
// and offers a direct "Open in Strategy Studio" jump.

import { useMemo, useState } from "react";
import { Check, ExternalLink, RefreshCw, Search } from "@/lib/icons";
import { isBacktestComplete, useStrategyCatalog } from "@/lib/strategies/catalog";
import { navigateToStrategy } from "@/lib/navigation/app-nav";
import type { StrategySummary } from "@/lib/backtest/backtest-client";
import { cn } from "@/lib/utils";

export interface StrategyPickerProps {
  strategyId: string;
  strategyVersion: string;
  onSelect: (strategy: StrategySummary) => void;
  disabled?: boolean;
}

export function StrategyPicker({
  strategyId,
  strategyVersion,
  onSelect,
  disabled,
}: StrategyPickerProps) {
  const catalog = useStrategyCatalog();
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return catalog.items;
    return catalog.items.filter((item) =>
      [item.id, item.name, item.description ?? ""].some((field) =>
        field.toLowerCase().includes(needle),
      ),
    );
  }, [catalog.items, query]);

  return (
    <div className="rounded-lg border border-border/15 p-2">
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-semibold">Strategy</span>
        <span className="text-[10px] text-muted-foreground">
          {catalog.loading ? "loading…" : `${catalog.items.length} saved`}
        </span>
        <button
          type="button"
          onClick={catalog.refresh}
          disabled={catalog.loading}
          aria-label="Refresh strategies"
          className="ml-auto rounded p-1 text-muted-foreground hover:bg-white/5 hover:text-foreground disabled:opacity-50"
        >
          <RefreshCw size={12} className={cn(catalog.loading && "animate-spin")} />
        </button>
        <label className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
          <input
            type="checkbox"
            checked={catalog.includeArchived}
            onChange={(event) => catalog.setIncludeArchived(event.target.checked)}
          />
          archived
        </label>
      </div>

      <label className="relative mt-1 block">
        <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search strategies by name or id"
          aria-label="Search strategies"
          className="w-full rounded-lg border border-input bg-transparent py-1.5 pl-7 pr-2 text-xs outline-none focus-visible:border-ring"
        />
      </label>

      {catalog.error && (
        <p className="mt-1 text-[10px] text-rose-300">
          {catalog.error}{" "}
          <button type="button" onClick={catalog.refresh} className="underline">
            Retry
          </button>
        </p>
      )}

      <div className="mt-1 max-h-48 space-y-0.5 overflow-y-auto">
        {!catalog.loading && visible.length === 0 ? (
          <div className="px-2 py-2 text-[11px] text-muted-foreground">
            {catalog.items.length === 0
              ? "No strategies yet."
              : "No strategy matches that search."}{" "}
            <button
              type="button"
              onClick={() => navigateToStrategy()}
              className="text-sky-300 underline"
            >
              Create one in Strategy Studio
            </button>
          </div>
        ) : null}

        {visible.map((item) => {
          const selected = item.id === strategyId;
          const backtest = item.latestBacktest?.status;
          const complete = isBacktestComplete(backtest);
          const approved = item.approval?.status === "approved";
          return (
            <div
              key={item.id}
              className={cn(
                "flex items-start gap-2 rounded-lg px-2 py-1.5",
                selected ? "bg-primary/15 ring-1 ring-primary/30" : "hover:bg-white/5",
              )}
            >
              <button
                type="button"
                disabled={disabled}
                onClick={() => onSelect(item)}
                className="min-w-0 flex-1 text-left disabled:opacity-50"
              >
                <span className="flex items-center gap-1 text-[11px] text-foreground">
                  <span className="truncate">{item.name || item.id}</span>
                  {item.archived ? (
                    <span className="rounded bg-white/10 px-1 text-[9px] uppercase text-muted-foreground">
                      archived
                    </span>
                  ) : null}
                  {selected ? <Check size={11} className="shrink-0 text-emerald-300" /> : null}
                </span>
                <span className="block truncate font-mono text-[9px] text-muted-foreground">
                  {item.id} · v{item.latestVersion}
                </span>
                <span className="mt-0.5 flex flex-wrap gap-x-2 text-[9px]">
                  <span className={complete ? "text-emerald-300/90" : "text-amber-300/80"}>
                    {complete ? "backtest ✓" : backtest ? `backtest ${backtest}` : "no backtest"}
                  </span>
                  {approved ? <span className="text-emerald-300/90">approved</span> : null}
                  {item.lastPaperRun ? <span className="text-sky-300/80">paper ✓</span> : null}
                </span>
              </button>
              <button
                type="button"
                onClick={() => navigateToStrategy(item.id)}
                title="Open in Strategy Studio"
                aria-label={`Open ${item.name || item.id} in Strategy Studio`}
                className="mt-0.5 shrink-0 rounded p-1 text-muted-foreground hover:bg-white/5 hover:text-foreground"
              >
                <ExternalLink size={12} />
              </button>
            </div>
          );
        })}
      </div>

      {strategyId && (
        <button
          type="button"
          onClick={() => navigateToStrategy(strategyId)}
          className="mt-1 inline-flex items-center gap-1 text-[10px] text-sky-300 hover:underline"
        >
          Open {strategyId}@{strategyVersion || "?"} in Strategy Studio
          <ExternalLink size={10} />
        </button>
      )}
    </div>
  );
}
