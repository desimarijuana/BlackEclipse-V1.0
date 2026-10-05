"use client";

// ── General settings panel ────────────────────────────────────────────────
// The "General" tab of the merged General/Customization surface. Hosts the
// app background picker plus the presentation-layer preferences: destructive-
// action safety (localStorage via `general-prefs`), the server-backed default
// market / refresh interval and the local-only display currency / timezone.
//
// It is self-contained: the parent passes the values it already fetched and a
// persist callback, keeping the merge additive and the parent shell thin.

import { useEffect, useState } from "react";
import { RotateCcw, ShieldCheck } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { DISPLAY_CURRENCIES, getDisplayCurrency, setDisplayCurrency } from "@/lib/currency";
import { DISPLAY_TIMEZONES, browserTimeZone, getDisplayTimeZone, isValidTimeZone, setDisplayTimeZone } from "@/lib/timezone";
import { HEATMAP_MARKETS } from "@/lib/heatmap";
import { DEFAULT_GENERAL_PREFS, loadGeneralPrefs, saveGeneralPrefs, type GeneralPrefs } from "@/lib/general-prefs";
import { BackgroundSettingsPanel } from "./background-settings";

export interface GeneralAppPreferences {
  defaultMarket: string;
  refreshMs: number;
}

// Fallback market list, used only when /api/markets has not answered yet. It is
// the full supported universe (not a hardcoded few) so the selector is never
// silently narrowed to 4 markets.
const ALL_MARKETS = HEATMAP_MARKETS.map((m) => ({ id: m.id, label: m.country }));

const REFRESH_OPTIONS = [10000, 15000, 30000, 60000];

function Panel({ className, children, ...rest }: { className?: string; children: React.ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden", className)} {...rest}>
      {children}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-xs text-muted-foreground font-medium">{label}</Label>
      {children}
      {hint && <p className="text-[10px] text-muted-foreground/70 mt-0.5">{hint}</p>}
    </div>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center border rounded-full transition-colors cursor-pointer",
        checked ? "bg-primary/25 border-primary/50" : "bg-muted/60 border-border"
      )}
    >
      <span
        className={cn(
          "inline-block h-3.5 w-3.5 transform rounded-full shadow-sm transition-transform",
          checked ? "translate-x-[18px] bg-primary" : "translate-x-[2px] bg-muted-foreground/70"
        )}
      />
    </button>
  );
}

export function GeneralSettingsPanel({
  markets,
  prefs,
  onPrefsChange,
  onGeneralChange,
}: {
  /** Markets loaded from JDDS; empty falls back to the built-in list. */
  markets: { id: string; country: string }[];
  prefs: GeneralAppPreferences;
  onPrefsChange: (patch: Partial<GeneralAppPreferences>) => void;
  /** Notify the shell so its in-memory copy (destructive-clear gate) stays fresh. */
  onGeneralChange?: (prefs: GeneralPrefs) => void;
}) {
  const [general, setGeneral] = useState<GeneralPrefs>(DEFAULT_GENERAL_PREFS);
  useEffect(() => { setGeneral(loadGeneralPrefs()); }, []);
  const updateGeneral = (patch: Partial<GeneralPrefs>) => {
    setGeneral((g) => {
      const next = { ...g, ...patch };
      saveGeneralPrefs(next);
      onGeneralChange?.(next);
      return next;
    });
  };

  const [currency, setCurrency] = useState<string>("USD");
  useEffect(() => { setCurrency(getDisplayCurrency()); }, []);
  const applyCurrency = (code: string | null) => {
    if (!code) return;
    setCurrency(code);
    setDisplayCurrency(code);
  };

  const [timeZone, setTimeZone] = useState<string>("UTC");
  useEffect(() => { setTimeZone(getDisplayTimeZone()); }, []);
  const applyTimeZone = (tz: string | null) => {
    if (!tz || !isValidTimeZone(tz)) return;
    setTimeZone(tz);
    setDisplayTimeZone(tz);
  };

  const resetAll = () => {
    setDisplayCurrency("USD");
    setCurrency("USD");
    setDisplayTimeZone("UTC");
    setTimeZone("UTC");
    onPrefsChange({ defaultMarket: "US", refreshMs: 15000 });
    updateGeneral(DEFAULT_GENERAL_PREFS);
  };

  return (
    <div className="animate-fade-in-up space-y-4">
      {/* Background (pattern / wallpaper) — leads the General panel, with the
          shipped Eclipse wallpaper selected by default. Self-contained: it
          reads/writes its own store, so it applies live. */}
      <BackgroundSettingsPanel />

      <Panel className="p-5 md:p-6 space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Default Market">
            <Select value={prefs.defaultMarket} onValueChange={(v) => onPrefsChange({ defaultMarket: v ?? "US" })}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {markets.length > 0
                  ? markets.map((m) => <SelectItem key={m.id} value={m.id}>{m.country}</SelectItem>)
                  : ALL_MARKETS.map((m) => <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Live Refresh" hint="How often dashboards re-fetch prices.">
            <Select value={String(prefs.refreshMs)} onValueChange={(v) => onPrefsChange({ refreshMs: Number(v) })}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REFRESH_OPTIONS.map((ms) => (
                  <SelectItem key={ms} value={String(ms)}>{ms / 1000}s</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <Field label="Display Currency" hint="All portfolio totals, charts and analytics show in this currency. Individual asset prices keep their native market currency.">
          <Select value={currency} onValueChange={applyCurrency}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DISPLAY_CURRENCIES.map((c) => (
                <SelectItem key={c.code} value={c.code}>{c.code} — {c.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field
          label="Display Timezone"
          hint="Timestamps across the app (including Investor Eye event times) render in this zone. The zone is always printed with the time."
        >
          <Select value={timeZone} onValueChange={applyTimeZone}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={browserTimeZone()}>Device timezone — {browserTimeZone()}</SelectItem>
              {DISPLAY_TIMEZONES.filter((t) => t.id !== browserTimeZone()).map((t) => (
                <SelectItem key={t.id} value={t.id}>{t.label} — {t.id}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </Panel>

      <Panel className="p-5 md:p-6 space-y-5">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground/80">
          <ShieldCheck className="w-4 h-4 text-primary shrink-0" />
          <span>Behavior &amp; Safety</span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <Label className="text-xs text-muted-foreground font-medium">Confirm before clearing data</Label>
            <p className="text-[10px] text-muted-foreground/70 mt-0.5">
              Ask first before wiping local chats, watchlist or portfolio from the Data &amp; Storage tab.
            </p>
          </div>
          <Toggle
            checked={general.confirmDestructive}
            onChange={(v) => updateGeneral({ confirmDestructive: v })}
          />
        </div>
      </Panel>

      <div className="flex justify-end">
        <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={resetAll}>
          <RotateCcw className="w-3.5 h-3.5 mr-1" /> Reset to defaults
        </Button>
      </div>
    </div>
  );
}
