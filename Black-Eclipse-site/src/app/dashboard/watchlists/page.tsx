"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "@/components/auth/auth-context";
import { 
  FolderPlus, Plus, Trash2, TrendingUp, TrendingDown,
  Activity, Star, CheckCircle2, ShieldAlert, AlertCircle
} from "lucide-react";
import { redirect } from "next/navigation";
import { TopLoader } from "@/components/ui/top-loader";

interface WatchlistAsset {
  symbol: string;
  type: "crypto" | "stock";
  name?: string;
  price: number;
  changePercent: number;
  volume?: number;
  marketCap?: number;
}

interface Watchlist {
  id: string;
  name: string;
  assets: WatchlistAsset[];
  createdAt: string;
}

export default function WatchlistsPage() {
  const { user, loading: authLoading } = useAuth();
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form states
  const [newWatchlistName, setNewWatchlistName] = useState("");
  const [assetSymbol, setAssetSymbol] = useState("");
  const [assetType, setAssetType] = useState<"crypto" | "stock">("crypto");
  const [actionLoading, setActionLoading] = useState(false);

  const fetchWatchlists = async () => {
    try {
      const res = await fetch("/api/watchlists");
      if (!res.ok) throw new Error("Failed to load watchlists");
      const data = await res.json();
      setWatchlists(data);
      if (data.length > 0 && !selectedId) {
        setSelectedId(data[0].id);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load watchlists");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateWatchlist = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWatchlistName.trim()) return;
    setActionLoading(true);
    try {
      const res = await fetch("/api/watchlists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "create", name: newWatchlistName })
      });
      if (res.ok) {
        const newW = await res.json();
        setNewWatchlistName("");
        await fetchWatchlists();
        setSelectedId(newW.id);
      }
    } catch (err) {
      alert("Error creating watchlist");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteWatchlist = async (id: string) => {
    if (!confirm("Are you sure you want to delete this watchlist?")) return;
    setActionLoading(true);
    try {
      const res = await fetch("/api/watchlists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "delete", id })
      });
      if (res.ok) {
        if (selectedId === id) setSelectedId(null);
        await fetchWatchlists();
      }
    } catch (err) {
      alert("Error deleting watchlist");
    } finally {
      setActionLoading(false);
    }
  };

  const handleAddAsset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedId || !assetSymbol.trim()) return;
    setActionLoading(true);
    try {
      const res = await fetch("/api/watchlists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "add",
          id: selectedId,
          symbol: assetSymbol.trim().toUpperCase(),
          type: assetType
        })
      });
      const data = await res.json();
      if (!res.ok) {
        alert(data.error || "Failed to add asset. Verify that the asset exists and is not already tracked.");
      } else {
        setAssetSymbol("");
        await fetchWatchlists();
      }
    } catch (err) {
      alert("Error adding asset");
    } finally {
      setActionLoading(false);
    }
  };

  const handleRemoveAsset = async (symbol: string) => {
    if (!selectedId) return;
    setActionLoading(true);
    try {
      const res = await fetch("/api/watchlists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "remove",
          id: selectedId,
          symbol
        })
      });
      if (res.ok) {
        await fetchWatchlists();
      }
    } catch (err) {
      alert("Error removing asset");
    } finally {
      setActionLoading(false);
    }
  };

  useEffect(() => {
    if (!authLoading && !user) {
      redirect("/login");
    }
    fetchWatchlists();
    const interval = setInterval(fetchWatchlists, 15000); // refresh watchlist prices every 15 seconds
    return () => clearInterval(interval);
  }, [user, authLoading]);

  const activeWatchlist = watchlists.find(w => w.id === selectedId);

  // Compute top mover in the selected watchlist
  const getTopMover = (assets: WatchlistAsset[]) => {
    if (!assets || assets.length === 0) return null;
    return [...assets].sort((a, b) => Math.abs(b.changePercent) - Math.abs(a.changePercent))[0];
  };
  const topMover = activeWatchlist ? getTopMover(activeWatchlist.assets) : null;

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

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          {/* Sidebar skeleton */}
          <div className="flex flex-col gap-4 border border-border/40 bg-card/25 rounded-3xl p-5 h-fit">
            <div className="h-5 w-32 bg-muted/30 rounded-md"></div>
            <div className="space-y-2">
              <div className="h-9 w-full bg-muted/20 rounded-xl"></div>
              <div className="h-9 w-full bg-muted/10 rounded-xl"></div>
              <div className="h-9 w-full bg-muted/10 rounded-xl"></div>
            </div>
            <div className="h-10 w-full bg-muted/30 rounded-xl mt-2"></div>
          </div>

          {/* Main Content (Table) skeleton */}
          <div className="lg:col-span-3 flex flex-col gap-6">
            <div className="flex items-center justify-between border border-border/40 bg-card/15 rounded-3xl p-6">
              <div className="space-y-2">
                <div className="h-5 w-40 bg-muted/30 rounded-md"></div>
                <div className="h-3.5 w-48 bg-muted/15 rounded-md"></div>
              </div>
              <div className="h-8 w-24 bg-muted/30 rounded-xl"></div>
            </div>

            <div className="border border-border/40 bg-card/15 rounded-3xl overflow-hidden">
              <div className="h-12 w-full bg-muted/20 border-b border-border/30"></div>
              <div className="p-4 space-y-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="flex items-center justify-between py-1">
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded-full bg-muted/25"></div>
                      <div className="space-y-1.5">
                        <div className="h-4 w-16 bg-muted/20 rounded"></div>
                        <div className="h-3 w-28 bg-muted/10 rounded"></div>
                      </div>
                    </div>
                    <div className="h-4 w-20 bg-muted/20 rounded"></div>
                    <div className="h-4 w-12 bg-muted/25 rounded"></div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
      </>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      {/* Header */}
      <div className="flex flex-col gap-1 border-b border-border/40 pb-5">
        <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-primary">Portfolio Tracking</span>
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Personal Watchlists</h1>
        <p className="text-xs text-muted-foreground mt-1">
          Monitor customized watchlists of crypto assets and stock symbols with PostgreSQL-backed data.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-4">
        {/* Column 1: Watchlists Navigation & Create */}
        <div className="flex flex-col border border-border/40 bg-card/25 rounded-3xl p-6 shadow-sm gap-5 h-fit">
          <h2 className="font-serif text-md font-bold text-foreground">My Watchlists</h2>

          <div className="flex flex-col gap-2 font-mono text-xs">
            {watchlists.map((w) => {
              const isSelected = selectedId === w.id;
              return (
                <div key={w.id} className="flex items-center justify-between group">
                  <button
                    onClick={() => setSelectedId(w.id)}
                    className={`flex-1 text-left rounded-xl p-3 border font-semibold truncate transition-all cursor-pointer ${
                      isSelected 
                        ? "bg-primary/10 border-primary text-foreground shadow-sm shadow-primary/5" 
                        : "bg-white/[0.01] border-border/5 text-muted-foreground hover:border-border/25 hover:text-foreground"
                    }`}
                  >
                    {w.name} <span className="text-[9px] text-muted-foreground font-normal">({w.assets.length})</span>
                  </button>
                  <button 
                    onClick={() => handleDeleteWatchlist(w.id)}
                    className="opacity-0 group-hover:opacity-100 hover:text-rose-400 p-2 transition-all cursor-pointer"
                    title="Delete Watchlist"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              );
            })}

            {watchlists.length === 0 && (
              <span className="text-xs text-muted-foreground italic text-center py-4">No watchlists found.</span>
            )}
          </div>

          {/* Create Form */}
          <form onSubmit={handleCreateWatchlist} className="flex flex-col gap-2 border-t border-border/10 pt-4">
            <span className="font-mono text-[10px] text-muted-foreground uppercase">New Watchlist</span>
            <div className="flex gap-2">
              <input
                type="text"
                value={newWatchlistName}
                onChange={(e) => setNewWatchlistName(e.target.value)}
                placeholder="Name..."
                className="flex-1 rounded-xl border border-border/30 bg-white/[0.02] px-3 py-2 text-xs font-mono text-foreground focus:border-primary/50 focus:outline-none"
              />
              <button
                type="submit"
                disabled={actionLoading || !newWatchlistName.trim()}
                className="rounded-xl bg-primary text-primary-foreground p-2 px-3 hover:bg-primary/90 disabled:opacity-50 transition-all cursor-pointer"
              >
                <FolderPlus className="h-4 w-4" />
              </button>
            </div>
          </form>
        </div>

        {/* Columns 2-4: Active Watchlist Content */}
        <div className="lg:col-span-3 flex flex-col border border-border/40 bg-card/10 rounded-3xl p-6 min-h-[450px] shadow-sm relative">
          {!selectedId && (
            <div className="flex flex-col items-center justify-center gap-3 text-center my-auto text-muted-foreground">
              <Star className="h-10 w-10 opacity-30 text-primary animate-pulse" />
              <span className="font-serif text-sm">Select or Create a Watchlist</span>
              <p className="text-xs max-w-sm">
                Get started by creating a watchlist on the left and adding assets to monitor live values.
              </p>
            </div>
          )}

          {activeWatchlist && (
            <div className="flex flex-col gap-6 w-full h-full">
              {/* Watchlist Header Info */}
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/10 pb-4">
                <div>
                  <h2 className="font-serif text-xl font-bold text-foreground">{activeWatchlist.name}</h2>
                  <span className="font-mono text-[9px] text-muted-foreground uppercase">Active Tracked List</span>
                </div>
                
                {/* Watchlist Summary card */}
                {topMover && (
                  <div className="flex items-center gap-3 bg-white/[0.02] border border-border/5 rounded-2xl p-2 px-4 text-xs font-mono">
                    <span className="text-[10px] text-muted-foreground">WATCHLIST MOVER:</span>
                    <span className="font-bold text-foreground">{topMover.symbol}</span>
                    <span className={`flex items-center font-bold text-[10px] ${
                      topMover.changePercent >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}>
                      {topMover.changePercent >= 0 ? "+" : ""}{topMover.changePercent.toFixed(2)}%
                    </span>
                  </div>
                )}
              </div>

              {/* Add Symbol Input */}
              <form onSubmit={handleAddAsset} className="flex flex-wrap items-end gap-3 bg-white/[0.01] border border-border/5 rounded-2xl p-4">
                <div className="flex flex-col gap-1.5">
                  <span className="font-mono text-[9px] text-muted-foreground uppercase">Asset Symbol</span>
                  <input
                    type="text"
                    required
                    value={assetSymbol}
                    onChange={(e) => setAssetSymbol(e.target.value)}
                    placeholder="e.g. BTC or AAPL"
                    className="rounded-xl border border-border/30 bg-white/[0.02] px-3 py-2 text-xs font-mono text-foreground focus:border-primary/50 focus:outline-none w-[160px]"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <span className="font-mono text-[9px] text-muted-foreground uppercase">Asset Type</span>
                  <select
                    value={assetType}
                    onChange={(e: any) => setAssetType(e.target.value)}
                    className="rounded-xl border border-border/30 bg-white/[0.02] px-3 py-2 text-xs font-mono text-foreground focus:border-primary/50 focus:outline-none h-9 w-[120px] bg-card"
                  >
                    <option value="crypto">Crypto</option>
                    <option value="stock">US Stock</option>
                  </select>
                </div>
                <button
                  type="submit"
                  disabled={actionLoading || !assetSymbol.trim()}
                  className="rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground font-semibold text-xs py-2 px-4 h-9 flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50"
                >
                  <Plus className="h-4 w-4" /> Add Asset
                </button>
              </form>

              {/* Asset Table */}
              <div className="flex-1 overflow-x-auto">
                <table className="w-full text-left font-mono text-xs">
                  <thead>
                    <tr className="border-b border-border/10 text-muted-foreground text-[10px] uppercase">
                      <th className="py-3 font-normal">Asset</th>
                      <th className="py-3 font-normal">Class</th>
                      <th className="py-3 font-normal text-right">Price</th>
                      <th className="py-3 font-normal text-right">24h Change</th>
                      <th className="py-3 font-normal text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeWatchlist.assets.map((asset) => (
                      <tr key={asset.symbol} className="border-b border-border/5 hover:bg-white/[0.01] transition-all group">
                        <td className="py-3">
                          <div className="flex flex-col">
                            <span className="font-bold text-foreground text-sm">{asset.symbol}</span>
                            {asset.name && <span className="text-[9px] text-muted-foreground truncate max-w-[150px]">{asset.name}</span>}
                          </div>
                        </td>
                        <td className="py-3 text-[10px] text-muted-foreground capitalize">{asset.type}</td>
                        <td className="py-3 text-right font-bold text-foreground">
                          ${asset.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 })}
                        </td>
                        <td className="py-3 text-right">
                          <span className={`inline-flex items-center gap-0.5 font-bold rounded-lg px-2.5 py-0.5 ${
                            asset.changePercent >= 0 
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/10" 
                              : "bg-rose-500/10 text-rose-400 border border-rose-500/10"
                          }`}>
                            {asset.changePercent >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                            {asset.changePercent >= 0 ? "+" : ""}{asset.changePercent.toFixed(2)}%
                          </span>
                        </td>
                        <td className="py-3 text-right">
                          <button
                            onClick={() => handleRemoveAsset(asset.symbol)}
                            className="text-muted-foreground hover:text-rose-400 p-1 transition-all cursor-pointer"
                            title="Remove Asset"
                          >
                            <Trash2 className="h-4.5 w-4.5" />
                          </button>
                        </td>
                      </tr>
                    ))}

                    {activeWatchlist.assets.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-muted-foreground italic">
                          This watchlist has no assets. Add stocks or cryptocurrencies above.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              {/* Dynamic Alerts Simulation Structure */}
              <div className="border border-border/40 bg-card/25 rounded-2xl p-4 flex gap-3 text-xs leading-normal">
                <AlertCircle className="h-5 w-5 text-primary shrink-0" />
                <div className="flex flex-col gap-1">
                  <span className="font-serif font-bold text-foreground">Real-Time Alert Thresholds (Persisted)</span>
                  <span className="text-muted-foreground">
                    Notifications will trigger instantly if any tracked watchlist asset shifts above/below standard threshold limits.
                  </span>
                </div>
              </div>

            </div>
          )}
        </div>
      </div>
    </div>
  );
}
