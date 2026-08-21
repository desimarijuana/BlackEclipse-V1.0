"use client";

import { useEffect, useState } from "react";
import {
  SlidersHorizontal, Bot, Globe2, Newspaper, Palette, Database,
  Trash2, RotateCcw, Check, Eye, EyeOff, Activity, ShieldCheck,
  Save, Sparkles, ChevronRight, Cpu, Server, KeyRound,
  CircleDashed, RefreshCcw, Boxes,
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

interface MarketInfo {
  id: string;
  country: string;
  exchange: string;
  timezone: string;
  isCrypto: boolean;
  enabled: boolean;
  assetCount: number;
  pricedCount: number;
}

const ALL_MARKETS = [
  { id: "US", label: "United States" },
  { id: "PK", label: "Pakistan" },
  { id: "IN", label: "India" },
  { id: "CRYPTO", label: "Crypto" },
];

const REFRESH_OPTIONS = [10000, 15000, 30000, 60000];
type SectionId = "appearance" | "agent" | "market" | "news" | "integrations" | "data";

const PROVIDER_LABELS: Record<LLMProviderName, string> = {
  auto: "Auto (env) / Mock",
  openai: "OpenAI",
  ollama: "Ollama (local)",
  anthropic: "Anthropic",
  mock: "Mock (built-in)",
};

// ─── Small building blocks ──────────────────────────────────────────────

function Panel({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/10 dark:border-white/5 bg-white/50 dark:bg-[#0f0f0f]/40 backdrop-blur-xl overflow-hidden",
        className
      )}
    >
      {children}
    </div>
  );
}

function SectionHeader({
  icon: Icon,
  title,
  description,
  eyebrow,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  eyebrow?: string;
}) {
  return (
    <div className="mb-6">
      {eyebrow && (
        <p className="text-[10px] uppercase tracking-[0.2em] text-primary font-bold mb-2 flex items-center gap-1.5">
          <Sparkles size={11} /> {eyebrow}
        </p>
      )}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 shadow-sm shadow-primary/10">
          <Icon className="text-primary w-[18px] h-[18px]" />
        </div>
        <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">{title}</h2>
      </div>
      <p className="text-xs text-muted-foreground mt-2 leading-relaxed max-w-lg">{description}</p>
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

function Chip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border",
        className
      )}
    >
      {children}
    </span>
  );
}

function StatusDot({ ok }: { ok: boolean | undefined }) {
  return (
    <span
      className={cn(
        "inline-block w-2 h-2 rounded-full shrink-0",
        ok ? "bg-primary shadow-[0_0_8px] shadow-primary/60" : "bg-muted-foreground/40"
      )}
    />
  );
}

// ─── Main Component ─────────────────────────────────────────────────────

export function Settings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [section, setSection] = useState<SectionId>("appearance");

  // LLM
  const [llm, setLlm] = useState<LLMConfig>({
    provider: "auto", baseUrl: "https://api.openai.com/v1", apiKey: "", model: "gpt-4o-mini",
  });
  const [showApiKey, setShowApiKey] = useState(false);

  // News
  const [feeds, setFeeds] = useState<NewsFeed[]>([]);

  // Preferences
  const [prefs, setPrefs] = useState<AppPreferences>({ theme: "dark", defaultMarket: "US", refreshMs: 15000 });

  // Market data (loaded from JDDS)
  const [markets, setMarkets] = useState<MarketInfo[]>([]);
  const [selectedMarkets, setSelectedMarkets] = useState<string[]>(["US"]);

  // Integrations
  const [integrations, setIntegrations] = useState<IntegrationStatus | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [settingsRes, marketsRes] = await Promise.all([
        fetch("/api/settings"),
        fetch("/api/markets"),
      ]);
      const s = await settingsRes.json();
      const m = await marketsRes.json();

      if (s.llm) setLlm(s.llm);
      if (s.newsFeeds) setFeeds(s.newsFeeds);
      if (s.preferences) setPrefs(s.preferences);
      if (s.integrations) setIntegrations(s.integrations);

      if (Array.isArray(m.markets)) {
        setMarkets(m.markets);
        const enabled = m.markets.filter((mk: MarketInfo) => mk.enabled).map((mk: MarketInfo) => mk.id);
        if (enabled.length > 0) setSelectedMarkets(enabled);
      }
    } catch {
      setMessage("Failed to load settings. Is the server running?");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, []);

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
    } catch {
      setMessage("Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const clearStorage = (keys: string[]) => {
    keys.forEach((k) => localStorage.removeItem(k));
    setMessage(`Cleared ${keys.length} local data item${keys.length > 1 ? "s" : ""}.`);
  };

  const applyTheme = (theme: "dark" | "light") => {
    setPrefs((p) => ({ ...p, theme }));
    document.documentElement.classList.toggle("dark", theme === "dark");
  };

  if (loading) {
    return (
      <div className="w-full h-full flex items-center justify-center p-8">
        <TopLoader />
        <div className="animate-pulse space-y-4 w-full max-w-md">
          <div className="h-9 w-52 rounded-2xl bg-muted/15" />
          <div className="h-44 w-full rounded-2xl bg-muted/5 border border-white/5" />
          <div className="h-44 w-full rounded-2xl bg-muted/5 border border-white/5" />
        </div>
      </div>
    );
  }

  const NAV: { id: SectionId; label: string; desc: string; icon: React.ElementType }[] = [
    { id: "appearance", label: "Appearance", desc: "Theme & refresh", icon: Palette },
    { id: "agent", label: "AI Agent", desc: "Provider & model", icon: Bot },
    { id: "market", label: "Market Data", desc: "Active markets", icon: Globe2 },
    { id: "news", label: "News Feeds", desc: "RSS sources", icon: Newspaper },
    { id: "integrations", label: "Integrations", desc: "Service status", icon: ShieldCheck },
    { id: "data", label: "Data", desc: "Local storage", icon: Database },
  ];

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Left nav rail */}
      <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-border/10 bg-white/40 dark:bg-[#0f0f0f]/30 backdrop-blur-xl">
        <div className="flex items-center gap-3 px-5 h-16 border-b border-border/10">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center text-primary-foreground shadow-sm shadow-primary/20">
            <SlidersHorizontal size={16} />
          </div>
          <div>
            <p className="font-serif text-sm font-semibold leading-none text-foreground">Settings</p>
            <p className="text-[10px] text-muted-foreground mt-1 tracking-wide">BlackEclipse Console</p>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto scrollbar-hide p-3 space-y-1.5">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = section === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setSection(item.id)}
                className={cn(
                  "w-full flex items-center justify-between gap-2 px-3 py-2.5 rounded-xl text-xs font-medium transition-all cursor-pointer border",
                  active
                    ? "bg-primary/10 text-foreground border-primary/25 shadow-sm shadow-primary/5"
                    : "text-muted-foreground border-transparent hover:bg-accent/50 hover:text-foreground hover:border-border/20"
                )}
              >
                <span className="flex items-center gap-3 min-w-0">
                  <Icon size={15} className={cn("shrink-0", active ? "text-primary" : "text-muted-foreground")} />
                  <span className="flex flex-col items-start leading-tight">
                    <span>{item.label}</span>
                    <span className="text-[9px] text-muted-foreground font-normal tracking-wide hidden lg:block">{item.desc}</span>
                  </span>
                </span>
                {active && <ChevronRight size={13} className="text-primary shrink-0" />}
              </button>
            );
          })}
        </nav>

        <div className="p-4 border-t border-border/10">
          <p className="text-[10px] text-muted-foreground flex items-center gap-1.5">
            <Sparkles size={11} className="text-primary" /> Powered by JDDS
          </p>
        </div>
      </aside>

      {/* Right content */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 overflow-y-auto scrollbar-hide p-5 md:p-8">
          <div className="max-w-3xl mx-auto">
            {section === "appearance" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  eyebrow="Personalize"
                  icon={Palette}
                  title="Appearance & Preferences"
                  description="Tailor the interface theme, default market, and how frequently live data refreshes."
                />
                <Panel className="p-5 md:p-6 space-y-5">
                  <Field label="Theme">
                    <div className="grid grid-cols-2 gap-2">
                      {(["dark", "light"] as const).map((t) => (
                        <button
                          key={t}
                          onClick={() => applyTheme(t)}
                          className={cn(
                            "flex items-center justify-center gap-2 px-4 py-2.5 text-xs font-medium rounded-xl border transition-all cursor-pointer capitalize",
                            prefs.theme === t
                              ? "bg-primary/10 text-primary border-primary/40 shadow-sm shadow-primary/10"
                              : "bg-transparent text-muted-foreground border-border/40 hover:text-foreground hover:border-border"
                          )}
                        >
                          <span
                            className={cn(
                              "w-3 h-3 rounded-full border-2",
                              prefs.theme === t ? "border-primary bg-primary" : "border-muted-foreground/50"
                            )}
                          />
                          {t}
                        </button>
                      ))}
                    </div>
                  </Field>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Default Market">
                      <Select value={prefs.defaultMarket} onValueChange={(v) => setPrefs((p) => ({ ...p, defaultMarket: v ?? "US" }))}>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {markets.length > 0
                            ? markets.map((m) => (
                                <SelectItem key={m.id} value={m.id}>{m.country}</SelectItem>
                              ))
                            : ALL_MARKETS.map((m) => (
                                <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>
                              ))}
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label="Live Refresh" hint="How often dashboards re-fetch prices.">
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
                    </Field>
                  </div>
                </Panel>
              </div>
            )}

            {section === "agent" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  eyebrow="Intelligence"
                  icon={Bot}
                  title="AI Agent Provider"
                  description="Choose which model powers the chat and research agents that drive your market analysis."
                />
                <Panel className="p-5 md:p-6 space-y-5">
                  <div className="flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3">
                    <Cpu className="text-primary w-4 h-4 shrink-0" />
                    <p className="text-[11px] text-foreground/80 leading-relaxed">
                      {PROVIDER_LABELS[llm.provider]} —{" "}
                      <span className="font-mono text-primary">{llm.model}</span>
                    </p>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Provider">
                      <Select value={llm.provider} onValueChange={(v) => setLlm((p) => ({ ...p, provider: v as LLMProviderName }))}>
                        <SelectTrigger className="w-full">
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
                    </Field>
                    <Field label="Model">
                      <Input
                        value={llm.model}
                        onChange={(e) => setLlm((p) => ({ ...p, model: e.target.value }))}
                        placeholder="gpt-4o-mini / llama3.1"
                        className="font-mono"
                      />
                    </Field>
                  </div>

                  <Field label="Base URL" hint="Endpoint used for OpenAI-compatible APIs.">
                    <div className="relative">
                      <Server className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5" />
                      <Input
                        value={llm.baseUrl}
                        onChange={(e) => setLlm((p) => ({ ...p, baseUrl: e.target.value }))}
                        placeholder="https://api.openai.com/v1"
                        className="pl-8 font-mono"
                      />
                    </div>
                  </Field>

                  <Field label="API Key" hint="Keys are stored in the local JDDS database, never in the frontend bundle.">
                    <div className="relative">
                      <KeyRound className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5" />
                      <Input
                        type={showApiKey ? "text" : "password"}
                        value={llm.apiKey}
                        onChange={(e) => setLlm((p) => ({ ...p, apiKey: e.target.value }))}
                        placeholder={llm.provider === "mock" ? "Not required for mock" : "sk-..."}
                        className="pl-8 pr-9 font-mono"
                      />
                      <button
                        onClick={() => setShowApiKey((v) => !v)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-primary cursor-pointer p-1 rounded-md hover:bg-primary/10"
                        type="button"
                      >
                        {showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </Field>
                </Panel>
              </div>
            )}

            {section === "market" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  eyebrow="Coverage"
                  icon={Globe2}
                  title="Market Data"
                  description="Choose which markets loaded in JDDS are surfaced across the site."
                />
                {markets.length === 0 ? (
                  <Panel className="p-8 text-center">
                    <Boxes className="mx-auto text-muted-foreground w-8 h-8 mb-3" />
                    <p className="text-xs text-muted-foreground">
                      No markets found in JDDS yet. Import or scrape market data to populate the database.
                    </p>
                  </Panel>
                ) : (
                  <div className="space-y-2.5">
                    {markets.map((m) => {
                      const active = selectedMarkets.includes(m.id);
                      return (
                        <button
                          key={m.id}
                          onClick={() =>
                            setSelectedMarkets((prev) =>
                              prev.includes(m.id) ? prev.filter((x) => x !== m.id) : [...prev, m.id]
                            )
                          }
                          className={cn(
                            "w-full flex items-center justify-between gap-3 py-3.5 px-4 rounded-xl border transition-all cursor-pointer text-left group",
                            active
                              ? "bg-primary/10 border-primary/40 shadow-sm shadow-primary/10"
                              : "bg-white/40 dark:bg-[#0f0f0f]/30 border-border/20 hover:border-border/40 hover:bg-accent/30"
                          )}
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <div
                              className={cn(
                                "w-5 h-5 rounded-md border-2 shrink-0 flex items-center justify-center transition-colors",
                                active ? "border-primary bg-primary/20" : "border-border/50"
                              )}
                            >
                              {active && <Check className="text-primary w-3 h-3" />}
                            </div>
                            <div className="min-w-0">
                              <span className="text-xs font-semibold text-foreground flex items-center gap-2">
                                {m.country}
                                {m.isCrypto && (
                                  <Chip className="text-primary bg-primary/10 border-primary/20 uppercase tracking-widest">Crypto</Chip>
                                )}
                              </span>
                              <span className="text-[10px] text-muted-foreground block truncate font-mono">
                                {m.exchange} · {m.assetCount} assets · {m.pricedCount} priced
                              </span>
                            </div>
                          </div>
                          <Chip
                            className={cn(
                              "shrink-0",
                              active
                                ? "text-primary bg-primary/10 border-primary/20"
                                : "text-muted-foreground bg-muted/40 border-transparent"
                            )}
                          >
                            {active ? "Showing" : "Hidden"}
                          </Chip>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {section === "news" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  eyebrow="Bulletins"
                  icon={Newspaper}
                  title="News Feeds"
                  description="Toggle which RSS sources feed the Market News bulletin."
                />
                <Panel className="divide-y divide-border/10">
                  {feeds.map((f) => (
                    <div key={f.id} className="flex items-center justify-between gap-3 px-5 py-4">
                      <div className="flex items-center gap-3 min-w-0">
                        <span
                          className={cn(
                            "w-2.5 h-2.5 rounded-full shrink-0",
                            f.enabled ? "bg-primary shadow-[0_0_8px] shadow-primary/60" : "bg-border"
                          )}
                        />
                        <div className="min-w-0">
                          <span className="text-xs font-medium text-foreground block">{f.source}</span>
                          <span className="text-[10px] text-muted-foreground block truncate max-w-[260px] font-mono">{f.url}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className={cn("text-[10px] font-semibold hidden sm:block", f.enabled ? "text-primary" : "text-muted-foreground")}>
                          {f.enabled ? "Live" : "Paused"}
                        </span>
                        <Toggle
                          checked={f.enabled}
                          onChange={(v) => setFeeds((prev) => prev.map((x) => (x.id === f.id ? { ...x, enabled: v } : x)))}
                        />
                      </div>
                    </div>
                  ))}
                </Panel>
              </div>
            )}

            {section === "integrations" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  eyebrow="Connectivity"
                  icon={ShieldCheck}
                  title="Integrations & Status"
                  description="Live connection status for every external service powering BlackEclipse."
                />
                <Panel className="divide-y divide-border/10">
                  {[
                    { label: "AI Model", ok: integrations?.llm.configured, detail: integrations ? `${integrations.llm.provider} · ${integrations.llm.model}` : "—" },
                    { label: "Finnhub", ok: integrations?.finnhub, detail: integrations?.finnhub ? "API key set" : "Not configured" },
                    { label: "Binance", ok: integrations?.binance, detail: integrations?.binance ? "API key set" : "Not configured (public API used)" },
                    { label: "CoinGecko", ok: integrations?.coingecko, detail: integrations?.coingecko ? "API key set" : "Not configured" },
                    { label: "Yahoo Finance", ok: integrations?.yahoo, detail: integrations?.yahoo ? "Enabled" : "Disabled" },
                    { label: "Auth", ok: integrations?.auth, detail: integrations?.auth ? "Configured" : "Guest mode" },
                    { label: "Database (JDDS)", ok: integrations?.database, detail: "Connected" },
                  ].map((row) => (
                    <div key={row.label} className="flex items-center justify-between gap-3 px-5 py-3.5 hover:bg-accent/20 transition-colors">
                      <span className="text-xs text-foreground">{row.label}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-muted-foreground font-mono">{row.detail}</span>
                        <StatusDot ok={row.ok} />
                      </div>
                    </div>
                  ))}
                </Panel>
              </div>
            )}

            {section === "data" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  eyebrow="Hygiene"
                  icon={Database}
                  title="Data Management"
                  description="Clear locally stored chats, watchlists, or portfolio data from this device."
                />
                <Panel className="p-5 md:p-6">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Button variant="outline" size="sm" className="cursor-pointer justify-start rounded-xl" onClick={() => clearStorage(["chats_guest"])}>
                      <Trash2 className="w-4 h-4 mr-1" /> Clear Chats
                    </Button>
                    <Button variant="outline" size="sm" className="cursor-pointer justify-start rounded-xl" onClick={() => clearStorage(["watchlist_guest"])}>
                      <Trash2 className="w-4 h-4 mr-1" /> Clear Watchlist
                    </Button>
                    <Button variant="outline" size="sm" className="cursor-pointer justify-start rounded-xl" onClick={() => clearStorage(["portfolio_tx_guest", "portfolio_alerts_guest"])}>
                      <Trash2 className="w-4 h-4 mr-1" /> Clear Portfolio
                    </Button>
                    <Button variant="outline" size="sm" className="cursor-pointer justify-start rounded-xl text-rose-400 hover:text-rose-300 hover:border-rose-500/40 hover:bg-rose-500/10" onClick={() => clearStorage(["chats_guest", "watchlist_guest", "portfolio_tx_guest", "portfolio_alerts_guest"])}>
                      <RotateCcw className="w-4 h-4 mr-1" /> Reset All Local Data
                    </Button>
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-4 flex items-center gap-1.5">
                    <CircleDashed className="w-3 h-3" /> Cleared data is removed from this browser only.
                  </p>
                </Panel>
              </div>
            )}
          </div>
        </div>

        {/* Save bar */}
        <div className="shrink-0 border-t border-border/10 bg-white/50 dark:bg-[#0f0f0f]/40 backdrop-blur-xl px-6 md:px-8 py-3 flex items-center justify-between gap-3">
          {message ? (
            <span className="text-xs text-primary flex items-center gap-1.5">
              {saved && <Check className="w-3.5 h-3.5" />}
              {message}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-primary" /> Changes take effect immediately.
            </span>
          )}
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={() => fetchAll()}>
              <RefreshCcw className="w-4 h-4 mr-1" /> Discard
            </Button>
            <Button size="sm" className="cursor-pointer rounded-xl" onClick={() => saveSettings()} disabled={saving}>
              <Save className="w-4 h-4 mr-1" />
              {saving ? "Saving..." : "Save All"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
