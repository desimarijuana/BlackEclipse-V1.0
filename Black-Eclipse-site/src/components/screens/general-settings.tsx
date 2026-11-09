"use client";

// ── General settings panel ────────────────────────────────────────────────
// The "General" tab of the merged General/Customization surface. Grouped into
// titled sections so related preferences sit together instead of one long mix:
//
//   * Startup & Display — which screen the app opens on (start screen), the
//     server-backed default market / refresh interval and the local-only
//     display currency / timezone.
//   * Live Data         — how often dashboards re-fetch prices.
//   * Safety            — destructive-action confirmation (localStorage via
//     `general-prefs`).
//
// The ChatBot page backdrop/wordmark now lives on Customization › ChatBot Page.
//
// It is self-contained: the parent passes the values it already fetched and a
// persist callback, keeping the merge additive and the parent shell thin.

import { useEffect, useState } from "react";
import { Loader2, Monitor, RefreshCcw, RotateCcw, ShieldCheck, Sparkles } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DISPLAY_CURRENCIES, getDisplayCurrency, setDisplayCurrency } from "@/lib/currency";
import { DISPLAY_TIMEZONES, browserTimeZone, getDisplayTimeZone, isValidTimeZone, setDisplayTimeZone } from "@/lib/timezone";
import { HEATMAP_MARKETS } from "@/lib/heatmap";
import {
  DEFAULT_GENERAL_PREFS, START_SCREEN_OPTIONS, loadGeneralPrefs, saveGeneralPrefs,
  type GeneralPrefs, type StartScreen,
} from "@/lib/general-prefs";
import { Field, Panel, SubSection, Toggle } from "./settings-ui";

export interface GeneralAppPreferences {
  defaultMarket: string;
  refreshMs: number;
}

// Fallback market list, used only when /api/markets has not answered yet. It is
// the full supported universe (not a hardcoded few) so the selector is never
// silently narrowed to 4 markets.
const ALL_MARKETS = HEATMAP_MARKETS.map((m) => ({ id: m.id, label: m.country }));

const REFRESH_OPTIONS = [10000, 15000, 30000, 60000];

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

  const [setupBusy, setSetupBusy] = useState(false);
  const restartOnboarding = async () => {
    if (general.confirmDestructive) {
      const ok = window.confirm(
        "Open the Eclipse setup questions again? Your API keys, chats and portfolio are kept.",
      );
      if (!ok) return;
    }
    setSetupBusy(true);
    try {
      const res = await fetch("/api/setup/reset", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ scope: "onboarding" }),
      });
      const data = (await res.json()) as { reload?: string; error?: string };
      if (!res.ok) throw new Error(data.error || "Could not restart setup");
      window.location.assign(data.reload || "/?setup=1");
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Could not restart setup");
      setSetupBusy(false);
    }
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
    <div className="animate-fade-in-up space-y-6">
      {/* Startup & Display — how the app opens and renders values. */}
      <SubSection icon={Monitor} title="Startup & Display">
        <Panel className="p-5 md:p-6 space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Start screen" hint="Which screen the app opens on. “Last screen” resumes where you left off.">
              <Select
                value={general.startScreen}
                onValueChange={(v) => v && updateGeneral({ startScreen: v as StartScreen })}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {START_SCREEN_OPTIONS.map((s) => (
                    <SelectItem key={s.id} value={s.id}>{s.label} — {s.hint}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
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
      </SubSection>

      {/* Live Data — polling cadence for dashboards. */}
      <SubSection icon={RefreshCcw} title="Live Data">
        <Panel className="p-5 md:p-6">
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
        </Panel>
      </SubSection>

      {/* Setup — re-run the first-run questions without touching data. */}
      <SubSection icon={Sparkles} title="Setup">
        <Panel className="p-5 md:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <Label className="text-xs text-muted-foreground font-medium">Run setup again</Label>
              <p className="text-[10px] text-muted-foreground/70 mt-0.5">
                Reopens the welcome, AI and data questions. Keys, chats, portfolio and research
                are kept; you can change any answer.
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="cursor-pointer rounded-xl"
              disabled={setupBusy}
              onClick={() => void restartOnboarding()}
            >
              {setupBusy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              Run setup again
            </Button>
          </div>
        </Panel>
      </SubSection>

      {/* Safety — destructive-action guardrails. */}
      <SubSection icon={ShieldCheck} title="Behavior & Safety">
        <Panel className="p-5 md:p-6">
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
      </SubSection>

      {/* Background + landing wordmark moved to Customization › ChatBot Page,
          alongside the conversation font, so every ChatBot-page look lives in
          one place. */}

      <div className="flex justify-end">
        <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={resetAll}>
          <RotateCcw className="w-3.5 h-3.5 mr-1" /> Reset General to defaults
        </Button>
      </div>
    </div>
  );
}
