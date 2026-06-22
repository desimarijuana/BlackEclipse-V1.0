"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "@/components/auth/auth-context";
import { redirect } from "next/navigation";
import { TopLoader } from "@/components/ui/top-loader";
import { 
  Settings, Key, Clock, Bell, Save, 
  CheckCircle2, Activity, ShieldAlert 
} from "lucide-react";

export default function SettingsPage() {
  const { user, loading: authLoading } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form states
  const [finnhubToken, setFinnhubToken] = useState("");
  const [binanceApiKey, setBinanceApiKey] = useState("");
  const [marketauxToken, setMarketauxToken] = useState("");
  const [cryptopanicToken, setCryptopanicToken] = useState("");
  const [cryptoInterval, setCryptoInterval] = useState("120000");
  const [stockInterval, setStockInterval] = useState("120000");
  const [emailAlerts, setEmailAlerts] = useState(false);

  const fetchSettings = async () => {
    try {
      const res = await fetch("/api/settings");
      if (!res.ok) throw new Error("Failed to load settings from server");
      const data = await res.json();
      setFinnhubToken(data.finnhubToken);
      setBinanceApiKey(data.binanceApiKey);
      setMarketauxToken(data.marketauxToken || "");
      setCryptopanicToken(data.cryptopanicToken || "");
      setCryptoInterval(data.cryptoInterval);
      setStockInterval(data.stockInterval);
      setEmailAlerts(data.emailAlerts);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failure");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSuccess(false);
    setError(null);
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          finnhubToken,
          binanceApiKey,
          marketauxToken,
          cryptopanicToken,
          cryptoInterval,
          stockInterval,
          emailAlerts
        })
      });
      if (!res.ok) throw new Error("Server failed to save configuration");
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failure");
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    if (!authLoading && !user) {
      redirect("/login");
    }
    fetchSettings();
  }, [user, authLoading]);

  if (authLoading || loading) {
    return (
      <>
        <TopLoader />
        <div className="flex flex-col gap-8 animate-pulse">
          {/* Header skeleton */}
          <div className="flex flex-col gap-2 border-b border-border/40 pb-5">
          <div className="h-3.5 w-28 bg-muted/30 rounded-md"></div>
          <div className="h-8 w-60 bg-muted/20 rounded-lg"></div>
          <div className="h-4 w-96 bg-muted/10 rounded-md mt-1"></div>
        </div>

        <div className="max-w-4xl flex flex-col gap-6">
          {/* Gateway card skeleton */}
          <div className="flex flex-col border border-border/40 bg-card/25 rounded-3xl p-6 gap-5">
            <div className="h-5 w-40 bg-muted/30 rounded-md"></div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <div className="h-3 w-32 bg-muted/20 rounded-md"></div>
                <div className="h-10 w-full bg-muted/10 rounded-xl"></div>
              </div>
              <div className="flex flex-col gap-2">
                <div className="h-3 w-28 bg-muted/20 rounded-md"></div>
                <div className="h-10 w-full bg-muted/10 rounded-xl"></div>
              </div>
            </div>
          </div>

          {/* Clock card skeleton */}
          <div className="flex flex-col border border-border/40 bg-card/25 rounded-3xl p-6 gap-3">
            <div className="h-5 w-48 bg-muted/30 rounded-md"></div>
            <div className="h-3.5 w-full bg-muted/10 rounded-md"></div>
            <div className="h-3.5 w-3/4 bg-muted/10 rounded-md"></div>
          </div>

          {/* Bell card skeleton */}
          <div className="flex flex-col border border-border/40 bg-card/25 rounded-3xl p-6 gap-4">
            <div className="h-5 w-44 bg-muted/30 rounded-md"></div>
            <div className="flex items-center gap-3">
              <div className="h-5 w-5 bg-muted/20 rounded-md"></div>
              <div className="h-3.5 w-64 bg-muted/10 rounded-md"></div>
            </div>
          </div>

          {/* Button skeleton */}
          <div className="h-10 w-40 bg-muted/30 rounded-xl"></div>
        </div>
      </div>
      </>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      {/* Header */}
      <div className="flex flex-col gap-1 border-b border-border/40 pb-5">
        <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-primary">System Parameters</span>
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Application Settings</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Configure API connection endpoints, background ingestion intervals, and database alerting preferences.
        </p>
      </div>

      <div className="max-w-4xl">
        <form onSubmit={handleSave} className="flex flex-col gap-6">
          {success && (
            <div className="flex items-center gap-2 rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4 font-mono text-xs text-emerald-400">
              <CheckCircle2 className="h-4.5 w-4.5" />
              <span>Configuration successfully saved and synced in PostgreSQL!</span>
            </div>
          )}

          {error && (
            <div className="flex items-center gap-2 rounded-2xl border border-rose-500/20 bg-rose-500/10 p-4 font-mono text-xs text-rose-400">
              <ShieldAlert className="h-4.5 w-4.5" />
              <span>Error: {error}</span>
            </div>
          )}

          {/* Card 1: API Gateways */}
          <div className="flex flex-col border border-border/40 bg-card/25 rounded-3xl p-6 shadow-sm gap-5">
            <h2 className="font-serif text-md font-bold text-foreground flex items-center gap-2">
              <Key className="h-4.5 w-4.5 text-primary" /> API Key Integrations
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5 font-mono text-xs">
                <span className="text-muted-foreground uppercase text-[10px]">Finnhub Ingestion Token</span>
                <input
                  type="password"
                  value={finnhubToken}
                  onChange={(e) => setFinnhubToken(e.target.value)}
                  placeholder="Enter Finnhub API Key"
                  className="rounded-xl border border-border/30 bg-white/[0.02] px-4 py-2.5 text-xs text-foreground focus:border-primary/50 focus:outline-none"
                />
              </div>

              <div className="flex flex-col gap-1.5 font-mono text-xs">
                <span className="text-muted-foreground uppercase text-[10px]">Binance Auth Key</span>
                <input
                  type="password"
                  value={binanceApiKey}
                  onChange={(e) => setBinanceApiKey(e.target.value)}
                  placeholder="Enter Binance Key"
                  className="rounded-xl border border-border/30 bg-white/[0.02] px-4 py-2.5 text-xs text-foreground focus:border-primary/50 focus:outline-none"
                />
              </div>

              <div className="flex flex-col gap-1.5 font-mono text-xs">
                <span className="text-muted-foreground uppercase text-[10px]">MarketAux News API Token</span>
                <input
                  type="password"
                  value={marketauxToken}
                  onChange={(e) => setMarketauxToken(e.target.value)}
                  placeholder="Enter MarketAux Token"
                  className="rounded-xl border border-border/30 bg-white/[0.02] px-4 py-2.5 text-xs text-foreground focus:border-primary/50 focus:outline-none"
                />
              </div>

              <div className="flex flex-col gap-1.5 font-mono text-xs">
                <span className="text-muted-foreground uppercase text-[10px]">CryptoPanic News Auth Token</span>
                <input
                  type="password"
                  value={cryptopanicToken}
                  onChange={(e) => setCryptopanicToken(e.target.value)}
                  placeholder="Enter CryptoPanic Token (Optional)"
                  className="rounded-xl border border-border/30 bg-white/[0.02] px-4 py-2.5 text-xs text-foreground focus:border-primary/50 focus:outline-none"
                />
              </div>
            </div>
          </div>

          {/* Card 2: Ingestion Control Reference */}
          <div className="flex flex-col border border-border/40 bg-card/25 rounded-3xl p-6 shadow-sm gap-3">
            <h2 className="font-serif text-md font-bold text-foreground flex items-center gap-2">
              <Clock className="h-4.5 w-4.5 text-primary" /> JDdS Ingestion Control
            </h2>
            <p className="text-xs text-muted-foreground leading-relaxed">
              All ingestion scheduling (universe sync intervals, price polling intervals, Run Now controls) 
              is now managed from the <span className="font-bold text-primary">JDdS Command Station</span> in 
              the Admin dashboard. Navigate there for full control over daemon timing and execution.
            </p>
          </div>

          {/* Card 3: Alert Notifications */}
          <div className="flex flex-col border border-border/40 bg-card/25 rounded-3xl p-6 shadow-sm gap-4">
            <h2 className="font-serif text-md font-bold text-foreground flex items-center gap-2">
              <Bell className="h-4.5 w-4.5 text-primary" /> Notifications & Alerts
            </h2>
            <label className="flex items-center gap-3 font-mono text-xs cursor-pointer text-muted-foreground hover:text-foreground transition-all">
              <input
                type="checkbox"
                checked={emailAlerts}
                onChange={(e) => setEmailAlerts(e.target.checked)}
                className="rounded border-border bg-white/[0.02] text-primary focus:ring-primary h-4.5 w-4.5"
              />
              <span>Enable Email Alerts on API Connection Failures & Timeouts</span>
            </label>
          </div>

          {/* Save Button */}
          <button
            type="submit"
            disabled={saving}
            className="flex items-center justify-center gap-2 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs py-3 max-w-[200px] transition-all cursor-pointer disabled:opacity-50"
          >
            {saving ? (
              <>
                <Activity className="h-4 w-4 animate-spin" /> Saving...
              </>
            ) : (
              <>
                <Save className="h-4 w-4" /> Save Configuration
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
