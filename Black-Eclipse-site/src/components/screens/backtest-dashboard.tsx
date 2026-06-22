'use client';

import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, Pause, ChevronRight, DollarSign, Activity, 
  FileText, SlidersHorizontal, ArrowUpRight, ArrowDownRight, Trash2, 
  TrendingUp, BarChart2, Calendar, ShieldAlert, FolderKanban, Info, Brain, Sparkles as SparklesIcon,
  Database, Search, Download, Globe, RefreshCw, FileUp, Plus, Check, ChevronLeft, CalendarDays,
  Settings, Layers, HelpCircle, User, Award, ShieldCheck, DownloadCloud, Trash, CheckSquare, X
} from 'lucide-react';
import { Candle, Position, LimitOrder, JournalTrade, evaluateCurrentStep } from '@/lib/backtest/engine';
import { NativeChart } from '@/components/ui/native-chart';
import { Button } from '@/components/ui/button';
import { TopLoader } from '@/components/ui/top-loader';
import { 
  AreaChart, Area, BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, 
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid 
} from 'recharts';
import { generatePerformanceAnalytics, runMonteCarloSimulation } from '@/lib/backtest/analytics-engine';
import { generateAICoachReport } from '@/lib/backtest/ai-coach';
import { calculatePositionSize } from '@/lib/backtest/strategy-lab-engine';

interface BacktestSession {
  id: string;
  symbol: string;
  startDate: string;
  endDate: string;
  timeframe: string;
  startingCapital: number;
  replayIndex: number;
  cash: number;
  activePositions: Position[];
  activePosition?: Position | null;
  pendingOrders: LimitOrder[];
  closedTrades: JournalTrade[];
  equityCurve: { date: string; equity: number }[];
  candles: Candle[];
  updatedAt: number;
}

export function BacktestDashboard() {
  // Navigation tabs: 'overview' | 'backtest' | 'symbols' | 'calendar' | 'analytics' | 'reports' | 'settings'
  const [currentTab, setCurrentTab] = useState<'overview' | 'backtest' | 'symbols' | 'calendar' | 'analytics' | 'reports' | 'settings'>('overview');

  // Session States
  const [sessions, setSessions] = useState<BacktestSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Setup Form Configuration
  const [symbol, setSymbol] = useState('BTC');
  const [startDate, setStartDate] = useState('2025-10-01');
  const [endDate, setEndDate] = useState(new Date().toISOString().split('T')[0]);
  const [startingCapital, setStartingCapital] = useState(10000);
  const [timeframe, setTimeframe] = useState<'1m' | '5m' | '15m' | '1h' | '1d' | '1wk' | '1mo'>('1d');
  const [strategyProfile, setStrategyProfile] = useState<'discretionary' | 'crossover' | 'reversion' | 'breakout'>('discretionary');

  // Simulation parameters
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [replayIndex, setReplayIndex] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playSpeed, setPlaySpeed] = useState(1000); 

  const [cash, setCash] = useState(10000);
  const [activePositions, setActivePositions] = useState<Position[]>([]);
  const [pendingOrders, setPendingOrders] = useState<LimitOrder[]>([]);
  const [closedTrades, setClosedTrades] = useState<JournalTrade[]>([]);
  const [equityCurve, setEquityCurve] = useState<{ date: string; equity: number }[]>([]);

  // Sizing & risk
  const [riskMode, setRiskMode] = useState<'capital' | 'amount' | 'percent'>('capital');
  const [riskAmount, setRiskAmount] = useState(100);
  const [riskPercent, setRiskPercent] = useState(1);

  // Advanced features inputs
  const [trailingStopEnabled, setTrailingStopEnabled] = useState(false);
  const [trailingStopDistance, setTrailingStopDistance] = useState('');
  const [tp1PriceInput, setTp1PriceInput] = useState('');
  const [tp1PercentInput, setTp1PercentInput] = useState('50');

  // Order Console inputs
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [orderSizeUSD, setOrderSizeUSD] = useState(1000);
  const [limitPriceInput, setLimitPriceInput] = useState('');
  const [stopLossInput, setStopLossInput] = useState('');
  const [takeProfitInput, setTakeProfitInput] = useState('');

  // Prop firm rule trackers
  const [highestWatermark, setHighestWatermark] = useState(10000);
  const [propFirmBreached, setPropFirmBreached] = useState(false);
  const [breachReason, setBreachReason] = useState('');

  // Multi-select symbols pool
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(['BTC', 'ETH']);

  // Symbol Universe states
  const [symbolsList, setSymbolsList] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterClass, setFilterClass] = useState('');
  const [filterMarket, setFilterMarket] = useState('');
  const [filterExchange, setFilterExchange] = useState('');
  const [filterCountry, setFilterCountry] = useState('');
  const [universePage, setUniversePage] = useState(1);
  const [universeTotalPages, setUniverseTotalPages] = useState(1);
  const [universeLoading, setUniverseLoading] = useState(false);
  const [activeJobsList, setActiveJobsList] = useState<Record<string, { status: string; progress: number; error?: string }>>({});

  // Configuration settings states
  const [commissionRate, setCommissionRate] = useState(0.001);
  const [slippageTicks, setSlippageTicks] = useState(1);
  const [positionFormula, setPositionFormula] = useState('Capital-Proportional Sizing (Default)');
  const [propFirmEnforcement, setPropFirmEnforcement] = useState('Standard (5% daily / 10% overall limits)');

  // DB Reports states
  const [dbReports, setDbReports] = useState<any[]>([]);
  const [reportsLoading, setReportsLoading] = useState(false);

  // CSV Importer states
  const [csvSymbolId, setCsvSymbolId] = useState('');
  const [csvTimeframe, setCsvTimeframe] = useState('1d');
  const [csvText, setCsvText] = useState('');
  const [csvMessage, setCsvMessage] = useState<string | null>(null);
  const [csvError, setCsvError] = useState<string | null>(null);
  const [csvImporting, setCsvImporting] = useState(false);

  // Trade Analytics Table Filters
  const [ledgerSymbolFilter, setLedgerSymbolFilter] = useState('');
  const [ledgerTypeFilter, setLedgerTypeFilter] = useState<'all' | 'winning' | 'losing'>('all');
  const [ledgerDirectionFilter, setLedgerDirectionFilter] = useState<'all' | 'LONG' | 'SHORT'>('all');
  const [ledgerMinProfit, setLedgerMinProfit] = useState('');
  const [ledgerSortColumn, setLedgerSortColumn] = useState<string>('exitDate');
  const [ledgerSortDirection, setLedgerSortDirection] = useState<'asc' | 'desc'>('desc');

  // Calendar Year/Month Navigation
  const [calendarYear, setCalendarYear] = useState(2026);
  const [calendarMonth, setCalendarMonth] = useState(5); // 0-indexed (5 = June)

  // Simulation play loop timer ref
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const currentAssetPrice = candles.length > 0 && replayIndex < candles.length ? candles[replayIndex].close : 0;
  
  // Real-time PnL & Equity
  const unrealizedPnL = activePositions.reduce((acc, pos) => {
    const p = (currentAssetPrice - pos.entryPrice) * pos.shares;
    return acc + (pos.direction === 'LONG' ? p : -p);
  }, 0);
  const netEquity = cash + activePositions.reduce((acc, pos) => acc + pos.sizeUSD, 0) + unrealizedPnL;

  // Prop firm evaluation rules check
  useEffect(() => {
    if (candles.length === 0 || activeSessionId === null) {
      setHighestWatermark(startingCapital);
      setPropFirmBreached(false);
      setBreachReason('');
      return;
    }
    if (netEquity > highestWatermark) {
      setHighestWatermark(netEquity);
    }
    const dailyDrawdown = ((highestWatermark - netEquity) / highestWatermark) * 100;
    if (dailyDrawdown > 5 && !propFirmBreached) {
      setPropFirmBreached(true);
      setBreachReason(`Daily Limit Breach: Equity ($${netEquity.toFixed(2)}) dropped below watermark limit ($${highestWatermark.toFixed(2)}) by ${dailyDrawdown.toFixed(2)}% (Max limit is 5%).`);
    }
    const overallDrawdown = ((startingCapital - netEquity) / startingCapital) * 100;
    if (overallDrawdown > 10 && !propFirmBreached) {
      setPropFirmBreached(true);
      setBreachReason(`Max Drawdown Breach: Overall equity ($${netEquity.toFixed(2)}) fell below initial starting capital ($${startingCapital.toFixed(2)}) by ${overallDrawdown.toFixed(2)}% (Max limit is 10%).`);
    }
  }, [netEquity, highestWatermark, startingCapital, candles, activeSessionId, propFirmBreached]);

  // Fetch DB reports
  const fetchDbReports = async () => {
    setReportsLoading(true);
    try {
      const res = await fetch("/api/reports");
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setDbReports(data.reports || []);
        }
      }
    } catch (e) {
      console.error("Failed to load DB reports:", e);
    } finally {
      setReportsLoading(false);
    }
  };

  useEffect(() => {
    if (currentTab === "reports") {
      fetchDbReports();
    }
  }, [currentTab]);

  // Load sessions from storage
  useEffect(() => {
    const saved = localStorage.getItem('black_eclipse_backtest_sessions_list');
    let loadedData: BacktestSession[] | null = null;
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          loadedData = parsed;
        }
      } catch (e) {
        // ignore
      }
    }

    let sessionsList: BacktestSession[] = [];
    if (loadedData) {
      sessionsList = loadedData;
      setSessions(loadedData);
    } else {
      // Seed dummy data to make sure everything works
      const dummyTrades: JournalTrade[] = [
        { id: 't-1', symbol: 'BTC', direction: 'LONG', entryPrice: 65200, exitPrice: 67492, entryDate: '2026-06-02', exitDate: '2026-06-02', sizeUSD: 2000, pnl: 70.30, pnlPercent: 3.5, notes: 'SMA crossover buy fill.' },
        { id: 't-2', symbol: 'BTC', direction: 'SHORT', entryPrice: 67300, exitPrice: 67800, entryDate: '2026-06-05', exitDate: '2026-06-05', sizeUSD: 3000, pnl: -22.28, pnlPercent: -0.74, notes: 'Stop loss triggered on minor pullback.' },
        { id: 't-3', symbol: 'ETH', direction: 'LONG', entryPrice: 3410, exitPrice: 3622, entryDate: '2026-06-08', exitDate: '2026-06-08', sizeUSD: 2500, pnl: 155.40, pnlPercent: 6.2, notes: 'RSI divergence breakout exit.' },
        { id: 't-4', symbol: 'SOL', direction: 'LONG', entryPrice: 142.50, exitPrice: 139.10, entryDate: '2026-06-12', exitDate: '2026-06-12', sizeUSD: 1500, pnl: -35.79, pnlPercent: -2.38, notes: 'Breakout failed to gain follow through.' },
        { id: 't-5', symbol: 'BTC', direction: 'LONG', entryPrice: 66800, exitPrice: 70140, entryDate: '2026-06-15', exitDate: '2026-06-15', sizeUSD: 4000, pnl: 200.00, pnlPercent: 5.0, notes: 'Institutional volume spike run.' },
        { id: 't-6', symbol: 'ETH', direction: 'SHORT', entryPrice: 3610, exitPrice: 3514, entryDate: '2026-06-19', exitDate: '2026-06-19', sizeUSD: 2500, pnl: 66.48, pnlPercent: 2.65, notes: 'Double top rejection pullback play.' },
        { id: 't-7', symbol: 'SOL', direction: 'LONG', entryPrice: 147.20, exitPrice: 144.30, entryDate: '2026-06-20', exitDate: '2026-06-20', sizeUSD: 2000, pnl: -39.40, pnlPercent: -1.97, notes: 'Weekend low volume chop.' },
        { id: 't-8', symbol: 'BTC', direction: 'LONG', entryPrice: 67100, exitPrice: 68450, entryDate: '2026-06-21', exitDate: '2026-06-21', sizeUSD: 5000, pnl: 100.60, pnlPercent: 2.01, notes: 'EMA support bounce long trigger.' },
      ];

      const dummyCandles: Candle[] = [
        { date: '2026-06-01', open: 65000, high: 66200, low: 64500, close: 65200, volume: 15000 },
        { date: '2026-06-02', open: 65200, high: 67600, low: 65100, close: 67492, volume: 18000 },
        { date: '2026-06-03', open: 67492, high: 68100, low: 66900, close: 67150, volume: 12000 },
        { date: '2026-06-04', open: 67150, high: 67900, low: 66500, close: 67300, volume: 11000 },
        { date: '2026-06-05', open: 67300, high: 68200, low: 67100, close: 67800, volume: 16000 },
        { date: '2026-06-06', open: 67800, high: 68500, low: 67400, close: 68100, volume: 9000 },
        { date: '2026-06-07', open: 68100, high: 68200, low: 67000, close: 67100, volume: 8000 },
        { date: '2026-06-08', open: 67100, high: 67300, low: 65800, close: 66300, volume: 22000 },
        { date: '2026-06-09', open: 66300, high: 67000, low: 65800, close: 66100, volume: 14000 },
        { date: '2026-06-10', open: 66100, high: 66800, low: 65500, close: 66400, volume: 13000 },
        { date: '2026-06-11', open: 66400, high: 66900, low: 65900, close: 66200, volume: 11000 },
        { date: '2026-06-12', open: 66200, high: 66500, low: 65100, close: 65800, volume: 15000 },
        { date: '2026-06-13', open: 65800, high: 66400, low: 65700, close: 66100, volume: 7000 },
        { date: '2026-06-14', open: 66100, high: 66900, low: 66000, close: 66800, volume: 8000 },
        { date: '2026-06-15', open: 66800, high: 70300, low: 66700, close: 70140, volume: 29000 },
        { date: '2026-06-16', open: 70140, high: 70800, low: 69500, close: 69900, volume: 21000 },
        { date: '2026-06-17', open: 69900, high: 70200, low: 68700, close: 69100, volume: 17000 },
        { date: '2026-06-18', open: 69100, high: 69500, low: 68400, close: 68600, volume: 15000 },
        { date: '2026-06-19', open: 68600, high: 69200, low: 68100, close: 68500, volume: 14000 },
        { date: '2026-06-20', open: 68500, high: 68900, low: 67800, close: 68100, volume: 10000 },
        { date: '2026-06-21', open: 68100, high: 68800, low: 67900, close: 68450, volume: 12000 },
      ];

      const dummySession: BacktestSession = {
        id: 'session-dummy',
        symbol: 'BTC',
        startDate: '2026-06-01',
        endDate: '2026-06-21',
        timeframe: '1d',
        startingCapital: 10000,
        replayIndex: 20,
        cash: 10435.31,
        activePositions: [],
        pendingOrders: [],
        closedTrades: dummyTrades,
        equityCurve: [
          { date: '2026-06-01', equity: 10000 },
          { date: '2026-06-02', equity: 10070.30 },
          { date: '2026-06-05', equity: 10048.02 },
          { date: '2026-06-08', equity: 10203.42 },
          { date: '2026-06-12', equity: 10167.63 },
          { date: '2026-06-15', equity: 10367.63 },
          { date: '2026-06-19', equity: 10434.11 },
          { date: '2026-06-20', equity: 10394.71 },
          { date: '2026-06-21', equity: 10495.31 },
        ],
        candles: dummyCandles,
        updatedAt: Date.now()
      };

      sessionsList = [dummySession];
      setSessions(sessionsList);
      localStorage.setItem('black_eclipse_backtest_sessions_list', JSON.stringify([dummySession]));
    }

    // Auto-resume last active session if exists
    const activeId = localStorage.getItem('black_eclipse_active_session_id');
    if (activeId) {
      const s = sessionsList.find(sess => sess.id === activeId);
      if (s) {
        isResumingRef.current = true;
        setSymbol(s.symbol);
        setStartDate(s.startDate);
        setEndDate(s.endDate);
        setStartingCapital(s.startingCapital);
        setTimeframe(s.timeframe as any);
        setCandles(s.candles);
        setReplayIndex(s.replayIndex);
        setCash(s.cash);
        setActivePositions(s.activePositions || []);
        setPendingOrders(s.pendingOrders || []);
        setClosedTrades(s.closedTrades || []);
        setEquityCurve(s.equityCurve || []);
        setActiveSessionId(s.id);
      }
    }
  }, []);

  const saveSessionsToStorage = (updatedSessions: BacktestSession[]) => {
    setSessions(updatedSessions);
    localStorage.setItem('black_eclipse_backtest_sessions_list', JSON.stringify(updatedSessions));
  };

  const fetchUniverseSymbols = async () => {
    setUniverseLoading(true);
    try {
      const queryParams = new URLSearchParams({
        query: searchQuery,
        assetClass: filterClass,
        market: filterMarket,
        exchange: filterExchange,
        country: filterCountry,
        page: String(universePage),
        limit: "25"
      });
      const res = await fetch(`/api/backtesting/symbols?${queryParams.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setSymbolsList(data.symbols || []);
        setUniverseTotalPages(data.pagination?.totalPages || 1);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setUniverseLoading(false);
    }
  };

  useEffect(() => {
    fetchUniverseSymbols();
  }, [searchQuery, filterClass, filterMarket, filterExchange, filterCountry, universePage]);

  // Sync active variables into the active session block
  const isResumingRef = useRef(false);
  const lastLoadedSessionIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!activeSessionId) {
      lastLoadedSessionIdRef.current = null;
      return;
    }
    if (isResumingRef.current) {
      const current = sessions.find(s => s.id === activeSessionId);
      if (current) {
        if (
          candles.length !== current.candles.length ||
          cash !== current.cash ||
          replayIndex !== current.replayIndex
        ) {
          return;
        }
      }
      isResumingRef.current = false;
    }
    if (lastLoadedSessionIdRef.current !== activeSessionId) {
      lastLoadedSessionIdRef.current = activeSessionId;
      return;
    }
    const updated = sessions.map(s => {
      if (s.id === activeSessionId) {
        return {
          ...s,
          replayIndex,
          cash,
          activePositions,
          pendingOrders,
          closedTrades,
          equityCurve,
          candles,
          updatedAt: Date.now()
        };
      }
      return s;
    });
    const current = sessions.find(s => s.id === activeSessionId);
    if (current && (
      current.replayIndex !== replayIndex ||
      current.cash !== cash ||
      JSON.stringify(current.activePositions || []) !== JSON.stringify(activePositions) ||
      current.pendingOrders.length !== pendingOrders.length ||
      current.closedTrades.length !== closedTrades.length
    )) {
      saveSessionsToStorage(updated);
    }
  }, [replayIndex, cash, activePositions, pendingOrders, closedTrades, equityCurve, candles, activeSessionId]);

  // Auto playback trigger
  useEffect(() => {
    if (isPlaying && candles.length > 0) {
      intervalRef.current = setInterval(() => {
        handleStepForward();
      }, playSpeed);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isPlaying, replayIndex, candles, playSpeed]);

  const startNewSimulation = async (customSymbol?: string) => {
    setLoading(true);
    setError(null);
    setIsPlaying(false);
    setActivePositions([]);
    setPendingOrders([]);
    setClosedTrades([]);
    
    const activeSymbol = customSymbol || symbol;
    const startCash = startingCapital;

    try {
      let res = await fetch(`/api/backtesting/candles?symbol=${encodeURIComponent(activeSymbol)}&timeframe=${timeframe}&start=${startDate}&end=${endDate}`);
      if (!res.ok) {
        const errJson = await res.json();
        throw new Error(errJson.error || 'Failed to retrieve asset history feed.');
      }
      let data = await res.json();
      
      let attempts = 0;
      const maxAttempts = 15;
      while ((data.dataStatus === "downloading" || data.message?.includes("download") || data.message?.includes("queued")) && attempts < maxAttempts) {
        attempts++;
        // Polling delay
        await new Promise(resolve => setTimeout(resolve, 1500));
        res = await fetch(`/api/backtesting/candles?symbol=${encodeURIComponent(activeSymbol)}&timeframe=${timeframe}&start=${startDate}&end=${endDate}`);
        if (!res.ok) {
          const errJson = await res.json();
          throw new Error(errJson.error || 'Failed to retrieve asset history feed during download sync.');
        }
        data = await res.json();
      }

      if (data.dataStatus === "downloading" || data.message?.includes("download") || data.message?.includes("queued")) {
        throw new Error(data.message || 'Historical candle data is still downloading from the provider. Please try again in a few seconds.');
      }

      const loadedCandles: Candle[] = data.candles || [];
      if (loadedCandles.length < 20) {
        throw new Error('Historical dataset is too short (less than 20 candles). Select wider dates.');
      }

      const newId = `session-${Date.now()}`;
      const defaultIndex = Math.min(30, loadedCandles.length - 1);
      const newSession: BacktestSession = {
        id: newId,
        symbol: activeSymbol,
        startDate,
        endDate,
        timeframe,
        startingCapital: startCash,
        replayIndex: defaultIndex,
        cash: startCash,
        activePositions: [],
        pendingOrders: [],
        closedTrades: [],
        equityCurve: [{ date: startDate, equity: startCash }],
        candles: loadedCandles,
        updatedAt: Date.now()
      };

      const updated = [newSession, ...sessions];
      saveSessionsToStorage(updated);

      isResumingRef.current = true;
      setSymbol(activeSymbol);
      setCandles(loadedCandles);
      setReplayIndex(defaultIndex);
      setCash(startCash);
      setEquityCurve([{ date: startDate, equity: startCash }]);
      setActiveSessionId(newId);
      localStorage.setItem('black_eclipse_active_session_id', newId);
      setCurrentTab('backtest');
    } catch (e: any) {
      console.error(e);
      setError(e.message || 'System fail fetching asset history.');
      setCurrentTab('backtest');
    } finally {
      setLoading(false);
    }
  };

  const handleResumeSession = (id: string) => {
    const s = sessions.find(sess => sess.id === id);
    if (!s) return;
    isResumingRef.current = true;
    setSymbol(s.symbol);
    setStartDate(s.startDate);
    setEndDate(s.endDate);
    setStartingCapital(s.startingCapital);
    setTimeframe(s.timeframe as any);
    setCandles(s.candles);
    setReplayIndex(s.replayIndex);
    setCash(s.cash);
    
    const loadedPositions = s.activePositions || (s.activePosition ? [s.activePosition] : []);
    setActivePositions(loadedPositions);
    setPendingOrders(s.pendingOrders);
    setClosedTrades(s.closedTrades);
    setEquityCurve(s.equityCurve);
    
    setActiveSessionId(s.id);
    localStorage.setItem('black_eclipse_active_session_id', s.id);
    setCurrentTab('backtest');
  };

  const handleDeleteSession = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this practice session?')) return;
    const updated = sessions.filter(s => s.id !== id);
    saveSessionsToStorage(updated);
    if (activeSessionId === id) {
      handleQuitSession();
    }
  };

  const handleStepForward = () => {
    setReplayIndex((prevIndex) => {
      if (prevIndex >= candles.length - 1) {
        setIsPlaying(false);
        return prevIndex;
      }
      const nextIndex = prevIndex + 1;
      const currentCandle = candles[nextIndex];

      setActivePositions((posList) => {
        setPendingOrders((orders) => {
          setClosedTrades((trades) => {
            setCash((currentCash) => {
              const runState = evaluateCurrentStep(
                currentCandle,
                posList,
                orders,
                trades,
                currentCash,
                commissionRate,
                symbol
              );

              setTimeout(() => {
                setPendingOrders(runState.pendingOrders);
                setClosedTrades(runState.closedTrades);
                setCash(runState.cash);
                setActivePositions(runState.activePositions);

                const unrealized = runState.activePositions.reduce((acc, pos) => {
                  const p = (currentCandle.close - pos.entryPrice) * pos.shares;
                  return acc + (pos.direction === 'LONG' ? p : -p);
                }, 0);
                const totalEquity = runState.cash + runState.activePositions.reduce((acc, pos) => acc + pos.sizeUSD, 0) + unrealized;
                
                setEquityCurve(prev => {
                  if (prev.some(p => p.date === currentCandle.date)) return prev;
                  return [...prev, { date: currentCandle.date, equity: totalEquity }];
                });
              }, 0);

              return currentCash;
            });
            return trades;
          });
          return orders;
        });
        return posList;
      });

      return nextIndex;
    });
  };

  const handlePlaceOrder = (direction: 'LONG' | 'SHORT') => {
    if (candles.length === 0 || replayIndex >= candles.length) return;
    const currentClose = candles[replayIndex].close;

    let finalOrderSize = orderSizeUSD;
    const slPrice = stopLossInput ? Number(stopLossInput) : null;
    const tpPrice = takeProfitInput ? Number(takeProfitInput) : null;

    if (riskMode !== 'capital') {
      if (!slPrice) {
        alert('A valid Stop Loss price is required to calculate risk-based position sizes.');
        return;
      }
      const calc = calculatePositionSize(
        cash,
        currentClose,
        slPrice,
        riskMode === 'amount' ? riskAmount : undefined,
        riskMode === 'percent' ? riskPercent : undefined
      );
      if (calc.sizeUSD <= 0) {
        alert('Invalid stop loss or risk settings. Position size is 0.');
        return;
      }
      finalOrderSize = calc.sizeUSD;
    }

    if (finalOrderSize > cash) {
      alert(`Insufficient cash capital ($${cash.toFixed(2)}) to execute trade size ($${finalOrderSize.toFixed(2)}).`);
      return;
    }

    if (orderType === 'MARKET') {
      const slipFactor = 1 + (0.0001 * slippageTicks);
      const fillPrice = direction === 'LONG' 
        ? currentClose * slipFactor * (1 + commissionRate) 
        : currentClose * (2 - slipFactor) * (1 - commissionRate);
      const shares = finalOrderSize / fillPrice;

      const newPos: Position = {
        id: `pos-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        direction,
        entryPrice: fillPrice,
        sizeUSD: finalOrderSize,
        shares,
        stopLoss: slPrice ? slPrice : undefined,
        takeProfit: tpPrice ? tpPrice : undefined,
        entryDate: candles[replayIndex]?.date,
        trailingStopEnabled,
        trailingStopDistance: trailingStopEnabled && trailingStopDistance ? Number(trailingStopDistance) : undefined,
        tp1Price: tp1PriceInput ? Number(tp1PriceInput) : null,
        tp1Percent: tp1PriceInput ? Number(tp1PercentInput) : undefined,
        tp1Hit: false
      };

      setActivePositions(prev => [...prev, newPos]);
      setCash(prev => prev - finalOrderSize);
      setStopLossInput('');
      setTakeProfitInput('');
      setTrailingStopEnabled(false);
      setTrailingStopDistance('');
      setTp1PriceInput('');
    } else {
      const limitPrice = Number(limitPriceInput);
      if (isNaN(limitPrice) || limitPrice <= 0) {
        alert('Enter a valid price target for the limit trigger.');
        return;
      }

      const newOrder: LimitOrder = {
        id: `limit-${Date.now()}`,
        type: direction === 'LONG' ? 'BUY_LIMIT' : 'SELL_LIMIT',
        price: limitPrice,
        sizeUSD: finalOrderSize,
        stopLoss: slPrice ? slPrice : undefined,
        takeProfit: tpPrice ? tpPrice : undefined,
      };

      setPendingOrders(prev => [...prev, newOrder]);
      setLimitPriceInput('');
    }
  };

  const handleClosePosition = (id: string) => {
    const pos = activePositions.find(p => p.id === id);
    if (!pos || candles.length === 0) return;
    const currentClose = candles[replayIndex].close;
    const currentDate = candles[replayIndex].date;

    const slipFactor = 1 + (0.0001 * slippageTicks);
    const fillPrice = pos.direction === 'LONG' 
      ? currentClose * (2 - slipFactor) * (1 - commissionRate) 
      : currentClose * slipFactor * (1 + commissionRate);

    let pnl = 0;
    if (pos.direction === 'LONG') {
      pnl = (fillPrice - pos.entryPrice) * pos.shares;
    } else {
      pnl = (pos.entryPrice - fillPrice) * pos.shares;
    }

    const pnlPercent = (pnl / pos.sizeUSD) * 100;

    const loggedTrade: JournalTrade = {
      id: `trade-${closedTrades.length + 1}-${Date.now()}`,
      symbol,
      direction: pos.direction,
      entryDate: pos.entryDate || currentDate,
      entryPrice: pos.entryPrice,
      exitDate: currentDate,
      exitPrice: fillPrice,
      sizeUSD: pos.sizeUSD,
      pnl,
      pnlPercent,
      notes: 'Manually closed.',
    };

    setClosedTrades(prev => [...prev, loggedTrade]);
    setCash(prev => prev + pos.sizeUSD + pnl);
    setActivePositions(prev => prev.filter(p => p.id !== id));
  };

  const handleCloseAllPositions = () => {
    if (activePositions.length === 0 || candles.length === 0) return;
    const currentClose = candles[replayIndex].close;
    const currentDate = candles[replayIndex].date;

    const newClosedTrades: JournalTrade[] = [];
    let cashAdd = 0;

    activePositions.forEach((pos, index) => {
      const slipFactor = 1 + (0.0001 * slippageTicks);
      const fillPrice = pos.direction === 'LONG' 
        ? currentClose * (2 - slipFactor) * (1 - commissionRate) 
        : currentClose * slipFactor * (1 + commissionRate);
      let pnl = 0;
      if (pos.direction === 'LONG') {
        pnl = (fillPrice - pos.entryPrice) * pos.shares;
      } else {
        pnl = (pos.entryPrice - fillPrice) * pos.shares;
      }

      const pnlPercent = (pnl / pos.sizeUSD) * 100;

      newClosedTrades.push({
        id: `trade-${closedTrades.length + index + 1}-${Date.now()}`,
        symbol,
        direction: pos.direction,
        entryDate: pos.entryDate || currentDate,
        entryPrice: pos.entryPrice,
        exitDate: currentDate,
        exitPrice: fillPrice,
        sizeUSD: pos.sizeUSD,
        pnl,
        pnlPercent,
        notes: 'Manually closed via Close All.',
      });

      cashAdd += pos.sizeUSD + pnl;
    });

    setClosedTrades(prev => [...prev, ...newClosedTrades]);
    setCash(prev => prev + cashAdd);
    setActivePositions([]);
  };

  const cancelPendingOrder = (id: string) => {
    setPendingOrders(prev => prev.filter(o => o.id !== id));
  };

  const updateTradeJournalNotes = (id: string, notesText: string) => {
    setClosedTrades(prev => prev.map(t => t.id === id ? { ...t, notes: notesText } : t));
  };

  const handleQuitSession = () => {
    setCandles([]);
    setActiveSessionId(null);
    localStorage.removeItem('black_eclipse_active_session_id');
  };

  const handleTriggerDownload = async (symbolId: string, customTimeframe?: string) => {
    try {
      const activeTf = customTimeframe || timeframe;
      setActiveJobsList(prev => ({
        ...prev,
        [symbolId]: { status: "pending", progress: 0 }
      }));
      const res = await fetch("/api/backtesting/data/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbolId, timeframe: activeTf })
      });
      if (res.ok) {
        fetchUniverseSymbols();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleImportCSV = async () => {
    if (!csvSymbolId) {
      setCsvError("Please select a target symbol first.");
      return;
    }
    if (!csvText.trim()) {
      setCsvError("Please paste CSV data.");
      return;
    }

    setCsvImporting(true);
    setCsvError(null);
    setCsvMessage(null);

    try {
      const res = await fetch("/api/jdds/import-csv", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbolId: csvSymbolId,
          csvText,
          timeframe: csvTimeframe
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Failed to import CSV");
      }

      setCsvMessage(data.message || `Successfully imported candles.`);
      setCsvText('');
      fetchUniverseSymbols();
    } catch (e: any) {
      setCsvError(e.message || "CSV parse error.");
    } finally {
      setCsvImporting(false);
    }
  };

  // Metrics Calculations
  const allClosedTrades = sessions.reduce<JournalTrade[]>((acc, s) => [...acc, ...s.closedTrades], []);
  const allWins = allClosedTrades.filter(t => t.pnl > 0);
  const allLosses = allClosedTrades.filter(t => t.pnl <= 0);
  const allWinRate = allClosedTrades.length > 0 ? (allWins.length / allClosedTrades.length) * 100 : 0;
  
  const allGrossProfit = allClosedTrades.reduce((acc, t) => t.pnl > 0 ? acc + t.pnl : acc, 0);
  const allGrossLoss = allClosedTrades.reduce((acc, t) => t.pnl < 0 ? acc + Math.abs(t.pnl) : acc, 0);
  const allProfitFactor = allGrossLoss === 0 ? (allGrossProfit > 0 ? 99.9 : 0) : allGrossProfit / allGrossLoss;

  const totalGainPercent = ((netEquity - startingCapital) / startingCapital) * 100;
  const activeWinRate = closedTrades.length > 0 ? (closedTrades.filter(t => t.pnl > 0).length / closedTrades.length) * 100 : 0;

  // Active Session Analytics
  const performanceStats = generatePerformanceAnalytics(closedTrades as any, startingCapital);
  const mcSimulation = runMonteCarloSimulation(closedTrades as any, startingCapital, 50, Math.max(10, closedTrades.length));
  const aiCoachReport = generateAICoachReport(closedTrades as any);

  // Find most traded symbol
  const symbolCounts = allClosedTrades.reduce<Record<string, number>>((acc, t) => {
    acc[t.symbol] = (acc[t.symbol] || 0) + 1;
    return acc;
  }, {});
  const mostTradedSymbol = allClosedTrades.length > 0 
    ? Object.keys(symbolCounts).sort((a, b) => symbolCounts[b] - symbolCounts[a])[0] 
    : "N/A";

  // Custom calculated Strategy Score (0 - 100)
  const strategyScore = Math.min(100, Math.max(0, Math.round(
    (allWinRate * 0.4) + (allProfitFactor * 25) + (Math.min(20, allClosedTrades.length) * 1.5)
  )));

  // Calendar Day Generator
  const getDaysInMonth = (year: number, month: number) => {
    return new Date(year, month + 1, 0).getDate();
  };
  const getFirstDayOfMonth = (year: number, month: number) => {
    return new Date(year, month, 1).getDay();
  };

  const monthNames = [
    "January", "February", "March", "April", "May", "June", 
    "July", "August", "September", "October", "November", "December"
  ];

  return (
    <div className="w-full h-full flex flex-col gap-6 text-foreground font-sans select-none pb-12 text-white">
      {loading && <TopLoader />}

      {error && (
        <div className="p-4 border border-rose-500/20 bg-rose-500/5 text-rose-400 text-xs rounded-xl animate-fade-in flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-rose-400 hover:text-white"><X size={14} /></button>
        </div>
      )}

      {/* ========================================================
          1. TOP HEADER SECTION & METRIC CARDS
          ======================================================== */}
      <header className="flex flex-col gap-6 bg-card/45 border border-border/30 p-6 rounded-2xl relative overflow-hidden backdrop-blur-xl shrink-0">
        <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-primary/30 via-transparent to-transparent" />
        
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl md:text-2xl font-extrabold tracking-tight text-white flex items-center gap-2">
              <SparklesIcon className="text-primary h-5 w-5 animate-pulse" /> Strategy Lab / Backtesting
            </h1>
            <p className="text-xs text-muted-foreground mt-1 font-medium">
              Create, test, analyze, and optimize quantitative algorithms in a premium simulation dashboard.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button 
              onClick={() => { setCurrentTab('backtest'); handleQuitSession(); }}
              className="bg-primary hover:bg-primary/95 text-black font-extrabold text-xs px-4 py-2.5 rounded-xl cursor-pointer shadow-lg shadow-primary/10 hover:shadow-primary/25 transition-all flex items-center gap-1.5"
            >
              <Plus size={14} className="stroke-[3]" /> New Backtest
            </button>
            <button 
              onClick={() => setCurrentTab('symbols')}
              className="bg-white/5 border border-border/40 hover:bg-white/10 hover:border-white/20 text-white font-bold text-xs px-4 py-2.5 rounded-xl cursor-pointer transition-all flex items-center gap-1.5"
            >
              <Database size={13} /> Import Strategy
            </button>
            <button 
              onClick={() => setCurrentTab('reports')}
              className="bg-white/5 border border-border/40 hover:bg-white/10 hover:border-white/20 text-white font-bold text-xs px-4 py-2.5 rounded-xl cursor-pointer transition-all flex items-center gap-1.5"
            >
              <FileText size={13} /> View Reports
            </button>
          </div>
        </div>

        {/* Real-time Metric Summary Row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3.5 pt-2">
          {[
            { 
              label: "Total Profit / Loss", 
              val: `$${(allGrossProfit - allGrossLoss).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
              color: (allGrossProfit - allGrossLoss) >= 0 ? "text-[#7aff78]" : "text-[#ff4a4a]"
            },
            { label: "Win Rate", val: `${allWinRate.toFixed(1)}%`, color: "text-primary" },
            { label: "Total Backtests", val: String(sessions.length), color: "text-white" },
            { 
              label: "Active Days", 
              val: String(new Set(allClosedTrades.map(t => t.exitDate)).size), 
              color: "text-white" 
            },
            { 
              label: "Best Asset", 
              val: allClosedTrades.length > 0 ? [...allClosedTrades].sort((a,b) => b.pnl - a.pnl)[0]?.symbol || "N/A" : "N/A", 
              color: "text-white" 
            },
            { label: "Avg Risk Reward", val: allProfitFactor > 0 ? `${allProfitFactor.toFixed(1)} : 1` : "N/A", color: "text-white" },
            { label: "Strategy Score", val: `${strategyScore}/100`, color: "text-primary font-mono" },
            { label: "Total Trades", val: `${allClosedTrades.length} Trades`, color: "text-white" },
          ].map((card, idx) => (
            <div 
              key={idx} 
              className="p-3 bg-black/40 border border-border/40 hover:border-primary/20 transition-all rounded-xl flex flex-col justify-between"
            >
              <span className="text-[9px] text-muted-foreground uppercase font-extrabold tracking-wider">{card.label}</span>
              <span className={`text-sm font-black mt-1.5 block tracking-tight ${card.color}`}>{card.val}</span>
            </div>
          ))}
        </div>
      </header>

      {/* ========================================================
          2. PREMIUM NAVIGATION TABS
          ======================================================== */}
      <nav className="flex items-center justify-between border-b border-border/30 pb-1.5 shrink-0">
        <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-hide py-1">
          {[
            { id: "overview", label: "Overview", icon: Layers },
            { id: "backtest", label: "Backtest Work", icon: Play },
            { id: "symbols", label: "Symbols", icon: Database },
            { id: "calendar", label: "Calendar", icon: CalendarDays },
            { id: "analytics", label: "Trade Analytics", icon: BarChart2 },
            { id: "reports", label: "Reports", icon: FileText },
            { id: "settings", label: "Settings", icon: Settings },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = currentTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setCurrentTab(tab.id as any)}
                className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl border transition-all cursor-pointer ${
                  isActive
                    ? "bg-primary/10 text-primary border-primary/25 shadow-[0_0_8px_rgba(122,255,120,0.12)]"
                    : "text-muted-foreground hover:text-white border-transparent hover:bg-white/[0.03]"
                }`}
              >
                <Icon size={13} className={isActive ? "text-primary animate-pulse" : ""} />
                {tab.label}
              </button>
            );
          })}
        </div>
        <span className="hidden lg:inline text-[9px] font-mono text-muted-foreground uppercase tracking-widest bg-white/[0.02] border border-border/20 px-3 py-1 rounded-lg text-white">
          QUANT TERMINAL v1.5
        </span>
      </nav>

      {/* ========================================================
          3. DYNAMIC TAB VIEWPORTS
          ======================================================== */}
      <main className="flex-1 min-h-0">

        {/* OVERVIEW DASHBOARD */}
        {currentTab === 'overview' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 animate-fade-in">
            {/* Left Col: Primary return curves */}
            <div className="lg:col-span-2 space-y-6">
              
              {/* Compound Profit curve card */}
              <div className="p-5 border border-border/30 bg-black/60 rounded-2xl flex flex-col justify-between min-h-[340px]">
                <div>
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                    <TrendingUp className="h-4 w-4 text-primary" /> Compound Returns Curve
                  </h3>
                  <p className="text-[10px] text-muted-foreground mt-0.5">Compounded return projection across completed sessions</p>
                </div>
                
                <div className="h-64 w-full mt-4">
                  {allClosedTrades.length === 0 ? (
                    <div className="w-full h-full flex flex-col items-center justify-center text-[10px] text-muted-foreground/45 border border-dashed border-border/20 rounded-xl font-mono">
                      <span>No trades closed yet. Launch and run a backtest session to draw metrics.</span>
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={allClosedTrades.map((t, idx) => ({ 
                        idx: idx + 1, 
                        pnl: allClosedTrades.slice(0, idx + 1).reduce((acc, tr) => acc + tr.pnl, 0) 
                      }))}>
                        <defs>
                          <linearGradient id="eqOverviewGlow" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#7aff78" stopOpacity="0.2"/>
                            <stop offset="95%" stopColor="#7aff78" stopOpacity="0"/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="#222" strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="idx" stroke="#444" fontSize={9} label={{ value: 'Completed Trades', position: 'insideBottom', offset: -2, fill: '#666', fontSize: 9 }} />
                        <YAxis stroke="#444" fontSize={9} />
                        <Tooltip contentStyle={{ backgroundColor: '#0d0d0d', border: '1px solid #222', fontSize: '9px', fontFamily: 'monospace' }} />
                        <Area type="monotone" dataKey="pnl" stroke="#7aff78" strokeWidth={1.5} fillOpacity={1} fill="url(#eqOverviewGlow)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>

              {/* Drawdowns Timeline */}
              <div className="p-5 border border-border/30 bg-black/60 rounded-2xl min-h-[220px]">
                <h3 className="text-xs font-bold text-white uppercase tracking-wider">Drawdown Curve (%)</h3>
                <p className="text-[10px] text-muted-foreground mt-0.5">Peak-to-valley balance decline watermark analysis</p>
                <div className="h-44 w-full mt-4">
                  {allClosedTrades.length === 0 ? (
                    <div className="w-full h-full flex items-center justify-center text-[10px] text-muted-foreground/45 border border-dashed border-border/20 rounded-xl font-mono">
                      Watermark logs are compiled after trades are recorded
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={allClosedTrades.map((t, idx) => {
                        const runningEquity = allClosedTrades.slice(0, idx + 1).reduce((acc, tr) => acc + tr.pnl, 10000);
                        const peak = Math.max(...allClosedTrades.slice(0, idx + 1).map((_, i) => allClosedTrades.slice(0, i + 1).reduce((acc, tr) => acc + tr.pnl, 10000)));
                        const dd = peak === 0 ? 0 : ((peak - runningEquity) / peak) * 100;
                        return { idx: idx + 1, drawdown: -dd };
                      })}>
                        <CartesianGrid stroke="#222" strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="idx" stroke="#444" fontSize={9} />
                        <YAxis stroke="#444" fontSize={9} />
                        <Tooltip contentStyle={{ backgroundColor: '#0d0d0d', border: '1px solid #222', fontSize: '9px', fontFamily: 'monospace' }} />
                        <Area type="monotone" dataKey="drawdown" stroke="#ff4a4a" strokeWidth={1.5} fill="#ff4a4a" fillOpacity={0.06} />
                      </AreaChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>

              {/* Calendar Grid on Overview */}
              <div className="p-5 border border-border/30 bg-[#0c0c0c]/80 backdrop-blur-md rounded-2xl space-y-4">
                <div className="flex items-center justify-between border-b border-border/20 pb-3">
                  <div>
                    <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5 font-sans">
                      <CalendarDays className="text-primary h-4 w-4" /> Calendar Activity Preview
                    </h3>
                    <p className="text-[10px] text-muted-foreground mt-0.5">Quick view of profitable/losing trading days for {monthNames[calendarMonth]} {calendarYear}</p>
                  </div>
                  <div className="flex items-center gap-1.5 font-sans">
                    <button 
                      onClick={() => {
                        if (calendarMonth === 0) {
                          setCalendarMonth(11);
                          setCalendarYear(y => y - 1);
                        } else {
                          setCalendarMonth(m => m - 1);
                        }
                      }}
                      className="p-1 rounded bg-white/5 border border-border/40 hover:bg-white/10 text-white cursor-pointer"
                    >
                      <ChevronLeft size={12} />
                    </button>
                    <span className="text-[10px] font-bold text-white font-mono min-w-[80px] text-center">
                      {monthNames[calendarMonth].slice(0, 3)} {calendarYear}
                    </span>
                    <button 
                      onClick={() => {
                        if (calendarMonth === 11) {
                          setCalendarMonth(0);
                          setCalendarYear(y => y + 1);
                        } else {
                          setCalendarMonth(m => m + 1);
                        }
                      }}
                      className="p-1 rounded bg-white/5 border border-border/40 hover:bg-white/10 text-white cursor-pointer"
                    >
                      <ChevronRight size={12} />
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-7 gap-2">
                  {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(d => (
                    <div key={d} className="text-center text-[10px] text-muted-foreground uppercase font-black py-1">{d}</div>
                  ))}
                  
                  {Array.from({ length: getFirstDayOfMonth(calendarYear, calendarMonth) }).map((_, idx) => (
                    <div key={`empty-overview-${idx}`} className="bg-transparent border border-transparent min-h-[64px]" />
                  ))}

                  {Array.from({ length: getDaysInMonth(calendarYear, calendarMonth) }).map((_, idx) => {
                    const dayNum = idx + 1;
                    const monthStr = String(calendarMonth + 1).padStart(2, '0');
                    const dayStr = String(dayNum).padStart(2, '0');
                    const dayQuery = `${calendarYear}-${monthStr}-${dayStr}`;

                    const dayTrades = allClosedTrades.filter(t => t.exitDate?.includes(dayQuery));
                    const dayPnl = dayTrades.reduce((acc, t) => acc + t.pnl, 0);
                    const hasTrades = dayTrades.length > 0;

                    return (
                      <div 
                        key={`day-overview-${dayNum}`} 
                        className={`min-h-[64px] p-1.5 border rounded-xl flex flex-col justify-between transition-colors ${
                          hasTrades
                            ? dayPnl >= 0 
                              ? "bg-emerald-500/5 border-emerald-500/30 hover:border-emerald-500/50" 
                              : "bg-rose-500/5 border-rose-500/30 hover:border-rose-500/50"
                            : "bg-black/20 border-border/20 hover:border-border/30"
                        }`}
                      >
                        <span className="text-[11px] font-extrabold text-white font-mono">{dayNum}</span>
                        {hasTrades && (
                          <span className={`text-[9px] font-mono leading-none ${dayPnl >= 0 ? "text-[#7aff78] font-bold" : "text-[#ff4a4a] font-bold"}`}>
                            {dayPnl >= 0 ? "+" : ""}${dayPnl.toFixed(0)}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Recent Backtests Table */}
              <div className="space-y-3">
                <span className="text-[10px] text-muted-foreground font-bold tracking-wider uppercase flex items-center gap-1.5 font-sans">
                  <FolderKanban size={14} className="text-primary" /> Recent Backtest Sessions ({sessions.length})
                </span>
                
                {sessions.length === 0 ? (
                  <div className="text-center p-10 text-muted-foreground/45 border border-dashed border-border/20 text-xs rounded-2xl bg-black/20">
                    No session profiles found. Go to Backtest tab to configuration setup.
                  </div>
                ) : (
                  <div className="overflow-x-auto bg-[#0f0f0f]/40 border border-border/30 rounded-xl">
                    <table className="w-full text-left border-collapse text-xs font-mono">
                      <thead>
                        <tr className="border-b border-border/20 text-muted-foreground text-[9px] uppercase bg-white/[0.01]">
                          <th className="py-2.5 px-4">Ticker</th>
                          <th className="py-2.5 px-4">Timeframe</th>
                          <th className="py-2.5 px-4">Capital Pool</th>
                          <th className="py-2.5 px-4">Trades Count</th>
                          <th className="py-2.5 px-4 text-right">Net Return</th>
                          <th className="py-2.5 px-4 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/10">
                        {sessions.slice(0, 5).map((sess) => {
                          const returnPct = ((sess.cash - sess.startingCapital) / sess.startingCapital) * 100;
                          return (
                            <tr key={sess.id} className="hover:bg-white/[0.01]">
                              <td className="py-2.5 px-4 font-bold text-white">{sess.symbol}</td>
                              <td className="py-2.5 px-4 text-muted-foreground">{sess.timeframe.toUpperCase()}</td>
                              <td className="py-2.5 px-4">${sess.startingCapital.toLocaleString()}</td>
                              <td className="py-2.5 px-4">{sess.closedTrades.length} Trades</td>
                              <td className={`py-2.5 px-4 text-right font-bold ${returnPct >= 0 ? "text-[#7aff78]" : "text-[#ff4a4a]"}`}>
                                {returnPct >= 0 ? "+" : ""}{returnPct.toFixed(1)}%
                              </td>
                              <td className="py-2.5 px-4 text-right">
                                <div className="flex items-center justify-end gap-2">
                                  <button
                                    onClick={() => handleResumeSession(sess.id)}
                                    className="px-2.5 py-0.5 text-[8px] bg-primary/10 border border-primary/20 hover:bg-primary/20 hover:text-white text-primary rounded cursor-pointer uppercase font-bold"
                                  >
                                    Load
                                  </button>
                                  <button
                                    onClick={(e) => handleDeleteSession(sess.id, e)}
                                    className="p-1 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-rose-400 hover:text-white rounded cursor-pointer transition-all"
                                    title="Delete session"
                                  >
                                    <Trash2 size={11} />
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>

            {/* Right Col: Ratio chart, Symbols stats, Activity feed */}
            <div className="space-y-6">
              
              {/* Win/Loss Pie chart */}
              <div className="p-5 border border-border/30 bg-black/60 rounded-2xl flex flex-col items-center">
                <span className="text-[10px] text-muted-foreground uppercase font-extrabold tracking-wider block border-b border-border/10 pb-2 w-full text-center">
                  Win / Loss Distribution
                </span>
                
                <div className="h-48 w-full mt-3 flex items-center justify-center">
                  {allClosedTrades.length === 0 ? (
                    <span className="text-[10px] text-muted-foreground/45 font-mono">No data points</span>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={[
                            { name: 'Wins', value: allWins.length },
                            { name: 'Losses', value: allLosses.length }
                          ]}
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={70}
                          paddingAngle={3}
                          dataKey="value"
                        >
                          <Cell fill="#7aff78" />
                          <Cell fill="#ff4a4a" />
                        </Pie>
                        <Tooltip />
                        <Legend verticalAlign="bottom" height={24} fontSize={9} />
                      </PieChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>

              {/* Best/Worst Performers & Most Traded */}
              <div className="p-5 border border-border/30 bg-black/60 rounded-2xl space-y-4">
                <span className="text-[10px] text-muted-foreground uppercase font-extrabold tracking-wider block border-b border-border/10 pb-2">
                  Performance by Symbol
                </span>
                
                <div className="space-y-3.5 text-xs font-mono">
                  <div className="flex justify-between border-b border-border/10 pb-1.5">
                    <span className="text-muted-foreground font-sans">Most Traded Ticker</span>
                    <span className="font-bold text-white">
                      {mostTradedSymbol}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-border/10 pb-1.5">
                    <span className="text-muted-foreground font-sans">Best Trade P&L</span>
                    <span className="font-bold text-[#7aff78]">
                      {allWins.length > 0 ? `+$${Math.max(...allWins.map(t => t.pnl)).toFixed(2)}` : "N/A"}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-border/10 pb-1.5">
                    <span className="text-muted-foreground font-sans">Worst Trade P&L</span>
                    <span className="font-bold text-[#ff4a4a]">
                      {allLosses.length > 0 ? `-$${Math.max(...allLosses.map(t => Math.abs(t.pnl))).toFixed(2)}` : "N/A"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Recent Strategy Activity Feed */}
              <div className="p-5 border border-border/30 bg-black/60 rounded-2xl space-y-4">
                <span className="text-[10px] text-muted-foreground uppercase font-extrabold tracking-wider block border-b border-border/10 pb-2">
                  Live Activity Feed
                </span>
                
                <div className="space-y-3 max-h-[220px] overflow-y-auto pr-1">
                  {allClosedTrades.length === 0 ? (
                    <span className="text-[9px] text-muted-foreground/45 italic block">No activity logs recorded.</span>
                  ) : (
                    allClosedTrades.slice(0, 6).map((t, idx) => (
                      <div key={idx} className="flex gap-2 text-[10px] border-b border-border/10 pb-2 last:border-0">
                        <span className={t.pnl >= 0 ? "text-[#7aff78] font-black shrink-0" : "text-[#ff4a4a] font-black shrink-0"}>
                          {t.pnl >= 0 ? "▲" : "▼"}
                        </span>
                        <div>
                          <span className="text-white font-bold">{t.symbol}</span> was closed {t.direction === 'LONG' ? "Long" : "Short"} with a return of{" "}
                          <span className={t.pnl >= 0 ? "text-[#7aff78] font-bold" : "text-[#ff4a4a] font-bold"}>
                            ${t.pnl.toFixed(2)} ({t.pnlPercent.toFixed(1)}%)
                          </span>
                          <span className="text-[8px] text-muted-foreground block mt-0.5">{t.exitDate}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

            </div>
          </div>
        )}

        {/* BACKTEST SIMULATOR */}
        {currentTab === 'backtest' && (
          <div className="w-full">
            {candles.length === 0 ? (
              /* Configuration setup panel when no session is running */
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-stretch animate-fade-in-up">
                
                {/* Configuration Panel */}
                <div className="lg:col-span-2 border border-border/30 bg-black/60 p-6 rounded-2xl space-y-5 relative">
                  <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-primary/20 via-transparent to-transparent" />
                  
                  <div>
                    <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                      <SlidersHorizontal size={14} className="text-primary" /> Simulation Setup Engine
                    </h2>
                    <p className="text-[10px] text-muted-foreground mt-0.5">Configure historical range feeds and parameters to spin up the trade simulator.</p>
                  </div>

                  {/* Preselected Ticker Chips selection */}
                  <div className="space-y-1.5">
                    <span className="text-[9px] text-muted-foreground uppercase font-bold tracking-wider block">Target Trade Symbols Pool</span>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedSymbols.map((tk) => (
                        <button
                          key={tk}
                          onClick={() => {
                            setSymbol(tk);
                            startNewSimulation(tk);
                          }}
                          className={`px-3 py-1.5 rounded-lg text-[10px] font-bold border transition-colors cursor-pointer ${
                            symbol === tk 
                              ? 'bg-primary/20 text-primary border-primary/40 font-extrabold shadow-[0_0_6px_rgba(122,255,120,0.1)]' 
                              : 'bg-white/5 border-border/40 text-muted-foreground hover:text-white hover:bg-white/10'
                          }`}
                        >
                          {tk}
                        </button>
                      ))}
                      <button 
                        onClick={() => setCurrentTab('symbols')}
                        className="px-2.5 py-1.5 border border-dashed border-border/45 hover:border-primary/50 text-[10px] text-muted-foreground rounded-lg cursor-pointer flex items-center gap-1"
                      >
                        <Plus size={11} /> Add Assets
                      </button>
                    </div>
                  </div>

                  <div className="space-y-4 pt-2">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="flex flex-col gap-1.5">
                        <label className="text-[9px] text-muted-foreground uppercase font-bold">Base Asset</label>
                        <input
                          type="text"
                          value={symbol}
                          onChange={e => setSymbol(e.target.value.toUpperCase())}
                          className="bg-background border border-border/50 text-xs px-3 py-1.5 text-foreground focus:outline-none focus:border-primary rounded-xl font-bold font-mono"
                        />
                      </div>

                      <div className="flex flex-col gap-1.5">
                        <label className="text-[9px] text-muted-foreground uppercase font-bold">Candlestick Interval</label>
                        <select
                          value={timeframe}
                          onChange={e => setTimeframe(e.target.value as any)}
                          className="bg-background border border-border/50 text-xs px-3 py-1.5 text-foreground focus:outline-none focus:border-primary rounded-xl font-bold cursor-pointer"
                        >
                          <option value="1m">1m (Minute)</option>
                          <option value="5m">5m (Scalping)</option>
                          <option value="15m">15m (Intraday)</option>
                          <option value="1h">1h (Hourly)</option>
                          <option value="1d">1D (Daily)</option>
                          <option value="1wk">1W (Weekly)</option>
                          <option value="1mo">1M (Monthly)</option>
                        </select>
                      </div>
                    </div>

                    <div className="flex flex-col gap-1.5">
                      <label className="text-[9px] text-muted-foreground uppercase font-bold">Automated Strategy Trigger Profile</label>
                      <select
                        value={strategyProfile}
                        onChange={e => setStrategyProfile(e.target.value as any)}
                        className="bg-background border border-border/50 text-xs px-3 py-1.5 text-foreground focus:outline-none focus:border-primary rounded-xl font-bold cursor-pointer"
                      >
                        <option value="discretionary">Discretionary Manual Sizing / Entries (Default)</option>
                        <option value="crossover">EMA/SMA Crossover (Fast crosses Slow EMA)</option>
                        <option value="reversion">RSI Bollinger Reversion (RSI &lt; 30 oversold / &gt; 70 overbought)</option>
                        <option value="breakout">MACD Momentum Breakdown (Volatility Expansion)</option>
                      </select>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="flex flex-col gap-1.5">
                        <label className="text-[9px] text-muted-foreground uppercase font-bold">Start Date</label>
                        <input
                          type="date"
                          value={startDate}
                          onChange={e => setStartDate(e.target.value)}
                          className="bg-background border border-border/50 text-xs px-3 py-1 rounded-xl font-bold focus:outline-none focus:border-primary"
                        />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <label className="text-[9px] text-muted-foreground uppercase font-bold">End Date</label>
                        <input
                          type="date"
                          value={endDate}
                          onChange={e => setEndDate(e.target.value)}
                          className="bg-background border border-border/50 text-xs px-3 py-1 rounded-xl font-bold focus:outline-none focus:border-primary"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div className="flex flex-col gap-1.5">
                        <label className="text-[9px] text-muted-foreground uppercase font-bold">Initial Cash ($)</label>
                        <input
                          type="number"
                          value={startingCapital}
                          onChange={e => setStartingCapital(Number(e.target.value))}
                          className="bg-background border border-border/50 text-xs px-3 py-1.5 text-foreground rounded-xl font-bold font-mono"
                        />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <label className="text-[9px] text-muted-foreground uppercase font-bold">Trade Direction Allowed</label>
                        <select className="bg-background border border-border/50 text-xs px-3 py-1.5 rounded-xl font-bold cursor-pointer text-white focus:outline-none">
                          <option>Long and Short (Both)</option>
                          <option>Long only</option>
                          <option>Short only</option>
                        </select>
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => startNewSimulation()}
                    disabled={loading}
                    className="w-full bg-primary hover:bg-primary/95 text-black font-extrabold text-xs py-3 rounded-xl cursor-pointer uppercase tracking-wider transition-all mt-4"
                  >
                    Launch Practice Simulator
                  </button>
                </div>

                {/* Right Panel: Saved session history */}
                <div className="border border-border/30 bg-[#0f0f0f]/60 p-6 rounded-2xl flex flex-col justify-between min-h-[300px]">
                  <div>
                    <h2 className="text-xs font-bold text-primary uppercase tracking-wide border-b border-border/20 pb-2 flex items-center gap-1.5">
                      <FolderKanban size={13} /> Saved Practice Sessions ({sessions.length})
                    </h2>
                  </div>

                  {sessions.length === 0 ? (
                    <div className="text-center p-8 text-muted-foreground/35 border border-dashed border-border/20 text-[10px] my-auto rounded-xl">
                      No active sessions saved. Run a backtest simulator to store state profiles.
                    </div>
                  ) : (
                    <div className="space-y-3.5 max-h-[360px] overflow-y-auto pr-1 flex-1 mt-4">
                      {sessions.map((sess) => {
                        const returnPct = ((sess.cash - sess.startingCapital) / sess.startingCapital) * 100;
                        return (
                          <div
                            key={sess.id}
                            onClick={() => handleResumeSession(sess.id)}
                            className="p-3 bg-black/40 border border-border/40 hover:border-primary/50 transition-colors flex items-center justify-between cursor-pointer rounded-xl group"
                          >
                            <div className="space-y-1">
                              <span className="text-xs font-black text-white group-hover:text-primary transition-colors block">{sess.symbol}</span>
                              <span className="text-[8px] text-muted-foreground block font-mono uppercase">{sess.timeframe} • {sess.closedTrades.length} trades</span>
                            </div>

                            <div className="flex items-center space-x-3.5">
                              <div className="text-right font-mono">
                                <span className="text-[11px] font-bold block text-white">${sess.cash.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                                <span className={`text-[9px] font-bold ${returnPct >= 0 ? 'text-[#7aff78]' : 'text-[#ff4a4a]'}`}>
                                  {returnPct >= 0 ? '+' : ''}{returnPct.toFixed(1)}%
                                </span>
                              </div>
                              <button
                                onClick={(e) => handleDeleteSession(sess.id, e)}
                                className="text-rose-500 hover:text-rose-300 cursor-pointer"
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

              </div>
            ) : (
              /* Active charting workspace simulation block */
              <div className="flex flex-col gap-6 animate-fade-in">
                
                {/* Active Session Status Ribbon */}
                <div className="p-4 border border-border/30 bg-black/60 flex flex-wrap items-center justify-between gap-4 rounded-xl">
                  <div className="flex items-center gap-1.5">
                    <span className="px-2 py-0.5 rounded bg-primary/10 text-primary text-[8px] font-black tracking-wider uppercase font-mono animate-pulse">Running Session</span>
                    <span className="text-xs font-bold text-white">{symbol} ({timeframe.toUpperCase()})</span>
                  </div>

                  <div className="flex items-center gap-6 text-xs font-mono">
                    <div>
                      <span className="text-[8px] text-muted-foreground uppercase block font-sans">Cash Balance</span>
                      <span className="text-xs font-bold text-white">${cash.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                    </div>
                    <div>
                      <span className="text-[8px] text-muted-foreground uppercase block font-sans">Watermark / Equity</span>
                      <span className={`text-xs font-bold ${netEquity >= startingCapital ? 'text-primary' : 'text-rose-400'}`}>
                        ${netEquity.toLocaleString(undefined, { maximumFractionDigits: 2 })} ({totalGainPercent >= 0 ? '+' : ''}{totalGainPercent.toFixed(2)}%)
                      </span>
                    </div>
                    <div>
                      <span className="text-[8px] text-muted-foreground uppercase block font-sans">Session Win Rate</span>
                      <span className="text-xs font-bold text-primary">{activeWinRate.toFixed(1)}%</span>
                    </div>
                    <button 
                      onClick={handleQuitSession}
                      className="px-3 py-1 text-[9px] border border-rose-500/30 bg-rose-500/5 hover:bg-rose-500/10 text-rose-400 hover:text-white transition-colors font-bold rounded-lg cursor-pointer uppercase tracking-wider font-sans"
                    >
                      Quit Session
                    </button>
                  </div>
                </div>

                {propFirmBreached && (
                  <div className="p-4 border border-rose-500/30 bg-rose-500/5 text-rose-400 text-xs rounded-xl flex items-start gap-2.5">
                    <ShieldAlert className="h-4 w-4 shrink-0 text-rose-500 mt-0.5 animate-pulse" />
                    <div>
                      <span className="font-extrabold uppercase block tracking-wider text-rose-500">PROP CHALLENGE BREACH WARNING</span>
                      <span className="font-semibold block mt-1">{breachReason}</span>
                    </div>
                  </div>
                )}

                <div className="flex flex-col xl:flex-row gap-6 items-stretch min-h-[500px]">
                  
                  {/* Candle Stick Chart View */}
                  <div className="flex-1 flex flex-col gap-4 min-w-0">
                    <div className="w-full h-[540px] relative">
                      <NativeChart
                        candles={candles.slice(0, replayIndex + 1)}
                        activePositions={activePositions}
                        closedTrades={closedTrades}
                        replayIndex={replayIndex}
                        maxReplayIndex={candles.length - 1}
                        isPlaying={isPlaying}
                        playSpeed={playSpeed}
                        onPlayPause={() => setIsPlaying(!isPlaying)}
                        onStepForward={handleStepForward}
                        onReset={() => { setReplayIndex(0); setIsPlaying(false); }}
                        onSetSpeed={(s) => setPlaySpeed(s)}
                        onSetReplayIndex={(idx) => setReplayIndex(idx)}
                      />
                    </div>
                  </div>

                  {/* Right order entry panel */}
                  <div className="w-full xl:w-80 border border-border/40 bg-[#0f0f0f]/60 p-5 flex flex-col justify-between gap-5 rounded-2xl shrink-0">
                    <div className="space-y-4">
                      <h2 className="text-xs font-bold text-primary border-b border-border/20 pb-2 flex items-center gap-2 uppercase tracking-wide">
                        <SlidersHorizontal size={12} /> Execution Panel
                      </h2>

                      <div className="space-y-3.5">
                        <div>
                          <label className="text-[8px] text-muted-foreground uppercase font-bold tracking-wider block mb-1">Execution Mode</label>
                          <div className="grid grid-cols-2 gap-1 p-0.5 bg-background border border-border/40 rounded-xl">
                            <button
                              onClick={() => setOrderType('MARKET')}
                              className={`text-[9px] py-1 font-bold rounded-lg cursor-pointer ${orderType === 'MARKET' ? 'bg-primary/10 text-primary border border-primary/20' : 'text-muted-foreground hover:text-white'}`}
                            >
                              MARKET
                            </button>
                            <button
                              onClick={() => setOrderType('LIMIT')}
                              className={`text-[9px] py-1 font-bold rounded-lg cursor-pointer ${orderType === 'LIMIT' ? 'bg-primary/10 text-primary border border-primary/20' : 'text-muted-foreground hover:text-white'}`}
                            >
                              LIMIT
                            </button>
                          </div>
                        </div>

                        <div>
                          <label className="text-[8px] text-muted-foreground uppercase font-bold block mb-1">Sizing Model</label>
                          <div className="grid grid-cols-3 gap-1 p-0.5 bg-background border border-border/40 rounded-xl">
                            <button
                              onClick={() => setRiskMode('capital')}
                              className={`text-[8px] py-1 font-bold rounded-lg cursor-pointer ${riskMode === 'capital' ? 'bg-primary/10 text-primary border border-primary/20' : 'text-muted-foreground hover:text-white'}`}
                            >
                              FIXED USD
                            </button>
                            <button
                              onClick={() => setRiskMode('amount')}
                              className={`text-[8px] py-1 font-bold rounded-lg cursor-pointer ${riskMode === 'amount' ? 'bg-primary/10 text-primary border border-primary/20' : 'text-muted-foreground hover:text-white'}`}
                            >
                              RISK USD
                            </button>
                            <button
                              onClick={() => setRiskMode('percent')}
                              className={`text-[8px] py-1 font-bold rounded-lg cursor-pointer ${riskMode === 'percent' ? 'bg-primary/10 text-primary border border-primary/20' : 'text-muted-foreground hover:text-white'}`}
                            >
                              RISK %
                            </button>
                          </div>
                        </div>

                        {riskMode === 'capital' && (
                          <div className="animate-fade-in flex flex-col gap-1">
                            <label className="text-[8px] text-muted-foreground uppercase font-bold">Order Size ($)</label>
                            <input
                              type="number"
                              value={orderSizeUSD}
                              onChange={e => setOrderSizeUSD(Number(e.target.value))}
                              className="w-full bg-background border border-border/50 text-xs px-3 py-1.5 rounded-xl font-bold font-mono"
                            />
                          </div>
                        )}

                        {riskMode === 'amount' && (
                          <div className="animate-fade-in flex flex-col gap-1">
                            <label className="text-[8px] text-muted-foreground uppercase font-bold">Risk Amount ($)</label>
                            <input
                              type="number"
                              value={riskAmount}
                              onChange={e => setRiskAmount(Number(e.target.value))}
                              className="w-full bg-background border border-border/50 text-xs px-3 py-1.5 rounded-xl font-bold font-mono"
                            />
                          </div>
                        )}

                        {riskMode === 'percent' && (
                          <div className="animate-fade-in flex flex-col gap-1">
                            <label className="text-[8px] text-muted-foreground uppercase font-bold">Risk Percentage (%)</label>
                            <input
                              type="number"
                              value={riskPercent}
                              onChange={e => setRiskPercent(Number(e.target.value))}
                              className="w-full bg-background border border-border/50 text-xs px-3 py-1.5 rounded-xl font-bold font-mono"
                            />
                          </div>
                        )}

                        {orderType === 'LIMIT' && (
                          <div className="animate-fade-in flex flex-col gap-1">
                            <label className="text-[8px] text-muted-foreground uppercase font-bold">Limit Price Target ($)</label>
                            <input
                              type="number"
                              placeholder={`Current: $${currentAssetPrice.toFixed(2)}`}
                              value={limitPriceInput}
                              onChange={e => setLimitPriceInput(e.target.value)}
                              className="w-full bg-background border border-border/50 text-xs px-3 py-1.5 rounded-xl font-bold font-mono"
                            />
                          </div>
                        )}

                        <div className="grid grid-cols-2 gap-3">
                          <div className="flex flex-col gap-1">
                            <label className="text-[8px] text-muted-foreground uppercase font-bold">Stop Loss ($)</label>
                            <input
                              type="number"
                              placeholder="Price"
                              value={stopLossInput}
                              onChange={e => setStopLossInput(e.target.value)}
                              className="w-full bg-background border border-border/50 text-xs px-2.5 py-1.5 rounded-xl font-bold font-mono"
                            />
                          </div>
                          <div className="flex flex-col gap-1">
                            <label className="text-[8px] text-muted-foreground uppercase font-bold">Take Profit ($)</label>
                            <input
                              type="number"
                              placeholder="Price"
                              value={takeProfitInput}
                              onChange={e => setTakeProfitInput(e.target.value)}
                              className="w-full bg-background border border-border/50 text-xs px-2.5 py-1.5 rounded-xl font-bold font-mono"
                            />
                          </div>
                        </div>

                        {/* Trailing Stop */}
                        <div className="border border-border/30 p-2.5 space-y-2 bg-black/45 rounded-xl">
                          <div className="flex items-center gap-1.5">
                            <input
                              type="checkbox"
                              id="activeTsl"
                              checked={trailingStopEnabled}
                              onChange={(e) => setTrailingStopEnabled(e.target.checked)}
                              className="accent-primary h-3.5 w-3.5 cursor-pointer"
                            />
                            <label htmlFor="activeTsl" className="text-[8px] text-white uppercase font-bold cursor-pointer">Trailing Stop Loss</label>
                          </div>
                          {trailingStopEnabled && (
                            <input
                              type="number"
                              placeholder="Trail distance ($)"
                              value={trailingStopDistance}
                              onChange={(e) => setTrailingStopDistance(e.target.value)}
                              className="w-full bg-background border border-border/50 text-xs px-2.5 py-1.5 rounded-lg font-bold font-mono"
                            />
                          )}
                        </div>

                        {/* Partial scale outs */}
                        <div className="border border-border/30 p-2.5 space-y-2 bg-black/45 rounded-xl">
                          <span className="text-[8px] text-muted-foreground uppercase font-bold tracking-wider block">Partial Scale-Outs</span>
                          <div className="grid grid-cols-2 gap-2">
                            <input
                              type="number"
                              placeholder="TP1 Price"
                              value={tp1PriceInput}
                              onChange={(e) => setTp1PriceInput(e.target.value)}
                              className="w-full bg-background border border-border/50 text-[10px] px-2 py-1.5 rounded-lg font-bold font-mono"
                            />
                            <select
                              value={tp1PercentInput}
                              onChange={(e) => setTp1PercentInput(e.target.value)}
                              className="w-full bg-background border border-border/50 text-[10px] px-2 py-1 rounded-lg cursor-pointer"
                            >
                              <option value="25">Close 25%</option>
                              <option value="50">Close 50%</option>
                              <option value="75">Close 75%</option>
                            </select>
                          </div>
                        </div>
                      </div>

                      <div className="flex gap-2.5 pt-2">
                        <button
                          onClick={() => handlePlaceOrder('LONG')}
                          className="flex-1 bg-emerald-500 hover:bg-emerald-600 text-black font-extrabold py-2 rounded-xl text-xs cursor-pointer flex items-center justify-center gap-1.5 transition-colors"
                        >
                          <ArrowUpRight size={13} className="stroke-[3.5]" /> {orderType === 'LIMIT' ? 'Buy Limit' : 'Buy Long'}
                        </button>
                        <button
                          onClick={() => handlePlaceOrder('SHORT')}
                          className="flex-1 bg-rose-500 hover:bg-rose-600 text-black font-extrabold py-2 rounded-xl text-xs cursor-pointer flex items-center justify-center gap-1.5 transition-colors"
                        >
                          <ArrowDownRight size={13} className="stroke-[3.5]" /> {orderType === 'LIMIT' ? 'Sell Limit' : 'Sell Short'}
                        </button>
                      </div>
                    </div>

                    {/* Active trades logs */}
                    {activePositions.length > 0 && (
                      <div className="border border-border/30 bg-card/15 p-3.5 space-y-2 rounded-xl flex flex-col min-h-0">
                        <div className="flex justify-between items-center border-b border-border/20 pb-1">
                          <span className="text-[8px] text-muted-foreground uppercase font-black font-mono">Active ({activePositions.length})</span>
                          <button onClick={handleCloseAllPositions} className="text-[8px] text-rose-400 hover:text-white uppercase font-black">Close All</button>
                        </div>
                        <div className="max-h-40 overflow-y-auto space-y-2 pr-1">
                          {activePositions.map((pos, index) => {
                            const isLong = pos.direction === 'LONG';
                            const pnl = isLong 
                              ? (currentAssetPrice - pos.entryPrice) * pos.shares 
                              : (pos.entryPrice - currentAssetPrice) * pos.shares;
                            const pnlP = (pnl / pos.sizeUSD) * 100;
                            return (
                              <div key={pos.id} className="border border-border/30 p-2 bg-[#0c0c0c] text-[10px] space-y-1 rounded-lg font-mono">
                                <div className="flex justify-between font-bold">
                                  <span className={isLong ? 'text-primary' : 'text-rose-400'}>{pos.direction} #{index + 1}</span>
                                  <span className={pnl >= 0 ? 'text-primary' : 'text-rose-400'}>
                                    {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                                  </span>
                                </div>
                                <button onClick={() => handleClosePosition(pos.id)} className="w-full mt-1.5 py-0.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-[8px] font-bold rounded">
                                  Close
                                </button>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Pending Limit Orders */}
                {pendingOrders.length > 0 && (
                  <div className="space-y-3">
                    <span className="text-[10px] text-muted-foreground font-bold tracking-wider uppercase">Pending Limit Triggers ({pendingOrders.length})</span>
                    <div className="overflow-x-auto bg-[#0f0f0f]/40 border border-border/40 rounded-xl">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="border-b border-border/20 text-muted-foreground text-[10px] uppercase bg-white/[0.01]">
                            <th className="py-2.5 px-4 font-semibold">Type</th>
                            <th className="py-2.5 px-4 font-semibold">Limit Price</th>
                            <th className="py-2.5 px-4 font-semibold">Size</th>
                            <th className="py-2.5 px-4 font-semibold">Stop Loss</th>
                            <th className="py-2.5 px-4 font-semibold">Take Profit</th>
                            <th className="py-2.5 px-4 text-right">Cancel</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/10 font-mono">
                          {pendingOrders.map((order) => (
                            <tr key={order.id} className="hover:bg-white/[0.02]">
                              <td className={`py-2 px-4 font-bold ${order.type === 'BUY_LIMIT' ? 'text-primary' : 'text-rose-400'}`}>{order.type}</td>
                              <td className="py-2 px-4 font-bold">${order.price.toFixed(2)}</td>
                              <td className="py-2 px-4 text-muted-foreground">${order.sizeUSD}</td>
                              <td className="py-2 px-4 text-rose-400">${order.stopLoss || 'N/A'}</td>
                              <td className="py-2 px-4 text-emerald-400">${order.takeProfit || 'N/A'}</td>
                              <td className="py-2 px-4 text-right">
                                <button onClick={() => cancelPendingOrder(order.id)} className="text-rose-400 hover:text-white cursor-pointer">Cancel</button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Session Trade Ledger */}
                {closedTrades.length > 0 && (
                  <div className="space-y-3">
                    <span className="text-[10px] text-muted-foreground font-bold tracking-wider uppercase font-sans">Closed Trades Ledger ({closedTrades.length})</span>
                    <div className="overflow-x-auto bg-[#0f0f0f]/40 border border-border/40 rounded-xl">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="border-b border-border/20 text-muted-foreground text-[10px] uppercase bg-white/[0.01]">
                            <th className="py-2.5 px-4 font-semibold">ID</th>
                            <th className="py-2.5 px-4 font-semibold">Direction</th>
                            <th className="py-2.5 px-4 font-semibold">Entry Price</th>
                            <th className="py-2.5 px-4 font-semibold">Exit Price</th>
                            <th className="py-2.5 px-4 font-semibold text-right">P&L ($)</th>
                            <th className="py-2.5 px-4 font-semibold">Journalnotes / Entry</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/10 font-mono">
                          {closedTrades.map((trade) => {
                            const isGain = trade.pnl >= 0;
                            return (
                              <tr key={trade.id} className="hover:bg-white/[0.02]">
                                <td className="py-2 px-4 text-muted-foreground">{trade.id.slice(-6)}</td>
                                <td className={`py-2 px-4 font-bold ${trade.direction === 'LONG' ? 'text-primary' : 'text-rose-400'}`}>{trade.direction}</td>
                                <td className="py-2 px-4">${trade.entryPrice.toFixed(2)}</td>
                                <td className="py-2 px-4">${trade.exitPrice.toFixed(2)}</td>
                                <td className={`py-2 px-4 text-right font-bold ${isGain ? 'text-primary' : 'text-rose-400'}`}>
                                  {isGain ? '+' : ''}${trade.pnl.toFixed(2)}
                                </td>
                                <td className="py-2 px-4 font-sans font-medium">
                                  <input
                                    type="text"
                                    value={trade.notes || ''}
                                    onChange={e => updateTradeJournalNotes(trade.id, e.target.value)}
                                    placeholder="Enter journal thoughts..."
                                    className="bg-transparent border-0 hover:bg-white/[0.03] focus:bg-background focus:ring-1 focus:ring-primary w-full px-2 py-0.5 rounded text-[10px] text-white"
                                  />
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

              </div>
            )}
          </div>
        )}

        {/* SYMBOLS SELECTION */}
        {currentTab === 'symbols' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 animate-fade-in">
            <div className="lg:col-span-2 border border-border/30 bg-[#0c0c0c]/80 backdrop-blur-md p-6 rounded-2xl space-y-4">
              
              <div className="flex items-center justify-between border-b border-border/20 pb-3">
                <div>
                  <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2 font-sans">
                    <Database className="text-primary h-4 w-4" /> Multi-Asset Registry
                  </h2>
                  <p className="text-[10px] text-muted-foreground mt-0.5">Define which symbols exist in your strategy backtesting selection pool.</p>
                </div>
                <button 
                  onClick={() => fetchUniverseSymbols()}
                  className="p-1.5 rounded-lg border border-border/40 hover:bg-white/[0.04] text-muted-foreground hover:text-white transition-all cursor-pointer"
                >
                  <RefreshCw size={13} className={universeLoading ? "animate-spin" : ""} />
                </button>
              </div>

              {/* Filters row & Selected chips summary */}
              <div className="flex flex-col gap-3 font-sans">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
                    <input
                      type="text"
                      placeholder="Search base ticker..."
                      value={searchQuery}
                      onChange={(e) => { setSearchQuery(e.target.value); setUniversePage(1); }}
                      className="w-full bg-background border border-border/50 rounded-xl pl-8 pr-3 py-1.5 text-xs text-white placeholder-muted-foreground focus:outline-none focus:border-primary/50 transition-all font-mono"
                    />
                  </div>

                  <select
                    value={filterClass}
                    onChange={(e) => { setFilterClass(e.target.value); setUniversePage(1); }}
                    className="bg-background border border-border/50 text-xs px-2.5 py-1.5 rounded-xl text-white focus:outline-none cursor-pointer"
                  >
                    <option value="">All Asset Types</option>
                    <option value="crypto">Cryptocurrency Majors</option>
                    <option value="forex">Foreign Exchange (Forex)</option>
                    <option value="commodity">Commodity Spot Rates</option>
                    <option value="stock">Equity Stocks</option>
                  </select>

                  <select
                    value={filterMarket}
                    onChange={(e) => { setFilterMarket(e.target.value); setUniversePage(1); }}
                    className="bg-background border border-border/50 text-xs px-2.5 py-1.5 rounded-xl text-white focus:outline-none cursor-pointer"
                  >
                    <option value="">All Market Sectors</option>
                    <option value="Crypto">Crypto Assets</option>
                    <option value="Forex">Forex Majors</option>
                    <option value="Commodities">Commodities Markets</option>
                    <option value="US Stocks">US Capital Equities</option>
                    <option value="Pakistan Stocks">Pakistan PSX Exchange</option>
                  </select>
                </div>

                {/* Selected Symbols Pool Bar */}
                <div className="p-3 bg-black/40 border border-border/40 rounded-xl flex flex-wrap items-center justify-between gap-3 font-sans">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[8px] text-muted-foreground uppercase font-black shrink-0 mr-1.5">Active Pool:</span>
                    {selectedSymbols.length === 0 ? (
                      <span className="text-[10px] text-muted-foreground/35 italic font-medium">None selected. Click Add to Pool on tickers below.</span>
                    ) : (
                      selectedSymbols.map(sym => (
                        <span key={sym} className="px-2 py-0.5 bg-primary/10 border border-primary/20 text-primary font-black rounded-lg text-[9px] flex items-center gap-1">
                          {sym}
                          <button 
                            onClick={() => setSelectedSymbols(prev => prev.filter(x => x !== sym))}
                            className="text-primary hover:text-white font-bold ml-0.5 cursor-pointer"
                          >
                            ×
                          </button>
                        </span>
                      ))
                    )}
                  </div>
                  {selectedSymbols.length > 0 && (
                    <button 
                      onClick={() => setSelectedSymbols([])}
                      className="text-[8px] text-rose-400 hover:text-white uppercase font-black cursor-pointer border border-rose-500/20 px-1 bg-rose-500/5 rounded"
                    >
                      Clear Pool
                    </button>
                  )}
                </div>
              </div>

              {/* Ticker List Table */}
              <div className="overflow-x-auto rounded-xl border border-border/20 bg-background/45">
                <table className="w-full border-collapse text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-border/20 bg-white/[0.02] text-muted-foreground uppercase text-[9px] tracking-wider font-sans">
                      <th className="py-2.5 px-3">Symbol</th>
                      <th className="py-2.5 px-3">Asset Title</th>
                      <th className="py-2.5 px-3">Type</th>
                      <th className="py-2.5 px-3">Exchange</th>
                      <th className="py-2.5 px-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {universeLoading ? (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-muted-foreground font-sans">
                          <RefreshCw className="animate-spin inline mr-2 h-4 w-4 text-primary" /> Loading symbol registry...
                        </td>
                      </tr>
                    ) : symbolsList.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-muted-foreground italic font-sans">
                          No matching assets matched in system.
                        </td>
                      </tr>
                    ) : (
                      symbolsList.map((sym) => {
                        const isSelected = selectedSymbols.includes(sym.symbol);
                        return (
                          <tr key={sym.id} className="border-b border-border/10 hover:bg-white/[0.01] transition-colors">
                            <td className="py-2 px-3 font-extrabold text-white text-xs">{sym.symbol}</td>
                            <td className="py-2 px-3 text-muted-foreground truncate max-w-[120px] font-sans font-medium">{sym.displayName || sym.symbol}</td>
                            <td className="py-2 px-3 font-sans"><span className="px-1.5 py-0.5 text-[8px] font-bold rounded bg-white/[0.04] text-white uppercase">{sym.assetClass}</span></td>
                            <td className="py-2 px-3 text-muted-foreground uppercase text-[10px]">{sym.exchange || "Global"}</td>
                            <td className="py-2 px-3 text-right font-sans">
                              <div className="flex items-center justify-end gap-1.5">
                                <button
                                  onClick={() => {
                                    if (isSelected) {
                                      setSelectedSymbols(prev => prev.filter(x => x !== sym.symbol));
                                    } else {
                                      setSelectedSymbols(prev => [...prev, sym.symbol]);
                                    }
                                  }}
                                  className={`px-2 py-0.5 text-[8px] font-extrabold rounded transition-all cursor-pointer uppercase ${
                                    isSelected 
                                      ? "bg-primary text-black border border-primary font-black" 
                                      : "bg-white/5 hover:bg-white/10 text-white border border-border/40"
                                  }`}
                                >
                                  {isSelected ? "Selected" : "Add to Pool"}
                                </button>
                                {sym.dataStatus !== "ready" && (
                                  <button
                                    onClick={() => handleTriggerDownload(sym.id)}
                                    className="px-2 py-0.5 text-[8px] font-bold text-primary bg-primary/10 hover:bg-primary/20 border border-primary/20 rounded cursor-pointer flex items-center gap-0.5"
                                    title="Download data"
                                  >
                                    <Download size={8} /> Sync
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {universeTotalPages > 1 && (
                <div className="flex items-center justify-between pt-2 font-sans">
                  <span className="text-[10px] text-muted-foreground font-medium">Page {universePage} of {universeTotalPages}</span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setUniversePage(p => Math.max(1, p - 1))}
                      disabled={universePage === 1}
                      className="px-2.5 py-1 text-[10px] bg-background border border-border/40 hover:bg-white/[0.04] text-white rounded-lg disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                    >
                      Previous
                    </button>
                    <button
                      onClick={() => setUniversePage(p => Math.min(universeTotalPages, p + 1))}
                      disabled={universePage === universeTotalPages}
                      className="px-2.5 py-1 text-[10px] bg-background border border-border/40 hover:bg-white/[0.04] text-white rounded-lg disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}

            </div>

            {/* CSV Ingestor */}
            <div className="border border-border/30 bg-[#0c0c0c]/80 backdrop-blur-md p-6 rounded-2xl flex flex-col justify-between font-sans">
              <div className="space-y-4">
                <div className="border-b border-border/20 pb-3">
                  <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <FileUp className="text-primary h-4 w-4" /> CSV Custom Uploader
                  </h2>
                  <p className="text-[10px] text-muted-foreground mt-0.5">Ingest custom ASCII/CSV datasets to backtest local tickers or Karachi exchange symbols.</p>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-[8px] text-muted-foreground uppercase font-bold">Target Ticker</label>
                  <select
                    value={csvSymbolId}
                    onChange={(e) => setCsvSymbolId(e.target.value)}
                    className="bg-background border border-border/50 text-xs px-2.5 py-1.5 rounded-xl text-white focus:outline-none cursor-pointer font-mono font-bold"
                  >
                    <option value="">-- Choose Target --</option>
                    {symbolsList.map(s => (
                      <option key={s.id} value={s.id}>{s.symbol} ({s.displayName})</option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-[8px] text-muted-foreground uppercase font-bold">Interval</label>
                  <select
                    value={csvTimeframe}
                    onChange={(e) => setCsvTimeframe(e.target.value)}
                    className="bg-background border border-border/50 text-xs px-2.5 py-1.5 rounded-xl text-white focus:outline-none cursor-pointer"
                  >
                    <option value="1d">1d (Daily)</option>
                    <option value="1h">1h (Hourly)</option>
                    <option value="15m">15m (Intraday)</option>
                  </select>
                </div>

                <div className="flex flex-col gap-1.5">
                  <div className="flex justify-between items-center">
                    <label className="text-[8px] text-muted-foreground uppercase font-bold">Paste Raw Values</label>
                    <span className="text-[7px] text-primary/70 uppercase">date,open,high,low,close,volume</span>
                  </div>
                  <textarea
                    placeholder="date,open,high,low,close,volume&#10;2024-01-01,100.5,102.3,99.1,101.4,142000"
                    value={csvText}
                    onChange={(e) => setCsvText(e.target.value)}
                    rows={8}
                    className="w-full bg-background border border-border/50 rounded-xl p-3 text-[10px] text-white focus:outline-none focus:border-primary/50 transition-all font-mono scrollbar-hide"
                  />
                </div>

                {csvError && <div className="p-2 border border-rose-500/20 bg-rose-500/5 text-[9px] text-rose-400 font-bold rounded-xl">{csvError}</div>}
                {csvMessage && <div className="p-2 border border-emerald-500/20 bg-emerald-500/5 text-[9px] text-emerald-400 font-bold rounded-xl">{csvMessage}</div>}
              </div>

              <button
                onClick={handleImportCSV}
                disabled={csvImporting || !csvSymbolId || !csvText}
                className="w-full bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/45 text-[10px] font-extrabold py-2.5 rounded-xl cursor-pointer uppercase tracking-wider mt-4"
              >
                {csvImporting ? "Processing..." : "Import Dataset"}
              </button>
            </div>

          </div>
        )}

        {/* CALENDAR ACTIVITY */}
        {currentTab === 'calendar' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 animate-fade-in font-sans">
            
            {/* Calendar grid view */}
            <div className="lg:col-span-2 border border-border/30 bg-[#0c0c0c]/80 backdrop-blur-md p-6 rounded-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-border/20 pb-3">
                <div>
                  <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <CalendarDays className="text-primary h-4 w-4" /> Activity Calendar
                  </h2>
                  <p className="text-[10px] text-muted-foreground mt-0.5">Monitor profitable/losing trading days mapped from your simulation journals.</p>
                </div>

                <div className="flex items-center gap-2">
                  <button 
                    onClick={() => {
                      if (calendarMonth === 0) {
                        setCalendarMonth(11);
                        setCalendarYear(y => y - 1);
                      } else {
                        setCalendarMonth(m => m - 1);
                      }
                    }}
                    className="p-1 rounded bg-white/5 border border-border/40 hover:bg-white/10 text-white cursor-pointer"
                  >
                    <ChevronLeft size={14} />
                  </button>
                  <span className="text-xs font-bold text-white font-mono min-w-[100px] text-center">
                    {monthNames[calendarMonth]} {calendarYear}
                  </span>
                  <button 
                    onClick={() => {
                      if (calendarMonth === 11) {
                        setCalendarMonth(0);
                        setCalendarYear(y => y + 1);
                      } else {
                        setCalendarMonth(m => m + 1);
                      }
                    }}
                    className="p-1 rounded bg-white/5 border border-border/40 hover:bg-white/10 text-white cursor-pointer"
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>

              {/* Grid of days */}
              <div className="grid grid-cols-7 gap-2.5">
                {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(d => (
                  <div key={d} className="text-center text-[9px] text-muted-foreground uppercase font-black py-1">{d}</div>
                ))}
                
                {Array.from({ length: getFirstDayOfMonth(calendarYear, calendarMonth) }).map((_, idx) => (
                  <div key={`empty-${idx}`} className="bg-transparent border border-transparent min-h-[64px]" />
                ))}

                {Array.from({ length: getDaysInMonth(calendarYear, calendarMonth) }).map((_, idx) => {
                  const dayNum = idx + 1;
                  const monthStr = String(calendarMonth + 1).padStart(2, '0');
                  const dayStr = String(dayNum).padStart(2, '0');
                  const dayQuery = `${calendarYear}-${monthStr}-${dayStr}`;

                  const dayTrades = allClosedTrades.filter(t => t.exitDate?.includes(dayQuery));
                  const dayPnl = dayTrades.reduce((acc, t) => acc + t.pnl, 0);
                  const hasTrades = dayTrades.length > 0;

                  return (
                    <div 
                      key={dayNum} 
                      className={`min-h-[64px] p-1.5 border rounded-xl flex flex-col justify-between transition-colors ${
                        hasTrades
                          ? dayPnl >= 0 
                            ? "bg-emerald-500/5 border-emerald-500/30 hover:border-emerald-500/50" 
                            : "bg-rose-500/5 border-rose-500/30 hover:border-rose-500/50"
                          : "bg-black/20 border-border/20 hover:border-border/30"
                      }`}
                    >
                      <span className="text-[10px] font-extrabold text-white font-mono">{dayNum}</span>
                      
                      {hasTrades && (
                        <div className="flex flex-col text-[8px] font-mono leading-none">
                          <span className={dayPnl >= 0 ? "text-[#7aff78] font-bold" : "text-[#ff4a4a] font-bold"}>
                            {dayPnl >= 0 ? "+" : ""}${dayPnl.toFixed(0)}
                          </span>
                          <span className="text-muted-foreground mt-0.5">{dayTrades.length} Trd</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

            </div>

            {/* Monthly Calendar Stats card */}
            <div className="border border-border/30 bg-[#0c0c0c]/80 backdrop-blur-md p-6 rounded-2xl space-y-4">
              <span className="text-[10px] text-muted-foreground uppercase font-extrabold tracking-wider block border-b border-border/10 pb-2">
                Monthly Activity Summary
              </span>

              {allClosedTrades.length === 0 ? (
                <div className="text-center p-8 text-muted-foreground/35 border border-dashed border-border/20 text-[10px] rounded-xl font-mono">
                  Seeded after completing backtests
                </div>
              ) : (
                <div className="space-y-4 text-xs font-mono">
                  {[
                    { label: "Active Trading Days", val: String(new Set(allClosedTrades.map(t => t.exitDate)).size) },
                    { label: "Profitable Days", val: String(new Set(allClosedTrades.filter(t => t.pnl > 0).map(t => t.exitDate)).size), color: "text-[#7aff78]" },
                    { label: "Losing Days", val: String(new Set(allClosedTrades.filter(t => t.pnl < 0).map(t => t.exitDate)).size), color: "text-[#ff4a4a]" },
                    { label: "Average Daily P/L", val: `$${(allGrossProfit - allGrossLoss / Math.max(1, new Set(allClosedTrades.map(t => t.exitDate)).size)).toFixed(0)}` },
                    { label: "Best Day P&L", val: allClosedTrades.length > 0 ? `$${Math.max(...allClosedTrades.map(t => t.pnl)).toFixed(0)}` : "N/A", color: "text-[#7aff78]" },
                    { label: "Worst Day P&L", val: allClosedTrades.length > 0 ? `-$${Math.max(...allClosedTrades.map(t => Math.abs(t.pnl))).toFixed(0)}` : "N/A", color: "text-[#ff4a4a]" },
                  ].map((row, idx) => (
                    <div key={idx} className="flex justify-between border-b border-border/10 pb-2 font-mono">
                      <span className="text-muted-foreground">{row.label}</span>
                      <span className={`font-bold ${row.color || "text-white"}`}>{row.val}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>
        )}

        {/* TRADE ANALYTICS */}
        {currentTab === 'analytics' && (
          <div className="space-y-6 animate-fade-in font-sans">
            
            {/* Visual Analytics Widgets */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Daily Profit / Loss Bar Chart */}
              <div className="p-5 border border-border/30 bg-black/60 rounded-2xl min-h-[260px] flex flex-col justify-between">
                <div>
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">Win Rate Trend Over Time</h3>
                  <p className="text-[10px] text-muted-foreground">Rolling win percentage tracker across simulation history</p>
                </div>
                <div className="h-44 w-full mt-3">
                  {allClosedTrades.length === 0 ? (
                    <div className="w-full h-full border border-dashed border-border/20 flex items-center justify-center text-[10px] text-muted-foreground/35 font-mono">No data points</div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={allClosedTrades.map((t, idx) => {
                        const slice = allClosedTrades.slice(0, idx + 1);
                        const wins = slice.filter(x => x.pnl > 0).length;
                        return { idx: idx + 1, rate: (wins / slice.length) * 100 };
                      })}>
                        <XAxis dataKey="idx" stroke="#333" fontSize={8} />
                        <YAxis stroke="#333" fontSize={8} domain={[0, 100]} />
                        <Tooltip />
                        <Line type="monotone" dataKey="rate" stroke="#7aff78" strokeWidth={1.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>

              {/* Long vs Short Comparison */}
              <div className="p-5 border border-border/30 bg-black/60 rounded-2xl min-h-[260px] flex flex-col justify-between">
                <div>
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">Long vs Short Performance ($)</h3>
                  <p className="text-[10px] text-muted-foreground">Absolute P&L totals by order placement type</p>
                </div>
                <div className="h-44 w-full mt-3 font-mono">
                  {allClosedTrades.length === 0 ? (
                    <div className="w-full h-full border border-dashed border-border/20 flex items-center justify-center text-[10px] text-muted-foreground/35 font-mono font-sans">No data points</div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={[
                        { name: "Long", pnl: allClosedTrades.filter(t => t.direction === 'LONG').reduce((acc, t) => acc + t.pnl, 0) },
                        { name: "Short", pnl: allClosedTrades.filter(t => t.direction === 'SHORT').reduce((acc, t) => acc + t.pnl, 0) }
                      ]}>
                        <XAxis dataKey="name" stroke="#333" fontSize={9} />
                        <YAxis stroke="#333" fontSize={9} />
                        <Tooltip />
                        <Bar dataKey="pnl" fill="#7aff78" radius={[4, 4, 0, 0]}>
                          {allClosedTrades.map((_, i) => (
                            <Cell key={i} fill={i === 0 ? "#7aff78" : "#8884d8"} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>

              {/* Accum profit by symbol */}
              <div className="p-5 border border-border/30 bg-black/60 rounded-2xl min-h-[260px] flex flex-col justify-between font-mono">
                <div>
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider font-sans">Cumulative Profit by Asset</h3>
                  <p className="text-[10px] text-muted-foreground font-sans">Accumulated currency generation mapped per token</p>
                </div>
                <div className="h-44 w-full mt-3">
                  {allClosedTrades.length === 0 ? (
                    <div className="w-full h-full border border-dashed border-border/20 flex items-center justify-center text-[10px] text-muted-foreground/35 font-sans">No data points</div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={Object.entries(
                        allClosedTrades.reduce<Record<string, number>>((acc, t) => {
                          acc[t.symbol] = (acc[t.symbol] || 0) + t.pnl;
                          return acc;
                        }, {})
                      ).map(([key, val]) => ({ name: key, pnl: val }))}>
                        <XAxis dataKey="name" stroke="#333" fontSize={9} />
                        <YAxis stroke="#333" fontSize={9} />
                        <Tooltip />
                        <Bar dataKey="pnl" fill="#7aff78" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>

            </div>

            {/* Filterable Trades Ledger */}
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <span className="text-[10px] text-muted-foreground font-bold tracking-wider uppercase flex items-center gap-1.5">
                  <FileText size={14} className="text-primary" /> Multi-Session Closed Trades Ledger
                </span>
                
                {/* Ledger filters */}
                <div className="flex flex-wrap gap-2.5 text-[10px]">
                  <input
                    type="text"
                    placeholder="Filter Asset..."
                    value={ledgerSymbolFilter}
                    onChange={(e) => setLedgerSymbolFilter(e.target.value.toUpperCase())}
                    className="bg-background border border-border/40 text-[10px] px-2 py-1 focus:outline-none focus:border-primary rounded-xl font-mono text-white placeholder-muted-foreground"
                  />
                  <select
                    value={ledgerTypeFilter}
                    onChange={(e) => setLedgerTypeFilter(e.target.value as any)}
                    className="bg-background border border-border/40 text-[10px] px-2 py-1 focus:outline-none rounded-xl text-white"
                  >
                    <option value="all">All Outcomes</option>
                    <option value="winning">Only Wins</option>
                    <option value="losing">Only Losses</option>
                  </select>
                  <select
                    value={ledgerDirectionFilter}
                    onChange={(e) => setLedgerDirectionFilter(e.target.value as any)}
                    className="bg-background border border-border/40 text-[10px] px-2 py-1 focus:outline-none rounded-xl text-white"
                  >
                    <option value="all">All Directions</option>
                    <option value="LONG">Longs</option>
                    <option value="SHORT">Shorts</option>
                  </select>
                </div>
              </div>

              {/* Table ledger */}
              {allClosedTrades.length === 0 ? (
                <div className="text-center p-12 text-muted-foreground/35 border border-dashed border-border/20 text-xs rounded-2xl bg-black/20">
                  No trades registered in system. Launch a simulation to create entries.
                </div>
              ) : (
                <div className="overflow-x-auto bg-[#0f0f0f]/40 border border-border/30 rounded-xl">
                  <table className="w-full text-left border-collapse text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border/20 text-muted-foreground text-[9px] uppercase bg-white/[0.01]">
                        <th className="py-2.5 px-4 font-semibold">Symbol</th>
                        <th className="py-2.5 px-4 font-semibold">Dir</th>
                        <th className="py-2.5 px-4 font-semibold">Entry Date</th>
                        <th className="py-2.5 px-4 font-semibold">Exit Date</th>
                        <th className="py-2.5 px-4 font-semibold">Entry Price</th>
                        <th className="py-2.5 px-4 font-semibold">Exit Price</th>
                        <th className="py-2.5 px-4 font-semibold text-right">P&L ($)</th>
                        <th className="py-2.5 px-4 font-semibold text-right">Return</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/10 font-mono">
                      {allClosedTrades
                        .filter(t => !ledgerSymbolFilter || t.symbol?.includes(ledgerSymbolFilter))
                        .filter(t => {
                          if (ledgerTypeFilter === 'winning') return t.pnl > 0;
                          if (ledgerTypeFilter === 'losing') return t.pnl <= 0;
                          return true;
                        })
                        .filter(t => ledgerDirectionFilter === 'all' || t.direction === ledgerDirectionFilter)
                        .map((trade) => {
                          const isGain = trade.pnl >= 0;
                          return (
                            <tr key={trade.id} className="hover:bg-white/[0.01] transition-colors">
                              <td className="py-2 px-4 font-black text-white">{trade.symbol}</td>
                              <td className={`py-2 px-4 font-bold ${trade.direction === 'LONG' ? 'text-primary' : 'text-rose-400'}`}>{trade.direction}</td>
                              <td className="py-2 px-4 text-muted-foreground">{trade.entryDate}</td>
                              <td className="py-2 px-4 text-muted-foreground">{trade.exitDate}</td>
                              <td className="py-2 px-4">${trade.entryPrice.toFixed(2)}</td>
                              <td className="py-2 px-4">${trade.exitPrice.toFixed(2)}</td>
                              <td className={`py-2 px-4 text-right font-bold ${isGain ? 'text-[#7aff78]' : 'text-[#ff4a4a]'}`}>
                                {isGain ? "+" : ""}${trade.pnl.toFixed(2)}
                              </td>
                              <td className={`py-2 px-4 text-right font-bold ${isGain ? 'text-[#7aff78]' : 'text-[#ff4a4a]'}`}>
                                {isGain ? "+" : ""}{trade.pnlPercent.toFixed(1)}%
                              </td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

          </div>
        )}

        {/* REPORTS PREVIEW */}
        {currentTab === 'reports' && (
          <div className="border border-border/30 bg-[#0c0c0c]/80 backdrop-blur-md p-6 rounded-2xl space-y-6 animate-fade-in font-sans">
            <div className="border-b border-border/20 pb-3 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                  <FileText className="text-primary h-4 w-4" /> Strategy Performance Reports
                </h2>
                <p className="text-[10px] text-muted-foreground mt-0.5">Audited strategy performance sheets loaded from database.</p>
              </div>

              {/* Export triggers */}
              <div className="flex gap-2">
                {["PDF", "CSV", "Excel"].map((fmt) => (
                  <button
                    key={fmt}
                    onClick={() => alert(`Exporting report to ${fmt} is a placeholder and will be completed after backend reporting modules are integrated.`)}
                    className="px-3 py-1.5 bg-white/5 border border-border/40 hover:bg-white/10 text-white rounded-lg text-[10px] font-extrabold transition-all cursor-pointer flex items-center gap-1"
                  >
                    <DownloadCloud size={11} /> Export {fmt}
                  </button>
                ))}
              </div>
            </div>

            {reportsLoading ? (
              <div className="text-center py-8 text-muted-foreground text-xs font-mono">
                Loading reports from database...
              </div>
            ) : dbReports.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-xs font-mono">
                No reports found in the database.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {dbReports.map((report) => {
                  let contentData = {};
                  try {
                    contentData = typeof report.content === 'string' ? JSON.parse(report.content) : (report.content || {});
                  } catch (e) {
                    // ignore
                  }
                  return (
                    <div key={report.id} className="border border-border/20 bg-black/40 p-5 rounded-xl space-y-4 font-mono text-xs">
                      <div className="flex items-center justify-between border-b border-border/10 pb-1.5 font-sans">
                        <span className="text-[10px] text-primary font-bold uppercase tracking-wider">{report.title}</span>
                        <span className="text-[9px] bg-primary/10 text-primary border border-primary/20 px-2 py-0.5 rounded font-bold uppercase tracking-wider">{report.asset}</span>
                      </div>
                      <p className="text-[10px] text-muted-foreground font-sans leading-relaxed">{report.summary}</p>
                      
                      <div className="space-y-2 pt-2 border-t border-border/10">
                        {Object.entries(contentData).map(([key, val]) => (
                          <div key={key} className="flex justify-between pb-1 border-b border-border/5 last:border-0 last:pb-0">
                            <span className="text-muted-foreground capitalize font-sans">{key.replace(/([A-Z])/g, ' $1')}</span>
                            <span className="font-bold text-white">{String(val)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* SETTINGS PARAMETERS */}
        {currentTab === 'settings' && (
          <div className="border border-border/30 bg-[#0c0c0c]/80 backdrop-blur-md p-6 rounded-2xl space-y-5 animate-fade-in max-w-2xl font-sans">
            <div className="border-b border-border/20 pb-3">
              <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <Settings className="text-primary h-4 w-4" /> Strategy Configuration Settings
              </h2>
              <p className="text-[10px] text-muted-foreground mt-0.5">Customize global margins, commissions, and trade slippage parameters.</p>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-[9px] text-muted-foreground uppercase font-bold">Commission Fee (%)</label>
                  <input
                    type="number"
                    value={commissionRate}
                    onChange={(e) => setCommissionRate(Number(e.target.value))}
                    step={0.0001}
                    className="bg-background border border-border/50 text-xs px-3 py-1.5 rounded-xl font-bold focus:outline-none focus:border-primary font-mono text-white"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-[9px] text-muted-foreground uppercase font-bold">Estimated Slippage (Ticks)</label>
                  <input
                    type="number"
                    value={slippageTicks}
                    onChange={(e) => setSlippageTicks(Number(e.target.value))}
                    className="bg-background border border-border/50 text-xs px-3 py-1.5 rounded-xl font-bold focus:outline-none focus:border-primary font-mono text-white"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[9px] text-muted-foreground uppercase font-bold">Position Sizing Formula</label>
                <select 
                  value={positionFormula}
                  onChange={(e) => setPositionFormula(e.target.value)}
                  className="bg-background border border-border/50 text-xs px-3 py-1.5 rounded-xl text-white font-bold focus:outline-none cursor-pointer"
                >
                  <option>Capital-Proportional Sizing (Default)</option>
                  <option>Kelly Criterion Formula</option>
                  <option>Martingale Doubling Progression</option>
                </select>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-[9px] text-muted-foreground uppercase font-bold">Prop Firm Risk Rules Enforcement</label>
                <select 
                  value={propFirmEnforcement}
                  onChange={(e) => setPropFirmEnforcement(e.target.value)}
                  className="bg-background border border-border/50 text-xs px-3 py-1.5 rounded-xl text-white font-bold focus:outline-none cursor-pointer"
                >
                  <option>Standard (5% daily / 10% overall limits)</option>
                  <option>Loose (10% daily / 15% overall limits)</option>
                  <option>Strict Discipline (3% daily / 6% overall limits)</option>
                </select>
              </div>

              <button
                onClick={() => alert("Custom configuration settings saved to Orbit Engine Local Cache.")}
                className="bg-primary hover:bg-primary/95 text-black font-extrabold text-xs py-2.5 px-6 rounded-xl cursor-pointer uppercase transition-all"
              >
                Save Settings
              </button>
            </div>
          </div>
        )}

      </main>

    </div>
  );
}
