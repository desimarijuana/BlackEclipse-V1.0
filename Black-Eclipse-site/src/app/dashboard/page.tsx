"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
import { useAuth } from "@/components/auth/auth-context";
import { 
  Server, Database, Clock, RefreshCw, 
  CheckCircle2, XCircle, Sliders, Activity, 
  DatabaseZap, Cpu, Network, Play, CheckCircle,
  Shield, Settings2, TrendingUp, TrendingDown,
  Loader2, Hourglass, Globe, DollarSign, Zap,
  Power, Timer, ToggleLeft, ToggleRight
} from "lucide-react";
import { redirect } from "next/navigation";
import { TopLoader } from "@/components/ui/top-loader";

interface SyncProgressInfo {
  status: "idle" | "running" | "failed";
  current: number;
  total: number;
  newAssets?: number;
  updatedAssets?: number;
  newStocksCount?: number;
  updatedStocksCount?: number;
  message: string;
}

interface HealthData {
  status: "UP" | "DEGRADED" | "DOWN";
  timestamp: string;
  activeMode: string;
  paused?: boolean;
  jobs?: {
    active: number;
    pending: number;
    completed: number;
    failed: number;
  };
  telemetry?: {
    totalSymbols: number;
    activeSymbols: number;
    backtestReadySymbols?: number;
    cryptoSymbols?: number;
    forexSymbols?: number;
    stockSymbols?: number;
    pakistanSymbols?: number;
    stocksInDb?: number;
    cryptosInDb?: number;
    activeStocks?: number;
    activeCryptos?: number;
    newsArticlesCount?: number;
    lastUniverseRun: string;
    lastPriceRun: string;
    lastNewsRun?: string;
    symbolsUpdatedLastCycle: number;
  };
  customConfig?: {
    crypto?: {
      universeEnabled: boolean;
      universeSyncInterval: number;
      priceEnabled: boolean;
      priceUpdateInterval: number;
      // Legacy fallbacks
      enabled?: boolean;
      universeSyncSchedule?: string;
    };
    stocks?: {
      universeEnabled: boolean;
      universeSyncInterval: number;
      priceEnabled: boolean;
      priceUpdateInterval: number;
      enabled?: boolean;
      universeSyncSchedule?: string;
    };
    api?: {
      binanceEnabled: boolean;
      finnhubEnabled: boolean;
      timeout: number;
      retryCount: number;
    };
    system?: {
      globalPause: boolean;
      mode: string;
    };
  };
  runNow?: {
    universe: string;
    prices: string;
  };
  services: {
    database: {
      name: string;
      status: string;
      readLatency: string;
      writeLatency: string;
      latency: string;
      stocksInDb: number;
      cryptosInDb: number;
      activeMarkets: number;
      readWritePerf: string;
    };
    finnhubApi: {
      name: string;
      status: string;
      latency: string;
      successRate: string;
    };
    binanceApi: {
      name: string;
      status: string;
      latency: string;
      successRate: string;
      keyConfigured: boolean;
    };
    marketauxApi?: {
      name: string;
      status: string;
      latency: string;
      successRate: string;
      keyConfigured: boolean;
    };
    cryptopanicApi?: {
      name: string;
      status: string;
      latency: string;
      successRate: string;
      keyConfigured: boolean;
    };
    workers: {
      crypto_universe_worker: { running: boolean; idle: boolean; crashed: boolean; last_heartbeat: string };
      crypto_price_worker: { running: boolean; idle: boolean; crashed: boolean; last_heartbeat: string };
      stock_universe_worker: { running: boolean; idle: boolean; crashed: boolean; last_heartbeat: string };
      stock_price_worker: { running: boolean; idle: boolean; crashed: boolean; last_heartbeat: string };
    };
    jddsEngine: {
      name: string;
      status: string;
      lastPollTime: string;
      lastCryptoUpdated: string;
      lastStockUpdated: string;
      failures: number;
      retries: number;
      queueStatus?: string;
    };
  };
  system: {
    nodeVersion: string;
    platform: string;
    uptime: number;
  };
  listings: {
    crypto: Array<{ symbol: string; createdAt: string }>;
    stock: Array<{ symbol: string; name: string; createdAt: string }>;
  };
  movers: {
    crypto: Array<{ symbol: string; price: number; change: number }>;
    stock: Array<{ symbol: string; name: string; price: number; change: number }>;
  };
  universeSyncProgress: {
    crypto: SyncProgressInfo;
    stock: SyncProgressInfo;
  };
}

// ─── INTERVAL FORMATTING HELPER ────────────────────────────────────────

function formatIntervalLabel(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return s > 0 ? `${m}m ${s}s` : `${m} min`;
  }
  if (seconds < 86400) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return m > 0 ? `${h}h ${m}m` : `${h} hour${h > 1 ? "s" : ""}`;
  }
  if (seconds < 604800) {
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    return h > 0 ? `${d}d ${h}h` : `${d} day${d > 1 ? "s" : ""}`;
  }
  const w = Math.floor(seconds / 604800);
  const d = Math.floor((seconds % 604800) / 86400);
  return d > 0 ? `${w}w ${d}d` : `${w} week${w > 1 ? "s" : ""}`;
}

function formatTimeAgo(timestampMs: number): string {
  if (!timestampMs) return "Never";
  const diff = Date.now() - timestampMs;
  if (diff < 60000) return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  return `${Math.floor(diff / 3600000)}h ago`;
}

export default function AdminDashboardPage() {
  const { user, loading: authLoading } = useAuth();
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [updatingMode, setUpdatingMode] = useState(false);

  // Countdown timer for next telemetry refresh
  const [refreshInterval, setRefreshInterval] = useState(180);
  const [countdown, setCountdown] = useState(180);

  // Feedback
  const [feedback, setFeedback] = useState<string | null>(null);

  // ─── NEW JDDS STATS AND JOBS STATE ────────────────────────────────
  const [jddsStatus, setJddsStatus] = useState<any>(null);
  const [jddsJobs, setJddsJobs] = useState<any[]>([]);


  // ─── UNIVERSE CONTROL STATE ───────────────────────────────────────
  const [cryptoUniverseEnabled, setCryptoUniverseEnabled] = useState(true);
  const [cryptoUniverseInterval, setCryptoUniverseInterval] = useState(3600);
  const [cryptoUniverseCustom, setCryptoUniverseCustom] = useState("");
  const [stocksUniverseEnabled, setStocksUniverseEnabled] = useState(true);
  const [stocksUniverseInterval, setStocksUniverseInterval] = useState(3600);

  // ─── PRICE CONTROL STATE ──────────────────────────────────────────
  const [cryptoPriceEnabled, setCryptoPriceEnabled] = useState(true);
  const [cryptoPriceInterval, setCryptoPriceInterval] = useState(120);
  const [cryptoPriceCustom, setCryptoPriceCustom] = useState("");
  const [stocksPriceEnabled, setStocksPriceEnabled] = useState(true);
  const [stocksPriceInterval, setStocksPriceInterval] = useState(120);

  // ─── API & SYSTEM STATE ───────────────────────────────────────────
  const [binanceEnabled, setBinanceEnabled] = useState(true);
  const [finnhubEnabled, setFinnhubEnabled] = useState(true);
  const [apiTimeout, setApiTimeout] = useState(4000);
  const [apiRetry, setApiRetry] = useState(3);
  const [globalPause, setGlobalPause] = useState(false);

  // Save state
  const [savingConfig, setSavingConfig] = useState(false);
  const [runningUniverse, setRunningUniverse] = useState(false);
  const [runningPrices, setRunningPrices] = useState(false);
  const [runningNews, setRunningNews] = useState(false);
  const [universeCountdownText, setUniverseCountdownText] = useState("Never");
  const [priceCountdownText, setPriceCountdownText] = useState("Never");
  const [newsCountdownText, setNewsCountdownText] = useState("Never");
  const [universeProgress, setUniverseProgress] = useState(0);
  const [priceProgress, setPriceProgress] = useState(0);
  const [newsProgress, setNewsProgress] = useState(0);

  // Debounce ref for auto-save
  const saveTimerRef = useRef<NodeJS.Timeout | null>(null);
  const saveConfigRef = useRef<() => Promise<void>>(async () => {});

  const fetchHealth = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await fetch("/api/admin/health");
      if (res.status === 403 || res.status === 401) {
        redirect("/dashboard");
      }
      if (!res.ok) {
        throw new Error(`Health API responded with status ${res.status}`);
      }
      const data: HealthData = await res.json();
      setHealth(data);
      
      if (data.customConfig) {
        const c = data.customConfig;
        if (c.crypto) {
          setCryptoUniverseEnabled(c.crypto.universeEnabled ?? c.crypto.enabled ?? true);
          setCryptoUniverseInterval(c.crypto.universeSyncInterval ?? 3600);
          setCryptoPriceEnabled(c.crypto.priceEnabled ?? c.crypto.enabled ?? true);
          setCryptoPriceInterval(c.crypto.priceUpdateInterval ?? 120);
        }
        if (c.stocks) {
          setStocksUniverseEnabled(c.stocks.universeEnabled ?? c.stocks.enabled ?? true);
          setStocksUniverseInterval(c.stocks.universeSyncInterval ?? 3600);
          setStocksPriceEnabled(c.stocks.priceEnabled ?? c.stocks.enabled ?? true);
          setStocksPriceInterval(c.stocks.priceUpdateInterval ?? 120);
        }
        if (c.api) {
          setBinanceEnabled(c.api.binanceEnabled ?? true);
          setFinnhubEnabled(c.api.finnhubEnabled ?? true);
          setApiTimeout(c.api.timeout ?? 4000);
          setApiRetry(c.api.retryCount ?? 3);
        }
        if (c.system) {
          setGlobalPause(c.system.globalPause ?? false);
        }
      }

      // Check Run Now statuses
      if (data.runNow) {
        setRunningUniverse(data.runNow.universe === "running" || data.runNow.universe === "pending");
        setRunningPrices(data.runNow.prices === "running" || data.runNow.prices === "pending");
        setRunningNews((data.runNow as any).news === "running" || (data.runNow as any).news === "pending");
      }

      setError(null);

      // Fetch new JDDS status & jobs
      try {
        const [statusRes, jobsRes] = await Promise.all([
          fetch("/api/jdds/status"),
          fetch("/api/jdds/jobs?limit=15")
        ]);
        if (statusRes.ok) {
          const sData = await statusRes.json();
          setJddsStatus(sData);
        }
        if (jobsRes.ok) {
          const jData = await jobsRes.json();
          setJddsJobs(jData.jobs || []);
        }
      } catch (e) {
        console.error("Failed to load JDDS stats in background:", e);
      }

    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load system diagnostics");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const handleUpdateMode = async (newMode: string) => {
    setUpdatingMode(true);
    setFeedback(null);
    try {
      const res = await fetch("/api/admin/system/mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: newMode })
      });
      if (res.ok) {
        await fetchHealth();
        setFeedback(`Engine mode switched to ${newMode.replace("_", " ").toUpperCase()}`);
      } else {
        const data = await res.json();
        alert(data.error || "Failed to update mode");
      }
    } catch (err) {
      alert("Error contacting server");
    } finally {
      setUpdatingMode(false);
    }
  };

  // ─── SAVE CONFIG (called by auto-save or manual submit) ────────────
  const saveConfig = useCallback(async () => {
    setSavingConfig(true);
    try {
      const res = await fetch("/api/admin/system/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          crypto: {
            universeEnabled: cryptoUniverseEnabled,
            universeSyncInterval: Number(cryptoUniverseInterval),
            priceEnabled: cryptoPriceEnabled,
            priceUpdateInterval: Number(cryptoPriceInterval),
          },
          stocks: {
            universeEnabled: stocksUniverseEnabled,
            universeSyncInterval: Number(stocksUniverseInterval),
            priceEnabled: stocksPriceEnabled,
            priceUpdateInterval: Number(stocksPriceInterval),
          },
          api: {
            binanceEnabled,
            finnhubEnabled,
            timeout: Number(apiTimeout),
            retryCount: Number(apiRetry)
          },
          system: {
            globalPause,
            mode: health?.activeMode || "hybrid"
          }
        })
      });

      if (res.ok) {
        setFeedback("Configuration saved to PostgreSQL.");
      } else {
        const data = await res.json();
        console.error("Config save failed:", data.error);
      }
    } catch (err) {
      console.error("Error saving config:", err);
    } finally {
      setSavingConfig(false);
    }
  }, [
    cryptoUniverseEnabled, cryptoUniverseInterval, cryptoPriceEnabled, cryptoPriceInterval,
    stocksUniverseEnabled, stocksUniverseInterval, stocksPriceEnabled, stocksPriceInterval,
    binanceEnabled, finnhubEnabled, apiTimeout, apiRetry, globalPause, health?.activeMode
  ]);

  // Keep saveConfigRef up to date with latest saveConfig function
  useEffect(() => {
    saveConfigRef.current = saveConfig;
  }, [saveConfig]);

  // Auto-save with 800ms debounce when any config changes (using ref to bypass stale closures)
  const triggerAutoSave = useCallback(() => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      saveConfigRef.current();
    }, 800);
  }, []);

  // ─── RUN NOW HANDLERS ──────────────────────────────────────────────
  const handleRunNow = async (action: "run_universe" | "run_prices" | "run_news") => {
    const isUniverse = action === "run_universe";
    const isPrices = action === "run_prices";
    const isNews = action === "run_news";
    if (isUniverse) setRunningUniverse(true);
    else if (isPrices) setRunningPrices(true);
    else setRunningNews(true);
    setFeedback(null);
  
    try {
      const res = await fetch("/api/admin/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action })
      });
      const data = await res.json();
      if (res.ok) {
        setFeedback(data.message || `${isUniverse ? "Universe sync" : isPrices ? "Price poll" : "News poll"} queued successfully.`);
        // Refresh after a short delay to show the updated status
        setTimeout(fetchHealth, 2000);
      } else {
        alert(data.error || "Failed to trigger action.");
        if (isUniverse) setRunningUniverse(false);
        else if (isPrices) setRunningPrices(false);
        else setRunningNews(false);
      }
    } catch (err) {
      alert("Error contacting server");
      if (isUniverse) setRunningUniverse(false);
      else if (isPrices) setRunningPrices(false);
      else setRunningNews(false);
    }
  };

  // Auth check
  useEffect(() => {
    if (!authLoading && !user) {
      redirect("/login");
    }
    fetchHealth();
  }, [user, authLoading, fetchHealth]);

  // Telemetry poll countdown ticker
  useEffect(() => {
    setCountdown(refreshInterval);
  }, [refreshInterval]);

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          fetchHealth();
          return refreshInterval;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [refreshInterval, fetchHealth]);

  // Live Next Run Countdown Ticker
  useEffect(() => {
    const timer = setInterval(() => {
      if (!health) return;
      
      const mode = health.activeMode;
      const isPaused = health.customConfig?.system?.globalPause || mode === "suspended";
      
      // 1. Universe Countdown
      const isUniverseActive = (mode === "hybrid" || mode === "universe_only") && !isPaused;
      const uEnabled = cryptoUniverseEnabled || stocksUniverseEnabled;
      
      if (!isUniverseActive || !uEnabled) {
        setUniverseCountdownText("Paused");
        setUniverseProgress(0);
      } else {
        const lastUniverseTime = health.telemetry?.lastUniverseRun && health.telemetry.lastUniverseRun !== "Never"
          ? new Date(health.telemetry.lastUniverseRun).getTime()
          : 0;
          
        if (lastUniverseTime === 0) {
          setUniverseCountdownText("Immediately");
          setUniverseProgress(100);
        } else {
          const intervalMs = Math.min(cryptoUniverseInterval || 3600, stocksUniverseInterval || 3600) * 1000;
          const nextRun = lastUniverseTime + intervalMs;
          const diff = nextRun - Date.now();
          if (diff <= 0) {
            setUniverseCountdownText("Executing...");
            setUniverseProgress(100);
          } else {
            const h = Math.floor(diff / 3600000);
            const m = Math.floor((diff % 3600000) / 60000);
            const s = Math.floor((diff % 60000) / 1000);
            setUniverseCountdownText(`${h}h ${m}m ${s}s`);
            
            const elapsed = intervalMs - diff;
            const pct = Math.max(0, Math.min(100, (elapsed / intervalMs) * 100));
            setUniverseProgress(pct);
          }
        }
      }

      // 2. Price Countdown
      const isPriceActive = (mode === "hybrid" || mode === "price_only") && !isPaused;
      const pEnabled = cryptoPriceEnabled || stocksPriceEnabled;
      
      if (!isPriceActive || !pEnabled) {
        setPriceCountdownText("Paused");
        setPriceProgress(0);
      } else {
        const lastPriceTime = health.telemetry?.lastPriceRun && health.telemetry.lastPriceRun !== "Never"
          ? new Date(health.telemetry.lastPriceRun).getTime()
          : 0;
          
        if (lastPriceTime === 0) {
          setPriceCountdownText("Immediately");
          setPriceProgress(100);
        } else {
          const intervalMs = Math.min(cryptoPriceInterval || 120, stocksPriceInterval || 120) * 1000;
          const nextRun = lastPriceTime + intervalMs;
          const diff = nextRun - Date.now();
          if (diff <= 0) {
            setPriceCountdownText("Executing...");
            setPriceProgress(100);
          } else {
            const h = Math.floor(diff / 3600000);
            const m = Math.floor((diff % 3600000) / 60000);
            const s = Math.floor((diff % 60000) / 1000);
            setPriceCountdownText(`${h}h ${m}m ${s}s`);
            
            const elapsed = intervalMs - diff;
            const pct = Math.max(0, Math.min(100, (elapsed / intervalMs) * 100));
            setPriceProgress(pct);
          }
        }
      }

      // 3. News Countdown
      if (isPaused) {
        setNewsCountdownText("Paused");
        setNewsProgress(0);
      } else {
        const lastNewsTime = health?.telemetry?.lastNewsRun && health.telemetry.lastNewsRun !== "Never"
          ? new Date(health.telemetry.lastNewsRun).getTime()
          : 0;

        if (lastNewsTime === 0) {
          setNewsCountdownText("Immediately");
          setNewsProgress(100);
        } else {
          const intervalMs = 300 * 1000; // 5 minutes
          const nextRun = lastNewsTime + intervalMs;
          const diff = nextRun - Date.now();
          if (diff <= 0) {
            setNewsCountdownText("Executing...");
            setNewsProgress(100);
          } else {
            const m = Math.floor(diff / 60000);
            const s = Math.floor((diff % 60000) / 1000);
            setNewsCountdownText(`${m}m ${s}s`);

            const elapsed = intervalMs - diff;
            const pct = Math.max(0, Math.min(100, (elapsed / intervalMs) * 100));
            setNewsProgress(pct);
          }
        }
      }
    }, 1000);
    
    return () => clearInterval(timer);
  }, [health, cryptoUniverseEnabled, stocksUniverseEnabled, cryptoUniverseInterval, stocksUniverseInterval, cryptoPriceEnabled, stocksPriceEnabled, cryptoPriceInterval, stocksPriceInterval]);

  if (authLoading || loading) {
    return (
      <>
        <TopLoader />
        <div className="flex flex-col gap-8 animate-pulse">
          {/* Header skeleton */}
          <div className="flex flex-col gap-2 border-b border-border/40 pb-5">
          <div className="h-3.5 w-28 bg-muted/30 rounded-md"></div>
          <div className="h-8 w-72 bg-muted/20 rounded-lg"></div>
          <div className="h-4 w-96 bg-muted/10 rounded-md mt-1"></div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main system config panel */}
          <div className="lg:col-span-2 flex flex-col gap-6">
            <div className="border border-border/40 bg-card/25 rounded-3xl p-6 space-y-4">
              <div className="h-5 w-40 bg-muted/30 rounded-md"></div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="h-20 bg-muted/15 border border-border/20 rounded-2xl p-4"></div>
                ))}
              </div>
            </div>

            <div className="border border-border/40 bg-card/15 rounded-3xl p-6 space-y-5">
              <div className="h-5 w-48 bg-muted/30 rounded-md"></div>
              <div className="space-y-3">
                <div className="h-10 w-full bg-muted/10 rounded-xl"></div>
                <div className="h-10 w-full bg-muted/10 rounded-xl"></div>
              </div>
            </div>
          </div>

          {/* Sidebar controls / statuses */}
          <div className="flex flex-col gap-6">
            <div className="border border-border/40 bg-card/25 rounded-3xl p-6 space-y-4">
              <div className="h-5 w-36 bg-muted/30 rounded-md"></div>
              <div className="space-y-2.5">
                <div className="h-8 w-full bg-muted/20 rounded-lg"></div>
                <div className="h-8 w-full bg-muted/10 rounded-lg"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[500px] flex-col items-center justify-center gap-4 text-center">
        <XCircle className="h-12 w-12 text-rose-500 animate-bounce" />
        <h2 className="font-sans font-bold text-lg text-foreground">JDdS Connection Blocked</h2>
        <p className="font-mono text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 px-4 py-2.5 rounded-2xl max-w-md">{error}</p>
        <button onClick={fetchHealth} className="mt-2 rounded-xl bg-primary px-5 py-2.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 cursor-pointer">
          Reconnect System
        </button>
      </div>
    );
  }

  const formatDateTime = (dateStr: string) => {
    if (!dateStr || dateStr === "Never" || dateStr === "unknown") return "Never";
    return new Date(dateStr).toLocaleTimeString();
  };

  const formatUptime = (seconds: number) => {
    const d = Math.floor(seconds / (3600*24));
    const h = Math.floor((seconds % (3600*24)) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${d}d ${h}h ${m}m`;
  };

  // Color mappings for modes (NO MANUAL MODE)
  const modeColors: Record<string, { bg: string; text: string; border: string; label: string; desc: string }> = {
    hybrid: {
      bg: "bg-purple-500/10",
      text: "text-purple-400",
      border: "border-purple-500/20",
      label: "Hybrid",
      desc: "Universe sync + Price polling both active"
    },
    universe_only: {
      bg: "bg-blue-500/10",
      text: "text-blue-400",
      border: "border-blue-500/20",
      label: "Universe Only",
      desc: "Build & sync asset listings only"
    },
    price_only: {
      bg: "bg-emerald-500/10",
      text: "text-emerald-400",
      border: "border-emerald-500/20",
      label: "Prices Only",
      desc: "Live market quotes polling only"
    },
    manual: {
      bg: "bg-amber-500/10",
      text: "text-amber-400",
      border: "border-amber-500/20",
      label: "Manual",
      desc: "No auto execution, API triggers only"
    },
    suspended: {
      bg: "bg-rose-500/10",
      text: "text-rose-400",
      border: "border-rose-500/20",
      label: "Suspended",
      desc: "All automated tasks stopped"
    }
  };

  const currentModeStyle = modeColors[health?.activeMode || "hybrid"] || modeColors.hybrid;

  // Active processes evaluations
  const isUniverseWorkerRunning = health?.services.workers?.crypto_universe_worker?.running || health?.services.workers?.stock_universe_worker?.running;
  const isPriceWorkerRunning = health?.services.workers?.crypto_price_worker?.running || health?.services.workers?.stock_price_worker?.running;

  // Determine if universe is currently building
  const isCryptoUniverseBuilding = health?.universeSyncProgress.crypto.status === "running";
  const isStockUniverseBuilding = health?.universeSyncProgress.stock.status === "running";
  const isAnyUniverseBuilding = isCryptoUniverseBuilding || isStockUniverseBuilding;

  // Universe interval slider presets (in seconds)
  const universeSliderSteps = [60, 300, 600, 900, 1800, 3600, 7200, 14400, 28800, 43200, 86400, 172800, 259200, 432000, 604800];
  const priceSliderSteps = [30, 60, 90, 120, 180, 300, 600];

  const findClosestStep = (val: number, steps: number[]) => {
    let closest = steps[0];
    for (const s of steps) {
      if (Math.abs(s - val) < Math.abs(closest - val)) closest = s;
    }
    return steps.indexOf(closest);
  };
  // ─── TOGGLE + SLIDER COMPONENT ──────────────────────────────────────
  const ToggleSwitch = ({ enabled, onToggle, size = "md" }: { enabled: boolean; onToggle: () => void; size?: "sm" | "md" }) => {
    const dims = size === "sm" ? "h-5 w-9" : "h-6 w-11";
    const thumbDims = size === "sm" ? "h-4 w-4" : "h-5 w-5";
    const translateOn = size === "sm" ? "translate-x-4" : "translate-x-5";
    return (
      <button
        type="button"
        onClick={() => { onToggle(); triggerAutoSave(); }}
        className={`relative inline-flex ${dims} shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
          enabled ? "bg-emerald-500" : "bg-neutral-700"
        }`}
      >
        <span className={`pointer-events-none inline-block ${thumbDims} transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
          enabled ? translateOn : "translate-x-0"
        }`} />
      </button>
    );
  };

  return (
    <div className="flex flex-col gap-6 animate-fade-in font-sans leading-relaxed text-neutral-200">
      
      {/* ────────────────── COMMAND STATION HEADER ────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-5 border-b border-border/20 pb-5 bg-card/10 p-5 rounded-2xl border border-border/10 backdrop-blur-3xl">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-ping" />
            <span className="font-mono text-[9px] font-bold uppercase tracking-widest text-primary">
              BlackEclipse Intelligence Terminal
            </span>
          </div>
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-white">Central Operations Terminal</h1>
          <p className="text-[10px] text-muted-foreground">Global Markets • Crypto • Forex • Commodities • Stocks • Pakistan Stock Exchange (PSX)</p>
        </div>
        
        <div className="flex flex-wrap items-center gap-3">
          <span className="px-2.5 py-1 rounded-md text-[8px] font-bold tracking-wider uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> JDDS Online</span>
          <span className="px-2.5 py-1 rounded-md text-[8px] font-bold tracking-wider uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Live Prices Active</span>
          <span className="px-2.5 py-1 rounded-md text-[8px] font-bold tracking-wider uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Backtest Data Engine Ready</span>
          <span className="px-2.5 py-1 rounded-md text-[8px] font-bold tracking-wider uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Universe Synced</span>

          <button 
            onClick={fetchHealth} 
            disabled={refreshing}
            className="flex items-center gap-2 rounded-xl border border-border bg-card/60 px-4 h-9 text-xs font-bold text-muted-foreground hover:bg-accent/40 hover:text-foreground transition-all disabled:opacity-50 cursor-pointer font-sans"
          >
            <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} />
            Sync Telemetry
          </button>
        </div>
      </div>

      {/* ────────────────── TERMINAL CODES GRID ────────────────── */}
      <div className="grid gap-4 grid-cols-2 md:grid-cols-6">
        
        {/* Total Symbols Available */}
        <div className="border border-border/10 bg-black/40 rounded-xl p-4 flex flex-col justify-between h-24 hover:border-primary/20 transition-all duration-300">
          <span className="text-[8px] uppercase font-bold tracking-wider text-muted-foreground font-sans">Global Asset Universe</span>
          <span className="text-2xl font-extrabold text-white font-mono mt-1">{health?.telemetry?.totalSymbols ?? 0}</span>
          <span className="text-[8px] text-muted-foreground/80 font-sans block mt-1">Total Symbols Ingested</span>
        </div>

        {/* Symbols with Backtesting history */}
        <div className="border border-border/10 bg-black/40 rounded-xl p-4 flex flex-col justify-between h-24 hover:border-primary/20 transition-all duration-300">
          <span className="text-[8px] uppercase font-bold tracking-wider text-primary font-sans">Backtesting Ready</span>
          <span className="text-2xl font-extrabold text-[#7aff78] font-mono mt-1">{health?.telemetry?.backtestReadySymbols ?? 0}</span>
          <span className="text-[8px] text-muted-foreground/80 font-sans block mt-1">With Cached Candles</span>
        </div>

        {/* Engine mode status */}
        <div className="border border-border/10 bg-black/40 rounded-xl p-4 flex flex-col justify-between h-24 hover:border-primary/20 transition-all duration-300">
          <span className="text-[8px] uppercase font-bold tracking-wider text-blue-400 font-sans">JDDS Engine Health</span>
          <span className="text-md font-extrabold text-white font-mono mt-1 truncate uppercase">{health?.activeMode ?? "Hybrid"}</span>
          <span className="text-[8px] text-[#7aff78] font-mono block mt-1">{health?.paused ? "⏸ Suspended" : "▶ Running"}</span>
        </div>

        {/* Market coverage details summary */}
        <div className="border border-border/10 bg-black/40 rounded-xl p-4 flex flex-col justify-between h-24 hover:border-primary/20 transition-all duration-300">
          <span className="text-[8px] uppercase font-bold tracking-wider text-purple-400 font-sans">Market Coverage</span>
          <div className="text-[9px] font-mono mt-1 space-y-0.5 text-white/95">
            <div>C: {health?.telemetry?.cryptoSymbols ?? 0} • F: {health?.telemetry?.forexSymbols ?? 0}</div>
            <div>S: {health?.telemetry?.stockSymbols ?? 0} • P: {health?.telemetry?.pakistanSymbols ?? 0}</div>
          </div>
        </div>

        {/* Active download data jobs count */}
        <div className="border border-border/10 bg-black/40 rounded-xl p-4 flex flex-col justify-between h-24 hover:border-primary/20 transition-all duration-300">
          <span className="text-[8px] uppercase font-bold tracking-wider text-amber-400 font-sans">Active Data Jobs</span>
          <span className="text-2xl font-extrabold text-amber-400 font-mono mt-1">{health?.jobs?.active ?? 0}</span>
          <span className="text-[8px] text-muted-foreground block mt-1">Pending Workers Queue</span>
        </div>

        {/* Data Quality status pill */}
        <div className="border border-border/10 bg-black/40 rounded-xl p-4 flex flex-col justify-between h-24 hover:border-primary/20 transition-all duration-300">
          <span className="text-[8px] uppercase font-bold tracking-wider text-emerald-400 font-sans">Data Quality Feed</span>
          <span className="text-sm font-extrabold text-white font-mono mt-1 flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Clean Feed</span>
          <span className="text-[8px] text-muted-foreground block mt-1">0% Invalid Candlesticks</span>
        </div>

      </div>

      {/* Feedback Banner */}
      {feedback && (
        <div className="flex items-center gap-2.5 rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4 font-mono text-xs text-emerald-400 animate-fade-in">
          <CheckCircle className="h-4 w-4 shrink-0" />
          <span>{feedback}</span>
        </div>
      )}

      {/* ────────────────── TWO COLUMN PANEL (CONTROLS & QUICK START) ────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Ingestion controls - Left Column */}
        <div className="lg:col-span-2 border border-border/20 bg-black/40 p-6 rounded-xl space-y-4">
          <div className="border-b border-border/10 pb-3 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <Settings2 className="text-primary h-4 w-4" /> JDDS Ingestion Control Panel
              </h2>
              <p className="text-[10px] text-muted-foreground mt-0.5">Manage data synchronization schedulers, rates, and active provider limits</p>
            </div>
          </div>

          {/* Ingestion Mode Select */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-[9px] text-muted-foreground uppercase font-bold">Ingestion Engine Mode</label>
              <div className="flex flex-wrap gap-2">
                {["hybrid", "universe_only", "price_only", "suspended"].map((m) => (
                  <button
                    key={m}
                    onClick={() => handleUpdateMode(m)}
                    disabled={updatingMode}
                    className={`px-3 py-1.5 text-[10px] font-bold font-mono tracking-wider uppercase transition-all rounded-lg border cursor-pointer ${
                      health?.activeMode === m 
                        ? "bg-primary/20 text-primary border-primary/30" 
                        : "bg-[#0a0a0a] text-muted-foreground border-border/40 hover:text-white"
                    }`}
                  >
                    {m.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>

            {/* Quick action buttons */}
            <div className="flex flex-col gap-1.5 justify-end">
              <label className="text-[9px] text-muted-foreground uppercase font-bold">Manual Engine Triggers</label>
              <div className="flex flex-wrap gap-2 mb-1">
                <button
                  onClick={() => handleRunNow("run_universe")}
                  disabled={runningUniverse}
                  className={`px-3 py-1.5 text-[10px] font-bold font-mono tracking-wider uppercase transition-all rounded-lg border cursor-pointer ${
                    runningUniverse 
                      ? "bg-primary/25 text-primary border-primary/45" 
                      : "bg-[#0a0a0a] text-muted-foreground border-border/40 hover:text-white"
                  }`}
                >
                  {runningUniverse ? "Syncing..." : "Sync Universe"}
                </button>
                <button
                  onClick={() => handleRunNow("run_prices")}
                  disabled={runningPrices}
                  className={`px-3 py-1.5 text-[10px] font-bold font-mono tracking-wider uppercase transition-all rounded-lg border cursor-pointer ${
                    runningPrices 
                      ? "bg-primary/25 text-primary border-primary/45" 
                      : "bg-[#0a0a0a] text-muted-foreground border-border/40 hover:text-white"
                  }`}
                >
                  {runningPrices ? "Polling..." : "Poll Prices"}
                </button>
              </div>

              <div className="border border-border/10 bg-black/20 p-2.5 rounded-lg font-mono text-[9px] space-y-1">
                <div className="flex justify-between border-b border-border/5 pb-1 font-sans">
                  <span className="text-muted-foreground">Price Updates Worker:</span>
                  <span className={`font-bold font-mono px-1 rounded ${isPriceWorkerRunning ? "text-emerald-400 bg-emerald-500/15" : "text-neutral-500 bg-neutral-500/10"}`}>
                    {isPriceWorkerRunning ? "YES / ACTIVE" : "NO / IDLE"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">System Uptime:</span>
                  <span className="font-bold text-foreground">{health ? formatUptime(health.system.uptime) : "0s"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Last Crypto Update:</span>
                  <span className="font-bold text-white">{formatDateTime(health?.services.jddsEngine.lastCryptoUpdated ?? "")}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Last Stock Update:</span>
                  <span className="font-bold text-white">{formatDateTime(health?.services.jddsEngine.lastStockUpdated ?? "")}</span>
                </div>
              </div>
            </div>

            {/* Database Stats */}
            <div className="border border-border/40 bg-card/25 rounded-3xl p-5 shadow-lg relative overflow-hidden">
              <div className="flex items-center gap-2 border-b border-border/10 pb-3 mb-3">
                <DatabaseZap className="h-4.5 w-4.5 text-primary" />
                <span className="font-sans font-bold text-xs text-foreground">Ingested Pipeline Registry</span>
              </div>
              <div className="flex flex-col gap-2 font-mono text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Crypto Assets in DB:</span>
                  <span className="font-bold text-white">{health?.services.database.cryptosInDb ?? 0} symbols</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Stock Assets in DB:</span>
                  <span className="font-bold text-white">{health?.services.database.stocksInDb ?? 0} symbols</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Active Crypto Markets:</span>
                  <span className="font-bold text-white">{health?.services.database.activeMarkets ?? 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Universe Interval:</span>
                  <span className="font-bold text-white font-sans">{formatIntervalLabel(cryptoUniverseInterval)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Price Interval:</span>
                  <span className="font-bold text-white font-sans">{formatIntervalLabel(cryptoPriceInterval)}</span>
                </div>
              </div>
            </div>

            {/* Latency Benchmarks */}
            <div className="border border-border/40 bg-card/25 rounded-3xl p-5 shadow-lg relative overflow-hidden sm:col-span-2">
              <div className="flex items-center gap-2 border-b border-border/10 pb-3 mb-3">
                <Activity className="h-4.5 w-4.5 text-primary" />
                <span className="font-sans font-bold text-xs text-foreground">JDdS Engine Gateway Latency Benchmarks</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-3 font-mono text-xs">
                <div className="bg-white/[0.01] border border-border/5 rounded-xl p-3">
                  <span className="text-[10px] text-muted-foreground block mb-1 uppercase font-bold font-sans">PostgreSQL DB</span>
                  <div className="flex flex-col">
                    <span className="text-xs text-emerald-400 font-bold font-sans">CONNECTED</span>
                    <span className="text-white mt-1 text-[11px]">Read: {health?.services.database.readLatency ?? "0ms"}</span>
                    <span className="text-white text-[11px]">Write: {health?.services.database.writeLatency ?? "0ms"}</span>
                  </div>
                </div>
                <div className="bg-white/[0.01] border border-border/5 rounded-xl p-3">
                  <span className="text-[10px] text-muted-foreground block mb-1 uppercase font-bold font-sans">Binance API</span>
                  <div className="flex flex-col">
                    <span className={`text-xs font-bold font-sans ${health?.services.binanceApi.status === "Healthy" ? "text-emerald-400" : "text-rose-400"}`}>
                      {health?.services.binanceApi.status.toUpperCase()}
                    </span>
                    <span className="text-white mt-1 text-[11px]">Latency: {health?.services.binanceApi.latency ?? "0ms"}</span>
                    <span className="text-white text-[11px]">Success: {health?.services.binanceApi.successRate ?? "100%"}</span>
                  </div>
                </div>
                 <div className="bg-white/[0.01] border border-border/5 rounded-xl p-3">
                  <span className="text-[10px] text-muted-foreground block mb-1 uppercase font-bold font-sans">Finnhub API</span>
                  <div className="flex flex-col">
                    <span className={`text-xs font-bold font-sans ${health?.services.finnhubApi.status === "Healthy" ? "text-emerald-400" : "text-rose-400"}`}>
                      {health?.services.finnhubApi.status.toUpperCase()}
                    </span>
                    <span className="text-white mt-1 text-[11px]">Latency: {health?.services.finnhubApi.latency ?? "0ms"}</span>
                    <span className="text-white text-[11px]">Rate delay: 1500ms</span>
                  </div>
                </div>
                {health?.services.marketauxApi && (
                  <div className="bg-white/[0.01] border border-border/5 rounded-xl p-3">
                    <span className="text-[10px] text-muted-foreground block mb-1 uppercase font-bold font-sans">MarketAux News API</span>
                    <div className="flex flex-col">
                      <span className={`text-xs font-bold font-sans ${health.services.marketauxApi.status === "Healthy" ? "text-emerald-400" : "text-rose-400"}`}>
                        {health.services.marketauxApi.status.toUpperCase()}
                      </span>
                      <span className="text-white mt-1 text-[11px]">Latency: {health.services.marketauxApi.latency ?? "0ms"}</span>
                      <span className="text-white text-[11px]">Success: {health.services.marketauxApi.successRate ?? "100%"}</span>
                    </div>
                  </div>
                )}
                {health?.services.cryptopanicApi && (
                  <div className="bg-white/[0.01] border border-border/5 rounded-xl p-3">
                    <span className="text-[10px] text-muted-foreground block mb-1 uppercase font-bold font-sans">CryptoPanic News API</span>
                    <div className="flex flex-col">
                      <span className={`text-xs font-bold font-sans ${health.services.cryptopanicApi.status === "Healthy" ? "text-emerald-400" : health.services.cryptopanicApi.status === "Not Configured" ? "text-amber-400" : "text-rose-400"}`}>
                        {health.services.cryptopanicApi.status.toUpperCase()}
                      </span>
                      <span className="text-white mt-1 text-[11px]">Latency: {health.services.cryptopanicApi.latency ?? "0ms"}</span>
                      <span className="text-white text-[11px]">Success: {health.services.cryptopanicApi.successRate ?? "100%"}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* SECTION 4: LIVE MARKET SNAPSHOT */}
          <div className="border border-border/40 bg-card/25 rounded-3xl p-5 shadow-lg">
            <div className="flex items-center gap-2 border-b border-border/10 pb-3 mb-4">
              <TrendingUp className="h-4.5 w-4.5 text-primary" />
              <span className="font-sans font-bold text-xs text-foreground font-semibold">Live Pipeline Market Snapshot (Movers)</span>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="bg-white/[0.01] border border-border/5 rounded-2xl p-4">
                <span className="text-[11px] text-primary uppercase font-bold tracking-wider block mb-3 font-sans">Crypto Universe Movers</span>
                {health?.movers.crypto && health.movers.crypto.length > 0 ? (
                  <div className="flex flex-col gap-2.5 font-mono text-xs">
                    {health.movers.crypto.map((coin) => (
                      <div key={coin.symbol} className="flex justify-between items-center border-b border-border/[0.03] pb-1.5">
                        <span className="font-bold text-white">{coin.symbol}</span>
                        <div className="flex gap-4">
                          <span className="text-muted-foreground">${coin.price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                          <span className={coin.change >= 0 ? "text-emerald-400" : "text-rose-400"}>
                            {coin.change >= 0 ? "+" : ""}{coin.change.toFixed(2)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className="text-xs text-muted-foreground/60 italic font-mono block">No crypto movers records found.</span>
                )}
              </div>
              <div className="bg-white/[0.01] border border-border/5 rounded-2xl p-4">
                <span className="text-[11px] text-primary uppercase font-bold tracking-wider block mb-3 font-sans">Stock Universe Movers</span>
                {health?.movers.stock && health.movers.stock.length > 0 ? (
                  <div className="flex flex-col gap-2.5 font-mono text-xs">
                    {health.movers.stock.map((stock) => (
                      <div key={stock.symbol} className="flex justify-between items-center border-b border-border/[0.03] pb-1.5">
                        <span className="font-bold text-white">{stock.symbol}</span>
                        <div className="flex gap-4">
                          <span className="text-muted-foreground">${stock.price.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                          <span className={stock.change >= 0 ? "text-emerald-400" : "text-rose-400"}>
                            {stock.change >= 0 ? "+" : ""}{stock.change.toFixed(2)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span className="text-xs text-muted-foreground/60 italic font-mono block">No stock movers records found.</span>
                )}
              </div>
            </div>
          </div>

        </div>

        {/* ═══════════ RIGHT COLUMN: SYSTEM SETTINGS (1/3) ═══════════ */}
        <div className="flex flex-col border border-border/40 bg-card/30 rounded-3xl p-6 shadow-xl backdrop-blur-md relative h-fit">
          <div className="flex items-center gap-2 border-b border-border/10 pb-4 mb-4">
            <Settings2 className="h-5 w-5 text-primary animate-spin-slow" />
            <h2 className="font-sans font-bold text-md text-foreground">System Configuration</h2>
          </div>

          <div className="flex flex-col gap-5 text-xs">

            {/* Global Pause */}
            <div className="border border-border/10 bg-white/[0.01] rounded-2xl p-3.5 flex items-center justify-between">
              <div className="flex flex-col gap-0.5">
                <span className="font-bold text-foreground text-[11px] font-sans">Global Ingestion State</span>
                <span className="text-[9px] text-muted-foreground font-mono">
                  {globalPause ? "⏸ All loops paused" : "▶ All loops active"}
                </span>
              </div>
              <ToggleSwitch 
                enabled={!globalPause} 
                onToggle={() => setGlobalPause(!globalPause)}
              />
            </div>

            {/* API Gateways */}
            <div className="flex flex-col gap-3 border border-border/10 bg-white/[0.01] rounded-2xl p-4">
              <span className="font-sans font-bold text-[11px] text-primary uppercase block">API Gateways</span>
              
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground font-mono">Binance API:</span>
                <ToggleSwitch enabled={binanceEnabled} onToggle={() => setBinanceEnabled(!binanceEnabled)} size="sm" />
              </div>

              <div className="flex items-center justify-between">
                <span className="text-muted-foreground font-mono">Finnhub API:</span>
                <ToggleSwitch enabled={finnhubEnabled} onToggle={() => setFinnhubEnabled(!finnhubEnabled)} size="sm" />
              </div>

              <div className="flex justify-between items-center gap-2 mt-1">
                <span className="text-muted-foreground font-mono text-[10px]">Timeout (ms):</span>
                <input 
                  type="number" 
                  value={apiTimeout}
                  onChange={(e) => { setApiTimeout(Number(e.target.value)); triggerAutoSave(); }}
                  className="w-20 border border-border/20 rounded-xl px-2 py-1 bg-card text-right font-mono text-white text-[11px]"
                />
              </div>

              <div className="flex justify-between items-center gap-2">
                <span className="text-muted-foreground font-mono text-[10px]">Retry Limit:</span>
                <input 
                  type="number" 
                  value={apiRetry}
                  onChange={(e) => { setApiRetry(Number(e.target.value)); triggerAutoSave(); }}
                  className="w-20 border border-border/20 rounded-xl px-2 py-1 bg-card text-right font-mono text-white text-[11px]"
                />
              </div>
            </div>

            {/* Save Button */}
            <button
              type="button"
              onClick={saveConfig}
              disabled={savingConfig}
              className="w-full flex items-center justify-center gap-2 rounded-2xl bg-primary text-primary-foreground hover:bg-primary/95 text-xs font-bold py-3 transition-all cursor-pointer disabled:opacity-50 font-sans"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${savingConfig ? "animate-spin" : ""}`} />
              {savingConfig ? "Saving..." : "Save Configuration"}
            </button>

          </div>
        </div>

      </div>

    </div>
  );
}
