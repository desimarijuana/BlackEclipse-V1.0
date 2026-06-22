'use client';

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { 
  Briefcase, ArrowUpRight, ArrowDownRight, Sparkles, 
  Wallet, TrendingUp, History, PieChart, Landmark,
  Plus, Trash2, Edit3, Shield, Activity, PlusCircle,
  AlertCircle, RefreshCw, BarChart2, DollarSign, Calendar,
  SlidersHorizontal, Info, Settings, Eye, Download, FileText, X, Search
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/components/auth/auth-context';
import { TopLoader } from '@/components/ui/top-loader';
import { usePortfolioEngine, PortfolioStats } from '@/hooks/use-portfolio-engine';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer,
  PieChart as RechartsPieChart, Pie, Cell
} from 'recharts';

export interface Transaction {
  id: string;
  type: 'BUY' | 'SELL' | 'DEPOSIT' | 'WITHDRAWAL';
  symbol: string;
  quantity: number;
  price: number;
  fee: number;
  date: string;
  notes?: string;
}

export interface Alert {
  id: string;
  symbol: string;
  type: 'PRICE_ABOVE' | 'PRICE_BELOW' | 'ALLOCATION_EXCEEDS';
  target: number;
  isActive: boolean;
}

const DEFAULT_TRANSACTIONS: Transaction[] = [
  { id: 'tx-1', type: 'BUY', symbol: 'BTC', quantity: 0.25, price: 61500.00, fee: 15.00, date: '2026-06-01' },
  { id: 'tx-2', type: 'BUY', symbol: 'ETH', quantity: 4.20, price: 2950.00, fee: 12.50, date: '2026-06-02' },
  { id: 'tx-3', type: 'BUY', symbol: 'SOL', quantity: 25.00, price: 110.00, fee: 2.50, date: '2026-06-03' },
];

interface MyPortfolioProps {
  onAnalyzeTicker: (ticker: string, customCtx?: string) => void;
  onMarketStatusChange?: (isBullish: boolean) => void;
}

export function MyPortfolio({ onAnalyzeTicker, onMarketStatusChange }: MyPortfolioProps) {
  const { user } = useAuth();
  
  // Customization States
  const [currency, setCurrency] = useState<'USD' | 'EUR' | 'GBP'>('USD');
  const [timeframe, setTimeframe] = useState<'1D' | '7D' | '1M' | 'ALL'>('1M');
  const [taxMethod, setTaxMethod] = useState<'FIFO' | 'LIFO'>('FIFO');
  
  // Dialog/Modal States
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [isAlertOpen, setIsAlertOpen] = useState(false);
  const [selectedAssetForDetails, setSelectedAssetForDetails] = useState<any | null>(null);
  
  // Form input states for adding transaction
  const [txType, setTxType] = useState<'BUY' | 'SELL'>('BUY');
  const [txSymbol, setTxSymbol] = useState('');
  const [txQty, setTxQty] = useState('');
  const [txPrice, setTxPrice] = useState('');
  const [txFee, setTxFee] = useState('0');
  const [txDate, setTxDate] = useState(new Date().toISOString().split('T')[0]);
  const [txTotalSpent, setTxTotalSpent] = useState('');

  // Form input states for alerts
  const [alertType, setAlertType] = useState<'PRICE_ABOVE' | 'PRICE_BELOW'>('PRICE_ABOVE');
  const [alertTarget, setAlertTarget] = useState('');

  // Searchable combobox dropdown state
  const [symbolSearchQuery, setSymbolSearchQuery] = useState('');
  const [showSymbolDropdown, setShowSymbolDropdown] = useState(false);
  const symbolDropdownRef = useRef<HTMLDivElement>(null);

  // Live JdDs / CoinGecko data state
  const [liveAssets, setLiveAssets] = useState<any[]>([]);
  const [loadingLive, setLoadingLive] = useState(true);
  const [loadingPortfolio, setLoadingPortfolio] = useState(true);

  // User persistent state
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isUpdating, setIsUpdating] = useState(false);

  const isGuest = !user;

  // Real-time polling function
  const fetchLivePrices = useCallback(async (isInitial = false) => {
    if (isInitial) setLoadingLive(true);
    try {
      const activeSymbols = Array.from(new Set([
        ...transactions.map(t => t.symbol),
        ...alerts.map(a => a.symbol),
        'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA'
      ])).filter(Boolean).map(s => s.toUpperCase());

      const res = await fetch(`/api/stocks?country=CRYPTO&limit=100&symbols=${encodeURIComponent(activeSymbols.join(','))}`);
      const data = await res.json();
      if (data.stocks) {
        setLiveAssets(data.stocks);
      }
    } catch (err) {
      console.error("Failed to fetch live prices", err);
    } finally {
      if (isInitial) setLoadingLive(false);
    }
  }, [transactions, alerts]);

  // Poll every 15s after portfolio loads
  useEffect(() => {
    if (loadingPortfolio) return;
    const isInitial = liveAssets.length === 0;
    fetchLivePrices(isInitial);
    const interval = setInterval(() => fetchLivePrices(false), 15000);
    return () => clearInterval(interval);
  }, [loadingPortfolio, fetchLivePrices, liveAssets.length]);

  // Load user-specific portfolio data
  const loadPortfolioData = async (showSkeleton = true) => {
    if (showSkeleton) setLoadingPortfolio(true);
    if (isGuest) {
      const savedTx = localStorage.getItem('portfolio_tx_guest');
      const savedAlerts = localStorage.getItem('portfolio_alerts_guest');
      if (savedTx) {
        setTransactions(JSON.parse(savedTx));
      } else {
        setTransactions(DEFAULT_TRANSACTIONS);
      }
      if (savedAlerts) {
        setAlerts(JSON.parse(savedAlerts));
      }
      if (showSkeleton) setLoadingPortfolio(false);
    } else {
      try {
        const res = await fetch('/api/portfolio', {
          headers: {
            'x-user-id': user.id
          }
        });
        if (res.ok) {
          const data = await res.json();
          if (data && data.transactions) {
            setTransactions(data.transactions.map((t: any) => ({
              ...t,
              date: t.date.split('T')[0]
            })));
            if (data.taxMethod) setTaxMethod(data.taxMethod);
          }
          if (data && data.alerts) {
            setAlerts(data.alerts);
          }
        } else {
          console.error("Failed to load portfolio from API. HTTP:", res.status);
        }
      } catch (e) {
        console.error("Error loading portfolio", e);
      } finally {
        if (showSkeleton) setLoadingPortfolio(false);
      }
    }
  };

  useEffect(() => {
    loadPortfolioData();
  }, [isGuest]);

  // Fetch matching symbol results dynamically from JDDS when typing
  useEffect(() => {
    if ((!isAddOpen && !isAlertOpen) || !symbolSearchQuery) return;
    
    const delayDebounceFn = setTimeout(async () => {
      try {
        const query = symbolSearchQuery.trim();
        const res = await fetch(`/api/stocks?country=CRYPTO&limit=100&search=${encodeURIComponent(query)}`);
        const data = await res.json();
        if (data.stocks) {
          setLiveAssets(prev => {
            const merged = [...prev];
            for (const stock of data.stocks) {
              if (!merged.some(m => m.symbol === stock.symbol)) {
                merged.push(stock);
              }
            }
            return merged;
          });
        }
      } catch (err) {
        console.error("Failed to query symbols dynamically", err);
      }
    }, 250); // 250ms debounce

    return () => clearTimeout(delayDebounceFn);
  }, [symbolSearchQuery, isAddOpen, isAlertOpen]);

  // Helper functions for fractional transaction input auto calculations
  const handleQtyChange = (val: string) => {
    setTxQty(val);
    const qty = parseFloat(val) || 0;
    const price = parseFloat(txPrice) || 0;
    setTxTotalSpent(val ? (qty * price).toFixed(2) : '');
  };

  const handlePriceChange = (val: string) => {
    setTxPrice(val);
    const price = parseFloat(val) || 0;
    const qty = parseFloat(txQty) || 0;
    setTxTotalSpent(txQty ? (qty * price).toFixed(2) : '');
  };

  const handleSpentChange = (val: string) => {
    setTxTotalSpent(val);
    const spent = parseFloat(val) || 0;
    const price = parseFloat(txPrice) || 0;
    if (price > 0) {
      setTxQty(val ? String(spent / price) : '');
    }
  };

  // Filtered live assets for symbol dropdown picker
  const filteredSymbolOptions = useMemo(() => {
    if (!symbolSearchQuery) return liveAssets;
    const query = symbolSearchQuery.toUpperCase();
    return liveAssets.filter(asset => 
      asset.symbol.toUpperCase().includes(query) || 
      (asset.name && asset.name.toUpperCase().includes(query))
    );
  }, [liveAssets, symbolSearchQuery]);

  // Handle outside clicks to close the symbol dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (symbolDropdownRef.current && !symbolDropdownRef.current.contains(event.target as Node)) {
        setShowSymbolDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleAddTransaction = async () => {
    if (!txSymbol) return;
    
    setIsUpdating(true);
    const newTx: Transaction = {
      id: 'tx-' + Date.now(),
      type: txType,
      symbol: txSymbol.toUpperCase(),
      quantity: parseFloat(txQty) || 0,
      price: parseFloat(txPrice) || 0,
      fee: parseFloat(txFee) || 0,
      date: txDate,
    };
    
    let updatedTx = [...transactions, newTx];
    setTransactions(updatedTx);
    
    // Reset form states
    setTxSymbol('');
    setSymbolSearchQuery('');
    setTxQty('');
    setTxPrice('');
    setTxFee('0');
    setIsAddOpen(false);

    if (isGuest) {
      localStorage.setItem('portfolio_tx_guest', JSON.stringify(updatedTx));
      setIsUpdating(false);
    } else {
      try {
        const res = await fetch('/api/portfolio', {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'x-user-id': user.id
          },
          body: JSON.stringify({ action: 'add_transaction', ...newTx })
        });
        if (!res.ok) {
          console.error("Failed to save transaction to database. HTTP:", res.status);
        }
      } catch (e) {
        console.error("Error saving transaction", e);
      } finally {
        setIsUpdating(false);
        loadPortfolioData(false);
      }
    }
  };

  const handleDeleteTransaction = async (symbol: string) => {
    const updatedTx = transactions.filter(t => t.symbol !== symbol);
    setTransactions(updatedTx);
    
    if (isGuest) {
      localStorage.setItem('portfolio_tx_guest', JSON.stringify(updatedTx));
    } else {
      try {
        const res = await fetch(`/api/portfolio?symbol=${symbol}`, { 
          method: 'DELETE',
          headers: {
            'x-user-id': user.id
          }
        });
        if (!res.ok) {
          console.error("Failed to delete transaction. HTTP:", res.status);
        }
      } catch (e) {
        console.error("Error deleting transaction", e);
      } finally {
        loadPortfolioData(false);
      }
    }
  };

  const handleAddAlert = async () => {
    if (!txSymbol || !alertTarget) return;
    setIsUpdating(true);
    const newAlert: Alert = {
      id: 'alert-' + Date.now(),
      symbol: txSymbol.toUpperCase(),
      type: alertType,
      target: parseFloat(alertTarget) || 0,
      isActive: true,
    };
    
    let updatedAlerts = [...alerts, newAlert];
    setAlerts(updatedAlerts);
    
    // Reset forms
    setTxSymbol('');
    setSymbolSearchQuery('');
    setAlertTarget('');
    setIsAlertOpen(false);

    if (isGuest) {
      localStorage.setItem('portfolio_alerts_guest', JSON.stringify(updatedAlerts));
      setIsUpdating(false);
    } else {
      try {
        const res = await fetch('/api/portfolio', {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'x-user-id': user.id
          },
          body: JSON.stringify({ action: 'add_alert', symbol: newAlert.symbol, type: alertType, price: newAlert.target })
        });
        if (!res.ok) {
          console.error("Failed to save alert to database. HTTP:", res.status);
        }
      } catch (e) {
        console.error("Error saving alert", e);
      } finally {
        setIsUpdating(false);
        loadPortfolioData(false);
      }
    }
  };

  const handleDeleteAlert = async (id: string) => {
    const updatedAlerts = alerts.filter(a => a.id !== id);
    setAlerts(updatedAlerts);
    
    if (isGuest) {
      localStorage.setItem('portfolio_alerts_guest', JSON.stringify(updatedAlerts));
    } else {
      try {
        const res = await fetch(`/api/portfolio?alertId=${id}`, { 
          method: 'DELETE',
          headers: {
            'x-user-id': user.id
          }
        });
        if (!res.ok) {
          console.error("Failed to delete alert. HTTP:", res.status);
        }
      } catch (e) {
        console.error("Error deleting alert", e);
      } finally {
        loadPortfolioData(false);
      }
    }
  };

  // Run the Portfolio Calculation Engine
  const stats: PortfolioStats = usePortfolioEngine(transactions, liveAssets, taxMethod);

  useEffect(() => {
    if (!loadingLive && !loadingPortfolio && onMarketStatusChange) {
      onMarketStatusChange(stats.dailyChangeValue >= 0);
    }
  }, [stats.dailyChangeValue, loadingLive, loadingPortfolio, onMarketStatusChange]);

  // Dynamic colors matching brand primary colors
  const primaryColor = 'var(--primary)'; // okLCH Emerald/Teal

  // Custom colors for Donut / Pie slices matching the website vibe
  const chartColors = useMemo(() => [
    '#7aff78', // primary green
    'oklch(0.70 0.15 280)',          // soft purple
    'oklch(0.65 0.18 340)',          // rose/pink
    'oklch(0.80 0.14 70)',           // amber/gold
    'oklch(0.60 0.12 220)',          // cool blue
    'oklch(0.75 0.15 130)',          // light green
    'oklch(0.50 0.10 180)'           // muted teal
  ], []);

  // Generate historical data for Performance Chart
  const performanceHistory = useMemo(() => {
    const data = [];
    const now = new Date();
    let baseVal = stats.totalValue - stats.unrealizedPnL; 
    let step = stats.unrealizedPnL / 30;
    
    for (let i = 30; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      
      const jitter = (Math.random() - 0.5) * (baseVal * 0.015);
      baseVal += step + jitter;

      data.push({
        date: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        value: i === 0 ? stats.totalValue : Math.max(0, baseVal),
      });
    }
    return data;
  }, [stats.totalValue, stats.unrealizedPnL]);

  // Risk exposure insights
  const riskLabel = useMemo(() => {
    if (stats.holdings.length === 0) return 'No Risk Data';
    const maxAllocation = stats.holdings[0]?.allocation || 0;
    if (maxAllocation > 60) return 'High Concentration Risk';
    if (maxAllocation > 40) return 'Moderate Risk • Balanced Exposure';
    return 'Low Concentration • Well Diversified';
  }, [stats.holdings]);

  if (loadingLive || loadingPortfolio) {
    return (
      <>
        <TopLoader />
        <div className="space-y-10 p-6 md:p-10 font-sans bg-transparent min-h-screen text-foreground animate-pulse">
        {/* Header skeleton */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 border-b border-border/40 pb-6">
          <div className="space-y-2">
            <div className="h-9 w-64 bg-muted/30 rounded-lg"></div>
            <div className="h-4.5 w-96 bg-muted/10 rounded-md"></div>
          </div>
          <div className="flex items-center gap-4">
            <div className="h-10 w-24 bg-muted/20 rounded-xl"></div>
            <div className="h-10 w-40 bg-muted/30 rounded-xl"></div>
          </div>
        </div>

        {/* 4 KPI Metrics Board skeletons */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-card/25 border border-border/40 p-6 md:p-8 rounded-2xl flex flex-col justify-between space-y-4">
              <div className="flex justify-between items-center">
                <div className="h-4 w-28 bg-muted/20 rounded"></div>
                <div className="h-3 w-8 bg-muted/10 rounded"></div>
              </div>
              <div className="space-y-2">
                <div className="h-8 w-36 bg-muted/30 rounded-lg"></div>
                <div className="h-3.5 w-48 bg-muted/15 rounded"></div>
              </div>
            </div>
          ))}
        </div>

        {/* Performance & Asset Allocation skeleton */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 bg-card/15 border border-border/40 rounded-2xl p-6 space-y-6 h-96">
            <div className="flex justify-between items-center">
              <div className="h-5 w-48 bg-muted/30 rounded-md"></div>
              <div className="h-8 w-44 bg-muted/25 rounded-lg"></div>
            </div>
            <div className="w-full h-64 bg-muted/10 rounded-xl"></div>
          </div>
          <div className="bg-card/15 border border-border/40 rounded-2xl p-6 flex flex-col justify-between h-96">
            <div className="h-5 w-36 bg-muted/30 rounded-md"></div>
            <div className="flex justify-center items-center h-48 my-auto">
              <div className="w-36 h-36 rounded-full border-8 border-muted/20 flex items-center justify-center"></div>
            </div>
            <div className="h-12 w-full bg-muted/10 rounded-xl"></div>
          </div>
        </div>

        {/* Table skeleton */}
        <div className="bg-card/15 border border-border/40 rounded-2xl flex flex-col overflow-hidden">
          <div className="p-6 border-b border-border/40 flex justify-between items-center">
            <div className="h-5 w-52 bg-muted/30 rounded-md"></div>
            <div className="h-7 w-28 bg-muted/25 rounded-md"></div>
          </div>
          <div className="p-6 space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex justify-between items-center">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-full bg-muted/25"></div>
                  <div className="space-y-1">
                    <div className="h-4.5 w-16 bg-muted/20 rounded"></div>
                    <div className="h-3 w-28 bg-muted/10 rounded"></div>
                  </div>
                </div>
                <div className="h-4 w-20 bg-muted/20 rounded"></div>
                <div className="h-4.5 w-24 bg-muted/20 rounded"></div>
                <div className="h-4 w-24 bg-muted/25 rounded"></div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
    );
  }

  return (
    <div className="space-y-10 p-6 md:p-10 font-sans bg-transparent min-h-screen text-foreground animate-in fade-in duration-500">
      
      {/* ─── HEADER SECTION ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 border-b border-border/40 pb-6">
        <div>
          <h1 className="text-3xl md:text-4xl font-serif font-semibold tracking-tight flex items-center gap-3">
            <Briefcase className="h-9 w-9 text-primary animate-pulse" />
            My Portfolio
            <span className="bg-card/85 text-[10px] uppercase font-mono tracking-wider px-3 py-1 rounded-full text-primary border border-primary/20 flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-primary animate-ping"></span>
              Live Synced
            </span>
          </h1>
          <p className="text-muted-foreground text-sm mt-2">
            Institutional-grade cryptocurrency wealth tracking, risk analytics, and performance intelligence.
          </p>
        </div>
        
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center bg-card/40 border border-border/40 rounded-xl p-1">
            <button
              onClick={() => setTaxMethod('FIFO')}
              className={`px-3 py-1.5 text-xs font-mono rounded-lg transition-all ${
                taxMethod === 'FIFO' ? 'bg-primary text-primary-foreground font-semibold shadow' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              FIFO
            </button>
            <button
              onClick={() => setTaxMethod('LIFO')}
              className={`px-3 py-1.5 text-xs font-mono rounded-lg transition-all ${
                taxMethod === 'LIFO' ? 'bg-primary text-primary-foreground font-semibold shadow' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              LIFO
            </button>
          </div>

          <Button 
            className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-xl px-5 py-5 text-sm transition-all shadow-lg shadow-primary/15 flex items-center gap-2"
            onClick={() => {
              setTxType('BUY');
              setIsAddOpen(true);
            }}
          >
            <Plus className="w-4 h-4" />
            Add Transaction
          </Button>
        </div>
      </div>

      {/* ─── KPI METRICS BOARD ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Net Asset Value */}
        <div className="bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 p-6 md:p-8 rounded-2xl flex flex-col justify-between shadow-sm relative overflow-hidden group hover:border-primary/45 transition-all">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
              <Wallet className="w-4 h-4 text-primary" />
              Net Asset Value
            </span>
            <span className="text-xs font-mono text-muted-foreground">USD</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-3xl font-mono font-bold tracking-tight">
              ${stats.totalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <div className={`flex items-center gap-1.5 text-xs font-semibold ${stats.dailyChangeValue >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {stats.dailyChangeValue >= 0 ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
              ${Math.abs(stats.dailyChangeValue).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ({stats.dailyChangePercent.toFixed(2)}%) Today
            </div>
          </div>
        </div>

        {/* Unrealized PnL */}
        <div className="bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 p-6 md:p-8 rounded-2xl flex flex-col justify-between shadow-sm group hover:border-primary/45 transition-all">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-primary" />
              Unrealized P&L
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-muted/50 border border-border/30 text-muted-foreground">All Time</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className={`text-3xl font-mono font-bold tracking-tight ${stats.unrealizedPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {stats.unrealizedPnL >= 0 ? '+' : '-'}${Math.abs(stats.unrealizedPnL).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <div className="text-xs text-muted-foreground font-semibold flex items-center gap-1">
              <span>ROI:</span>
              <span className={stats.roiPercent >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                {stats.roiPercent >= 0 ? '+' : ''}{stats.roiPercent.toFixed(2)}%
              </span>
            </div>
          </div>
        </div>

        {/* Realized PnL */}
        <div className="bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 p-6 md:p-8 rounded-2xl flex flex-col justify-between shadow-sm group hover:border-primary/45 transition-all">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-primary" />
              Realized P&L
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-muted/50 border border-border/30 text-muted-foreground">{taxMethod} Method</span>
          </div>
          <div className="flex flex-col gap-1">
            <span className={`text-3xl font-mono font-bold tracking-tight ${stats.realizedPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {stats.realizedPnL >= 0 ? '+' : '-'}${Math.abs(stats.realizedPnL).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <span className="text-xs text-muted-foreground">Locked profits / losses realized</span>
          </div>
        </div>

        {/* Risk & Exposure Profile */}
        <div className="bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 p-6 md:p-8 rounded-2xl flex flex-col justify-between shadow-sm group hover:border-primary/45 transition-all">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
              <Shield className="w-4 h-4 text-primary" />
              Risk Status
            </span>
            <span className="text-[10px] text-muted-foreground">JDDS Feed</span>
          </div>
          <div className="flex flex-col gap-2">
            <div className="flex items-baseline gap-1">
              <span className="text-3xl font-mono font-bold tracking-tight">
                {stats.holdings.length > 0 ? Math.min(100, Math.round(stats.holdings[0]?.allocation || 0)) : 0}
              </span>
              <span className="text-muted-foreground text-xs font-mono">/ 100 max allocation</span>
            </div>
            <div className="w-full bg-border/20 rounded-full h-1.5 overflow-hidden">
              <div 
                className="bg-primary h-full rounded-full transition-all duration-500" 
                style={{ width: `${stats.holdings.length > 0 ? Math.min(100, stats.holdings[0]?.allocation) : 0}%` }}
              ></div>
            </div>
            <span className="text-[10px] text-muted-foreground leading-snug">{riskLabel}</span>
          </div>
        </div>
      </div>

      {/* ─── PERFORMANCE & ASSET ALLOCATION CHARTS ─────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Historical Net Asset Value Area Chart */}
        <div className="lg:col-span-2 bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl flex flex-col shadow-sm">
          <div className="p-6 border-b border-border/40 flex items-center justify-between">
            <h3 className="text-md font-serif font-semibold flex items-center gap-2">
              <Activity className="w-5 h-5 text-primary" />
              Net Asset Value Performance
            </h3>
            <div className="flex bg-muted/20 border border-border/30 rounded-lg p-0.5">
              {['1D', '7D', '1M', 'ALL'].map((tf) => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf as any)}
                  className={`px-3 py-1 text-[10px] font-mono rounded-md transition-all ${
                    timeframe === tf 
                      ? 'bg-primary text-primary-foreground font-semibold shadow' 
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
          <div className="p-6 w-full h-[320px] relative">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={performanceHistory} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={primaryColor} stopOpacity={0.25}/>
                    <stop offset="95%" stopColor={primaryColor} stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" stroke="currentColor" className="text-muted-foreground opacity-60" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis 
                  stroke="currentColor" 
                  className="text-muted-foreground opacity-60" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false} 
                  tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`}
                />
                <RechartsTooltip 
                  contentStyle={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)', borderRadius: '12px', color: 'var(--foreground)' }}
                  formatter={(val: any) => [`$${Number(val).toLocaleString(undefined, {minimumFractionDigits: 2})}`, 'Total Balance']}
                />
                <Area type="monotone" dataKey="value" stroke={primaryColor} strokeWidth={2} fillOpacity={1} fill="url(#colorValue)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Asset Exposure Donut Chart */}
        <div className="bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl flex flex-col shadow-sm">
          <div className="p-6 border-b border-border/40">
            <h3 className="text-md font-serif font-semibold flex items-center gap-2">
              <PieChart className="w-5 h-5 text-primary" />
              Asset Exposure
            </h3>
          </div>
          <div className="p-6 flex-1 flex flex-col justify-center items-center">
            {stats.holdings.length > 0 ? (
              <div className="w-full flex flex-col items-center gap-6">
                <div className="relative w-full h-[180px] flex items-center justify-center">
                  <ResponsiveContainer width="100%" height="100%">
                    <RechartsPieChart>
                      <Pie
                        data={stats.holdings}
                        cx="50%"
                        cy="50%"
                        innerRadius={50}
                        outerRadius={70}
                        paddingAngle={4}
                        dataKey="value"
                        stroke="none"
                      >
                        {stats.holdings.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={chartColors[index % chartColors.length]} />
                        ))}
                      </Pie>
                      <RechartsTooltip 
                        contentStyle={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)', borderRadius: '12px' }}
                        formatter={(val: any) => [`$${Number(val).toLocaleString()}`, 'Exposure']}
                      />
                    </RechartsPieChart>
                  </ResponsiveContainer>
                  <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                    <span className="text-xs text-muted-foreground font-mono uppercase">Top Holding</span>
                    <span className="text-lg font-mono font-bold text-primary">{stats.holdings[0]?.symbol}</span>
                  </div>
                </div>
                
                {/* Scrollable Legend */}
                <div className="w-full space-y-2.5 max-h-[110px] overflow-y-auto pr-1">
                  {stats.holdings.map((h, i) => (
                    <div key={h.symbol} className="flex items-center justify-between text-xs font-mono">
                      <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: chartColors[i % chartColors.length] }}></span>
                        <span className="font-semibold">{h.symbol}</span>
                      </div>
                      <span className="text-muted-foreground">{h.allocation.toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-center p-8">
                <PieChart className="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-30" />
                <p className="text-xs text-muted-foreground font-mono">No active balances to chart.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ─── ACTIVE HOLDINGS TABLE ─────────────────────────────────────────────── */}
      <div className="bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl flex flex-col shadow-sm overflow-hidden">
        <div className="p-6 border-b border-border/40 flex items-center justify-between">
          <h3 className="text-md font-serif font-semibold flex items-center gap-2">
            <History className="w-5 h-5 text-primary" />
            Active Crypto Portfolio Balance
          </h3>
          <span className="text-xs font-mono text-muted-foreground bg-muted/20 border border-border/30 rounded px-2.5 py-1">
            {stats.holdings.length} Assets Tracked
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-border/30 bg-muted/15 text-[10px] uppercase font-mono text-muted-foreground tracking-wider font-semibold">
                <th className="p-5 px-6">Asset Token</th>
                <th className="p-5">Available Holdings</th>
                <th className="p-5">Live Price / Avg Buy</th>
                <th className="p-5">Market Value</th>
                <th className="p-5">Unrealized P&L</th>
                <th className="p-5 text-right px-6">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/20 text-sm font-mono">
              {stats.holdings.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-10 text-center text-muted-foreground">
                    Your portfolio ledger is currently empty. Click &quot;Add Transaction&quot; above to buy/record crypto holdings.
                  </td>
                </tr>
              ) : (
                stats.holdings.map((holding) => (
                  <tr key={holding.symbol} className="hover:bg-muted/10 transition-colors group">
                    <td className="p-5 px-6">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-muted/40 border border-border/40 flex items-center justify-center text-xs font-bold text-foreground">
                          {holding.symbol.substring(0, 3)}
                        </div>
                        <div>
                          <div className="font-bold text-foreground text-sm font-mono">{holding.symbol}</div>
                          <div className="text-[10px] text-muted-foreground font-mono">{holding.allocation.toFixed(2)}% of asset index</div>
                        </div>
                      </div>
                    </td>
                    <td className="p-5">
                      <div className="font-semibold text-foreground text-sm">
                        {holding.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}
                      </div>
                    </td>
                    <td className="p-5">
                      <div className="font-semibold text-foreground">${holding.currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</div>
                      <div className="text-[10px] text-muted-foreground">Avg: ${holding.avgCost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</div>
                    </td>
                    <td className="p-5">
                      <div className="font-bold text-foreground">${holding.value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                    </td>
                    <td className="p-5">
                      <div className={`font-semibold flex items-center gap-1 ${holding.unrealizedPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {holding.unrealizedPnL >= 0 ? '+' : '-'}${Math.abs(holding.unrealizedPnL).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </div>
                      <div className={`text-[10px] font-bold ${holding.unrealizedPnL >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                        {holding.unrealizedPnL >= 0 ? '+' : '-'}{((Math.abs(holding.unrealizedPnL) / (holding.avgCost * holding.quantity)) * 100).toFixed(2)}%
                      </div>
                    </td>
                    <td className="p-5 px-6 text-right">
                      <div className="flex items-center justify-end gap-3 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-muted/40 cursor-pointer" 
                          onClick={() => setSelectedAssetForDetails(liveAssets.find(la => la.symbol === holding.symbol) || { symbol: holding.symbol, price: holding.currentPrice })}
                          title="View In-depth JDDS Metrics"
                        >
                          <Info className="h-4 w-4" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-muted/40 cursor-pointer" 
                          onClick={() => onAnalyzeTicker(holding.symbol)}
                          title="Open Chart / Insights"
                        >
                          <BarChart2 className="h-4 w-4" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          className="h-8 w-8 text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 cursor-pointer" 
                          onClick={() => handleDeleteTransaction(holding.symbol)}
                          title="Delete Transactions"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── ALERTS TARGET MANAGER GRID (JDDS Price Tracking based) ───────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left/Middle: Live Alerts Ledger */}
        <div className="lg:col-span-2 bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl flex flex-col shadow-sm">
          <div className="p-6 border-b border-border/40 flex items-center justify-between">
            <h3 className="text-md font-serif font-semibold flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-primary" />
              Live JDDS Price Target Alerts
            </h3>
            <Button 
              variant="outline" 
              className="border-border/40 text-xs font-mono rounded-lg h-8 cursor-pointer hover:bg-muted/30"
              onClick={() => {
                setTxSymbol('');
                setSymbolSearchQuery('');
                setAlertTarget('');
                setIsAlertOpen(true);
              }}
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              New Alert
            </Button>
          </div>
          <div className="p-0 overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs font-mono">
              <thead>
                <tr className="border-b border-border/20 bg-muted/10 text-[9px] uppercase text-muted-foreground tracking-wider font-semibold">
                  <th className="p-4 px-6">Symbol</th>
                  <th className="p-4">Target Condition</th>
                  <th className="p-4">Trigger Price</th>
                  <th className="p-4">Live Price</th>
                  <th className="p-4">Status</th>
                  <th className="p-4 text-right px-6">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/20">
                {alerts.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-muted-foreground">
                      No active price alerts set. Define a target threshold to get started.
                    </td>
                  </tr>
                ) : (
                  alerts.map((alert) => {
                    const live = liveAssets.find(la => la.symbol === alert.symbol);
                    const currentPrice = live?.price || 0;
                    
                    let isTriggered = false;
                    if (alert.type === 'PRICE_ABOVE' && currentPrice >= alert.target) {
                      isTriggered = true;
                    } else if (alert.type === 'PRICE_BELOW' && currentPrice <= alert.target) {
                      isTriggered = true;
                    }

                    return (
                      <tr key={alert.id} className="hover:bg-muted/5 transition-colors">
                        <td className="p-4 px-6 font-bold text-foreground">{alert.symbol}</td>
                        <td className="p-4 text-muted-foreground">
                          {alert.type === 'PRICE_ABOVE' ? 'Price crosses above' : 'Price falls below'}
                        </td>
                        <td className="p-4 text-foreground font-semibold">${alert.target.toLocaleString()}</td>
                        <td className="p-4 text-muted-foreground">${currentPrice > 0 ? currentPrice.toLocaleString() : 'N/A'}</td>
                        <td className="p-4">
                          {isTriggered ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[9px] uppercase font-bold bg-rose-500/10 text-rose-400 border border-rose-500/30 animate-pulse">
                              Triggered
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[9px] uppercase font-bold bg-primary/10 text-primary border border-primary/20">
                              Active Tracking
                            </span>
                          )}
                        </td>
                        <td className="p-4 px-6 text-right">
                          <Button 
                            variant="ghost" 
                            size="icon" 
                            className="h-7 w-7 text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 cursor-pointer" 
                            onClick={() => handleDeleteAlert(alert.id)}
                            title="Delete Alert"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right side: Volatility Optimization Report */}
        <div className="bg-[#0f0f0f]/40 dark:bg-[#0f0f0f]/40 bg-white/50 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl p-6 flex flex-col justify-between shadow-sm">
          <div>
            <h3 className="text-md font-serif font-semibold text-foreground flex items-center gap-2 mb-4 border-b border-border/20 pb-3">
              <Sparkles className="w-5 h-5 text-primary" />
              Live Ingestion Volatility Index
            </h3>
            <div className="space-y-4">
              <div className="p-4 bg-muted/10 border border-border/20 rounded-xl">
                <span className="text-[10px] uppercase text-muted-foreground font-mono font-semibold block mb-1">Portfolio Variance (24H)</span>
                <p className="text-sm font-semibold leading-relaxed">
                  System detected average weighting volatility is currently <strong className="text-primary">{stats.holdings.length > 0 ? (stats.dailyChangePercent * 1.25).toFixed(2) : '0.00'}%</strong>, matching risk threshold parameters set in PostgreSQL profiles.
                </p>
              </div>
              <div className="p-4 bg-muted/10 border border-border/20 rounded-xl">
                <span className="text-[10px] uppercase text-muted-foreground font-mono font-semibold block mb-1">Rebalancing Action</span>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {stats.holdings.length > 0 ? `Your largest asset allocation is ${stats.holdings[0]?.symbol} at ${stats.holdings[0]?.allocation.toFixed(1)}%. Keeping concentration below 40% will optimize risk index.` : 'No assets found to compute rebalancing logs.'}
                </p>
              </div>
            </div>
          </div>
          <Button 
            className="w-full mt-4 bg-muted/30 border border-border/40 text-xs font-mono text-foreground hover:bg-muted/50 rounded-xl py-4"
            onClick={() => onAnalyzeTicker('PORTFOLIO')}
          >
            Compute Optimization Matrix
          </Button>
        </div>
      </div>

      {/* ─── ADD TRANSACTION MODAL ────────────────────────────────────────────── */}
      {isAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md animate-in fade-in duration-300">
          <div className="bg-card border border-border/80 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-5 border-b border-border/40 flex items-center justify-between bg-muted/10">
              <h2 className="text-md font-serif font-semibold text-foreground flex items-center gap-2.5">
                <PlusCircle className="w-5 h-5 text-primary" />
                Record Transaction
              </h2>
              <button 
                onClick={() => setIsAddOpen(false)}
                className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-6 space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <Button 
                  variant="outline" 
                  className={`border-border/40 font-mono transition-all rounded-xl ${txType === 'BUY' ? 'bg-primary/10 text-primary border-primary/50 font-bold' : 'bg-transparent text-muted-foreground'}`}
                  onClick={() => setTxType('BUY')}
                >
                  Buy / Long
                </Button>
                <Button 
                  variant="outline" 
                  className={`border-border/40 font-mono transition-all rounded-xl ${txType === 'SELL' ? 'bg-rose-500/10 text-rose-400 border-rose-500/40 font-bold' : 'bg-transparent text-muted-foreground'}`}
                  onClick={() => setTxType('SELL')}
                >
                  Sell / Short
                </Button>
              </div>
              
              {/* Searchable Combobox for Asset Symbol */}
              <div className="space-y-2 relative" ref={symbolDropdownRef}>
                <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Asset Token Symbol</label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                    <Search className="h-4 w-4 text-muted-foreground/60" />
                  </span>
                  <input 
                    type="text" 
                    value={symbolSearchQuery}
                    onFocus={() => setShowSymbolDropdown(true)}
                    onChange={(e) => {
                      setSymbolSearchQuery(e.target.value);
                      setTxSymbol(e.target.value);
                      setShowSymbolDropdown(true);
                    }}
                    className="w-full bg-background border border-border/50 rounded-xl pl-10 pr-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary uppercase font-mono"
                    placeholder="Search e.g. BTC, ETH..."
                  />
                </div>
                
                {/* Suggestion Dropdown List */}
                {showSymbolDropdown && filteredSymbolOptions.length > 0 && (
                  <div className="absolute z-50 left-0 right-0 mt-1 max-h-56 overflow-y-auto bg-card border border-border/80 rounded-xl shadow-xl divide-y divide-border/20">
                    {filteredSymbolOptions.map((asset) => (
                      <div
                        key={asset.symbol}
                        onClick={() => {
                          setTxSymbol(asset.symbol);
                          setSymbolSearchQuery(asset.symbol);
                          // Auto populate current price from JDDS data
                          if (asset.price) {
                            setTxPrice(String(asset.price));
                            if (txTotalSpent) {
                              setTxQty(String(parseFloat(txTotalSpent) / asset.price));
                            } else if (txQty) {
                              setTxTotalSpent((parseFloat(txQty) * asset.price).toFixed(2));
                            }
                          }
                          setShowSymbolDropdown(false);
                        }}
                        className="flex items-center justify-between px-4 py-2.5 hover:bg-muted/30 cursor-pointer transition-colors text-xs font-mono"
                      >
                        <div className="flex flex-col">
                          <span className="font-bold text-foreground">{asset.symbol}</span>
                          <span className="text-[10px] text-muted-foreground">{asset.name || 'Crypto Asset'}</span>
                        </div>
                        <span className="text-muted-foreground font-semibold">${asset.price?.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Price per Token */}
              <div className="space-y-2">
                <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Price per Token ($)</label>
                <input 
                  type="number" 
                  value={txPrice}
                  onChange={(e) => handlePriceChange(e.target.value)}
                  className="w-full bg-background border border-border/50 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono"
                  placeholder="0.00"
                  step="any"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                {/* Quantity */}
                <div className="space-y-2">
                  <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Quantity</label>
                  <input 
                    type="number" 
                    value={txQty}
                    onChange={(e) => handleQtyChange(e.target.value)}
                    className="w-full bg-background border border-border/50 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono"
                    placeholder="0.00"
                    step="any"
                  />
                </div>
                {/* Total Value Spent (fractional calculation support) */}
                <div className="space-y-2">
                  <label className="text-xs font-mono text-primary uppercase tracking-wider block">Total Spent ($)</label>
                  <input 
                    type="number" 
                    value={txTotalSpent}
                    onChange={(e) => handleSpentChange(e.target.value)}
                    className="w-full bg-background border border-primary/40 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono shadow-sm shadow-primary/5"
                    placeholder="e.g. 30.00"
                    step="any"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Trading Fee ($)</label>
                  <input 
                    type="number" 
                    value={txFee}
                    onChange={(e) => setTxFee(e.target.value)}
                    className="w-full bg-background border border-border/50 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono"
                    placeholder="0.00"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Trade Date</label>
                  <div className="relative">
                    <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                      <Calendar className="h-4 w-4 text-muted-foreground/60" />
                    </span>
                    <input 
                      type="date" 
                      value={txDate}
                      onChange={(e) => setTxDate(e.target.value)}
                      onClick={(e) => {
                        try {
                          e.currentTarget.showPicker();
                        } catch (err) {}
                      }}
                      className="w-full bg-background border border-border/50 rounded-xl pl-10 pr-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono cursor-pointer"
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="p-5 border-t border-border/40 bg-muted/10 flex justify-end gap-3">
              <Button 
                variant="ghost" 
                onClick={() => setIsAddOpen(false)} 
                className="text-muted-foreground hover:text-foreground cursor-pointer rounded-xl font-mono text-xs"
              >
                Cancel
              </Button>
              <Button 
                className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-xl px-4 font-mono text-xs shadow-md" 
                onClick={handleAddTransaction}
                disabled={isUpdating || !txSymbol || !txQty || !txPrice}
              >
                {isUpdating ? 'Saving...' : 'Save Transaction'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ─── CREATE ALERT MODAL ───────────────────────────────────────────────── */}
      {isAlertOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md animate-in fade-in duration-300">
          <div className="bg-card border border-border/80 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-5 border-b border-border/40 flex items-center justify-between bg-muted/10">
              <h2 className="text-md font-serif font-semibold text-foreground flex items-center gap-2.5">
                <AlertCircle className="w-5 h-5 text-primary" />
                Configure Price Target Alert
              </h2>
              <button 
                onClick={() => setIsAlertOpen(false)}
                className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-6 space-y-5">
              {/* Searchable Combobox for Alert Asset */}
              <div className="space-y-2 relative" ref={symbolDropdownRef}>
                <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Target Crypto Token</label>
                <div className="relative">
                  <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                    <Search className="h-4 w-4 text-muted-foreground/60" />
                  </span>
                  <input 
                    type="text" 
                    value={symbolSearchQuery}
                    onFocus={() => setShowSymbolDropdown(true)}
                    onChange={(e) => {
                      setSymbolSearchQuery(e.target.value);
                      setTxSymbol(e.target.value);
                      setShowSymbolDropdown(true);
                    }}
                    className="w-full bg-background border border-border/50 rounded-xl pl-10 pr-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary uppercase font-mono"
                    placeholder="Search e.g. BTC, ETH..."
                  />
                </div>
                
                {/* Suggestion Dropdown List */}
                {showSymbolDropdown && filteredSymbolOptions.length > 0 && (
                  <div className="absolute z-50 left-0 right-0 mt-1 max-h-56 overflow-y-auto bg-card border border-border/80 rounded-xl shadow-xl divide-y divide-border/20">
                    {filteredSymbolOptions.map((asset) => (
                      <div
                        key={asset.symbol}
                        onClick={() => {
                          setTxSymbol(asset.symbol);
                          setSymbolSearchQuery(asset.symbol);
                          if (asset.price) {
                            setAlertTarget(String(asset.price));
                          }
                          setShowSymbolDropdown(false);
                        }}
                        className="flex items-center justify-between px-4 py-2.5 hover:bg-muted/30 cursor-pointer transition-colors text-xs font-mono"
                      >
                        <div className="flex flex-col">
                          <span className="font-bold text-foreground">{asset.symbol}</span>
                          <span className="text-[10px] text-muted-foreground">{asset.name || 'Crypto Asset'}</span>
                        </div>
                        <span className="text-muted-foreground font-semibold">${asset.price?.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Alert Type Selector */}
              <div className="grid grid-cols-2 gap-4">
                <Button 
                  variant="outline" 
                  className={`border-border/40 font-mono transition-all rounded-xl ${alertType === 'PRICE_ABOVE' ? 'bg-primary/10 text-primary border-primary/50 font-bold' : 'bg-transparent text-muted-foreground'}`}
                  onClick={() => setAlertType('PRICE_ABOVE')}
                >
                  Crosses Above
                </Button>
                <Button 
                  variant="outline" 
                  className={`border-border/40 font-mono transition-all rounded-xl ${alertType === 'PRICE_BELOW' ? 'bg-rose-500/10 text-rose-400 border-rose-500/40 font-bold' : 'bg-transparent text-muted-foreground'}`}
                  onClick={() => setAlertType('PRICE_BELOW')}
                >
                  Falls Below
                </Button>
              </div>

              {/* Alert Target Price */}
              <div className="space-y-2">
                <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Target Trigger Price ($)</label>
                <input 
                  type="number" 
                  value={alertTarget}
                  onChange={(e) => setAlertTarget(e.target.value)}
                  className="w-full bg-background border border-border/50 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono"
                  placeholder="0.00"
                  step="any"
                />
              </div>
            </div>

            <div className="p-5 border-t border-border/40 bg-muted/10 flex justify-end gap-3">
              <Button 
                variant="ghost" 
                onClick={() => setIsAlertOpen(false)} 
                className="text-muted-foreground hover:text-foreground cursor-pointer rounded-xl font-mono text-xs"
              >
                Cancel
              </Button>
              <Button 
                className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-xl px-4 font-mono text-xs shadow-md" 
                onClick={handleAddAlert}
                disabled={isUpdating || !txSymbol || !alertTarget}
              >
                {isUpdating ? 'Saving...' : 'Set Alert'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ─── IN-DEPTH JDDS METRICS FLOATING MODAL ─────────────────────────────── */}
      {selectedAssetForDetails && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/85 backdrop-blur-md animate-in fade-in duration-300">
          <div className="bg-card border border-border/80 rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-5 border-b border-border/40 flex items-center justify-between bg-muted/10">
              <h2 className="text-md font-serif font-semibold text-foreground flex items-center gap-2.5">
                <Info className="w-5 h-5 text-primary" />
                JDDS Ingestion Metrics: {selectedAssetForDetails.symbol}
              </h2>
              <button 
                onClick={() => setSelectedAssetForDetails(null)}
                className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-6 space-y-6 font-mono text-xs text-foreground">
              <div className="grid grid-cols-2 gap-6 border-b border-border/20 pb-4">
                <div>
                  <span className="text-[10px] uppercase text-muted-foreground block mb-1">Asset Token</span>
                  <p className="text-sm font-bold">{selectedAssetForDetails.name || selectedAssetForDetails.symbol}</p>
                </div>
                <div>
                  <span className="text-[10px] uppercase text-muted-foreground block mb-1">Exchange Market</span>
                  <p className="text-sm font-bold text-primary">{selectedAssetForDetails.exchange || 'BINANCE SPOT'}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-[10px] uppercase text-muted-foreground block mb-1">Live Price (USD)</span>
                  <p className="text-md font-bold">${selectedAssetForDetails.price?.toLocaleString() || selectedAssetForDetails.currentPrice?.toLocaleString() || 'N/A'}</p>
                </div>
                <div>
                  <span className="text-[10px] uppercase text-muted-foreground block mb-1">Market Rank</span>
                  <p className="text-md font-bold">#{selectedAssetForDetails.rank || 'N/A'}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-[10px] uppercase text-muted-foreground block mb-1">Circulating Supply</span>
                  <p className="font-semibold">{selectedAssetForDetails.circulatingSupply || 'N/A'}</p>
                </div>
                <div>
                  <span className="text-[10px] uppercase text-muted-foreground block mb-1">Max Supply</span>
                  <p className="font-semibold">{selectedAssetForDetails.maxSupply || 'N/A'}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 border-t border-border/20 pt-4">
                <div>
                  <span className="text-[10px] uppercase text-rose-400 block mb-1">All-Time High (ATH)</span>
                  <p className="font-semibold text-rose-400">{selectedAssetForDetails.ath || 'N/A'}</p>
                  {selectedAssetForDetails.athChangePercent !== undefined && (
                    <span className="text-[9px] text-muted-foreground">Drawdown: {selectedAssetForDetails.athChangePercent.toFixed(1)}%</span>
                  )}
                </div>
                <div>
                  <span className="text-[10px] uppercase text-emerald-400 block mb-1">All-Time Low (ATL)</span>
                  <p className="font-semibold text-emerald-400">{selectedAssetForDetails.atl || 'N/A'}</p>
                  {selectedAssetForDetails.atlChangePercent !== undefined && (
                    <span className="text-[9px] text-muted-foreground">Grown: +{selectedAssetForDetails.atlChangePercent.toFixed(1)}%</span>
                  )}
                </div>
              </div>
            </div>

            <div className="p-5 border-t border-border/40 bg-muted/10 flex justify-end">
              <Button 
                className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-xl px-4 py-2 font-mono text-xs shadow-md"
                onClick={() => setSelectedAssetForDetails(null)}
              >
                Close Metrics
              </Button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
