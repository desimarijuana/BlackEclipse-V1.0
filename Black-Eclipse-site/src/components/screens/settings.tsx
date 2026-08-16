"use client";

import { useEffect, useState } from "react";
import {
  SlidersHorizontal, Bot, Globe2, Newspaper, Palette, Database,
  RefreshCw, Trash2, RotateCcw, Check, Eye, EyeOff, Activity, ShieldCheck,
  Save, Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TopLoader } from "@/components/ui/top-loader";
import { cn } from "@/lib/utils";

// ─── Types ──────────────────────────────────────────────────────────────

type LLMProviderName = "auto" | "openai" | "ollama" | "anthropic" | "mock";

interface LLMConfig {
  provider: LLMProviderName;
  baseUrl: string;
  apiKey: string;
  model: string;
}

interface NewsFeed {
  id: string;
  url: string;
  source: string;
  enabled: boolean;
}

interface AppPreferences {
  theme: "dark" | "light";
  defaultMarket: string;
  refreshMs: number;
}

interface IntegrationStatus {
  llm: { provider: string; model: string; configured: boolean };
  finnhub: boolean;
  binance: boolean;
  coingecko: boolean;
  yahoo: boolean;
  auth: boolean;
  database: boolean;
}

interface ScraperStatus {
  markets: string[];
  intervalMinutes: number;
  mode: "auto" | "off" | "manual";
  pageSize?: number;
  lastRunAt: string | null;
}

const ALL_MARKETS = [
  { id: "US", label: "United States" },
  { id: "PK", label: "Pakistan" },
  { id: "IN", label: "India" },
  { id: "CRYPTO", label: "Crypto" },
];

const INTERVALS = [5, 15, 30, 60];
const REFRESH_OPTIONS = [10000, 15000, 30000, 60000];

// ─── Helpers ────────────────────────────────────────────────────────────

function SettingSection({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-border/10 bg-card/40 p-5">
      <div className="flex items-center gap-2 mb-1">
        <Icon className="text-primary w-4 h-4 shrink-0" />
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
      </div>
      <p className="text-xs text-muted-foreground mb-4">{description}</p>
      {children}
    </div>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors cursor-pointer",
        checked ? "bg-primary/30 border-primary/40" : "bg-muted border-border"
      )}
    >
      <span
        className={cn(
          "inline-block h-3.5 w-3.5 transform rounded-full bg-primary transition-transform",
          checked ? "translate-x-[18px]" : "translate-x-[2px]"
        )}
      />
    </button>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────

export function Settings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // LLM
  const [llm, setLlm] = useState<LLMConfig>({
    provider: "auto", baseUrl: "https://api.openai.com/v1", apiKey: "", model: "gpt-4o-mini",
  });
  const [showApiKey, setShowApiKey] = useState(false);

  // News
  const [feeds, setFeeds] = useState<NewsFeed[]>([]);

  // Preferences
  const [prefs, setPrefs] = useState<AppPreferences>({ theme: "dark", defaultMarket: "US", refreshMs: 15000 });

  // Scraper
  const [markets, setMarkets] = useState<string[]>(["US"]);
  const [intervalMinutes, setIntervalMinutes] = useState(15);
  const [scraperMode, setScraperMode] = useState<"auto" | "off" | "manual">("auto");
  const [pageSize, setPageSize] = useState(20);
  const [lastRunAt, setLastRunAt] = useState<string | null>(null);

  // Integrations
  const [integrations, setIntegrations] = useState<IntegrationStatus | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [settingsRes, scraperRes] = await Promise.all([
        fetch("/api/settings"),
        fetch("/api/scraper"),
      ]);
      const s = await settingsRes.json();
      const sc = await scraperRes.json();

      if (s.llm) setLlm(s.llm);
      if (s.newsFeeds) setFeeds(s.newsFeeds);
      if (s.preferences) setPrefs(s.preferences);
      if (s.integrations) setIntegrations(s.integrations);

      if (sc) {
        if (sc.markets) setMarkets(sc.markets);
        if (sc.intervalMinutes) setIntervalMinutes(sc.intervalMinutes);
        if (sc.mode === "auto" || sc.mode === "off" || sc.mode === "manual") setScraperMode(sc.mode);
        if (sc.pageSize) setPageSize(sc.pageSize);
        setLastRunAt(sc.lastRunAt || null);
      }
    } catch (e) {
      setMessage("Failed to load settings. Is the server running?");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Save handlers ────────────────────────────────────────────────────

  const saveSettings = async (sections?: string[]) => {
    setSaving(true);
    setSaved(false);
    setMessage(null);
    try {
      const body: Record<string, unknown> = {};
      const should = (n: string) => !sections || sections.includes(n);

      if (should("llm")) body.llm = llm;
      if (should("feeds")) body.newsFeeds = feeds;
      if (should("prefs")) body.preferences = prefs;

      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (res.ok) {
        setSaved(true);
        setMessage("Settings saved.");
        setTimeout(() => setSaved(false), 2000);
      } else {
        setMessage(data.error || "Failed to save settings");
      }
    } catch (e) {
      setMessage("Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const saveScraper = async () => {
    setSaving(true);
    try {
      const res = await fetch("/api/cron", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ intervalMinutes, markets }),
      });
      await fetch("/api/scraper", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: { mode: scraperMode, pageSize } }),
      });
      if (res.ok) setMessage("Market data settings saved.");
    } finally {
      setSaving(false);
    }
  };

  // ── Data management ──────────────────────────────────────────────────

  const clearStorage = (keys: string[]) => {
    keys.forEach((k) => localStorage.removeItem(k));
    setMessage(`Cleared ${keys.length} local data item${keys.length > 1 ? "s" : ""}.`);
  };

  const applyTheme = (theme: "dark" | "light") => {
    setPrefs((p) => ({ ...p, theme }));
    document.documentElement.classList.toggle("dark", theme === "dark");
  };

  // ── Render ────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 md:px-8 py-8">
        <TopLoader />
        <div className="animate-pulse space-y-4">
          <div className="h-8 w-64 rounded-lg bg-muted/20" />
          <div className="h-32 w-full rounded-2xl bg-muted/10" />
          <div className="h-32 w-full rounded-2xl bg-muted/10" />
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-4xl mx-auto px-4 md:px-8 py-8 space-y-6 pb-20">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-border/10 pb-4">
        <SlidersHorizontal className="text-primary w-6 h-6" />
        <div>
          <h1 className="font-serif text-2xl font-semibold tracking-tight text-foreground">Settings</h1>
          <p className="text-muted-foreground text-xs mt-0.5">
            Control every aspect of BlackEclipse — AI agent, market data, news feeds, appearance, and data hygiene.
          </p>
        </div>
      </div>

      {/* Appearance & Preferences */}
      <SettingSection icon={Palette} title="Appearance & Preferences" description="Theme, default market, and live-data refresh cadence.">
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="flex flex-col gap-2">
            <Label>Theme</Label>
            <div className="flex gap-2">
              {(["dark", "light"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => applyTheme(t)}
                  className={cn(
                    "px-4 py-2 rounded-xl text-xs font-medium border transition-all cursor-pointer capitalize",
                    prefs.theme === t
                      ? "bg-accent text-foreground border-border/40"
                      : "bg-transparent text-muted-foreground border-border hover:text-foreground"
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Default Market</Label>
            <Select value={prefs.defaultMarket} onValueChange={(v) => setPrefs((p) => ({ ...p, defaultMarket: v ?? "US" }))}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ALL_MARKETS.map((m) => (
                  <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Live Refresh</Label>
            <Select value={String(prefs.refreshMs)} onValueChange={(v) => setPrefs((p) => ({ ...p, refreshMs: Number(v) }))}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REFRESH_OPTIONS.map((ms) => (
                  <SelectItem key={ms} value={String(ms)}>
                    {ms / 1000}s
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </SettingSection>

      {/* LLM / AI Agent */}
      <SettingSection icon={Bot} title="AI Agent Provider" description="Choose which model powers the chat and research agents.">
        <div className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:gap-4">
            <div className="flex-1">
              <Label>Provider</Label>
              <Select value={llm.provider} onValueChange={(v) => setLlm((p) => ({ ...p, provider: v as LLMProviderName }))}>
                <SelectTrigger className="w-full mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto (env) / Mock</SelectItem>
                  <SelectItem value="openai">OpenAI</SelectItem>
                  <SelectItem value="ollama">Ollama (local)</SelectItem>
                  <SelectItem value="anthropic">Anthropic</SelectItem>
                  <SelectItem value="mock">Mock (built-in)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1">
              <Label>Model</Label>
              <Input
                className="mt-1"
                value={llm.model}
                onChange={(e) => setLlm((p) => ({ ...p, model: e.target.value }))}
                placeholder="gpt-4o-mini / llama3.1"
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label>Base URL</Label>
            <Input
              value={llm.baseUrl}
              onChange={(e) => setLlm((p) => ({ ...p, baseUrl: e.target.value }))}
              placeholder="https://api.openai.com/v1"
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>API Key</Label>
            <div className="relative">
              <Input
                type={showApiKey ? "text" : "password"}
                value={llm.apiKey}
                onChange={(e) => setLlm((p) => ({ ...p, apiKey: e.target.value }))}
                placeholder={llm.provider === "mock" ? "Not required for mock" : "sk-..."}
              />
              <button
                onClick={() => setShowApiKey((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer p-1"
                type="button"
              >
                {showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            <p className="text-[10px] text-muted-foreground">
              Keys are stored in the local JDDS database, never in the frontend bundle.
            </p>
          </div>
        </div>
      </SettingSection>

      {/* Market Data & Scraper */}
      <SettingSection icon={Globe2} title="Market Data & Scraper" description="Configure which markets price_scraper crawls and how prices refresh.">
        <div className="space-y-5">
          <div>
            <Label className="mb-2 block">Markets to Scrape</Label>
            <div className="flex flex-wrap gap-2">
              {ALL_MARKETS.map((m) => {
                const active = markets.includes(m.id);
                return (
                  <button
                    key={m.id}
                    onClick={() =>
                      setMarkets((prev) =>
                        prev.includes(m.id) ? prev.filter((x) => x !== m.id) : [...prev, m.id]
                      )
                    }
                    className={cn(
                      "px-4 py-2 rounded-xl text-xs font-medium border transition-all cursor-pointer",
                      active
                        ? "bg-accent text-foreground border-border/40"
                        : "bg-transparent text-muted-foreground border-border hover:text-foreground"
                    )}
                  >
                    {m.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-2">
              <Label>Scraper Mode</Label>
              <Select value={scraperMode} onValueChange={(v) => setScraperMode(v as typeof scraperMode)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Auto</SelectItem>
                  <SelectItem value="manual">Manual</SelectItem>
                  <SelectItem value="off">Off</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label>Refresh Interval</Label>
              <Select value={String(intervalMinutes)} onValueChange={(v) => setIntervalMinutes(Number(v))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {INTERVALS.map((m) => (
                    <SelectItem key={m} value={String(m)}>Every {m} min</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label>Page Size</Label>
              <Select value={String(pageSize)} onValueChange={(v) => setPageSize(Number(v))}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[20, 50, 100].map((n) => (
                    <SelectItem key={n} value={String(n)}>{n} stocks/page</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-[10px] text-muted-foreground font-mono">
              {lastRunAt ? `Last run: ${new Date(lastRunAt).toLocaleTimeString()}` : "No scrape run yet"}
            </span>
            <Button variant="outline" size="sm" className="cursor-pointer" onClick={saveScraper} disabled={saving}>
              <RefreshCw className="w-4 h-4 mr-1" />
              Save Market Data
            </Button>
          </div>
        </div>
      </SettingSection>

      {/* News Feeds */}
      <SettingSection icon={Newspaper} title="News Feeds" description="Toggle which RSS sources feed the Market News bulletin.">
        <div className="space-y-2">
          {feeds.map((f) => (
            <div key={f.id} className="flex items-center justify-between gap-3 rounded-xl border border-border/10 px-3 py-2.5">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-2 h-2 rounded-full shrink-0" style={{ background: f.enabled ? "var(--primary)" : "var(--border)" }} />
                <div className="min-w-0">
                  <span className="text-xs font-medium text-foreground block">{f.source}</span>
                  <span className="text-[10px] text-muted-foreground block truncate max-w-[300px] font-mono">{f.url}</span>
                </div>
              </div>
              <Toggle
                checked={f.enabled}
                onChange={(v) => setFeeds((prev) => prev.map((x) => (x.id === f.id ? { ...x, enabled: v } : x)))}
              />
            </div>
          ))}
        </div>
      </SettingSection>

      {/* Integrations */}
      <SettingSection icon={ShieldCheck} title="Integrations & Status" description="Current connection status for external services.">
        <div className="grid gap-2 sm:grid-cols-2">
          {[
            { label: "AI Model", ok: integrations?.llm.configured, detail: integrations ? `${integrations.llm.provider} · ${integrations.llm.model}` : "—" },
            { label: "Finnhub", ok: integrations?.finnhub, detail: integrations?.finnhub ? "API key set" : "Not configured" },
            { label: "Binance", ok: integrations?.binance, detail: integrations?.binance ? "API key set" : "Not configured (public API used)" },
            { label: "CoinGecko", ok: integrations?.coingecko, detail: integrations?.coingecko ? "API key set" : "Not configured" },
            { label: "Yahoo Finance", ok: integrations?.yahoo, detail: integrations?.yahoo ? "Enabled" : "Disabled" },
            { label: "Auth", ok: integrations?.auth, detail: integrations?.auth ? "Configured" : "Guest mode" },
            { label: "Database (JDDS)", ok: integrations?.database, detail: "Connected" },
          ].map((row) => (
            <div key={row.label} className="flex items-center justify-between rounded-xl border border-border/10 px-3 py-2.5">
              <span className="text-xs text-foreground">{row.label}</span>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground">{row.detail}</span>
                <span
                  className={cn(
                    "w-2 h-2 rounded-full shrink-0",
                    row.ok ? "bg-primary" : "bg-muted-foreground/40"
                  )}
                />
              </div>
            </div>
          ))}
        </div>
      </SettingSection>

      {/* Data Management */}
      <SettingSection icon={Database} title="Data Management" description="Clear locally stored chats, watchlists, or portfolio data.">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => clearStorage(["chats_guest"])}>
            <Trash2 className="w-4 h-4 mr-1" /> Clear Chats
          </Button>
          <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => clearStorage(["watchlist_guest"])}>
            <Trash2 className="w-4 h-4 mr-1" /> Clear Watchlist
          </Button>
          <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => clearStorage(["portfolio_tx_guest", "portfolio_alerts_guest"])}>
            <Trash2 className="w-4 h-4 mr-1" /> Clear Portfolio
          </Button>
          <Button variant="outline" size="sm" className="cursor-pointer text-rose-400 hover:text-rose-300" onClick={() => clearStorage(["chats_guest", "watchlist_guest", "portfolio_tx_guest", "portfolio_alerts_guest"])}>
            <RotateCcw className="w-4 h-4 mr-1" /> Reset All Local Data
          </Button>
        </div>
      </SettingSection>

      {/* Save bar */}
      <div className="sticky bottom-0 -mx-4 px-4 py-3 bg-background/80 backdrop-blur-xl border-t border-border/10 flex items-center justify-between gap-3">
        {message ? (
          <span className="text-xs text-primary flex items-center gap-1.5">
            {saved && <Check className="w-3.5 h-3.5" />}
            {message}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5" /> Changes take effect immediately.
          </span>
        )}
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => fetchAll()}>
            <RotateCcw className="w-4 h-4 mr-1" /> Discard
          </Button>
          <Button size="sm" className="cursor-pointer" onClick={() => saveSettings()} disabled={saving}>
            <Save className="w-4 h-4 mr-1" />
            {saving ? "Saving..." : "Save All"}
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-center gap-2 text-[10px] text-muted-foreground pt-2">
        <Sparkles className="w-3 h-3" />
        BlackEclipse Settings · Powered by JDDS
      </div>
    </div>
  );
}
