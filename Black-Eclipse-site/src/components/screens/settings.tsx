"use client";

// TODO(P2, deferred): this file is the Settings shell plus the inline bodies
// for General / AI / Investor Eye / Economics / Market / News / Data / System
// (~1180 lines). Those bodies depend on parent state (llm, prefs, feeds,
// markets, integrations) so splitting them cleanly means lifting that state
// into a context/provider. Low risk to leave; deferred to avoid a rushed
// refactor. Already-extracted panels live in their own files (aurora-settings,
// chart-settings, sidebar-settings, alert-notifications-settings,
// provider-registry-panel, data-sources-panel).

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Cog, Bot, Globe2, Newspaper, Palette, Database,
  Trash2, RotateCcw, Check, Activity, ShieldCheck,
  ChevronRight, Cpu, Server,
  CircleDashed, RefreshCcw, Boxes, PanelLeft, Eye as EyeIcon,
  Loader2, Search, AlertCircle, Volume2, BarChart3,
  GitBranch, Plug,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { GitPanel } from "./git-panel";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { TopLoader } from "@/components/ui/top-loader";
import { cn } from "@/lib/utils";
import { AlertNotificationsPanel } from "./alert-notifications-settings";
import { AnalyticsSettingsPanel } from "./analytics-settings";
import { SidebarSettingsPanel } from "./sidebar-settings";
import { DataSourcesPanel } from "./data-sources-panel";
import { MCPSettingsPanel } from "./mcp-settings";
import { CustomizationSettingsPanel } from "./customization-settings";
import { GeneralSettingsPanel } from "./general-settings";
import { SoundSettingsPanel } from "./sound-settings";
import { ProviderRegistry, InvestorEyeFeatureMap, InvestorEyeSources, SettingsStatusHeader, ProviderKeyEditor, useProviderHealth } from "./provider-registry-panel";
import { LLM_PRESETS, presetForBaseUrl, isLocalBaseUrl } from "@/lib/agent/presets";
import { useModelCatalog, modelsForProvider } from "@/lib/agent/model-catalog";
import { getUserMarket, setUserMarket } from "@/lib/user-market";
import { sound } from "@/lib/sounds";
import {
  DEFAULT_GENERAL_PREFS, loadGeneralPrefs,
  type GeneralPrefs,
} from "@/lib/general-prefs";


// ─── Types ──────────────────────────────────────────────────────────────

type LLMProviderName = "auto" | "openai" | "ollama" | "anthropic" | "mock";

interface LLMConfig {
  provider: LLMProviderName;
  baseUrl: string;
  apiKey: string;
  model: string;
  /** Server reports whether a key is stored; the raw key is never sent back. */
  hasApiKey?: boolean;
  /**
   * Optional operator-declared context window (tokens). Used only when the
   * runtime catalog cannot resolve one; `null`/undefined means "unknown" and
   * clears any prior declaration.
   */
  contextWindow?: number | null;
}

interface NewsFeed {
  id: string;
  url: string;
  source: string;
  enabled: boolean;
}

interface AppPreferences {
  defaultMarket: string;
  refreshMs: number;
}

interface IntegrationStatus {
  llm: { provider: string; model: string; configured: boolean };
  // Only integrations actually wired at runtime — mirrors
  // `getIntegrationsStatus()` in `src/lib/settings.ts`.
  yahoo: boolean;
  fred: boolean;
  bea: boolean;
  bls: boolean;
  tradingEconomics: boolean;
  akshare: boolean;
  database: boolean;
  /** Env var → is it set. Drives honest per-provider key status. */
  envFlags: Record<string, boolean>;
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

// The Settings information architecture. Sections are named for WHAT the user
// is configuring, never for how the backend is implemented:
//   general        — startup + behavior, plus the full theme/customization tabs
//   sound          — UI audio feedback
//   ai             — every LLM: providers, keys, base URLs, model, test
//   investor-eye   — every financial/data provider, grouped by purpose
//   market         — supported markets, exchanges, JDDS data
//   news           — RSS feeds + news providers
//   sidebar        — navigation order & shortcuts
//   alerts         — notification channels
//   data           — local chats/watchlist/portfolio + reset
//   system         — JDDS status, health, internal integrations
export type SectionId =
  | "general" | "sound" | "ai" | "investor-eye" | "economics" | "market" | "news"
  | "analytics" | "sidebar" | "alerts" | "data" | "git" | "mcp" | "system";

/** Valid settings sub-view ids, for the palette's settings sub-pages. */
export const SETTINGS_SECTIONS: readonly SectionId[] = [
  "general", "sound", "ai", "investor-eye", "economics", "market", "news",
  "analytics", "sidebar", "alerts", "data", "git", "mcp", "system",
] as const;

/**
 * Legacy section ids still arriving from saved subroutes / deep links. The
 * standalone `customization` section was folded into `general`; route its old
 * id to the merged section rather than rendering an empty pane.
 */
const LEGACY_SECTION_ALIASES: Record<string, SectionId> = { customization: "general" };

function resolveSection(raw: string | undefined): SectionId {
  if (!raw) return "general";
  if (raw in LEGACY_SECTION_ALIASES) return LEGACY_SECTION_ALIASES[raw];
  return (SETTINGS_SECTIONS as readonly string[]).includes(raw) ? (raw as SectionId) : "general";
}
const PROVIDER_LABELS: Record<LLMProviderName, string> = {
  auto: "Auto (env)",
  openai: "OpenAI-compatible endpoint",
  ollama: "Ollama (local)",
  anthropic: "Anthropic",
  mock: "Mock (offline)",
};

// ─── Small building blocks ──────────────────────────────────────────────

function Panel({
  className,
  children,
  ...rest
}: {
  className?: string;
  children: React.ReactNode;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/10 dark:border-white/5 glass-card overflow-hidden",
        className
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

function SectionHeader({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
}) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
          <Icon className="text-primary" size={22} />
        </span>
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

export function Settings({
  initialSection,
  initialAnchor,
}: {
  initialSection?: SectionId;
  /** Optional block id to scroll to once mounted (e.g. "priority"). */
  initialAnchor?: string;
} = {}) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // Transient result toast shown in the footer status area.
  const [toast, setToast] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [section, setSection] = useState<SectionId>(resolveSection(initialSection));
  const [query, setQuery] = useState("");

  // LLM
  const [llm, setLlm] = useState<LLMConfig>({
    provider: "auto", baseUrl: "https://api.openai.com/v1", apiKey: "", model: "gpt-4o-mini",
    contextWindow: undefined,
  });
  const [testingLlm, setTestingLlm] = useState(false);
  const [llmTest, setLlmTest] = useState<{ ok: boolean; message: string; latencyMs?: number } | null>(null);
  // Declared model ids per provider, from the Python runtime catalog (a
  // convenience list, never an allowlist — a custom id is always typeable).
  const modelCatalog = useModelCatalog();

  // News
  const [feeds, setFeeds] = useState<NewsFeed[]>([]);

  // Preferences (server-backed: default market + refresh interval)
  const [prefs, setPrefs] = useState<AppPreferences>({ defaultMarket: "US", refreshMs: 15000 });

  // General preferences (localStorage, presentation-layer): start screen and
  // whether destructive local-data clears need confirmation. The merged General
  // tab owns the start screen control; this shell only needs `confirmDestructive`
  // to gate the Data & Storage clears, so it reads (never writes) the prefs.
  const [general, setGeneral] = useState<GeneralPrefs>(DEFAULT_GENERAL_PREFS);
  useEffect(() => {
    setGeneral(loadGeneralPrefs());
  }, []);

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

      if (s.llm) {
        // The server masks the stored key — keep the local input empty but
        // remember that a key exists so the placeholder can show it.
        setLlm({ ...s.llm, apiKey: "" });
      }
      if (s.newsFeeds) setFeeds(s.newsFeeds);
      if (s.preferences) {
        setPrefs(s.preferences);
        // Seed the shared market preference from the saved default, but never
        // override a market the user already picked on a market surface.
        if (s.preferences.defaultMarket && !getUserMarket()) {
          setUserMarket(s.preferences.defaultMarket);
        }
      }
      if (s.integrations) setIntegrations(s.integrations);

      if (Array.isArray(m.markets)) {
        setMarkets(m.markets);
        const enabled = m.markets.filter((mk: MarketInfo) => mk.enabled).map((mk: MarketInfo) => mk.id);
        if (enabled.length > 0) setSelectedMarkets(enabled);
      }
    } catch {
      setToast({ kind: "error", text: "Failed to load settings. Is the server running?" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, []);

  /**
   * Persist a partial settings payload. Every server-backed control applies
   * instantly (there is no Save button), so this is called on change — debounced
   * by the callers below to coalesce rapid keystrokes/toggles. It reports the
   * real result via the transient toast and never claims success on failure.
   */
  const persist = useCallback(async (body: Record<string, unknown>) => {
    setSaving(true);
    setToast(null);
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setToast({ kind: "error", text: data.error || "Failed to save" });
        sound.error();
        return;
      }
      if (data.llm) setLlm({ ...data.llm, apiKey: "" });
      if (Array.isArray(data.newsFeeds)) setFeeds(data.newsFeeds);
      if (data.preferences) setPrefs(data.preferences);
      setToast({ kind: "ok", text: "Saved" });
      sound.success();
    } catch {
      setToast({ kind: "error", text: "Failed to save" });
      sound.error();
    } finally {
      setSaving(false);
    }
  }, []);

  // Debounced preference persistence (currency/timezone are local-only, but
  // theme/market/refresh live server-side). One timer coalesces rapid changes.
  const persistTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queuePrefs = useCallback(
    (next: AppPreferences) => {
      if (persistTimer.current) clearTimeout(persistTimer.current);
      persistTimer.current = setTimeout(() => void persist({ preferences: next }), 500);
    },
    [persist],
  );
  useEffect(() => () => {
    if (persistTimer.current) clearTimeout(persistTimer.current);
  }, []);

  const updatePrefs = (patch: Partial<AppPreferences>) => {
    setPrefs((p) => {
      const next = { ...p, ...patch };
      queuePrefs(next);
      return next;
    });
  };

  // LLM config persists on change too, debounced so typing a model id or key
  // does not fire a request per keystroke. The server keeps the stored key when
  // `apiKey` is blank, so a masked field never wipes it.
  const llmTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (llmTimer.current) clearTimeout(llmTimer.current);
  }, []);
  const updateLlm = (patch: Partial<LLMConfig>, debounce = 600) => {
    setLlm((p) => {
      const next = { ...p, ...patch };
      if (llmTimer.current) clearTimeout(llmTimer.current);
      llmTimer.current = setTimeout(() => void persist({ llm: next }), debounce);
      return next;
    });
  };

  // Auto-dismiss a success toast after a beat; keep errors until replaced.
  useEffect(() => {
    if (!toast || toast.kind === "error") return;
    const t = setTimeout(() => setToast(null), 2200);
    return () => clearTimeout(t);
  }, [toast]);
  const clearStorage = (keys: string[], label: string) => {
    // Confirmation is on by default (Settings › General). A mis-click here used
    // to wipe chats/watchlist/portfolio instantly and irreversibly.
    if (general.confirmDestructive && typeof window !== "undefined") {
      const ok = window.confirm(`Clear ${label}? This only affects this browser and cannot be undone.`);
      if (!ok) return;
    }
    keys.forEach((k) => localStorage.removeItem(k));
    setToast({ kind: "ok", text: `Cleared ${keys.length} local data item${keys.length > 1 ? "s" : ""}.` });
  };

  // Test the current LLM config against the live endpoint. The in-progress
  // values are sent with the request, so it tests what the field shows even if
  // the debounced save has not landed yet.
  const testLlm = async () => {
    setTestingLlm(true);
    setLlmTest(null);
    try {
      const res = await fetch("/api/agent/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ baseUrl: llm.baseUrl, model: llm.model }),
      });
      const data = (await res.json()) as { ok: boolean; message: string; latencyMs?: number; error?: string };
      setLlmTest(data.error ? { ok: false, message: data.error } : { ok: data.ok, message: data.message, latencyMs: data.latencyMs });
    } catch {
      setLlmTest({ ok: false, message: "Test request failed" });
    } finally {
      setTestingLlm(false);
    }
  };

  // Rail items carry extra `terms` so the search box can match the words a
  // user would actually type ("dark", "key", "fred", "rss") — not just labels.
  const NAV: {
    id: SectionId;
    label: string;
    desc: string;
    icon: React.ElementType;
    group: "Personalize" | "Intelligence" | "System";
    terms: string[];
  }[] = [
    { id: "general", label: "General", desc: "Startup, theme, branding & preferences", icon: Palette, group: "Personalize", terms: ["general", "start", "startup", "start screen", "home", "landing", "last screen", "resume", "market", "currency", "timezone", "refresh", "confirm", "delete", "safety", "theme", "branding", "logo", "favicon", "app name", "font", "typography", "monospace", "primary", "accent", "colors", "bullish", "bearish", "radius", "density", "glow", "aurora", "chart", "charts", "candles", "palette", "series", "animation", "preset", "language", "translate", "locale", "accessibility", "a11y", "motion", "contrast", "text size", "screen reader", "rtl"] },
    { id: "sound", label: "Sound", desc: "UI sounds & feedback", icon: Volume2, group: "Personalize", terms: ["sound", "sounds", "audio", "volume", "click", "tick", "toggle", "feedback", "notification", "voice", "pack", "mute", "muted", "silence", "chime", "beep"] },
    { id: "sidebar", label: "Sidebar & Navigation", desc: "Menu & shortcuts", icon: PanelLeft, group: "Personalize", terms: ["sidebar", "navigation", "menu", "shortcuts", "keys", "reorder"] },

    { id: "ai", label: "AI / LLM", desc: "Models, keys & testing", icon: Bot, group: "Intelligence", terms: ["ai", "llm", "agent", "model", "openai", "anthropic", "ollama", "groq", "gemini", "api key", "base url", "chat"] },
    { id: "investor-eye", label: "Investor Eye", desc: "World-state sources", icon: EyeIcon, group: "Intelligence", terms: ["investor eye", "world state", "gdelt", "usgs", "firms", "events", "geopolitics", "map", "sources"] },
    { id: "economics", label: "Economics", desc: "Macro & calendar providers", icon: Activity, group: "Intelligence", terms: ["economics", "macro", "fred", "bea", "bls", "calendar", "indicators", "yield", "inflation"] },
    { id: "market", label: "Market Data", desc: "Screener, charts & markets", icon: Globe2, group: "Intelligence", terms: ["market", "screener", "stocks", "crypto", "prices", "fundamentals", "polygon", "finnhub", "alpha vantage", "coin"] },
    { id: "news", label: "News", desc: "Feeds & providers", icon: Newspaper, group: "Intelligence", terms: ["news", "rss", "feeds", "headlines", "sentiment", "finnhub"] },
    { id: "analytics", label: "Analytics", desc: "Token usage & runs", icon: BarChart3, group: "Intelligence", terms: ["analytics", "usage", "tokens", "token", "consumption", "cost", "spend", "runs", "steps", "agent", "llm", "metrics", "stats"] },
    { id: "mcp", label: "MCP Servers", desc: "External tool connections", icon: Plug, group: "Intelligence", terms: ["mcp", "model context protocol", "servers", "tools", "external", "stdio", "integration", "plugins"] },

    { id: "alerts", label: "Alerts", desc: "Notification channels", icon: ShieldCheck, group: "System", terms: ["alerts", "notifications", "channels", "email", "webhook", "telegram", "discord", "slack"] },
    { id: "data", label: "Data & Storage", desc: "Local data & reset", icon: Database, group: "System", terms: ["data", "storage", "clear", "reset", "chats", "watchlist", "portfolio", "cache"] },
    { id: "git", label: "Git", desc: "Plan, commit & push", icon: GitBranch, group: "System", terms: ["git", "commit", "push", "branch", "stage", "diff", "version control", "repo"] },
    { id: "system", label: "System", desc: "Health & integrations", icon: Cpu, group: "System", terms: ["system", "health", "database", "jdds", "integrations", "status", "diagnostics"] },
  ];

  const GROUPS: Array<"Personalize" | "Intelligence" | "System"> = ["Personalize", "Intelligence", "System"];

  // The vault env var that stores the selected provider's key (if it is a
  // known preset). The AI section's key editor is keyed off this.
  const activeKeyEnvVar = presetForBaseUrl(llm.baseUrl)?.envVar;

  // The declared model list + context window for the currently selected
  // provider, from the runtime catalog. `provider` = the provider kind; when the
  // mode is `auto` or the provider is not in the catalog, fall back to the
  // preset id (the base URL identifies the vendor). Never an allowlist.
  const activeCatalogProvider =
    (llm.provider !== "auto" && llm.provider !== "mock" ? modelCatalog[llm.provider] : undefined) ??
    modelCatalog[presetForBaseUrl(llm.baseUrl)?.id ?? ""];
  const activeModelOptions = activeCatalogProvider?.models ?? [];
  const activeWindow =
    activeCatalogProvider?.modelWindows?.[llm.model] ??
    activeCatalogProvider?.contextWindow ??
    null;
  const activeWindowKnown = activeWindow != null;

  // Rail attention dots: sections whose providers still need a key.
  const { health: homeHealth } = useProviderHealth();
  const ATTENTION: Record<string, number> = {
    ai: homeHealth.ai.needsKey,
    "investor-eye": homeHealth["investor-eye"].needsKey,
    economics: homeHealth.economics.needsKey,
    news: homeHealth.news.needsKey,
    market: homeHealth.market.needsKey,
  };

  const needle = query.trim().toLowerCase();
  const visibleNav = useMemo(() => {
    if (!needle) return NAV;
    return NAV.filter((item) => {
      const hay = [item.label, item.desc, ...item.terms].join(" ").toLowerCase();
      return hay.includes(needle);
    });
  }, [needle, NAV]);

  // Keyboard navigation: `/` focuses the search, ↑/↓ move between sections
  // (within the current search), Esc clears/blurs. Ignored while typing in a
  // field so it never hijacks input.
  const searchRef = useRef<HTMLInputElement | null>(null);
  const modalRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (e.key === "Escape" && typing) {
        (target as HTMLInputElement).blur();
        return;
      }
      if ((e.key === "ArrowDown" || e.key === "ArrowUp") && !typing) {
        const list = visibleNav.length > 0 ? visibleNav : NAV;
        const idx = list.findIndex((i) => i.id === section);
        const nextIdx = e.key === "ArrowDown"
          ? (idx + 1) % list.length
          : (idx - 1 + list.length) % list.length;
        e.preventDefault();
        setSection(list[nextIdx].id);
      }
    };
    const node = modalRef.current;
    node?.addEventListener("keydown", onKey);
    return () => node?.removeEventListener("keydown", onKey);
    // `loading` matters: the ref is null while the skeleton renders, so the
    // effect must re-run once the real shell (and its ref) has mounted.
  }, [visibleNav, section, loading]);

  // Scroll to a deep-linked block once content has rendered.
  useEffect(() => {
    if (loading || !initialAnchor) return;
    const t = setTimeout(() => {
      modalRef.current?.querySelector(`[data-anchor="${initialAnchor}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 150);
    return () => clearTimeout(t);
  }, [loading, initialAnchor]);

  // All hooks run before this early return (rules of hooks).
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

  return (
    <div ref={modalRef} className="flex h-full w-full overflow-hidden" tabIndex={-1}>
      {/* Left nav rail */}
      <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-border/10 glass-card-subtle">
        <div className="flex items-center gap-3 px-5 h-16 border-b border-border/10">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
            <Cog className="text-primary" size={20} />
          </span>
          <div>
            <p className="font-serif text-sm font-semibold leading-none text-foreground">Settings</p>
            <p className="text-[10px] text-muted-foreground mt-1 tracking-wide">BlackEclipse Console</p>
          </div>
        </div>

        {/* Rail search — answers "where do I change X?" without scanning. */}
        <div className="px-3 pt-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input
              ref={searchRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search settings…  /"
              className="w-full h-9 rounded-xl border border-border/30 bg-transparent pl-8 pr-2.5 text-[11px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/40"
            />
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto scrollbar-hide p-3 space-y-1.5">
          {visibleNav.length === 0 && (
            <p className="px-3 py-6 text-[10px] text-muted-foreground text-center">
              No settings match “{query}”.
            </p>
          )}
          {GROUPS.map((group) => {
            const items = visibleNav.filter((i) => i.group === group);
            if (items.length === 0) return null;
            return (
              <div key={group} className="space-y-1.5">
                {!needle && (
                  <p className="px-3 pt-2 pb-0.5 text-[9px] uppercase tracking-[0.18em] font-bold text-muted-foreground/60">
                    {group}
                  </p>
                )}
                {items.map((item) => {
                  const Icon = item.icon;
                  const active = section === item.id;
                  return (
                    <button
                      key={item.id}
                      data-sound="tick"
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
                          <span className="flex items-center gap-1.5">
                            {item.label}
                            {ATTENTION[item.id] > 0 && !active && (
                              <span
                                className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0"
                                title={`${ATTENTION[item.id]} provider${ATTENTION[item.id] === 1 ? "" : "s"} need a key`}
                              />
                            )}
                          </span>
                          <span className="text-[9px] text-muted-foreground font-normal tracking-wide hidden lg:block">{item.desc}</span>
                        </span>
                      </span>
                      {active && <ChevronRight size={13} className="text-primary shrink-0" />}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </nav>
      </aside>

      {/* Right content */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 overflow-y-auto scrollbar-hide p-5 md:p-8">
          <div className="max-w-3xl mx-auto">
            {/* Mobile: horizontal, scrollable pill row (thumb-friendly) instead
                of a dropdown, so switching sections is one tap. */}
            <div className="md:hidden -mx-5 px-5 mb-4 overflow-x-auto scrollbar-hide">
              <div className="flex gap-2 w-max">
                {NAV.map((item) => {
                  const Icon = item.icon;
                  const active = section === item.id;
                  return (
                    <button
                      key={item.id}
                      data-sound="tick"
                      onClick={() => setSection(item.id)}
                      className={cn(
                        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1.5 text-[11px] font-medium transition-colors cursor-pointer",
                        active
                          ? "bg-primary/10 text-foreground border-primary/30"
                          : "text-muted-foreground border-border/30 hover:text-foreground hover:border-border/60"
                      )}
                    >
                      <Icon size={13} className={active ? "text-primary" : "text-muted-foreground"} />
                      {item.label}
                      {ATTENTION[item.id] > 0 && !active && (
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            <SettingsStatusHeader />

            {section === "general" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  icon={Palette}
                  title="General"
                  description="How the app opens and behaves, plus centralized theming — branding, typography, colors, radius, density and motion. Theme changes apply live across the whole app through shared design tokens."
                />
                <CustomizationSettingsPanel
                  generalTab={
                    <GeneralSettingsPanel
                      markets={markets}
                      prefs={prefs}
                      onPrefsChange={updatePrefs}
                      onGeneralChange={setGeneral}
                    />
                  }
                />
              </div>
            )}

            {section === "sound" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  icon={Volume2}
                  title="UI Sounds"
                  description="Terminal-style audio feedback for navigation, actions and alerts. Pick a voice pack, fine-tune every cue, or upload your own clips — all stored on this device."
                />
                <SoundSettingsPanel />
              </div>
            )}

            {/* ── AI / LLM ────────────────────────────────────────────────
                Every LLM concern lives here — providers, keys, base URLs,
                model selection, active provider, test, status. Nothing else
                in Settings configures an LLM. */}
            {section === "ai" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  icon={Bot}
                  title="AI / LLM"
                  description="Choose the model provider that powers Chat, Research and the Investor Eye analyst. Keys, base URLs and model selection all live here — never mixed with financial/data APIs."
                />

                {/* One provider picker (not a dropdown AND a list). Clicking a
                    preset fills the base URL + model below; the key is the only
                    thing left for the operator. */}
                <div className="grid gap-2 sm:grid-cols-2 mb-4">
                  {LLM_PRESETS.map((preset) => {
                    const active = presetForBaseUrl(llm.baseUrl)?.id === preset.id;
                    const envSet = preset.envVar ? Boolean(integrations?.envFlags?.[preset.envVar]) : false;
                    return (
                      <button
                        key={preset.id}
                        onClick={() =>
                          updateLlm({ baseUrl: preset.baseUrl, model: preset.model }, 0)
                        }
                        className={cn(
                          "text-left rounded-xl border px-3.5 py-3 transition-all cursor-pointer",
                          active
                            ? "border-primary/45 bg-primary/10 shadow-sm shadow-primary/10"
                            : "border-border/20 glass-card-subtle hover:border-border/40 hover:bg-accent/30"
                        )}
                      >
                        <p className="text-[11px] font-semibold text-foreground flex items-center gap-1.5 flex-wrap">
                          {preset.name}
                          {preset.recommended && (
                            <span className="px-1.5 py-0.5 rounded-full text-[8px] font-bold border border-primary/30 bg-primary/10 text-primary">
                              RECOMMENDED
                            </span>
                          )}
                          {active && <Check className="w-3 h-3 text-primary" />}
                        </p>
                        <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug">{preset.description}</p>
                        <p className="text-[9px] font-mono mt-1.5 flex items-center gap-1.5">
                          {preset.keyless ? (
                            <span className="text-emerald-400/90">no key needed</span>
                          ) : envSet ? (
                            <span className="text-emerald-400/90">key set via {preset.envVar}</span>
                          ) : (
                            <span className="text-amber-400/90">needs {preset.envVar}</span>
                          )}
                        </p>
                      </button>
                    );
                  })}
                </div>

                <Panel className="p-5 md:p-6 space-y-5">
                  <div className="flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3">
                    <Cpu className="text-primary w-4 h-4 shrink-0" />
                    <p className="text-[11px] text-foreground/80 leading-relaxed">
                      Active: <span className="font-semibold">{presetForBaseUrl(llm.baseUrl)?.name ?? "Custom endpoint"}</span>
                      {" · "}
                      <span className="font-mono text-primary">{llm.model}</span>
                      {" · "}
                      <span className="text-muted-foreground">{PROVIDER_LABELS[llm.provider]}</span>
                    </p>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field
                      label="Model"
                      hint="Pick a known model or type any id this provider expects."
                    >
                      {/* A native datalist gives a dropdown of the runtime's
                          declared models AND still accepts a custom id — never an
                          allowlist. When the catalog is empty it is a plain field. */}
                      <Input
                        value={llm.model}
                        onChange={(e) => updateLlm({ model: e.target.value })}
                        placeholder="gpt-4o-mini / llama3.1"
                        className="font-mono"
                        list={activeModelOptions.length > 0 ? "llm-model-options" : undefined}
                      />
                      {activeModelOptions.length > 0 && (
                        <datalist id="llm-model-options">
                          {activeModelOptions.map((m) => (
                            <option key={m} value={m} />
                          ))}
                        </datalist>
                      )}
                      <p className="text-[10px] text-muted-foreground mt-1.5 flex items-center gap-1.5">
                        {activeWindowKnown ? (
                          <span className="text-emerald-400/90">
                            {activeWindow.toLocaleString()}-token context window
                          </span>
                        ) : (
                          <span className="text-muted-foreground/80">Context window unknown</span>
                        )}
                        {activeModelOptions.length > 0 && (
                          <span className="text-muted-foreground/60">
                            · {activeModelOptions.length} known model{activeModelOptions.length === 1 ? "" : "s"}
                          </span>
                        )}
                      </p>
                    </Field>
                    <Field label="Mode" hint="Auto follows environment variables.">
                      <Select value={llm.provider} onValueChange={(v) => updateLlm({ provider: v as LLMProviderName }, 0)}>
                        <SelectTrigger className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="auto">Auto (env)</SelectItem>
                          <SelectItem value="openai">Use this endpoint</SelectItem>
                          <SelectItem value="ollama">Ollama (local)</SelectItem>
                          <SelectItem value="anthropic">Anthropic</SelectItem>
                          <SelectItem value="mock">Mock (offline)</SelectItem>
                        </SelectContent>
                      </Select>
                    </Field>
                  </div>

                  {/* The runtime catalog cannot know a local server's / router's /
                      custom endpoint's window. When it is unknown, let the operator
                      DECLARE it (tokens) — a real declaration, not a guess. Leaving
                      it blank keeps the conservative ceiling. When the catalog knows
                      it, the resolved value is shown read-only. */}
                  {!activeWindowKnown && (
                    <Field
                      label="Context window (optional)"
                      hint="Token limit for this model. Leave blank if unknown — the runtime then uses a safe conservative bound."
                    >
                      <Input
                        type="number"
                        min={1}
                        value={llm.contextWindow ?? ""}
                        onChange={(e) => {
                          const raw = e.target.value.trim();
                          const parsed = raw ? Number(raw) : undefined;
                          updateLlm({
                            contextWindow:
                              parsed && Number.isFinite(parsed) && parsed > 0
                                ? Math.floor(parsed)
                                : null,
                          });
                        }}
                        placeholder="e.g. 8192"
                        className="font-mono"
                      />
                    </Field>
                  )}

                  <Field label="Base URL" hint="Any OpenAI-compatible endpoint.">
                    <div className="relative">
                      <Server className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground w-3.5 h-3.5" />
                      <Input
                        value={llm.baseUrl}
                        onChange={(e) => updateLlm({ baseUrl: e.target.value })}
                        placeholder="https://api.openai.com/v1"
                        className="pl-8 font-mono"
                      />
                    </div>
                  </Field>

                  {/* One key, one home: the API key lives in the provider-key
                      vault (keyed by the selected provider's env var), and the
                      LLM runtime reads it. No second key field to keep in sync. */}
                  {isLocalBaseUrl(llm.baseUrl) ? (
                    <p className="text-[10px] text-muted-foreground flex items-center gap-1.5">
                      <Server size={12} className="text-primary shrink-0" />
                      No API key needed — local endpoints ignore it.
                    </p>
                  ) : activeKeyEnvVar ? (
                    <ProviderKeyEditor envVar={activeKeyEnvVar} label={presetForBaseUrl(llm.baseUrl)?.name} />
                  ) : (
                    <Field label="API Key" hint="This custom endpoint has no known key variable. Use a preset above to store its key in the vault.">
                      <Input value="" disabled placeholder="Use a known provider preset to manage its key" className="font-mono" />
                    </Field>
                  )}

                  {/* Test connection — makes a real request to the endpoint. */}
                  <div className="flex flex-wrap items-center gap-3 pt-1">
                    <Button
                      variant="outline"
                      size="sm"
                      className="cursor-pointer rounded-xl"
                      disabled={testingLlm}
                      onClick={() => void testLlm()}
                    >
                      {testingLlm ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Activity className="w-3.5 h-3.5 mr-1" />}
                      Test Connection
                    </Button>
                    {llmTest && (
                      <span className={cn("text-[11px] flex items-center gap-1.5", llmTest.ok ? "text-emerald-400" : "text-rose-400")}>
                        {llmTest.ok ? <Check size={12} /> : <CircleDashed size={12} />}
                        {llmTest.message}
                        {llmTest.latencyMs !== undefined && <span className="text-muted-foreground/60">· {llmTest.latencyMs} ms</span>}
                      </span>
                    )}
                  </div>
                </Panel>
              </div>
            )}

            {/* ── Investor Eye ────────────────────────────────────────────
                Only what powers the Investor Eye world-state page: its own
                keyless event sources (GDELT/USGS/FIRMS) and the feature map.
                Macro, market and news providers live in their own sections. */}
            {section === "investor-eye" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  icon={EyeIcon}
                  title="Investor Eye"
                  description="The sources behind the Investor Eye world-state map, and a map of which provider powers each feature. Providers are configured in their own sections — tap a chip to jump there."
                />

                <div className="mb-5">
                  <InvestorEyeFeatureMap />
                </div>

                <InvestorEyeSources />
              </div>
            )}

            {/* ── Economics ───────────────────────────────────────────────
                Only macro/economic providers. */}
            {section === "economics" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  icon={Activity}
                  title="Economics"
                  description="Providers that power the Economics calendar, indicators and time-series explorer—macro series, national accounts and central-bank data."
                />
                <ProviderRegistry home="economics" title="Economics & macro providers" />
              </div>
            )}

            {section === "analytics" && <AnalyticsSettingsPanel />}

            {section === "sidebar" && <SidebarSettingsPanel />}

            {section === "market" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  icon={Globe2}
                  title="Market Data"
                  description="Providers that power the Market Screener, charts and Fundamentals. Choose which markets and exchanges loaded in JDDS are surfaced, and review the price-source fallback chain."
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
                      return (                        <button
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
                              : "glass-card-subtle border-border/20 hover:border-border/40 hover:bg-accent/30"
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

                <div className="mt-4 space-y-4">
                  <ProviderRegistry home="market" title="Market Screener providers" />
                  <Panel className="p-5 md:p-6" data-anchor="priority">
                    <p className="text-[11px] font-semibold text-foreground mb-1">Price-source priority & fallback</p>
                    <p className="text-[10px] text-muted-foreground leading-relaxed">
                      JDDS serves stored prices first, then the built-in scraper chain escalates automatically:
                      TradingView scanner → HTTP/scraper → Playwright browser → optional yfinance bridge.
                      Configure keys for alternative sources above to widen coverage and rate limits.
                    </p>
                  </Panel>
                  <DataSourcesPanel />
                </div>
              </div>
            )}

            {section === "news" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  icon={Newspaper}
                  title="News"
                  description="Providers that power the Market News bulletin and sentiment—RSS feeds and news APIs. No other section lists news providers."
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
                          onChange={(v) => {
                            const next = feeds.map((x) => (x.id === f.id ? { ...x, enabled: v } : x));
                            setFeeds(next);
                            void persist({ newsFeeds: next });
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </Panel>

                <div className="mt-4">
                  <ProviderRegistry home="news" title="News providers" />
                </div>
              </div>
            )}

            {section === "alerts" && <AlertNotificationsPanel />}

            {section === "data" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  icon={Database}
                  title="Data & Storage"
                  description="Clear locally stored chats, watchlists, or portfolio data from this device."
                />
                <Panel className="p-5 md:p-6">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Button variant="outline" size="sm" className="cursor-pointer justify-start rounded-xl" onClick={() => clearStorage(["chats_guest"], "all chats")}>
                      <Trash2 className="w-4 h-4 mr-1" /> Clear Chats
                    </Button>
                    <Button variant="outline" size="sm" className="cursor-pointer justify-start rounded-xl" onClick={() => clearStorage(["watchlist_guest"], "your watchlist")}>
                      <Trash2 className="w-4 h-4 mr-1" /> Clear Watchlist
                    </Button>
                    <Button variant="outline" size="sm" className="cursor-pointer justify-start rounded-xl" onClick={() => clearStorage(["portfolio_tx_guest", "portfolio_alerts_guest"], "your portfolio")}>
                      <Trash2 className="w-4 h-4 mr-1" /> Clear Portfolio
                    </Button>
                    <Button variant="outline" size="sm" className="cursor-pointer justify-start rounded-xl text-rose-400 hover:text-rose-300 hover:border-rose-500/40 hover:bg-rose-500/10" onClick={() => clearStorage(["chats_guest", "watchlist_guest", "portfolio_tx_guest", "portfolio_alerts_guest"], "all local data")}>
                      <RotateCcw className="w-4 h-4 mr-1" /> Reset All Local Data
                    </Button>
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-4 flex items-center gap-1.5">
                    <CircleDashed className="w-3 h-3" /> Cleared data is removed from this browser only.
                  </p>
                </Panel>
              </div>
            )}

            {/* ── Git ─────────────────────────────────────────────────────
                Plan → review → commit → push. Commits and pushes are explicit
                actions; the server refuses secret-looking paths. */}
            {section === "git" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  icon={GitBranch}
                  title="Git"
                  description="Review changes, stage what you mean, write a message (or draft one from the real diff), commit, then push. Push is always manual."
                />
                <GitPanel />
              </div>
            )}

            {/* ── MCP servers ─────────────────────────────────────────────
                The user-directed extension surface: connect local stdio MCP
                servers and select which read-only tools the agent may use. */}
            {section === "mcp" && <MCPSettingsPanel />}

            {/* ── System ──────────────────────────────────────────────────
                Technical/internal only: database, health and the status of
                the services BlackEclipse itself runs. No user-facing provider
                configuration lives here. */}
            {section === "system" && (
              <div className="animate-fade-in-up">
                <SectionHeader
                  icon={Cpu}
                  title="System & Integrations"
                  description="Technical status only — JDDS/database health and the internal services BlackEclipse runs. Providers are configured in their own sections."
                />
                <Panel className="divide-y divide-border/10">
                  {[
                    { label: "Database (JDDS)", ok: integrations?.database, detail: "Connected" },
                    { label: "AI Model", ok: integrations?.llm.configured, detail: integrations ? `${integrations.llm.provider} · ${integrations.llm.model}` : "—" },
                    { label: "Investor Eye runtime", ok: true, detail: "Scheduler active" },
                    { label: "News ingestion", ok: true, detail: `${feeds.filter((f) => f.enabled).length} feeds enabled` },
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
          </div>
        </div>

        {/* Status strip — there is no Save button: every control applies
            instantly. This line reports the real save state (or the last
            error) so the user always knows whether their change persisted. */}
        <div className="shrink-0 border-t border-border/10 glass-card px-6 md:px-8 py-3 flex items-center justify-between gap-3">
          {toast ? (
            <span
              className={cn(
                "text-xs flex items-center gap-1.5",
                toast.kind === "error" ? "text-rose-400" : "text-primary"
              )}
            >
              {toast.kind === "error" ? <AlertCircle className="w-3.5 h-3.5" /> : <Check className="w-3.5 h-3.5" />}
              {toast.text}
            </span>
          ) : saving ? (
            <span className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" /> Saving…
            </span>
          ) : (
            <span className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-primary" /> Changes save automatically.
            </span>
          )}
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground font-mono">
              {feeds.filter((f) => f.enabled).length}/{feeds.length} feeds live
            </span>
            <Button
              variant="outline"
              size="sm"
              className="cursor-pointer rounded-xl"
              onClick={() => { setToast(null); void fetchAll(); }}
              title="Reload from the server"
            >
              <RefreshCcw className="w-4 h-4 mr-1" /> Reload
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
