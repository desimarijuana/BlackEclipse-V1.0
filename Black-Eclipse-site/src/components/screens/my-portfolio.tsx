'use client';

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';
import {
  Briefcase, ArrowUpRight, ArrowDownRight, Sparkles,
  Wallet, TrendingUp, History, PieChart,
  Plus, Trash2, Shield, Activity, PlusCircle,
  AlertCircle, BarChart2, DollarSign, Calendar,
  X, Search, Star, ChevronDown, ChevronUp, Flame, Gauge, Grid3x3,
  Home, GraduationCap, PiggyBank, Plane, Car, Heart,
  Gift, Rocket, Landmark, Coins, LayoutDashboard, SquarePen,
  GripVertical, Settings2, Eye, EyeOff, RotateCcw} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TopLoader } from '@/components/ui/top-loader';
import { SkeletonCardGrid, SkeletonHeader, SkeletonPanel, SkeletonTable } from '@/components/ui/skeleton';
import { usePortfolioEngine, computePortfolioStats, PortfolioStats } from '@/hooks/use-portfolio-engine';
import { usePriceHistories } from '@/hooks/use-price-histories';
import {
  getDisplayCurrency, setDisplayCurrency, fetchFxMatrix, convertFromUsd, fmtMoney, fmtMoneyCompact,
  DISPLAY_CURRENCIES,
  type Currency,
} from '@/lib/currency';
import {
  computeHealthScore, buildBrief, buildChanges,
  type HoldingMeta,
} from '@/lib/portfolio-analysis';

// ─── Shared panel / tile styling (site design system) ──────────────────────
// Frost glass — this is the site's default glass panel style. The same
// bg/blur/border recipe used across market-overview, market-news and
// portfolio-watchlist so every screen looks consistent.
const PANEL = 'bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-2xl shadow-sm';
const TILE = 'bg-[#0f0f0f]/60 dark:bg-[#0f0f0f]/60 bg-white/70 backdrop-blur-xl border border-white/10 dark:border-white/5 rounded-xl';
// Frosted-glass grey — dark neutral glass matching the site's panel recipe for
// edit/customize mode. Handles stay compact and fade to near-invisible unless
// the widget is hovered, so edit mode stays quiet.
const EDIT_HANDLE = 'bg-zinc-800/85 dark:bg-zinc-800/90 bg-zinc-600/80 backdrop-blur-md border border-white/20 dark:border-white/12 shadow-lg';
const EDIT_GRIP = 'bg-zinc-800/80 dark:bg-zinc-800/85 bg-zinc-600/70 backdrop-blur-md border border-white/18 dark:border-white/10 shadow-md';
const UP = '#34d399';
const DOWN = '#fb7185';

export interface Transaction {
  id: string;
  type: 'BUY' | 'SELL' | 'DEPOSIT' | 'WITHDRAWAL' | 'DIVIDEND';
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
  type: 'PRICE_ABOVE' | 'PRICE_BELOW' | 'ALLOCATION_EXCEEDS' | 'DAILY_MOVE';
  target: number;
  isActive: boolean;
}

const DEFAULT_TRANSACTIONS: Transaction[] = [
  { id: 'tx-1', type: 'BUY', symbol: 'BTC', quantity: 0.25, price: 61500.00, fee: 15.00, date: '2026-06-01' },
  { id: 'tx-2', type: 'BUY', symbol: 'ETH', quantity: 4.20, price: 2950.00, fee: 12.50, date: '2026-06-02' },
  { id: 'tx-3', type: 'BUY', symbol: 'SOL', quantity: 25.00, price: 110.00, fee: 2.50, date: '2026-06-03' },
  // PSX equities — UBL, Meezan Bank, Sazgar (prices in PKR).
  { id: 'tx-4', type: 'BUY', symbol: 'UBL', quantity: 150, price: 300.00, fee: 45.00, date: '2026-05-12' },
  { id: 'tx-5', type: 'BUY', symbol: 'UBL', quantity: 80, price: 338.00, fee: 28.00, date: '2026-07-20' },
  { id: 'tx-6', type: 'BUY', symbol: 'MEBL', quantity: 400, price: 152.50, fee: 60.00, date: '2026-04-18' },
  { id: 'tx-7', type: 'BUY', symbol: 'MEBL', quantity: 250, price: 171.00, fee: 40.00, date: '2026-08-05' },
  { id: 'tx-8', type: 'BUY', symbol: 'SAZEW', quantity: 60, price: 880.00, fee: 55.00, date: '2026-06-25' },
  { id: 'tx-9', type: 'SELL', symbol: 'SAZEW', quantity: 15, price: 1010.00, fee: 15.00, date: '2026-08-18' },
];

// Which JDDS market each symbol lives in — drives /api/price-history ticker
// resolution (PK tickers get the .PSX/.KA fallback chain, crypto gets -USD).
const MARKET_HINT: Record<string, string> = {
  BTC: 'CRYPTO', ETH: 'CRYPTO', SOL: 'CRYPTO', BNB: 'CRYPTO', XRP: 'CRYPTO',
  DOGE: 'CRYPTO', ADA: 'CRYPTO',
  UBL: 'PK', MEBL: 'PK', SAZEW: 'PK', OGDC: 'PK', LUCK: 'PK', HBL: 'PK', PSO: 'PK', ENGRO: 'PK', SYS: 'PK',
};

interface DemoAsset {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  category: string;
  aiTag?: string;
  currency?: 'USD' | 'PKR';
}

const DEMO_LIVE_PRICES: DemoAsset[] = [
  { symbol: 'BTC', name: 'Bitcoin', price: 67840.00, changePercent: 2.14, category: 'Store of Value', aiTag: 'ETF inflows accelerating — spot demand absorbing supply near range highs.' },
  { symbol: 'ETH', name: 'Ethereum', price: 3500.20, changePercent: 2.41, category: 'Smart Contracts', aiTag: 'Staking yield compressing as inflows rise; watch L2 fee migration.' },
  { symbol: 'SOL', name: 'Solana', price: 168.40, changePercent: 3.82, category: 'Smart Contracts', aiTag: 'Highest beta position — DEX volumes driving outsized momentum.' },
  { symbol: 'BNB', name: 'BNB', price: 585.50, changePercent: -1.20, category: 'Exchange' },
  { symbol: 'XRP', name: 'Ripple', price: 0.53, changePercent: -0.84, category: 'Payments' },
  { symbol: 'DOGE', name: 'Dogecoin', price: 0.16, changePercent: 1.12, category: 'Meme', aiTag: 'Sentiment-driven; correlation to BTC spikes during risk-off moves.' },
  { symbol: 'ADA', name: 'Cardano', price: 0.45, changePercent: -1.32, category: 'Smart Contracts' },
  // PSX equities (prices in PKR) — UBL, Meezan Bank, Sazgar.
  { symbol: 'UBL', name: 'United Bank Limited', price: 350.50, changePercent: 1.20, category: 'Banking', currency: 'PKR', aiTag: 'Strong net interest income; dividend yield above market average.' },
  { symbol: 'MEBL', name: 'Meezan Bank Limited', price: 185.25, changePercent: 0.85, category: 'Banking', currency: 'PKR', aiTag: 'Shariah-compliant growth — deposits compounding faster than the sector.' },
  { symbol: 'SAZEW', name: 'Sazgar Engineering Works', price: 1045.00, changePercent: 2.10, category: 'Automobile', currency: 'PKR', aiTag: 'Rising local EV/3-wheeler volumes supporting margin expansion.' },
];

// Per-asset risk profile used by stress testing, risk metrics & Monte Carlo.
const RISK: Record<string, { beta: number; vol: number; sharpe: number; mdd: number; target: number }> = {
  BTC:  { beta: 1.00, vol: 48.0, sharpe: 1.42, mdd: -32.0, target: 35 },
  ETH:  { beta: 1.18, vol: 62.0, sharpe: 1.10, mdd: -45.0, target: 25 },
  SOL:  { beta: 1.55, vol: 88.0, sharpe: 0.94, mdd: -62.0, target: 15 },
  BNB:  { beta: 0.92, vol: 52.0, sharpe: 1.05, mdd: -38.0, target: 10 },
  XRP:  { beta: 1.08, vol: 66.0, sharpe: 0.72, mdd: -52.0, target: 8 },
  DOGE: { beta: 1.42, vol: 95.0, sharpe: 0.58, mdd: -70.0, target: 4 },
  ADA:  { beta: 1.22, vol: 71.0, sharpe: 0.49, mdd: -58.0, target: 3 },
  // PSX equities (lower vol vs crypto, PKR).
  UBL:  { beta: 0.65, vol: 24.0, sharpe: 1.25, mdd: -18.0, target: 12 },
  MEBL: { beta: 0.78, vol: 28.0, sharpe: 1.35, mdd: -22.0, target: 12 },
  SAZEW: { beta: 0.92, vol: 34.0, sharpe: 1.10, mdd: -28.0, target: 8 },
  // Generic fallback for any other JDDS asset the user adds (equity-like).
  DEFAULT: { beta: 0.9, vol: 30.0, sharpe: 0.9, mdd: -25.0, target: 10 },
};

const CORR: Record<string, Record<string, number>> = {
  BTC:  { BTC: 1, ETH: 0.86, SOL: 0.78, BNB: 0.81, XRP: 0.72, DOGE: 0.74, ADA: 0.7, UBL: 0.28, MEBL: 0.31, SAZEW: 0.26 },
  ETH:  { ETH: 1, SOL: 0.82, BNB: 0.79, XRP: 0.68, DOGE: 0.71, ADA: 0.76, UBL: 0.25, MEBL: 0.28, SAZEW: 0.22 },
  SOL:  { SOL: 1, BNB: 0.7, XRP: 0.64, DOGE: 0.69, ADA: 0.73, UBL: 0.22, MEBL: 0.24, SAZEW: 0.19 },
  BNB:  { BNB: 1, XRP: 0.66, DOGE: 0.62, ADA: 0.65, UBL: 0.3, MEBL: 0.33, SAZEW: 0.27 },
  XRP:  { XRP: 1, DOGE: 0.6, ADA: 0.63, UBL: 0.2, MEBL: 0.22, SAZEW: 0.18 },
  DOGE: { DOGE: 1, ADA: 0.61, UBL: 0.15, MEBL: 0.17, SAZEW: 0.13 },
  ADA:  { ADA: 1, UBL: 0.18, MEBL: 0.2, SAZEW: 0.16 },
  UBL:  { UBL: 1, MEBL: 0.82, SAZEW: 0.58 },
  MEBL: { MEBL: 1, SAZEW: 0.55 },
  SAZEW: { SAZEW: 1 },
};

const STRESS_SCENARIOS = [
  { id: 'market', label: 'Market −25%', desc: 'Broad crypto drawdown — correlations converge toward 1 and alts bleed harder than majors.', mkt: -25, alt: 0 },
  { id: 'btc', label: 'BTC −10% / alts −25%', desc: 'Bitcoin-led flush where high-beta alts de-risk twice as fast.', mkt: -10, alt: -15 },
  { id: 'rates', label: 'Liquidity shock', desc: 'Rate scare drains leverage; thin-liquidity positions gap down.', mkt: -8, alt: -10 },
  { id: 'capitulation', label: 'Capitulation −45%', desc: 'Cycle-bottom event: forced deleveraging across the entire complex.', mkt: -30, alt: -15 },
  { id: 'meltup', label: 'Melt-up +20%', desc: 'Risk-on rally led by high-beta smart-contract assets.', mkt: 12, alt: 8 },
];

const ALERT_TYPES: Array<{ value: Alert['type']; label: string }> = [
  { value: 'PRICE_ABOVE', label: 'Price above' },
  { value: 'PRICE_BELOW', label: 'Price below' },
  { value: 'DAILY_MOVE', label: '24h move >' },
];

const AVAILABLE_CASH = 8450.32;

// ── Multi-fund model ────────────────────────────────────────────────────────
// Users can create multiple goal-scoped portfolios ("House Fund", "College
// Fund", …). Each fund owns its own transaction ledger and lives in localStorage
// under `portfolio_funds_guest` as { id, name, icon, color, goalUsd?, tx: [] }.
// A legacy single-portfolio (key `portfolio_tx_guest`) is auto-migrated into a
// "Main Portfolio" fund on first load.

interface Fund {
  id: string;
  name: string;
  icon: string;      // lucide icon key — see FUND_ICONS
  color: string;     // hex accent used across cards & charts
  goalUsd?: number;  // optional savings goal for progress display
  tx: Transaction[];
}

const FUND_COLORS = ['#7aff78', '#8d92f9', '#d35bb1', '#f7ac4d', '#0090b1', '#8ec053', '#fbbf24'];

const FUND_ICONS: Record<string, React.ComponentType<{ className?: string; style?: React.CSSProperties }>> = {
  home: Home,
  education: GraduationCap,
  savings: PiggyBank,
  travel: Plane,
  car: Car,
  health: Heart,
  gift: Gift,
  growth: Rocket,
  reserve: Landmark,
  crypto: Coins,
  briefcase: Briefcase,
};

const FUND_ICON_OPTIONS = Object.keys(FUND_ICONS);

// Demo ledgers for the starter goal funds shown to first-time users.
const HOUSE_TX: Transaction[] = [
  { id: 'h-tx-1', type: 'BUY', symbol: 'UBL', quantity: 200, price: 292.00, fee: 55.00, date: '2026-03-14' },
  { id: 'h-tx-2', type: 'BUY', symbol: 'MEBL', quantity: 300, price: 148.00, fee: 48.00, date: '2026-05-02' },
  { id: 'h-tx-3', type: 'BUY', symbol: 'OGDC', quantity: 500, price: 21.40, fee: 30.00, date: '2026-06-11' },
];
const COLLEGE_TX: Transaction[] = [
  { id: 'c-tx-1', type: 'BUY', symbol: 'BTC', quantity: 0.12, price: 60200.00, fee: 11.00, date: '2026-04-08' },
  { id: 'c-tx-2', type: 'BUY', symbol: 'HBL', quantity: 350, price: 128.50, fee: 40.00, date: '2026-06-22' },
];

// Additional goal-fund ledgers for the seeded demo book.
const TRAVEL_TX: Transaction[] = [
  { id: 't-tx-1', type: 'BUY', symbol: 'SOL', quantity: 18.00, price: 102.00, fee: 6.50, date: '2026-05-19' },
  { id: 't-tx-2', type: 'BUY', symbol: 'PSO', quantity: 250, price: 342.00, fee: 35.00, date: '2026-05-30' },
  { id: 't-tx-3', type: 'BUY', symbol: 'SOL', quantity: 12.00, price: 141.75, fee: 4.20, date: '2026-07-09' },
  { id: 't-tx-4', type: 'SELL', symbol: 'PSO', quantity: 50, price: 368.00, fee: 12.00, date: '2026-08-14' },
  { id: 't-tx-5', type: 'BUY', symbol: 'ETH', quantity: 0.65, price: 3120.00, fee: 9.00, date: '2026-07-28' },
];
const RAINY_TX: Transaction[] = [
  { id: 'r-tx-1', type: 'BUY', symbol: 'HBL', quantity: 420, price: 131.20, fee: 42.00, date: '2026-02-20' },
  { id: 'r-tx-2', type: 'BUY', symbol: 'ENGRO', quantity: 180, price: 288.50, fee: 36.00, date: '2026-04-25' },
  { id: 't-tx-5', type: 'BUY', symbol: 'SYS', quantity: 120, price: 462.00, fee: 28.00, date: '2026-08-01' },
  { id: 'r-tx-4', type: 'BUY', symbol: 'ETH', quantity: 1.10, price: 2870.00, fee: 8.00, date: '2026-06-15' },
  { id: 'r-tx-3', type: 'SELL', symbol: 'HBL', quantity: 100, price: 147.20, fee: 18.00, date: '2026-08-12' },
];
const GROWTH_TX: Transaction[] = [
  { id: 'g-tx-1', type: 'BUY', symbol: 'ETH', quantity: 2.60, price: 3010.00, fee: 14.00, date: '2026-03-19' },
  { id: 'g-tx-2', type: 'BUY', symbol: 'SOL', quantity: 40.00, price: 96.50, fee: 10.00, date: '2026-04-02' },
  { id: 'g-tx-3', type: 'BUY', symbol: 'SYS', quantity: 120, price: 470.00, fee: 32.00, date: '2026-06-30' },
  { id: 'g-tx-4', type: 'BUY', symbol: 'SOL', quantity: 15.00, price: 128.60, fee: 6.00, date: '2026-08-12' },
];

// Default seed: one main portfolio plus five goal funds. Existing users with
// a legacy single ledger are migrated into "Main Portfolio" on first load.
const DEFAULT_FUNDS: Fund[] = [
  {
    id: 'fund-main',
    name: 'Main Portfolio',
    icon: 'briefcase',
    color: FUND_COLORS[0],
    tx: DEFAULT_TRANSACTIONS,
  },
  {
    id: 'fund-house',
    name: 'House Fund',
    icon: 'home',
    color: FUND_COLORS[1],
    goalUsd: 50000,
    tx: HOUSE_TX,
  },
  {
    id: 'fund-college',
    name: 'College Fund',
    icon: 'education',
    color: FUND_COLORS[2],
    goalUsd: 40000,
    tx: COLLEGE_TX,
  },
  {
    id: 'fund-travel',
    name: 'Travel Fund',
    icon: 'travel',
    color: FUND_COLORS[3],
    goalUsd: 8000,
    tx: TRAVEL_TX,
  },
  {
    id: 'fund-rainy',
    name: 'Rainy Day',
    icon: 'reserve',
    color: FUND_COLORS[4],
    goalUsd: 15000,
    tx: RAINY_TX,
  },
  {
    id: 'fund-growth',
    name: 'Growth Fund',
    icon: 'growth',
    color: FUND_COLORS[5],
    goalUsd: 100000,
    tx: GROWTH_TX,
  },
];

const FUNDS_KEY = 'portfolio_funds_guest';
const PROTECTED_FUND_IDS = new Set(['fund-main', 'fund-house', 'fund-college', 'fund-travel', 'fund-rainy', 'fund-growth']);

const makeFundId = () => 'fund-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

// Seed funds can be renamed but not deleted, so the demo book never breaks.
const isFundProtected = (id: string) => PROTECTED_FUND_IDS.has(id);

// ── Fund storage (load / merge-seeds / migrate / persist) ──────────────────
// Seed funds that ship with the app (House, College, Travel, …) are merged
// into any saved book that is missing them, so updates reach existing users
// without clobbering their edits.
function loadFunds(): { funds: Fund[]; activeId: string } {
  if (typeof window === 'undefined') return { funds: DEFAULT_FUNDS, activeId: DEFAULT_FUNDS[0].id };
  let saved: Fund[] | null = null;
  try {
    const raw = localStorage.getItem(FUNDS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Fund[];
      if (Array.isArray(parsed)) {
        saved = parsed
          .filter(f => f && typeof f.id === 'string' && Array.isArray(f.tx))
          .map(f => ({
            ...f,
            name: f.name || 'Unnamed Fund',
            icon: FUND_ICONS[f.icon] ? f.icon : 'briefcase',
            color: /^#[0-9a-fA-F]{6}$/.test(f.color ?? '') ? f.color : FUND_COLORS[0],
            goalUsd: typeof f.goalUsd === 'number' && f.goalUsd > 0 ? f.goalUsd : undefined,
          }));
      }
    }
  } catch { saved = null; }

  if (saved && saved.length > 0) {
    // Merge: add any seed fund the saved set doesn't have yet.
    const merged = [...saved];
    for (const seed of DEFAULT_FUNDS) {
      if (!merged.some(f => f.id === seed.id)) merged.push(seed);
    }
    // Keep Main Portfolio first, seeds in declared order, user funds after.
    merged.sort((a, b) => {
      const ia = DEFAULT_FUNDS.findIndex(f => f.id === a.id);
      const ib = DEFAULT_FUNDS.findIndex(f => f.id === b.id);
      return (ia === -1 ? DEFAULT_FUNDS.length : ia) - (ib === -1 ? DEFAULT_FUNDS.length : ib);
    });
    if (merged.length !== saved.length) saveFunds(merged);
    return { funds: merged, activeId: merged[0].id };
  }

  // Migration: existing single-portfolio users get their transactions kept
  // as "Main Portfolio" instead of being reset.
  try {
    const legacyTx = localStorage.getItem('portfolio_tx_guest');
    const migrated: Fund[] = legacyTx
      ? [{ ...DEFAULT_FUNDS[0], tx: JSON.parse(legacyTx) as Transaction[] }, ...DEFAULT_FUNDS.slice(1)]
      : DEFAULT_FUNDS;
    localStorage.setItem(FUNDS_KEY, JSON.stringify(migrated));
    return { funds: migrated, activeId: migrated[0].id };
  } catch {
    return { funds: DEFAULT_FUNDS, activeId: DEFAULT_FUNDS[0].id };
  }
}

function saveFunds(funds: Fund[]) {
  try {
    localStorage.setItem(FUNDS_KEY, JSON.stringify(funds));
  } catch { /* quota exceeded — in-memory state still holds */ }
}

// Demo metadata for quick-start suggestions in the New Fund dialog.
const STARTER_GOAL_FUNDS: Array<Pick<Fund, 'name' | 'icon' | 'color' | 'goalUsd'>> = [
  { name: 'House Fund', icon: 'home', color: FUND_COLORS[1], goalUsd: 50000 },
  { name: 'College Fund', icon: 'education', color: FUND_COLORS[2], goalUsd: 40000 },
  { name: 'Travel Fund', icon: 'travel', color: FUND_COLORS[3], goalUsd: 8000 },
  { name: 'Rainy Day', icon: 'reserve', color: FUND_COLORS[4], goalUsd: 15000 },
];

// ── Formatting helpers ──────────────────────────────────────────────────────
const fmtUsd = (n: number, dp = 2) =>
  `${n < 0 ? '-' : ''}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
const fmtK = (n: number) => {
  const a = Math.abs(n);
  if (a >= 1e6) return `${n < 0 ? '-' : ''}$${(a / 1e6).toFixed(2)}M`;
  if (a >= 1000) return `$${Math.round(n / 1000)}k`;
  return `$${Math.round(n)}`;
};
const fmtPct = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;

// ── CSV export helpers (client-side download) ───────────────────────────────
function downloadCsv(filename: string, rows: Array<Array<string | number>>) {
  const esc = (v: string | number) => {
    const s = String(v ?? '');
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = rows.map(r => r.map(esc).join(',')).join('\n');
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Price formatter that respects the asset's currency (PKR for PSX equities).
const fmtPrice = (n: number, currency?: 'USD' | 'PKR', dp = 2) => {
  const sym = currency === 'PKR' ? '₨' : '$';
  return `${n < 0 ? '-' : ''}${sym}${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
};

// ── oklch → hex conversion ─────────────────────────────────────────────────
// zrender (ECharts' renderer) cannot parse oklch() strings — its color math
// (modifyHSL / treemap calculateBorderColor) throws on them and crashes the
// chart, taking the whole screen down via the error boundary. CSS variables
// in globals.css are defined in oklch, so resolve + convert them to hex
// before any value reaches an ECharts option.
function oklchToHex(lch: string): string {
  const m = lch.match(/oklch\(\s*([\d.]+)%?\s+([\d.]+)%?\s+([\d.]+)/i);
  if (!m) return lch;
  const L = parseFloat(m[1]);
  const C = m[2].includes('%') ? (parseFloat(m[2]) / 100) * 0.4 : parseFloat(m[2]);
  const H = parseFloat(m[3]);
  const rad = (H * Math.PI) / 180;
  const a = C * Math.cos(rad);
  const b = C * Math.sin(rad);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.2914855480 * b;
  const l = l_ ** 3;
  const mm = m_ ** 3;
  const s = s_ ** 3;
  const r = 4.0767416621 * l - 3.3077115913 * mm + 0.2309699292 * s;
  const g = -1.2684380046 * l + 2.6097574011 * mm - 0.3413193965 * s;
  const bl = -0.0041960863 * l - 0.7034186147 * mm + 1.7076147010 * s;
  const gam = (c: number) => {
    c = Math.min(1, Math.max(0, c));
    return c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
  };
  const hx = (c: number) => Math.round(gam(c) * 255).toString(16).padStart(2, '0');
  return `#${hx(r)}${hx(g)}${hx(bl)}`;
}

function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  if (!v) return fallback;
  // Some browsers resolve oklch() to rgb() natively; only convert if needed.
  return v.startsWith('oklch(') ? oklchToHex(v) : v;
}

// ── Apache ECharts wrapper ──────────────────────────────────────────────────
interface EChartProps {
  option: EChartsOption;
  height?: number | string;
  className?: string;
  notMerge?: boolean;
}

// ── Dashboard customization (overview page) ─────────────────────────────────
// Each widget has a visibility flag, a width span on a 4-col grid, and an
// order. Persisted per-browser in localStorage; edited via an inline customize
// panel (drag to reorder, toggle visibility, pick size S/M/L/XL).

type WidgetId = 'total-value' | 'unreal-pl' | 'top-exposure' | 'fund-compare' | 'fund-cards';

interface WidgetLayout {
  id: WidgetId;
  visible: boolean;
  span: 1 | 2 | 3 | 4; // 4-col grid spans: S=1, M=2, L=3, XL=4
}

interface DashboardLayout {
  widgets: WidgetLayout[];
}

const WIDGET_META: Record<WidgetId, { label: string; desc: string; defaultSpan: WidgetLayout['span'] }> = {
  'total-value': { label: 'Total Value', desc: 'Aggregate value across all funds', defaultSpan: 1 },
  'unreal-pl': { label: 'Unrealized P/L', desc: 'Profit/loss vs cost basis', defaultSpan: 1 },
  'top-exposure': { label: 'Top Exposure', desc: 'Largest holdings across funds', defaultSpan: 1 },
  'fund-compare': { label: 'Fund Comparison', desc: 'Indexed NAV curves, zoomable', defaultSpan: 4 },
  'fund-cards': { label: 'Your Funds', desc: 'Fund cards + create button', defaultSpan: 4 },
};

const DEFAULT_LAYOUT: DashboardLayout = {
  widgets: [
    { id: 'total-value', visible: true, span: 1 },
    { id: 'unreal-pl', visible: true, span: 1 },
    { id: 'top-exposure', visible: true, span: 1 },
    { id: 'fund-compare', visible: true, span: 4 },
    { id: 'fund-cards', visible: true, span: 4 },
  ],
};

const DASHBOARD_LAYOUT_KEY = 'eclipse_portfolio_layout';

// ── Overview design templates: curated arrangements for the 5 widgets ────────
// preview = one bar per visual row; hidden widgets render as dashed slots.
const DASHBOARD_TEMPLATES: Array<{ id: string; name: string; desc: string; preview: Array<{ span: number; hidden?: boolean }>; build: () => DashboardLayout }> = [
  {
    id: 'default',
    name: 'Classic',
    desc: 'Stat trio + full-width charts',
    preview: [{ span: 1 }, { span: 4 }, { span: 4 }],
    build: () => DEFAULT_LAYOUT,
  },
  {
    id: 'grid',
    name: 'Grid',
    desc: 'Stat trio widened, side-by-side charts',
    preview: [{ span: 1 }, { span: 2 }, { span: 3 }, { span: 4 }],
    build: () => ({
      widgets: [
        { id: 'total-value', visible: true, span: 1 },
        { id: 'unreal-pl', visible: true, span: 1 },
        { id: 'top-exposure', visible: true, span: 2 },
        { id: 'fund-compare', visible: true, span: 3 },
        { id: 'fund-cards', visible: true, span: 4 },
      ],
    }),
  },
  {
    id: 'split',
    name: 'Split',
    desc: 'Charts on the left, stats in a right rail',
    preview: [{ span: 3 }, { span: 3 }, { span: 3 }, { span: 4 }],
    build: () => ({
      widgets: [
        { id: 'fund-compare', visible: true, span: 3 },
        { id: 'total-value', visible: true, span: 1 },
        { id: 'unreal-pl', visible: true, span: 1 },
        { id: 'top-exposure', visible: true, span: 2 },
        { id: 'fund-cards', visible: true, span: 4 },
      ],
    }),
  },
  {
    id: 'duo',
    name: 'Duo',
    desc: 'Two big halves — comparison vs funds',
    preview: [{ span: 2 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 4 }],
    build: () => ({
      widgets: [
        { id: 'total-value', visible: true, span: 2 },
        { id: 'unreal-pl', visible: true, span: 2 },
        { id: 'fund-compare', visible: true, span: 2 },
        { id: 'top-exposure', visible: true, span: 2 },
        { id: 'fund-cards', visible: true, span: 4 },
      ],
    }),
  },
  {
    id: 'focus',
    name: 'Focus',
    desc: 'Comparison hero, everything else compact',
    preview: [{ span: 4 }, { span: 1 }, { span: 4 }],
    build: () => ({
      widgets: [
        { id: 'fund-compare', visible: true, span: 4 },
        { id: 'total-value', visible: true, span: 1 },
        { id: 'unreal-pl', visible: true, span: 1 },
        { id: 'top-exposure', visible: true, span: 2 },
        { id: 'fund-cards', visible: true, span: 4 },
      ],
    }),
  },
];

function loadDashboardLayout(): DashboardLayout {
  if (typeof window === 'undefined') return DEFAULT_LAYOUT;
  try {
    const raw = window.localStorage.getItem(DASHBOARD_LAYOUT_KEY);
    if (!raw) return DEFAULT_LAYOUT;
    const parsed = JSON.parse(raw) as DashboardLayout;
    if (!Array.isArray(parsed.widgets)) return DEFAULT_LAYOUT;
    // Merge in any new widgets added later; drop unknown ids.
    const known = new Set(Object.keys(WIDGET_META) as WidgetId[]);
    const widgets = DEFAULT_LAYOUT.widgets
      .map((d) => parsed.widgets.find((w) => w.id === d.id) ?? d)
      .filter((w) => known.has(w.id));
    // Append widgets the user never had (e.g. after an app update).
    for (const d of DEFAULT_LAYOUT.widgets) {
      if (!widgets.some((w) => w.id === d.id)) widgets.push(d);
    }
    return { widgets };
  } catch {
    return DEFAULT_LAYOUT;
  }
}

const SPAN_CLASS: Record<WidgetLayout['span'], string> = {
  1: 'lg:col-span-1',
  2: 'lg:col-span-2',
  3: 'lg:col-span-3',
  4: 'lg:col-span-4',
};

const SPAN_LABEL: Record<WidgetLayout['span'], string> = { 1: 'S', 2: 'M', 3: 'L', 4: 'XL' };

/** Static class map for fund-widget shells — safe for Tailwind's scanner
 * (dynamic `lg:col-span-${n}` strings would be pruned at build time). */
const FUND_SPAN_CLASS: Record<FundWidgetLayout['span'], string> = {
  1: 'lg:col-span-1',
  2: 'lg:col-span-2',
  3: 'lg:col-span-3',
  4: 'lg:col-span-4',
};

interface FundWidgetShellProps {
  id: FundWidgetId;
  customizing: boolean;
  dragId: FundWidgetId | null;
  span: FundWidgetLayout['span'];
  onDragStart: (id: FundWidgetId) => void;
  onDrop: (target: FundWidgetId) => void;
  onResizeStart: (e: React.PointerEvent, id: FundWidgetId, mode: 'wider' | 'narrower' | 'taller' | 'shorter' | 'corner') => void;
  onSelectWidget: (id: FundWidgetId) => void;
  heightStyle?: React.CSSProperties;
  children: React.ReactNode;
}

/** Wraps a fund-page widget. In edit mode the whole card is draggable,
 * click-to-select enables keyboard nudge/resize (arrows move order, Shift+
 * arrows / +/- resize, X hides), and edge/corner handles appear on hover for
 * live width & height resizing. The grid span lives on this outer wrapper so
 * inner height styles never affect grid sizing. */
function FundWidgetShell({
  id, customizing, dragId, span, onDragStart, onDrop, onResizeStart, onSelectWidget, heightStyle, children,
}: FundWidgetShellProps) {
  const spanCls = FUND_SPAN_CLASS[span];
  const [dropHint, setDropHint] = useState(false);
  if (!customizing) {
    return <div className={spanCls} style={heightStyle}>{children}</div>;
  }
  return (
    <div
      className={`${spanCls} relative group/shell transition-all duration-150 ${dragId === id ? 'opacity-50 scale-[0.98]' : ''}`}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = 'move';
        // Use the card itself as the drag ghost so the preview matches what
        // the user grabbed (default ghost is the raw element at full size).
        try { e.dataTransfer.setDragImage(document.querySelector(`[data-widget-card="${id}"]`) as HTMLElement, 80, 24); } catch { /* default ghost */ }
        onDragStart(id);
      }}
      onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }}
      onDragEnter={(e) => { e.preventDefault(); if (dragId && dragId !== id) setDropHint(true); }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDropHint(false); }}
      onDrop={(e) => { e.preventDefault(); setDropHint(false); onDrop(id); }}
      onDragEnd={() => setDropHint(false)}
    >
      {/* Card itself is the drag surface — subtle edit outline + drop-target ring */}
      <div
        className={`rounded-2xl ring-1 transition-all duration-150 cursor-grab active:cursor-grabbing ${
          dropHint
            ? 'ring-2 ring-zinc-300/90 dark:ring-zinc-300/80 ring-offset-2 ring-offset-transparent shadow-[0_0_0_5px_rgba(161,161,170,0.18)] scale-[1.01]'
            : 'ring-zinc-500/25 dark:ring-zinc-600/30'
        }`}
        style={heightStyle}
        data-widget-card={id}
        onClick={(e) => { e.stopPropagation(); onSelectWidget(id); }}
      >
        {children}
      </div>
      {/* Floating drag pill — top edge, compact; hidden while this card is dragged */}
      <span
        className={`absolute -top-2 left-1/2 -translate-x-1/2 z-20 flex items-center gap-0.5 px-1.5 py-[1px] rounded-full ${EDIT_HANDLE} text-[7.5px] font-mono font-bold text-zinc-300 tracking-wider uppercase select-none transition-opacity ${dragId === id ? 'opacity-0' : 'opacity-70 group-hover/shell:opacity-100'}`}
      >
        <GripVertical className="w-2 h-2" /> {id}
      </span>
      {/* Corner resize handle (bottom-right) — diagonal drag adjusts both axes */}
      <div
        onPointerDown={(e) => onResizeStart(e, id, 'corner')}
        className={`absolute -bottom-1 -right-1 w-3.5 h-3.5 cursor-nwse-resize rounded-full ${EDIT_HANDLE} opacity-60 group-hover/shell:opacity-100 transition-all z-30 flex items-center justify-center`}
        title="Drag to resize (width + height)"
      >
        <svg viewBox="0 0 10 10" className="w-2 h-2 text-zinc-400">
          <path d="M9 1L1 9M9 5L5 9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" fill="none" />
        </svg>
      </div>
      {/* Right/left edges — slim frosted grey bars, dim until hovered */}
      <div
        onPointerDown={(e) => { e.stopPropagation(); onResizeStart(e, id, 'wider'); }}
        className={`absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-10 rounded-full cursor-ew-resize ${EDIT_HANDLE} opacity-40 group-hover/shell:opacity-100 transition-all z-20`}
        title="Drag right to widen"
      />
      <div
        onPointerDown={(e) => { e.stopPropagation(); onResizeStart(e, id, 'narrower'); }}
        className={`absolute -right-1 top-1/2 -translate-y-1/2 w-2 h-10 rounded-full cursor-ew-resize ${EDIT_HANDLE} opacity-40 group-hover/shell:opacity-100 transition-all z-20`}
        title="Drag left to narrow"
      />
      {/* Height handles — top/bottom edges */}
      <div
        onPointerDown={(e) => { e.stopPropagation(); onResizeStart(e, id, 'taller'); }}
        className={`absolute -bottom-1 left-1/2 -translate-x-1/2 h-2 w-10 rounded-full cursor-ns-resize ${EDIT_HANDLE} opacity-40 group-hover/shell:opacity-100 transition-all z-20`}
        title="Drag down to make taller"
      />
      <div
        onPointerDown={(e) => { e.stopPropagation(); onResizeStart(e, id, 'shorter'); }}
        className={`absolute -top-1 left-1/2 -translate-x-1/2 h-2 w-10 rounded-full cursor-ns-resize ${EDIT_HANDLE} opacity-40 group-hover/shell:opacity-100 transition-all z-20`}
        title="Drag up to make shorter"
      />
    </div>
  );
}

// ── Fund-page widget customization ──────────────────────────────────────────
// Same mechanism as the overview: each analytics section is a widget the user
// can show/hide, resize, and reorder with the mouse (drag & drop), persisted
// in localStorage per fund-agnostic layout (shared across funds).

type FundWidgetId =
  | 'kpi-board' | 'performance' | 'allocation' | 'ai-insights'
  | 'risk-metrics' | 'health' | 'risk-radar' | 'exposure-map'
  | 'changes' | 'rebalance' | 'holdings' | 'watchlist' | 'transactions'
  | 'stress' | 'correlation' | 'tools' | 'monte-carlo' | 'cost-basis';

interface FundWidgetLayout {
  id: FundWidgetId;
  visible: boolean;
  span: 1 | 2 | 3 | 4;
  /** Extra height in 40px steps (0 = natural). Applied via min-height. */
  height: number;
}

const FUND_WIDGET_META: Record<FundWidgetId, { label: string; desc: string; defaultSpan: FundWidgetLayout['span'] }> = {
  'kpi-board': { label: 'KPI Board', desc: 'NAV, P/L, cash tiles', defaultSpan: 4 },
  'performance': { label: 'Performance', desc: 'NAV curve vs benchmark', defaultSpan: 3 },
  'allocation': { label: 'Allocation', desc: 'Holdings donut + list', defaultSpan: 2 },
  'ai-insights': { label: 'AI Insights', desc: 'Position signals + discuss', defaultSpan: 2 },
  'risk-metrics': { label: 'Risk Metrics', desc: 'Beta, vol, Sharpe, drawdown', defaultSpan: 3 },
  'health': { label: 'Portfolio Health', desc: 'Score gauge + breakdown', defaultSpan: 2 },
  'risk-radar': { label: 'Risk Radar', desc: 'Five-dimension posture chart', defaultSpan: 2 },
  'exposure-map': { label: 'Exposure Map', desc: 'Category treemap + brief', defaultSpan: 3 },
  'changes': { label: 'What Changed', desc: 'Recent portfolio shifts', defaultSpan: 4 },
  'rebalance': { label: 'Rebalancing', desc: 'Drift vs model targets', defaultSpan: 4 },
  'holdings': { label: 'Active Holdings', desc: 'Full holdings table', defaultSpan: 4 },
  'watchlist': { label: 'Watchlist', desc: 'Starred positions', defaultSpan: 2 },
  'transactions': { label: 'Transactions', desc: 'Recent trade ledger', defaultSpan: 3 },
  'stress': { label: 'Stress Test', desc: 'Scenario shock model', defaultSpan: 3 },
  'correlation': { label: 'Correlation', desc: 'Pearson matrix heatmap', defaultSpan: 2 },
  'tools': { label: 'Trading Tools', desc: 'What-if, sizing, alerts', defaultSpan: 4 },
  'monte-carlo': { label: 'Monte Carlo', desc: 'Projection + attribution', defaultSpan: 4 },
  'cost-basis': { label: 'Cost Basis & DCA', desc: 'Entry vs live spread', defaultSpan: 4 },
};

const DEFAULT_FUND_LAYOUT: { widgets: FundWidgetLayout[] } = {
  widgets: Object.keys(FUND_WIDGET_META).map((id) => ({
    id: id as FundWidgetId,
    visible: true,
    span: FUND_WIDGET_META[id as FundWidgetId].defaultSpan,
    height: 0,
  })),
};

// ── Design templates: curated full-page layouts, one click to apply ──────────
// preview = one bar per visual row (span 1–4); hidden widgets render dashed.
// Every build() arranges rows so each visual row sums to exactly 4 columns —
// dense grid packing then composes them cleanly with no orphan gaps.
const FUND_TEMPLATES: Array<{ id: string; name: string; desc: string; preview: Array<{ span: number; hidden?: boolean }>; build: () => FundWidgetLayout[] }> = [
  {
    id: 'default',
    name: 'Classic',
    desc: 'KPIs on top, charts below, tables last',
    preview: [{ span: 4 }, { span: 3 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 4 }],
    build: () => DEFAULT_FUND_LAYOUT.widgets.map((w) => ({ ...w })),
  },
  {
    id: 'trader',
    name: 'Trader',
    desc: 'Performance & risk up top, tables at the bottom',
    preview: [{ span: 4 }, { span: 3 }, { span: 1 }, { span: 2 }, { span: 2 }, { span: 4 }],
    build: () => [
      { id: 'kpi-board', span: 4, height: 0 },
      { id: 'performance', span: 3, height: 0 },
      { id: 'risk-radar', span: 1, height: 1 },
      { id: 'stress', span: 2, height: 0 },
      { id: 'correlation', span: 2, height: 0 },
      { id: 'risk-metrics', span: 4, height: 0 },
      { id: 'holdings', span: 2, height: 0 },
      { id: 'watchlist', span: 2, height: 0 },
      { id: 'tools', span: 4, height: 0 },
      { id: 'allocation', span: 2, height: 0 },
      { id: 'health', span: 2, height: 0 },
      { id: 'exposure-map', span: 4, height: 0 },
      { id: 'changes', span: 2, height: 0 },
      { id: 'transactions', span: 2, height: 0 },
      { id: 'rebalance', span: 4, height: 0 },
      { id: 'cost-basis', span: 4, height: 0 },
      { id: 'monte-carlo', span: 4, height: 0 },
      { id: 'ai-insights', span: 4, height: 0 },
    ].map((w) => ({ id: w.id as FundWidgetId, visible: true, span: w.span as FundWidgetLayout['span'], height: w.height })),
  },
  {
    id: 'analyst',
    name: 'Analyst',
    desc: 'Big charts first — performance, exposure, Monte Carlo',
    preview: [{ span: 4 }, { span: 3 }, { span: 3 }, { span: 2 }, { span: 2 }, { span: 4 }],
    build: () => [
      { id: 'kpi-board', span: 4, height: 0 },
      { id: 'performance', span: 3, height: 0 },
      { id: 'risk-radar', span: 1, height: 0 },
      { id: 'exposure-map', span: 3, height: 0 },
      { id: 'watchlist', span: 1, height: 0 },
      { id: 'monte-carlo', span: 2, height: 1 },
      { id: 'stress', span: 2, height: 1 },
      { id: 'allocation', span: 2, height: 0 },
      { id: 'health', span: 2, height: 0 },
      { id: 'correlation', span: 2, height: 0 },
      { id: 'cost-basis', span: 2, height: 0 },
      { id: 'risk-metrics', span: 4, height: 0 },
      { id: 'holdings', span: 4, height: 0 },
      { id: 'transactions', span: 2, height: 0 },
      { id: 'rebalance', span: 2, height: 0 },
      { id: 'changes', span: 4, height: 0 },
      { id: 'tools', span: 4, height: 0 },
      { id: 'ai-insights', span: 4, height: 0 },
    ].map((w) => ({ id: w.id as FundWidgetId, visible: true, span: w.span as FundWidgetLayout['span'], height: w.height })),
  },
  {
    id: 'mosaic',
    name: 'Mosaic',
    desc: 'Dense mixed grid — two columns of small cards beside charts',
    preview: [{ span: 4 }, { span: 2 }, { span: 2 }, { span: 1 }, { span: 1 }, { span: 2 }, { span: 3 }],
    build: () => [
      { id: 'kpi-board', span: 4, height: 0 },
      { id: 'performance', span: 2, height: 1 },
      { id: 'allocation', span: 2, height: 1 },
      { id: 'risk-radar', span: 1, height: 0 },
      { id: 'correlation', span: 1, height: 0 },
      { id: 'health', span: 2, height: 0 },
      { id: 'exposure-map', span: 3, height: 0 },
      { id: 'watchlist', span: 1, height: 0 },
      { id: 'monte-carlo', span: 2, height: 2 },
      { id: 'stress', span: 1, height: 2 },
      { id: 'cost-basis', span: 1, height: 2 },
      { id: 'risk-metrics', span: 3, height: 0 },
      { id: 'ai-insights', span: 1, height: 0 },
      { id: 'changes', span: 2, height: 0 },
      { id: 'rebalance', span: 2, height: 0 },
      { id: 'holdings', span: 4, height: 0 },
      { id: 'transactions', span: 2, height: 0 },
      { id: 'tools', span: 2, height: 0 },
    ].map((w) => ({ id: w.id as FundWidgetId, visible: true, span: w.span as FundWidgetLayout['span'], height: w.height })),
  },
  {
    id: 'split',
    name: 'Split',
    desc: 'Left rail of small cards + wide chart column',
    preview: [{ span: 4 }, { span: 1 }, { span: 1 }, { span: 1 }, { span: 1 }, { span: 3 }, { span: 3 }],
    build: () => [
      { id: 'kpi-board', span: 4, height: 0 },
      { id: 'risk-radar', span: 1, height: 1 },
      { id: 'health', span: 1, height: 1 },
      { id: 'correlation', span: 1, height: 1 },
      { id: 'watchlist', span: 1, height: 1 },
      { id: 'performance', span: 3, height: 1 },
      { id: 'exposure-map', span: 3, height: 0 },
      { id: 'allocation', span: 2, height: 0 },
      { id: 'ai-insights', span: 2, height: 0 },
      { id: 'monte-carlo', span: 4, height: 0 },
      { id: 'stress', span: 2, height: 0 },
      { id: 'risk-metrics', span: 2, height: 0 },
      { id: 'holdings', span: 4, height: 0 },
      { id: 'transactions', span: 2, height: 0 },
      { id: 'rebalance', span: 2, height: 0 },
      { id: 'changes', span: 4, height: 0 },
      { id: 'cost-basis', span: 4, height: 0 },
      { id: 'tools', span: 4, height: 0 },
    ].map((w) => ({ id: w.id as FundWidgetId, visible: true, span: w.span as FundWidgetLayout['span'], height: w.height })),
  },
  {
    id: 'rows',
    name: 'Rows',
    desc: 'Alternating wide/narrow — magazine-style rhythm',
    preview: [{ span: 4 }, { span: 1 }, { span: 3 }, { span: 3 }, { span: 1 }, { span: 3 }, { span: 2 }],
    build: () => [
      { id: 'kpi-board', span: 4, height: 0 },
      { id: 'performance', span: 1, height: 1 },
      { id: 'exposure-map', span: 3, height: 1 },
      { id: 'allocation', span: 3, height: 0 },
      { id: 'risk-radar', span: 1, height: 0 },
      { id: 'monte-carlo', span: 1, height: 1 },
      { id: 'ai-insights', span: 3, height: 1 },
      { id: 'risk-metrics', span: 2, height: 0 },
      { id: 'health', span: 2, height: 0 },
      { id: 'stress', span: 2, height: 0 },
      { id: 'correlation', span: 2, height: 0 },
      { id: 'holdings', span: 4, height: 0 },
      { id: 'watchlist', span: 2, height: 0 },
      { id: 'transactions', span: 2, height: 0 },
      { id: 'rebalance', span: 4, height: 0 },
      { id: 'changes', span: 2, height: 0 },
      { id: 'cost-basis', span: 2, height: 0 },
      { id: 'tools', span: 4, height: 0 },
    ].map((w) => ({ id: w.id as FundWidgetId, visible: true, span: w.span as FundWidgetLayout['span'], height: w.height })),
  },
  {
    id: 'compact',
    name: 'Compact',
    desc: 'Everything half-width — dense two-column dashboard',
    preview: [{ span: 4 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 2 }, { span: 2 }],
    build: () => ['kpi-board', 'performance', 'allocation', 'health', 'holdings', 'watchlist', 'transactions', 'risk-metrics', 'risk-radar', 'correlation', 'stress', 'exposure-map', 'ai-insights', 'monte-carlo', 'rebalance', 'changes', 'cost-basis', 'tools']
      .map((id) => ({ id: id as FundWidgetId, visible: true, span: 2 as FundWidgetLayout['span'], height: 0 })),
  },
  {
    id: 'minimal',
    name: 'Minimal',
    desc: 'Just value, performance & holdings',
    preview: [{ span: 4 }, { span: 4 }, { span: 4 }, { span: 1, hidden: true }],
    build: () => [
      { id: 'kpi-board' as FundWidgetId, visible: true, span: 4 as FundWidgetLayout['span'], height: 0 },
      { id: 'performance' as FundWidgetId, visible: true, span: 4 as FundWidgetLayout['span'], height: 0 },
      { id: 'holdings' as FundWidgetId, visible: true, span: 4 as FundWidgetLayout['span'], height: 0 },
      ...(['allocation', 'ai-insights', 'risk-metrics', 'health', 'risk-radar', 'exposure-map', 'changes', 'rebalance', 'watchlist', 'transactions', 'stress', 'correlation', 'tools', 'monte-carlo', 'cost-basis'] as FundWidgetId[])
        .map((id) => ({ id, visible: false, span: FUND_WIDGET_META[id].defaultSpan, height: 0 })),
    ],
  },
  {
    id: 'focus',
    name: 'Focus',
    desc: 'Hero chart + small risk cluster, tables tucked at bottom',
    preview: [{ span: 4 }, { span: 4 }, { span: 2 }, { span: 1 }, { span: 1 }, { span: 2 }, { span: 2 }],
    build: () => [
      { id: 'kpi-board', span: 4, height: 0 },
      { id: 'performance', span: 4, height: 0 },
      { id: 'exposure-map', span: 2, height: 0 },
      { id: 'allocation', span: 2, height: 0 },
      { id: 'risk-radar', span: 1, height: 0 },
      { id: 'correlation', span: 1, height: 0 },
      { id: 'watchlist', span: 1, height: 0 },
      { id: 'health', span: 1, height: 0 },
      { id: 'monte-carlo', span: 2, height: 1 },
      { id: 'stress', span: 2, height: 1 },
      { id: 'risk-metrics', span: 2, height: 0 },
      { id: 'ai-insights', span: 2, height: 0 },
      { id: 'holdings', span: 4, height: 0 },
      { id: 'transactions', span: 2, height: 0 },
      { id: 'rebalance', span: 2, height: 0 },
      { id: 'changes', span: 4, height: 0 },
      { id: 'cost-basis', span: 4, height: 0 },
      { id: 'tools', span: 4, height: 0 },
    ].map((w) => ({ id: w.id as FundWidgetId, visible: true, span: w.span as FundWidgetLayout['span'], height: w.height })),
  },
];

const FUND_LAYOUT_KEY = 'eclipse_fund_layout';

function loadFundLayout(): { widgets: FundWidgetLayout[] } {
  if (typeof window === 'undefined') return DEFAULT_FUND_LAYOUT;
  try {
    const raw = window.localStorage.getItem(FUND_LAYOUT_KEY);
    if (!raw) return DEFAULT_FUND_LAYOUT;
    const parsed = JSON.parse(raw) as { widgets: FundWidgetLayout[] };
    if (!Array.isArray(parsed.widgets)) return DEFAULT_FUND_LAYOUT;
    const known = new Set(Object.keys(FUND_WIDGET_META) as FundWidgetId[]);
    const widgets = DEFAULT_FUND_LAYOUT.widgets
      .map((d) => {
        const saved = parsed.widgets.find((w) => w.id === d.id);
        return saved ? { ...d, ...saved, height: saved.height ?? 0 } : d;
      })
      .filter((w) => known.has(w.id));
    for (const d of DEFAULT_FUND_LAYOUT.widgets) {
      if (!widgets.some((w) => w.id === d.id)) widgets.push(d);
    }
    return { widgets };
  } catch {
    return DEFAULT_FUND_LAYOUT;
  }
}

function EChart({ option, height = 300, className, notMerge = true }: EChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, notMerge);
  }, [option, notMerge]);

  return <div ref={ref} className={className} style={{ width: '100%', height }} />;
}

// Tiny inline sparkline fed with REAL close data; renders flat-line empty
// state when the series is unavailable (no fabricated paths).
function Sparkline({ data, up }: { data: number[]; up: boolean }) {
  if (data.length < 2) {
    return (
      <div className="text-[10px] font-mono text-muted-foreground/60 w-[140px] text-center">
        — no series —
      </div>
    );
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const W = 140, H = 40, PAD = 3;
  const d = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * W;
      const y = PAD + (1 - (v - min) / span) * (H - PAD * 2);
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      <path d={d} fill="none" stroke={up ? UP : DOWN} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

// ── Overview: cross-fund dashboard with quick-glance cards ─────────────────
// Each card is a real_portfolio engine run over that fund's ledger (same
// FIFO/LIFO math as the fund view), so headline numbers always agree with
// what the user sees after clicking through.
interface OverviewViewProps {
  funds: Fund[];
  usdPkr: number;
  liveAssets: LiveAsset[];
  onOpenFund: (id: string) => void;
  onEditFund: (fund: Fund) => void;
  onDeleteFund: (id: string) => void;
  onCreateFund: () => void;
  onAnalyzeTicker: (ticker: string) => void;
  displayFx: Currency;
  fxRates: Record<string, number>;
  hasFx: boolean;
  fmtD: (usd: number, dp?: number) => string;
  fmtDK: (usd: number) => string;
  dispLabel: string;
  fundHistory: { closes: Record<string, number[]>; dates: Record<string, string[]> };
}

function FundCard({
  fund, usdPkr, liveAssets, onOpen, onEdit, onDelete, onAnalyzeTicker, canDelete, fmtD, fmtDK,
}: {
  fund: Fund;
  usdPkr: number;
  liveAssets: LiveAsset[];
  onOpen: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onAnalyzeTicker: (t: string) => void;
  canDelete: boolean;
  fmtD: (usd: number, dp?: number) => string;
  fmtDK: (usd: number) => string;
}) {
  const liveForEngine = useMemo(
    () => liveAssets.map(a => ({ ...a, fxToUsd: a.currency === 'PKR' ? 1 / usdPkr : 1 })),
    [liveAssets, usdPkr]
  );
  const s = usePortfolioEngine(fund.tx, liveForEngine, 'FIFO');
  const Icon = FUND_ICONS[fund.icon] ?? Briefcase;
  const up = s.dailyChangeValue >= 0;
  const goalPct = fund.goalUsd && fund.goalUsd > 0 ? Math.min(100, (s.totalValue / fund.goalUsd) * 100) : null;
  const topHoldings = s.holdings.slice(0, 3);
  const allocationMax = 100;

  return (
    <div
      onClick={onOpen}
      className={`${PANEL} ${up
        ? 'bg-gradient-to-br from-emerald-500/[0.03] via-[#0f0f0f]/60 to-[#0f0f0f]/30 dark:from-emerald-500/[0.03]'
        : 'bg-gradient-to-br from-rose-500/[0.03] via-[#0f0f0f]/60 to-[#0f0f0f]/30 dark:from-rose-500/[0.03]'} p-5 relative overflow-hidden group cursor-pointer hover:-translate-y-0.5 transition-all duration-300 hover:shadow-xl flex flex-col`}
      style={{ ['--fund-accent' as string]: fund.color }}
    >
      {/* Ambient glow — profit green / loss red, echoes market-news sentiment glows */}
      <div
        className={`absolute top-0 right-0 -translate-y-1/2 translate-x-1/2 w-48 h-48 rounded-full blur-[60px] pointer-events-none opacity-20 group-hover:opacity-30 transition-all duration-300 ${
          up ? 'bg-emerald-500 shadow-[0_0_40px_rgba(52,211,153,0.35)]' : 'bg-rose-500 shadow-[0_0_40px_rgba(251,113,133,0.35)]'
        }`}
      />

      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <span className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0" style={{ background: `${fund.color}1f`, border: `1px solid ${fund.color}45` }}>
            <Icon className="w-5 h-5" style={{ color: fund.color }} />
          </span>
          <div className="min-w-0">
            <h3 className="font-serif font-semibold text-base truncate">{fund.name}</h3>
            <span className="text-[10px] font-mono text-muted-foreground">
              {s.holdings.length} holding{s.holdings.length === 1 ? '' : 's'} · {fund.tx.length} tx
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); onEdit(); }}
            title="Edit fund"
            className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 cursor-pointer"
          >
            <SquarePen className="w-3.5 h-3.5" />
          </button>
          {canDelete && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              title="Delete fund"
              className="p-1.5 rounded-lg text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10 cursor-pointer"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      <div className="mb-3">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="text-2xl font-mono font-bold tracking-tight">{fmtD(s.totalValue)}</span>
          <span className={`text-xs font-semibold ${up ? 'text-emerald-400' : 'text-rose-400'}`}>
            {up ? <ArrowUpRight className="inline w-3.5 h-3.5" /> : <ArrowDownRight className="inline w-3.5 h-3.5" />}
            {fmtPct(s.dailyChangePercent)}
          </span>
        </div>
        <div className="text-[11px] text-muted-foreground mt-0.5">
          Today {fmtD(s.dailyChangeValue)} · ROI <span className={s.roiPercent >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{fmtPct(s.roiPercent)}</span> all-time
        </div>
      </div>

      {/* Goal progress */}
      {goalPct !== null && (
        <div className="mb-4">
          <div className="flex justify-between text-[10px] font-mono text-muted-foreground mb-1">
            <span>Goal {fmtD(fund.goalUsd!, 0)}</span>
            <span className={goalPct >= 100 ? 'text-emerald-400' : ''}>{goalPct.toFixed(0)}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-border/25 overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{ width: `${Math.max(2, goalPct)}%`, background: goalPct >= 100 ? '#34d399' : fund.color }}
            />
          </div>
        </div>
      )}

      {/* Mini allocation bars */}
      <div className="space-y-1.5 mb-4">
        {topHoldings.length > 0 ? topHoldings.map((h, i) => (
          <div key={h.symbol} className="flex items-center gap-2 text-[11px] font-mono">
            <span className="w-12 font-bold truncate">{h.symbol}</span>
            <div className="flex-1 h-1.5 rounded-full bg-border/20 overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(h.allocation / allocationMax) * 100}%`,
                  background: i === 0 ? fund.color : `${fund.color}77`,
                }}
              />
            </div>
            <span className="text-muted-foreground w-9 text-right">{h.allocation.toFixed(0)}%</span>
          </div>
        )) : (
          <p className="text-[11px] text-muted-foreground font-mono py-1">No holdings yet — click to add transactions.</p>
        )}
        {s.holdings.length > 3 && (
          <div className="text-[10px] text-muted-foreground font-mono text-right">+{s.holdings.length - 3} more…</div>
        )}
      </div>

      <div className="mt-auto pt-3 border-t border-border/20 flex items-center justify-between">
        <button
          onClick={(e) => { e.stopPropagation(); onAnalyzeTicker('PORTFOLIO'); }}
          className="text-[11px] font-mono text-primary hover:underline cursor-pointer"
        >
          Discuss with AI →
        </button>
        <span className="text-[11px] font-mono text-muted-foreground group-hover:text-primary transition-colors flex items-center gap-1">
          Open fund <ArrowUpRight className="w-3.5 h-3.5" />
        </span>
      </div>
    </div>
  );
}

/** Mini 4-column layout preview — renders each template's widget arrangement
 * as a tiny stacked-bar diagram so the user can see the layout before
 * applying. Hidden widgets render as hollow dashed slots. Capped at 7 rows;
 * rows flex to fill the fixed-height container so nothing overflows. */
function TemplateMiniGrid({ rows, cols = 4 }: { rows: Array<{ span: number; hidden?: boolean }>; cols?: number }) {
  const visible = rows.slice(0, 7);
  return (
    <div className="flex flex-col gap-[3px] h-9 w-full overflow-hidden" aria-hidden>
      {visible.map((r, i) => (
        <div key={i} className="flex gap-[3px] flex-1 min-h-0">
          {r.span >= cols ? (
            <div className={`flex-1 rounded-[3px] ${r.hidden ? 'border border-dashed border-zinc-500/40 dark:border-zinc-400/30' : 'bg-zinc-400/60 dark:bg-zinc-500/40'}`} />
          ) : (
            <>
              {Array.from({ length: r.span }).map((_, j) => (
                <div key={j} className={`flex-1 rounded-[3px] ${r.hidden ? 'border border-dashed border-zinc-500/40 dark:border-zinc-400/30' : 'bg-zinc-400/60 dark:bg-zinc-500/40'}`} />
              ))}
              {Array.from({ length: cols - r.span }).map((_, j) => (
                <div key={`e${j}`} className="flex-1 rounded-[3px] bg-zinc-500/10 dark:bg-zinc-400/10" />
              ))}
            </>
          )}
        </div>
      ))}
    </div>
  );
}

function OverviewView({
  funds, usdPkr, liveAssets, onOpenFund, onEditFund, onDeleteFund, onCreateFund, onAnalyzeTicker,
  displayFx, fxRates, hasFx, fmtD, fmtDK, dispLabel, fundHistory,
}: OverviewViewProps) {
  // Aggregate KPIs across every fund (each ran through the same engine).
  const agg = useMemo(() => {
    const liveForEngine = liveAssets.map(a => ({ ...a, fxToUsd: a.currency === 'PKR' ? 1 / usdPkr : 1 }));
    let value = 0, cost = 0, day = 0, unreal = 0;
    const symbolAlloc = new Map<string, { value: number; color?: string }>();
    for (const f of funds) {
      const s = computePortfolioStats(f.tx, liveForEngine, 'FIFO');
      value += s.totalValue;
      cost += s.costBasis;
      day += s.dailyChangeValue;
      unreal += s.unrealizedPnL;
      for (const h of s.holdings) {
        const cur = symbolAlloc.get(h.symbol);
        symbolAlloc.set(h.symbol, { value: (cur?.value ?? 0) + h.valueUsd, color: cur?.color });
      }
    }
    const roi = cost > 0 ? (unreal / cost) * 100 : 0;
    const dayPct = value - day > 0 ? (day / (value - day)) * 100 : 0;
    const top = [...symbolAlloc.entries()].map(([symbol, d]) => ({ symbol, value: d.value }))
      .sort((a, b) => b.value - a.value);
    const total = value || 1;
    return { value, cost, day, unreal, roi, dayPct, top: top.map(t => ({ ...t, pct: (t.value / total) * 100 })) };
  }, [funds, liveAssets, usdPkr]);

  // ── Dashboard customization state ────────────────────────────────────────
  const [layout, setLayout] = useState<DashboardLayout>(DEFAULT_LAYOUT);
  const [customizing, setCustomizing] = useState(false);
  const [dragWidget, setDragWidget] = useState<WidgetId | null>(null);
  useEffect(() => {
    setLayout(loadDashboardLayout());
  }, []);

  const updateLayout = useCallback((next: DashboardLayout) => {
    setLayout(next);
    try { window.localStorage.setItem(DASHBOARD_LAYOUT_KEY, JSON.stringify(next)); } catch { /* private mode */ }
  }, []);

  const patchWidget = useCallback((id: WidgetId, patch: Partial<WidgetLayout>) => {
    setLayout((prev) => {
      const widgets = prev.widgets.map((w) => (w.id === id ? { ...w, ...patch } : w));
      const next = { widgets };
      try { window.localStorage.setItem(DASHBOARD_LAYOUT_KEY, JSON.stringify(next)); } catch { /* private mode */ }
      return next;
    });
  }, []);

  const moveWidget = useCallback((from: WidgetId, to: WidgetId) => {
    if (from === to) return;
    setLayout((prev) => {
      const widgets = [...prev.widgets];
      const fromIdx = widgets.findIndex((w) => w.id === from);
      const toIdx = widgets.findIndex((w) => w.id === to);
      if (fromIdx === -1 || toIdx === -1) return prev;
      const [moved] = widgets.splice(fromIdx, 1);
      widgets.splice(toIdx, 0, moved);
      const next = { widgets };
      try { window.localStorage.setItem(DASHBOARD_LAYOUT_KEY, JSON.stringify(next)); } catch { /* private mode */ }
      return next;
    });
  }, []);

  const resetLayout = useCallback(() => {
    try { window.localStorage.removeItem(DASHBOARD_LAYOUT_KEY); } catch { /* ignore */ }
    setLayout(DEFAULT_LAYOUT);
  }, []);

  // ── Fund-vs-fund comparison: indexed NAV curves from real close series ─────
  const [showOnboarding, setShowOnboarding] = useState(false);
  useEffect(() => {
    try { setShowOnboarding(!localStorage.getItem('eclipse_onboarded')); } catch { setShowOnboarding(false); }
  }, []);
  const fundCompare = useMemo(() => {
    const series: Array<{ id: string; name: string; color: string; pct: number; data: number[]; firstDates: string[] }> = [];
    for (const f of funds) {
      const syms = [...new Set(f.tx.filter(t => t.type !== 'DIVIDEND').map(t => t.symbol))];
      const statsForFund = computePortfolioStats(f.tx, liveAssets.map(a => ({ ...a, fxToUsd: a.currency === 'PKR' ? 1 / usdPkr : 1 })), 'FIFO');
      const valueBySym = new Map<string, number>();
      for (const h of statsForFund.holdings) valueBySym.set(h.symbol, h.valueUsd);
      // Weights from current value; NAV path = Σ w_i × (close_i,t / close_i,0)
      const usable = syms.filter(s => (fundHistory.closes[s]?.length ?? 0) >= 2 && (valueBySym.get(s) ?? 0) > 0);
      if (usable.length === 0) continue;
      const totalVal = usable.reduce((a, s) => a + (valueBySym.get(s) ?? 0), 0);
      // ── Date-aligned aggregation (NOT min-length clipping) ──
      // A shorter series for one symbol (stale cache, recent listing) used to
      // clip the whole fund curve to its length, freezing the chart mid-window.
      // Instead: union of dates, each symbol forward/reverse-filled into it.
      const dateSet = new Set<string>();
      for (const s of usable) (fundHistory.dates[s] ?? []).forEach(d => dateSet.add(d));
      const unionDates = [...dateSet].sort();
      if (unionDates.length < 2) continue;
      const nav: number[] = [];
      for (const date of unionDates) {
        let v = 0;
        for (const sym of usable) {
          const ds = fundHistory.dates[sym];
          const cs = fundHistory.closes[sym];
          let idx = ds.indexOf(date);
          if (idx === -1) {
            if (date < ds[0]) idx = 0;
            else if (date > ds[ds.length - 1]) idx = ds.length - 1;
            else {
              let lo = 0;
              while (lo < ds.length - 1 && ds[lo + 1] <= date) lo++;
              idx = lo;
            }
          }
          const w = (valueBySym.get(sym) ?? 0) / totalVal;
          v += w * (cs[idx] / cs[0]);
        }
        nav.push(v);
      }
      if (nav.length < 2) continue;
      series.push({
        id: f.id,
        name: f.name,
        color: f.color,
        pct: ((nav[nav.length - 1] / nav[0]) - 1) * 100,
        data: nav.map(v => v / nav[0]),
        firstDates: unionDates,
      });
    }
    return series.sort((a, b) => b.pct - a.pct);
  }, [funds, liveAssets, usdPkr, fundHistory]);

  const fundCompareOption: EChartsOption = useMemo(() => ({
    animationDuration: 600,
    grid: { left: 8, right: 8, top: 40, bottom: 34, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#141414',
      borderColor: 'rgba(255,255,255,0.12)',
      textStyle: { color: '#f4f4f5', fontFamily: 'JetBrains Mono, monospace', fontSize: 11 },
      valueFormatter: (v) => fmtPct((Number(v) - 1) * 100),
    },
    legend: {
      top: 0, right: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 10,
      textStyle: { color: '#9ca3af', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' },
      // Leave room for the toolbox on the left; wrap instead of overlap.
      type: 'scroll',
      padding: [0, 40, 0, 90],
    },
    // Interactivity: scroll-wheel zoom inside the plot, drag to pan, slider
    // under the chart for touch/precise control, toolbox for export & reset.
    // Toolbox sits top-LEFT (legend owns top-right) so they never overlap.
    toolbox: {
      left: 4, top: 0, itemSize: 12, itemGap: 6,
      iconStyle: { borderColor: '#9ca3af' },
      emphasis: { iconStyle: { borderColor: '#7aff78' } },
      feature: {
        // Box-select a region to zoom into it.
        dataZoom: { yAxisIndex: 'none', title: { zoom: 'Box zoom', back: 'Reset zoom' }, iconStyle: { borderColor: '#9ca3af' } },
        saveAsImage: { title: 'Save as image', name: 'fund-comparison', backgroundColor: '#0a0a0a' },
        restore: { title: 'Reset' },
      },
    },
    dataZoom: [
      // Inside: wheel zoom + pinch + drag-pan directly on the plot.
      { type: 'inside', xAxisIndex: 0, start: 0, end: 100, zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false },
      // Slider: visible range control below the chart.
      {
        type: 'slider', xAxisIndex: 0, start: 0, end: 100, height: 18, bottom: 2,
        borderColor: 'rgba(255,255,255,0.10)',
        backgroundColor: 'rgba(255,255,255,0.03)',
        fillerColor: 'rgba(122,255,120,0.12)',
        handleStyle: { color: '#7aff78', borderColor: '#7aff78' },
        moveHandleStyle: { color: 'rgba(122,255,120,0.35)' },
        dataBackground: { lineStyle: { color: 'rgba(122,255,120,0.3)' }, areaStyle: { color: 'rgba(122,255,120,0.08)' } },
        selectedDataBackground: { lineStyle: { color: '#7aff78' }, areaStyle: { color: 'rgba(122,255,120,0.15)' } },
        textStyle: { color: '#9ca3af', fontSize: 9, fontFamily: 'JetBrains Mono, monospace' },
        labelFormatter: (v: number) => {
          // values here are category indices; resolve to the date label
          const labels = (fundCompare[0]?.firstDates ?? []).map(d => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }));
          return labels[v] ?? '';
        },
      },
    ],
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: (fundCompare[0]?.firstDates ?? []).map(d => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#9ca3af', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' },
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
      axisLabel: {
        color: '#9ca3af', fontSize: 10, fontFamily: 'JetBrains Mono, monospace',
        formatter: (v: number) => `${((v - 1) * 100).toFixed(0)}%`,
      },
    },
    series: fundCompare.map(s => ({
      name: s.name,
      type: 'line' as const,
      smooth: true,
      showSymbol: false,
      data: s.data,
      lineStyle: { width: 2, color: s.color },
      itemStyle: { color: s.color },
    })),
  }), [fundCompare, funds, fundHistory]);

  // Widget content renderer — the customize panel reorders/toggles these.
  const widgetHeader = (id: WidgetId) => {
    if (!customizing) return null;
    return (
      <button
        type="button"
        draggable
        onDragStart={(e) => { e.dataTransfer.effectAllowed = 'move'; setDragWidget(id); }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); if (dragWidget) moveWidget(dragWidget, id); setDragWidget(null); }}
        className={`absolute top-2.5 right-2.5 z-10 flex items-center gap-1 px-2 py-1 rounded-full ${EDIT_HANDLE} text-[8.5px] font-mono font-bold text-zinc-100 tracking-wider uppercase cursor-grab active:cursor-grabbing transition-transform hover:scale-105`}
        title="Drag to reorder"
      >
        <GripVertical className="w-3 h-3" /> {id}
      </button>
    );
  };

  const renderWidget = (id: WidgetId) => {
    switch (id) {
      case 'total-value':
        return (
          <div className={`${PANEL} p-6 relative h-full`}>
            {widgetHeader(id)}
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
                <Wallet className="w-4 h-4 text-primary" /> Total Value
              </span>
              <span className="text-[10px] font-mono text-muted-foreground">{funds.length} funds · {dispLabel}</span>
            </div>
            <span className="text-3xl font-mono font-bold tracking-tight block">{fmtD(agg.value)}</span>
            <span className={`text-xs font-semibold mt-1 block ${agg.day >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {fmtD(agg.day)} ({fmtPct(agg.dayPct)}) today
            </span>
          </div>
        );
      case 'unreal-pl':
        return (
          <div className={`${PANEL} p-6 relative h-full`}>
            {widgetHeader(id)}
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-primary" /> Unrealized P/L
              </span>
              <span className="text-[10px] font-mono text-muted-foreground">All time</span>
            </div>
            <span className={`text-3xl font-mono font-bold tracking-tight block ${agg.unreal >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {agg.unreal >= 0 ? '+' : '-'}{fmtD(Math.abs(agg.unreal))}
            </span>
            <span className="text-xs text-muted-foreground mt-1 block">Blended ROI {fmtPct(agg.roi)}</span>
          </div>
        );
      case 'top-exposure':
        return (
          <div className={`${PANEL} p-6 relative h-full`}>
            {widgetHeader(id)}
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
                <PieChart className="w-4 h-4 text-primary" /> Top Exposure
              </span>
              <span className="text-[10px] font-mono text-muted-foreground">Across funds</span>
            </div>
            {agg.top.length > 0 ? (
              <>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-mono font-bold">{agg.top[0].symbol}</span>
                  <span className="text-xs text-muted-foreground">{agg.top[0].pct.toFixed(0)}% of book</span>
                </div>
                <div className="flex gap-1 mt-2 h-1.5">
                  {agg.top.slice(0, 5).map(t => (
                    <div key={t.symbol} className="h-full rounded-full bg-primary/50" style={{ width: `${t.pct}%` }} title={`${t.symbol} ${t.pct.toFixed(1)}%`} />
                  ))}
                </div>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">No holdings yet.</p>
            )}
          </div>
        );
      case 'fund-compare':
        if (fundCompare.length === 0) return null;
        return (
          <div className={`${PANEL} p-5 relative`}>
            {widgetHeader(id)}
            <div className="flex items-baseline justify-between mb-2 flex-wrap gap-2 pr-8">
              <h3 className="text-md font-serif font-semibold flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-primary" /> Fund Comparison
              </h3>
              <span className="text-[11px] text-muted-foreground">
                Indexed NAV, best-to-worst · leader <span className="text-emerald-400 font-mono font-bold">{fundCompare[0].name} {fmtPct(fundCompare[0].pct)}</span>
              </span>
            </div>
            <EChart option={fundCompareOption} height={320} />
          </div>
        );
      case 'fund-cards':
        return (
          <div className="relative">
            {widgetHeader(id)}
            <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
              <h3 className="text-md font-serif font-semibold flex items-center gap-2">
                <Briefcase className="w-4 h-4 text-primary" /> Your Funds
              </h3>
              <span className="text-[11px] text-muted-foreground">Click a card to open that fund&apos;s full portfolio</span>
            </div>

            {/* First-run onboarding: 3-step checklist, dismissible */}
            {showOnboarding && (
              <div className={`${PANEL} p-5 mb-5 border-primary/25 relative`}>
                <button
                  onClick={() => { setShowOnboarding(false); try { localStorage.setItem('eclipse_onboarded', '1'); } catch { /* ignore */ } }}
                  className="absolute top-3 right-3 text-muted-foreground hover:text-foreground cursor-pointer p-1"
                  title="Dismiss"
                >
                  <X className="w-4 h-4" />
                </button>
                <h4 className="text-sm font-serif font-semibold mb-3 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-primary" /> Welcome to Eclipse Portfolios
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {[
                    { done: agg.value > 0, title: '1 · Record a trade', desc: 'Add your first BUY — crypto, PSX, or any JDDS market.', action: 'Add transaction' },
                    { done: displayFx !== 'USD' || getDisplayCurrency() !== 'USD', title: '2 · Pick your currency', desc: 'Totals show in USD by default — switch anytime.', action: 'Open Settings' },
                    { done: false, title: '3 · Explore analytics', desc: 'Stress tests, risk radar, Monte Carlo & AI briefs.', action: 'Scroll down' },
                  ].map(step => (
                    <div key={step.title} className={`${TILE} p-3.5 flex flex-col gap-1.5`}>
                      <div className="flex items-center gap-2">
                        <span className={`w-4 h-4 rounded-full border flex items-center justify-center shrink-0 ${step.done ? 'bg-primary border-primary' : 'border-border/50'}`}>
                          {step.done && <span className="text-[9px] font-bold text-[#0b0b0b]">✓</span>}
                        </span>
                        <span className="text-xs font-bold">{step.title}</span>
                      </div>
                      <p className="text-[11px] text-muted-foreground leading-relaxed">{step.desc}</p>
                      {!step.done && (
                        <button
                          onClick={() => {
                            if (step.action.startsWith('Add')) onOpenFund(funds[0]?.id ?? '');
                          }}
                          className="text-[10.5px] font-mono text-primary hover:underline text-left cursor-pointer mt-auto"
                        >
                          {step.action} →
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
              {funds.map(f => (
                <FundCard
                  key={f.id}
                  fund={f}
                  usdPkr={usdPkr}
                  liveAssets={liveAssets}
                  onOpen={() => onOpenFund(f.id)}
                  onEdit={() => onEditFund(f)}
                  onDelete={() => onDeleteFund(f.id)}
                  onAnalyzeTicker={onAnalyzeTicker}
                  canDelete={!isFundProtected(f.id)}
                  fmtD={fmtD}
                  fmtDK={fmtDK}
                />
              ))}
              <button
                onClick={onCreateFund}
                className="min-h-[220px] rounded-2xl border-2 border-dashed border-border/40 hover:border-primary/50 hover:bg-primary/[0.03] transition-all flex flex-col items-center justify-center gap-2 text-muted-foreground hover:text-primary cursor-pointer group"
              >
                <span className="w-11 h-11 rounded-xl bg-primary/10 border border-primary/25 flex items-center justify-center group-hover:scale-110 transition-transform">
                  <Plus className="w-5 h-5" />
                </span>
                <span className="text-sm font-semibold">Create New Fund</span>
                <span className="text-[11px]">House fund, college fund, trip — any goal.</span>
              </button>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      {/* Customize toolbar */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="text-[10px] uppercase tracking-wider font-mono text-muted-foreground flex items-center gap-1.5">
          <LayoutDashboard className="w-3.5 h-3.5" /> Dashboard
        </span>
        <button
          onClick={() => setCustomizing((v) => !v)}
          className={`flex items-center gap-1.5 text-[11px] font-bold tracking-wider border rounded-lg px-3 py-1.5 transition-all cursor-pointer ${
            customizing
              ? 'text-zinc-900 dark:text-zinc-100 bg-zinc-500/30 dark:bg-zinc-400/20 border-zinc-500/60 dark:border-zinc-400/50 shadow-inner backdrop-blur-md'
              : 'text-muted-foreground hover:text-primary bg-accent/40 hover:bg-accent/70 border-border/40'
          }`}
          title="Rearrange, show/hide, and resize dashboard widgets"
        >
          <Settings2 className="w-3.5 h-3.5" /> {customizing ? 'Done' : 'Customize'}
        </button>
      </div>

      {/* Inline customize panel */}
      {customizing && (
        <div className="edit-mode-banner px-3 py-2 animate-fade-in-up flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-zinc-500 dark:bg-zinc-400 animate-pulse shrink-0" />
          <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-200">Edit mode — drag, resize, or hide widgets below</p>
        </div>
      )}

      {customizing && (
        <div className={`${PANEL} p-4 animate-fade-in-up space-y-3 ring-1 ring-zinc-400/30 dark:ring-zinc-500/25`}>
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-bold uppercase tracking-wider">Dashboard Layout</p>
            <button
              onClick={resetLayout}
              className="text-[10px] font-bold text-muted-foreground hover:text-rose-400 uppercase tracking-wider cursor-pointer transition-colors flex items-center gap-1"
            >
              <RotateCcw className="w-3 h-3" /> Reset to defaults
            </button>
          </div>
          <p className="text-[10px] text-muted-foreground">Drag <GripVertical className="w-3 h-3 inline -mt-0.5" /> to reorder · toggle visibility · pick a width (S → XL spans a 4-column grid)</p>
          <div>
            <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-1.5">Layout templates</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
              {DASHBOARD_TEMPLATES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => updateLayout(t.build())}
                  title={t.desc}
                  className={`${TILE} p-2.5 text-left hover:border-zinc-400/60 dark:hover:border-zinc-500/50 hover:bg-zinc-500/[0.06] dark:hover:bg-zinc-400/[0.04] transition-all cursor-pointer`}
                >
                  <TemplateMiniGrid rows={t.preview} />
                  <p className="text-[11px] font-bold mt-2">{t.name}</p>
                  <p className="text-[9px] text-muted-foreground leading-snug">{t.desc}</p>
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {layout.widgets.map((w) => {
              const meta = WIDGET_META[w.id];
              return (
                <div
                  key={w.id}
                  draggable
                  onDragStart={(e) => { e.dataTransfer.effectAllowed = 'move'; setDragWidget(w.id); }}
                  onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }}
                  onDrop={(e) => { e.preventDefault(); if (dragWidget) moveWidget(dragWidget, w.id); setDragWidget(null); }}
                  className={`${TILE} ${w.visible ? '' : 'opacity-45'} p-3 flex items-center gap-3 cursor-grab active:cursor-grabbing transition-all duration-150 ${dragWidget === w.id ? 'opacity-40 scale-[0.98]' : dragWidget ? 'ring-1 ring-zinc-400/50 dark:ring-zinc-400/40' : ''}`}
                >
                  <span className={`flex items-center justify-center w-7 h-7 rounded-lg ${EDIT_GRIP} shrink-0 cursor-grab active:cursor-grabbing`} title="Drag to reorder">
                    <GripVertical className="w-4 h-4 text-zinc-200" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-bold truncate">{meta.label}</p>
                    <p className="text-[10px] text-muted-foreground truncate">{meta.desc}</p>
                  </div>
                  <div className="flex items-center gap-0.5 shrink-0">
                    {([1, 2, 3, 4] as const).map((s) => (
                      <button
                        key={s}
                        onClick={(e) => { e.stopPropagation(); patchWidget(w.id, { span: s }); }}
                        title={`${SPAN_LABEL[s]} width`}
                        className={`w-6 h-6 rounded-md text-[10px] font-bold cursor-pointer transition-colors border ${
                          w.span === s
                            ? 'bg-zinc-600/80 dark:bg-zinc-300/25 text-white dark:text-zinc-100 border-zinc-600 dark:border-zinc-400/60'
                            : 'text-zinc-600 dark:text-zinc-400 border-zinc-400/30 dark:border-zinc-500/25 hover:bg-zinc-500/15 dark:hover:bg-zinc-400/10'
                        }`}
                      >
                        {SPAN_LABEL[s]}
                      </button>
                    ))}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); patchWidget(w.id, { visible: !w.visible }); }}
                    title={w.visible ? 'Hide widget' : 'Show widget'}
                    className={`p-1.5 rounded-md cursor-pointer transition-colors shrink-0 ${w.visible ? 'text-zinc-200 hover:bg-zinc-500/15 dark:hover:bg-zinc-400/10' : 'text-muted-foreground hover:text-foreground'}`}
                  >
                    {w.visible ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Widget grid — order/size/visibility from the saved layout */}
      <div className="overview-widget-grid grid grid-cols-1 lg:grid-cols-4 gap-5">
        {layout.widgets.filter((w) => w.visible).map((w) => {
          if (w.id === 'fund-cards') {
            // Fund cards keep their own internal grid; span always full here.
            return (
              <div key={w.id} className="col-span-1 lg:col-span-4">
                {renderWidget(w.id)}
              </div>
            );
          }
          const fundCompareEmpty = w.id === 'fund-compare' && fundCompare.length === 0;
          if (fundCompareEmpty) return null;
          return (
            <div key={w.id} className={`col-span-1 ${SPAN_CLASS[w.span]}`}>
              {renderWidget(w.id)}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Live asset shape kept for compatibility with existing consumers ─────────
interface LiveAsset {
  symbol: string;
  name?: string;
  price: number;
  currentPrice?: number;
  changePercent?: number;
  exchange?: string;
  rank?: number;
  currency?: 'USD' | 'PKR';
  category?: string;
  aiTag?: string;
  marketId?: string;
}

interface MyPortfolioProps {
  onAnalyzeTicker: (ticker: string, customCtx?: string) => void;
  onMarketStatusChange?: (isBullish: boolean) => void;
}

export function MyPortfolio({ onAnalyzeTicker, onMarketStatusChange }: MyPortfolioProps) {

  // ── Multi-fund state ───────────────────────────────────────────────────────
  // viewMode 'overview' shows the cross-fund dashboard; otherwise the id of
  // the fund whose full portfolio is being viewed.
  const [funds, setFunds] = useState<Fund[]>([]);
  const [viewMode, setViewMode] = useState<string>('overview');
  const [isFundDialogOpen, setIsFundDialogOpen] = useState(false);
  const [fundEditorId, setFundEditorId] = useState<string | null>(null); // null = creating

  // New-fund form
  const [fundName, setFundName] = useState('');
  const [fundIcon, setFundIcon] = useState('savings');
  const [fundColor, setFundColor] = useState(FUND_COLORS[0]);
  const [fundGoal, setFundGoal] = useState('');

  // Customization states
  const [timeframe, setTimeframe] = useState<'1D' | '7D' | '1M' | 'ALL'>('1M');

  // Dialog state
  const [isAddOpen, setIsAddOpen] = useState(false);

  // Add-transaction form states
  const [txType, setTxType] = useState<'BUY' | 'SELL' | 'DIVIDEND'>('BUY');
  const [txSymbol, setTxSymbol] = useState('');
  const [txQty, setTxQty] = useState('');
  const [txPrice, setTxPrice] = useState('');
  const [txFee, setTxFee] = useState('0');
  const [txDate, setTxDate] = useState(new Date().toISOString().split('T')[0]);
  const [txTotalSpent, setTxTotalSpent] = useState('');

  // Symbol combobox
  const [symbolSearchQuery, setSymbolSearchQuery] = useState('');
  const [showSymbolDropdown, setShowSymbolDropdown] = useState(false);
  const symbolDropdownRef = useRef<HTMLDivElement>(null);
  // JDDS-wide search results (any asset across all markets).
  const [jddsSuggestions, setJddsSuggestions] = useState<Array<{ symbol: string; name: string; marketId: string; currency: string; price: number }>>([]);
  const [searchingSymbols, setSearchingSymbols] = useState(false);

  // Table controls
  const [filterText, setFilterText] = useState('');
  const [sortCol, setSortCol] = useState<'symbol' | 'value' | 'day' | 'total'>('value');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [watchlist, setWatchlist] = useState<Record<string, boolean>>({});

  // Tools state
  const [stressId, setStressId] = useState('market');
  const [severity, setSeverity] = useState(1);

  // ── Fund-page layout customization (mouse-driven) ────────────────────────
  const [fundLayout, setFundLayout] = useState<{ widgets: FundWidgetLayout[] }>(DEFAULT_FUND_LAYOUT);
  const [fundCustomizing, setFundCustomizing] = useState(false);
  const [fundDrag, setFundDrag] = useState<FundWidgetId | null>(null);
  // Click-selected widget in edit mode — enables keyboard nudge/resize.
  const [selectedWidget, setSelectedWidget] = useState<FundWidgetId | null>(null);
  useEffect(() => { setFundLayout(loadFundLayout()); }, []);
  const persistFundLayout = useCallback((widgets: FundWidgetLayout[]) => {
    setFundLayout({ widgets });
    try { window.localStorage.setItem(FUND_LAYOUT_KEY, JSON.stringify({ widgets })); } catch { /* private mode */ }
  }, []);
  const patchFundWidget = useCallback((id: FundWidgetId, patch: Partial<FundWidgetLayout>) => {
    setFundLayout((prev) => {
      const widgets = prev.widgets.map((w) => (w.id === id ? { ...w, ...patch } : w));
      try { window.localStorage.setItem(FUND_LAYOUT_KEY, JSON.stringify({ widgets })); } catch { /* private mode */ }
      return { widgets };
    });
  }, []);
  const moveFundWidget = useCallback((from: FundWidgetId, to: FundWidgetId) => {
    if (from === to) return;
    setFundLayout((prev) => {
      const widgets = [...prev.widgets];
      const fi = widgets.findIndex((w) => w.id === from);
      const ti = widgets.findIndex((w) => w.id === to);
      if (fi === -1 || ti === -1) return prev;
      const [moved] = widgets.splice(fi, 1);
      widgets.splice(ti, 0, moved);
      try { window.localStorage.setItem(FUND_LAYOUT_KEY, JSON.stringify({ widgets })); } catch { /* private mode */ }
      return { widgets };
    });
  }, []);
  const resetFundLayout = useCallback(() => {
    try { window.localStorage.removeItem(FUND_LAYOUT_KEY); } catch { /* ignore */ }
    setFundLayout(DEFAULT_FUND_LAYOUT);
  }, []);

  // Live mouse resize: pointer-drag on a widget's edge adjusts width (span)
  // or extra height in real time; the bottom-right corner adjusts both axes
  // at once. Pointer capture keeps events flowing even when the cursor leaves
  // the handle. ~120px travel = one width step, ~60px = one height step
  // (40px min-height each).
  const onWidgetResizeStart = useCallback((e: React.PointerEvent, id: FundWidgetId, mode: 'wider' | 'narrower' | 'taller' | 'shorter' | 'corner') => {
    e.preventDefault();
    e.stopPropagation();
    const horizontal = mode === 'wider' || mode === 'narrower' || mode === 'corner';
    const vertical = mode === 'taller' || mode === 'shorter' || mode === 'corner';
    const hDir = (mode === 'wider' || mode === 'corner') ? 1 : -1;
    const vDir = (mode === 'taller' || mode === 'corner') ? 1 : -1;
    const startX = e.clientX;
    const startY = e.clientY;
    let hSteps = 0;
    let vSteps = 0;
    const target = e.currentTarget as HTMLElement;
    // Pointer capture keeps the drag alive when the cursor outruns the handle.
    try { target.setPointerCapture(e.pointerId); } catch { /* older browsers */ }
    // Fallback capture layer for browsers without pointer capture.
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;cursor:nwse-resize;';
    document.body.appendChild(overlay);

    const onMove = (ev: PointerEvent) => {
      const apply = (patch: (w: FundWidgetLayout) => FundWidgetLayout) => {
        setFundLayout((prev) => {
          const widgets = prev.widgets.map((w) => (w.id === id ? patch(w) : w));
          try { window.localStorage.setItem(FUND_LAYOUT_KEY, JSON.stringify({ widgets })); } catch { /* private mode */ }
          return { widgets };
        });
      };
      if (horizontal) {
        const steps = Math.floor(Math.max(0, (ev.clientX - startX) * hDir) / 120);
        if (steps !== hSteps) {
          const diff = steps - hSteps;
          hSteps = steps;
          apply((w) => ({ ...w, span: Math.max(1, Math.min(4, w.span + diff)) as FundWidgetLayout['span'] }));
        }
      }
      if (vertical) {
        const steps = Math.floor(Math.max(0, (ev.clientY - startY) * vDir) / 60);
        if (steps !== vSteps) {
          const diff = steps - vSteps;
          vSteps = steps;
          apply((w) => ({ ...w, height: Math.max(0, Math.min(10, w.height + diff)) }));
        }
      }
    };
    const onUp = () => {
      overlay.remove();
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
  }, []);

  // Keyboard control for the click-selected widget (edit mode only):
  // ←/→/↑/↓ nudge order · Shift+←/→ width · Shift+↑/↓ height · +/- height ·
  // X hide · Escape deselect.
  useEffect(() => {
    if (!fundCustomizing) { setSelectedWidget(null); return; }
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || (el as HTMLElement).isContentEditable)) return;
      if (!selectedWidget) return;
      const patch = (p: Partial<FundWidgetLayout>) => patchFundWidget(selectedWidget, p);
      const nudge = (dir: -1 | 1) => {
        setFundLayout((prev) => {
          const widgets = [...prev.widgets];
          const i = widgets.findIndex((w) => w.id === selectedWidget);
          const j = i + dir;
          if (i === -1 || j < 0 || j >= widgets.length) return prev;
          const [m] = widgets.splice(i, 1);
          widgets.splice(j, 0, m);
          try { window.localStorage.setItem(FUND_LAYOUT_KEY, JSON.stringify({ widgets })); } catch { /* private mode */ }
          return { widgets };
        });
      };
      switch (e.key) {
        case 'ArrowLeft': e.preventDefault(); e.shiftKey ? patch({ span: Math.max(1, (fundLayout.widgets.find(w => w.id === selectedWidget)?.span ?? 2) - 1) as FundWidgetLayout['span'] }) : nudge(-1); break;
        case 'ArrowRight': e.preventDefault(); e.shiftKey ? patch({ span: Math.min(4, (fundLayout.widgets.find(w => w.id === selectedWidget)?.span ?? 2) + 1) as FundWidgetLayout['span'] }) : nudge(1); break;
        case 'ArrowUp': e.preventDefault(); e.shiftKey ? nudge(-1) : patch({ height: Math.min(10, (fundLayout.widgets.find(w => w.id === selectedWidget)?.height ?? 0) + 1) }); break;
        case 'ArrowDown': e.preventDefault(); e.shiftKey ? nudge(1) : patch({ height: Math.max(0, (fundLayout.widgets.find(w => w.id === selectedWidget)?.height ?? 0) - 1) }); break;
        case '+': case '=': e.preventDefault(); patch({ height: Math.min(10, (fundLayout.widgets.find(w => w.id === selectedWidget)?.height ?? 0) + 1) }); break;
        case '-': case '_': e.preventDefault(); patch({ height: Math.max(0, (fundLayout.widgets.find(w => w.id === selectedWidget)?.height ?? 0) - 1) }); break;
        case 'x': case 'X': e.preventDefault(); patch({ visible: false }); setSelectedWidget(null); break;
        case 'Escape': setSelectedWidget(null); break;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [fundCustomizing, selectedWidget, fundLayout, patchFundWidget]);
  const [wiSymbol, setWiSymbol] = useState('BTC');
  const [wiSide, setWiSide] = useState<'Buy' | 'Sell'>('Buy');
  const [wiQty, setWiQty] = useState('0.05');
  const [szEntry, setSzEntry] = useState('68000');
  const [szStop, setSzStop] = useState('64000');
  const [szTarget, setSzTarget] = useState('78000');
  const [szRisk, setSzRisk] = useState(1);
  const [mcYears, setMcYears] = useState(5);
  const [mcMonthly, setMcMonthly] = useState('500');

  // Alerts (inline builder + persisted ledger)
  const [alertType, setAlertType] = useState<Alert['type']>('PRICE_ABOVE');
  const [alertTarget, setAlertTarget] = useState('');

  // Server-side alert sync: register the ledger so the scheduler evaluates
  // thresholds against live prices even when this tab is closed. clientId is
  // a stable anonymous id; trigger marks persist server-side.
  const alertClientId = useRef<string>('');
  if (!alertClientId.current) {
    try {
      alertClientId.current = localStorage.getItem('eclipse_client_id') || (() => {
        const id = 'c-' + Math.random().toString(36).slice(2, 10);
        localStorage.setItem('eclipse_client_id', id);
        return id;
      })();
    } catch { alertClientId.current = 'c-anon'; }
  }

  // Live data state
  const [liveAssets, setLiveAssets] = useState<LiveAsset[]>([]);
  const [loadingLive, setLoadingLive] = useState(true);
  const [loadingPortfolio, setLoadingPortfolio] = useState(true);

  // Persistent state — transactions now derive from the ACTIVE fund.
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isUpdating, setIsUpdating] = useState(false);

  // Pull live prices from JDDS via /api/quote (same source as the rest of the
  // app) for every tracked symbol — the demo set plus anything the user has
  // added (transactions, watchlist, alerts). Merges in demo metadata where it
  // exists; JDDS-only assets get their real name/currency from the quote.
  // Falls back to the static demo prices if the endpoint is unreachable, slow,
  // or a symbol has no live quote yet. A hard timeout guards against a hung
  // request so the portfolio never blocks on skeletons forever.
  const [usdPkr, setUsdPkr] = useState(278);

  // ── Display currency (presentation layer; engine stays USD) ────────────────
  // Persisted in localStorage; settings changes broadcast `eclipse:currency-change`.
  const [fxRates, setFxRates] = useState<Record<string, number>>({ USD: 1 });
  const [fxAsOf, setFxAsOf] = useState<string | null>(null);
  const [displayFx, setDisplayFx] = useState<Currency>('USD');
  useEffect(() => {
    setDisplayFx(getDisplayCurrency());
    fetchFxMatrix().then(m => {
      setFxRates(m.rates); setFxAsOf(m.asOf);
      // Keep the engine's PKR fx chain synced to the freshest fetched rate.
      if (m.rates.PKR && m.rates.PKR > 0) setUsdPkr(m.rates.PKR);
    });
    const onChange = (e: Event) => {
      setDisplayFx((e as CustomEvent<string>).detail || 'USD');
      fetchFxMatrix().then(m => { setFxRates(m.rates); setFxAsOf(m.asOf); });
    };
    window.addEventListener('eclipse:currency-change', onChange);
    return () => window.removeEventListener('eclipse:currency-change', onChange);
  }, []);
  const fxRate = displayFx === 'USD' ? 1 : (fxRates[displayFx] ?? 0);
  const hasFx = displayFx === 'USD' || fxRate > 0;
  // USD-denominated value → display currency (falls back to USD when the
  // rate is unknown so numbers stay honest instead of wrong).
  const toDisp = useCallback((usd: number) => hasFx ? convertFromUsd(usd, displayFx, fxRates) : usd, [hasFx, displayFx, fxRates]);
  const fmtD = useCallback((usd: number, dp = 2) => fmtMoney(toDisp(usd), hasFx ? displayFx : 'USD', dp), [toDisp, hasFx, displayFx]);
  const fmtDK = useCallback((usd: number) => fmtMoneyCompact(toDisp(usd), hasFx ? displayFx : 'USD'), [toDisp, hasFx, displayFx]);
  const DISP_LABEL = hasFx ? displayFx : 'USD';

  const fetchLivePrices = useCallback(async (isInitial = false) => {
    if (isInitial) setLoadingLive(true);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const tracked = new Set<string>(DEMO_LIVE_PRICES.map(a => a.symbol));
      // Every fund's ledger contributes symbols — the Overview needs live
      // prices for holdings in funds that aren't currently open.
      funds.forEach(f => f.tx.forEach(t => tracked.add(t.symbol)));
      Object.keys(watchlist).forEach(s => tracked.add(s));
      alerts.forEach(a => tracked.add(a.symbol));
      const symbols = [...tracked].join(',');
      const res = await fetch(`/api/quote?symbols=${encodeURIComponent(symbols)}`, { signal: controller.signal });
      const data = await res.json();
      if (Array.isArray(data.quotes) && data.quotes.length > 0) {
        const quoteMap = new Map<string, { symbol: string; name: string; price: number; changePercent: number; currency?: string; marketId?: string }>(
          data.quotes.map((q: { symbol: string; name: string; price: number; changePercent: number; currency?: string; marketId?: string }) => [q.symbol, q])
        );
        const merged = [...tracked].map(sym => {
          const demo = DEMO_LIVE_PRICES.find(a => a.symbol === sym);
          const q = quoteMap.get(sym);
          if (q && q.price > 0) {
            return {
              symbol: sym,
              name: demo?.name ?? q.name ?? sym,
              price: q.price,
              changePercent: q.changePercent,
              currency: (q.currency === 'PKR' ? 'PKR' : demo?.currency ?? 'USD') as 'USD' | 'PKR',
              category: demo?.category ?? 'JDDS',
              aiTag: demo?.aiTag,
              marketId: q.marketId,
            };
          }
          if (demo) return demo;
          return { symbol: sym, name: sym, price: 0, changePercent: 0, currency: 'USD' as const, category: 'JDDS' };
        });
        setLiveAssets(merged);
      } else {
        setLiveAssets(DEMO_LIVE_PRICES);
      }
    } catch {
      setLiveAssets(DEMO_LIVE_PRICES);
    } finally {
      clearTimeout(timer);
      if (isInitial) setLoadingLive(false);
    }
  }, [funds, watchlist, alerts]);

  // Live USD→PKR FX rate from /api/forex (same Yahoo source as the forex
  // screen). Falls back to 278 when the endpoint is unavailable.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/forex', { signal: AbortSignal.timeout(9000) });
        const data = await res.json();
        const usdPkr = (data.pairs as Array<{ base: string; quote: string; price: number; found: boolean }> | undefined)
          ?.find(p => p.base === 'USD' && p.quote === 'PKR' && p.found);
        if (!cancelled && usdPkr && usdPkr.price > 0) setUsdPkr(usdPkr.price);
      } catch { /* fallback rate stands */ }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (loadingPortfolio) return;
    const isInitial = liveAssets.length === 0;
    fetchLivePrices(isInitial);
    const interval = setInterval(() => fetchLivePrices(false), 15000);
    return () => clearInterval(interval);
  }, [loadingPortfolio, fetchLivePrices, liveAssets.length]);

  // Cached copies so repeated loads (tab switches) don't re-read/clobber.
  const savedAlertsRef = useRef<Alert[] | null>(null);
  const savedWatchlistRef = useRef<Record<string, boolean> | null>(null);

  const loadPortfolioData = (showSkeleton = true) => {
    if (showSkeleton) setLoadingPortfolio(true);
    const { funds: loaded } = loadFunds();
    setFunds(loaded);
    if (savedAlertsRef.current) { setAlerts(savedAlertsRef.current); }
    else {
      try {
        const savedAlerts = localStorage.getItem('portfolio_alerts_guest');
        if (savedAlerts) {
          const parsed: Alert[] = JSON.parse(savedAlerts);
          savedAlertsRef.current = parsed;
          setAlerts(parsed);
        }
      } catch { /* ignore corrupt alerts */ }
    }
    if (savedWatchlistRef.current) { setWatchlist(savedWatchlistRef.current); }
    else {
      try {
        const savedWatchlist = localStorage.getItem('portfolio_watchlist_guest');
        if (savedWatchlist) {
          const parsed: Record<string, boolean> = JSON.parse(savedWatchlist);
          savedWatchlistRef.current = parsed;
          setWatchlist(parsed);
        }
        else setWatchlist({ BTC: true, ETH: true, SOL: true, UBL: true, MEBL: true, SAZEW: true });
      } catch { setWatchlist({ BTC: true, ETH: true, SOL: true, UBL: true, MEBL: true, SAZEW: true }); }
    }
    if (showSkeleton) setLoadingPortfolio(false);
  };

  useEffect(() => { loadPortfolioData(); }, []);

  // Push the alert ledger to the server whenever it changes so the scheduler
  // evaluates thresholds even while this tab is closed.
  useEffect(() => {
    if (alerts.length === 0) return;
    fetch('/api/portfolio-alerts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        clientId: alertClientId.current,
        alerts: alerts.map(a => ({ id: a.id, symbol: a.symbol, type: a.type, target: a.target, isActive: a.isActive })),
      }),
    }).catch(() => { /* offline — alerts still work client-side */ });
  }, [alerts]);

  // Fractional transaction auto-calculations
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
    if (price > 0) setTxQty(val ? String(spent / price) : '');
  };

  // JDDS-wide symbol search: any asset across all markets (US, PK, IN, CN,
  // CRYPTO, ...) can be added to the portfolio. Debounced against /api/quote's
  // autocomplete endpoint, which resolves real symbols + live prices from the DB.
  useEffect(() => {
    const q = symbolSearchQuery.trim();
    if (!q || q.length < 1) {
      setJddsSuggestions([]);
      setSearchingSymbols(false);
      return;
    }
    setSearchingSymbols(true);
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const res = await fetch(`/api/quote?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        if (!cancelled && Array.isArray(data.suggestions)) {
          setJddsSuggestions(data.suggestions);
        }
      } catch {
        if (!cancelled) setJddsSuggestions([]);
      } finally {
        if (!cancelled) setSearchingSymbols(false);
      }
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
  }, [symbolSearchQuery]);

  // Combined dropdown: JDDS matches first (they carry live prices + currency),
  // then the already-tracked demo/live assets as a fallback.
  const filteredSymbolOptions = useMemo(() => {
    const q = symbolSearchQuery.toUpperCase();
    const jdds = jddsSuggestions.map(s => ({
      symbol: s.symbol,
      name: s.name,
      price: s.price,
      changePercent: 0,
      currency: (s.currency === 'PKR' ? 'PKR' : 'USD') as 'USD' | 'PKR',
      category: 'JDDS',
      marketId: s.marketId,
    }));
    const tracked = liveAssets
      .filter(a => !q || a.symbol.toUpperCase().includes(q) || (a.name ?? '').toUpperCase().includes(q))
      .map(a => ({ ...a, marketId: 'TRACKED' }));
    if (!q) return [...jdds, ...tracked];
    return [...jdds, ...tracked];
  }, [jddsSuggestions, liveAssets, symbolSearchQuery]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (symbolDropdownRef.current && !symbolDropdownRef.current.contains(event.target as Node)) {
        setShowSymbolDropdown(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // ── Fund CRUD ──────────────────────────────────────────────────────────────
  const activeFund = useMemo(
    () => funds.find(f => f.id === viewMode) ?? null,
    [funds, viewMode]
  );

  // The full screen operates on the active fund's ledger. In overview mode
  // (or when the active fund vanished) fall back to the first fund so hooks
  // below always receive a stable array.
  const transactions = useMemo(
    () => activeFund?.tx ?? funds[0]?.tx ?? [],
    [activeFund, funds]
  );

  const persistFunds = (next: Fund[]) => {
    setFunds(next);
    saveFunds(next);
  };

  const persistTx = (next: Transaction[]) => {
    if (!activeFund) return;
    persistFunds(funds.map(f => (f.id === activeFund.id ? { ...f, tx: next } : f)));
  };

  const openCreateFundDialog = () => {
    setFundEditorId(null);
    setFundName('');
    setFundIcon('savings');
    setFundColor(FUND_COLORS[Math.min(funds.length, FUND_COLORS.length - 1)]);
    setFundGoal('');
    setIsFundDialogOpen(true);
  };

  const openEditFundDialog = (fund: Fund) => {
    setFundEditorId(fund.id);
    setFundName(fund.name);
    setFundIcon(fund.icon);
    setFundColor(fund.color);
    setFundGoal(fund.goalUsd ? String(fund.goalUsd) : '');
    setIsFundDialogOpen(true);
  };

  const handleSaveFund = () => {
    const name = fundName.trim();
    if (!name) return;
    const goal = parseFloat(fundGoal);
    if (fundEditorId) {
      persistFunds(funds.map(f =>
        f.id === fundEditorId
          ? { ...f, name, icon: fundIcon, color: fundColor, goalUsd: isFinite(goal) && goal > 0 ? goal : undefined }
          : f
      ));
    } else {
      const newFund: Fund = {
        id: makeFundId(),
        name,
        icon: FUND_ICONS[fundIcon] ? fundIcon : 'savings',
        color: fundColor,
        goalUsd: isFinite(goal) && goal > 0 ? goal : undefined,
        tx: [],
      };
      persistFunds([...funds, newFund]);
      setViewMode(newFund.id);
    }
    setIsFundDialogOpen(false);
  };

  const handleDeleteFund = (id: string) => {
    const next = funds.filter(f => f.id !== id);
    if (next.length === 0) return; // never allow an empty book
    persistFunds(next);
    if (viewMode === id) setViewMode('overview');
  };

  const handleAddTransaction = () => {
    if (!txSymbol) return;
    setIsUpdating(true);
    const isDiv = txType === 'DIVIDEND';
    const newTx: Transaction = {
      id: 'tx-' + Date.now(),
      type: txType,
      symbol: txSymbol.toUpperCase(),
      // Dividend: qty is optional — a bare total (price) records as 1×price.
      quantity: isDiv ? (parseFloat(txQty) || 1) : (parseFloat(txQty) || 0),
      price: parseFloat(txPrice) || 0,
      fee: parseFloat(txFee) || 0,
      date: txDate,
    };
    persistTx([...transactions, newTx]);
    setTxSymbol('');
    setSymbolSearchQuery('');
    setTxQty('');
    setTxPrice('');
    setTxFee('0');
    setIsAddOpen(false);
    setIsUpdating(false);
  };

  // Legacy no-op — transactions now persist through `persistFunds`.
  const handleDeleteTransaction = (symbol: string) => {
    persistTx(transactions.filter(t => t.symbol !== symbol));
  };

  const toggleStar = (symbol: string) => {
    const next = { ...watchlist, [symbol]: !watchlist[symbol] };
    setWatchlist(next);
    localStorage.setItem('portfolio_watchlist_guest', JSON.stringify(next));
  };

  const handleAddAlert = () => {
    const v = parseFloat(alertTarget);
    if (!isFinite(v)) return;
    const newAlert: Alert = {
      id: 'alert-' + Date.now(),
      symbol: wiSymbol.toUpperCase(),
      type: alertType,
      target: v,
      isActive: true,
    };
    const next = [...alerts, newAlert];
    setAlerts(next);
    localStorage.setItem('portfolio_alerts_guest', JSON.stringify(next));
    setAlertTarget('');
  };

  const handleDeleteAlert = (id: string) => {
    const next = alerts.filter(a => a.id !== id);
    setAlerts(next);
    localStorage.setItem('portfolio_alerts_guest', JSON.stringify(next));
  };

  const liveForEngine = useMemo(
    () => liveAssets.map(a => ({
      ...a,
      fxToUsd: a.currency === 'PKR' ? 1 / usdPkr : 1,
    })),
    [liveAssets, usdPkr]
  );
  const stats: PortfolioStats = usePortfolioEngine(transactions, liveForEngine, 'FIFO');

  // Real daily series per holding (Yahoo-backed). Powers the NAV chart,
  // sparklines and per-asset expanded charts. No fabrication: symbols with
  // no fetchable series are simply absent.
  const trackedSymbols = useMemo(() => {
    const s = new Set<string>();
    stats.holdings.forEach(h => s.add(h.symbol));
    Object.entries(watchlist).forEach(([sym, on]) => { if (on) s.add(sym); });
    return [...s];
  }, [stats.holdings, watchlist]);
  const history = usePriceHistories(trackedSymbols, MARKET_HINT);

  // ── Benchmark index comparison ────────────────────────────────────────────
  // Users compare their portfolio against real market indexes. Each entry
  // fetches the same Yahoo-backed daily series as holdings (GLOB market =
  // bare Yahoo ticker, no suffix). "cost" is the default: the portfolio's
  // own break-even line.
  const BENCHMARKS: Array<{ id: string; label: string; symbol: string }> = [
    { id: 'cost', label: 'Cost Basis', symbol: '' },
    { id: 'gspc', label: 'S&P 500', symbol: '^GSPC' },
    { id: 'ixic', label: 'Nasdaq', symbol: '^IXIC' },
    { id: 'dji', label: 'Dow Jones', symbol: '^DJI' },
    { id: 'ndx', label: 'Nasdaq 100', symbol: '^NDX' },
    { id: 'rut', label: 'Russell 2000', symbol: '^RUT' },
    { id: 'vix', label: 'VIX', symbol: '^VIX' },
    { id: 'kse100', label: 'KSE-100 (PSX)', symbol: '^KSE' },
    { id: 'nifty', label: 'Nifty 50 (India)', symbol: '^NSEI' },
    { id: 'hsi', label: 'Hang Seng', symbol: '^HSI' },
    { id: 'nikkei', label: 'Nikkei 225', symbol: '^N225' },
    { id: 'dax', label: 'DAX (Germany)', symbol: '^GDAXI' },
    { id: 'ftse', label: 'FTSE 100 (UK)', symbol: '^FTSE' },
    { id: 'btc', label: 'Bitcoin', symbol: 'BTC' },
    { id: 'eth', label: 'Ethereum', symbol: 'ETH' },
    { id: 'gold', label: 'Gold', symbol: 'GC=F' },
  ];
  const [benchmarkId, setBenchmarkId] = useState('cost');
  const activeBenchmark = BENCHMARKS.find(b => b.id === benchmarkId) ?? BENCHMARKS[0];
  const benchSymbols = useMemo(
    () => (activeBenchmark.symbol ? [activeBenchmark.symbol] : []),
    [activeBenchmark.symbol]
  );
  const benchHistory = usePriceHistories(benchSymbols, { [activeBenchmark.symbol]: 'GLOB' });

  // Fund comparison (overview): one shared history fetch across every fund's
  // holdings so the fund-vs-fund chart can build indexed NAV curves.
  const allFundSymbols = useMemo(() => {
    const s = new Set<string>();
    funds.forEach(f => f.tx.forEach(t => { if (t.type !== 'DIVIDEND') s.add(t.symbol); }));
    return [...s];
  }, [funds]);
  const fundHistRaw = usePriceHistories(allFundSymbols, MARKET_HINT);

  useEffect(() => {
    if (!loadingLive && !loadingPortfolio && onMarketStatusChange) {
      onMarketStatusChange(stats.dailyChangeValue >= 0);
    }
  }, [stats.dailyChangeValue, loadingLive, loadingPortfolio, onMarketStatusChange]);

  const priceOf = useCallback((sym: string) =>
    liveAssets.find(a => a.symbol === sym)?.price ?? 0, [liveAssets]);
  const dayOf = useCallback((sym: string) =>
    liveAssets.find(a => a.symbol === sym)?.changePercent ?? 0, [liveAssets]);
  const metaOf = useCallback((sym: string) =>
    liveAssets.find(a => a.symbol === sym), [liveAssets]);
  const currencyOf = useCallback((sym: string) =>
    liveAssets.find(a => a.symbol === sym)?.currency ?? 'USD', [liveAssets]);

  const totalCost = stats.costBasis || 1;
  const weightOf = useCallback((h: PortfolioStats['holdings'][number]) =>
    stats.totalValue > 0 ? h.value / stats.totalValue : 0, [stats.totalValue]);

  const wsum = useCallback((fn: (r: typeof RISK[string]) => number) =>
    stats.holdings.reduce((acc, h) => acc + fn(RISK[h.symbol] ?? RISK.DEFAULT) * weightOf(h), 0),
    [stats.holdings, weightOf]);

  const pBeta = wsum(r => r.beta);
  const pVol = wsum(r => r.vol);
  const pSharpe = wsum(r => r.sharpe);
  const pMdd = wsum(r => r.mdd);

  // Theme tokens resolved once per render for ECharts.
  const theme = useMemo(() => ({
    primary: cssVar('--primary', '#7aff78'),
    foreground: cssVar('--foreground', '#f4f4f5'),
    muted: cssVar('--muted-foreground', '#9ca3af'),
    border: 'rgba(255,255,255,0.08)',
    tooltipBg: cssVar('--popover', '#141414'),
    tooltipBorder: 'rgba(255,255,255,0.12)',
    fontMono: 'JetBrains Mono, IBM Plex Mono, SF Mono, Consolas, monospace',
  }), []);

  // ── Performance history (REAL data) ─────────────────────────────────────
  // Aligned-date indexed aggregation of every holding's real close series:
  //   NAV_i = Σ holding.value_usd × (close_symbol,i / close_symbol,0)
  // PKR series are converted at the live FX rate. Series are clipped to the
  // common window where ALL holdings have data, and windowed by timeframe
  // (1M ≈ 21 trading days, 7D ≈ 5, ALL = full fetched range). The benchmark
  // is the portfolio's own cost basis indexed the same way — an honest
  // "break-even" reference rather than an invented index. Endpoints are
  // forward/reverse-filled for the earliest date a symbol starts trading.
  const performanceSeries = useMemo(() => {
    const validHoldings = stats.holdings.filter(h => history.closes[h.symbol]?.length);
    if (validHoldings.length === 0 || history.loading) {
      return { labels: [], portData: [], benchData: [], benchLabel: '', real: false, granular: false };
    }

    // 1) Convert each series to USD-equivalent closes.
    const usdCloses: Record<string, number[]> = {};
    const usdDates: Record<string, string[]> = {};
    for (const h of validHoldings) {
      const fx = h.currency === 'PKR' ? 1 / usdPkr : 1;
      usdCloses[h.symbol] = (history.closes[h.symbol] ?? []).map(c => c * fx);
      usdDates[h.symbol] = history.dates[h.symbol] ?? [];
    }

    // Optional real-index benchmark series (same daily-close shape).
    const benchCloses = activeBenchmark.symbol ? (benchHistory.closes[activeBenchmark.symbol] ?? []) : [];
    const benchDates = activeBenchmark.symbol ? (benchHistory.dates[activeBenchmark.symbol] ?? []) : [];

    // 2) Union of all dates, ascending.
    const dateSet = new Set<string>();
    Object.values(usdDates).forEach(ds => ds.forEach(d => dateSet.add(d)));
    const allDates = [...dateSet].sort();
    const labels = allDates.map(d =>
      new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    );

    // 3) For each symbol: forward-fill before first date and reverse-fill after
    //    its last date (assets that IPO'd/ticker-listed mid-window stall at
    //    first/last price rather than dropping out of the portfolio).
    const portData: number[] = [];
    const benchData: number[] = [];
    for (const date of allDates) {
      let nav = 0;
      let bench = 0;
      for (const h of validHoldings) {
        const ds = usdDates[h.symbol];
        const cs = usdCloses[h.symbol];
        if (!ds || !cs || cs.length === 0) continue;
        let idx = ds.indexOf(date);
        if (idx === -1) {
          if (date < ds[0]) idx = 0;
          else if (date > ds[ds.length - 1]) idx = ds.length - 1;
          else {
            let lo = 0;
            while (lo < ds.length - 1 && ds[lo + 1] <= date) lo++;
            idx = lo;
          }
        }
        const base0 = cs[0];
        nav += h.valueUsd * (cs[idx] / base0);
        if (benchCloses.length < 2) {
          bench += (h.quantity * h.avgCost * h.fxToUsd) * (cs[idx] / base0);
        }
      }
      // Real-index benchmark: same aligned forward-fill as holdings.
      if (benchCloses.length >= 2 && benchDates.length === benchCloses.length) {
        let bidx = benchDates.indexOf(date);
        if (bidx === -1) {
          if (date < benchDates[0]) bidx = 0;
          else if (date > benchDates[benchDates.length - 1]) bidx = benchDates.length - 1;
          else {
            let lo = 0;
            while (lo < benchDates.length - 1 && benchDates[lo + 1] <= date) lo++;
            bidx = lo;
          }
        }
        bench = benchCloses[bidx];
      }
      portData.push(nav);
      benchData.push(bench);
    }

    // 4) Timeframe window (business days → calendar back-count).
    const backDays = timeframe === '1D' ? 1 : timeframe === '7D' ? 7 : timeframe === '1M' ? 30 : allDates.length;
    const startIdx = Math.max(0, allDates.length - Math.min(allDates.length, backDays === 1 ? 2 : backDays));
    const slicedLabels = labels.slice(startIdx);
    const slicedPort = portData.slice(startIdx);
    const slicedBench = benchData.slice(startIdx);
    // Rebase the window to 100 so the % change axis reads honestly.
    const rebasedPort = slicedPort.length ? slicedPort.map(v => v / (slicedPort[0] || 1)) : [];
    const rebasedBench = slicedBench.length ? slicedBench.map(v => v / (slicedBench[0] || 1)) : [];

    return { labels: slicedLabels, portData: rebasedPort, benchData: rebasedBench, benchLabel: activeBenchmark.label, real: true, granular: true };
  }, [stats.holdings, history, benchHistory, activeBenchmark, usdPkr, timeframe]);

  const perfDelta = useMemo(() => {
    const p = performanceSeries.portData;
    const b = performanceSeries.benchData;
    if (p.length === 0 || b.length === 0) return { port: 0, bench: 0 };
    return {
      port: ((p[p.length - 1] / p[0]) - 1) * 100,
      bench: ((b[b.length - 1] / b[0]) - 1) * 100,
    };
  }, [performanceSeries]);

  // Drawdown series: % below running peak at each point (the "underwater" view).
  const drawdownSeries = useMemo(() => {
    const p = performanceSeries.portData;
    if (p.length < 2) return [];
    let peak = p[0];
    return p.map(v => {
      peak = Math.max(peak, v);
      return peak > 0 ? (v / peak - 1) * 100 : 0;
    });
  }, [performanceSeries]);

  // Time-weighted return over the visible window — the standard portfolio
  // performance metric (removes the effect of cash-flow timing on simple ROI).
  const twr = useMemo(() => {
    if (drawdownSeries.length === 0) return null;
    // Daily TWR chain: r_t = NAV_t / NAV_{t-1} - 1, compounded.
    const p = performanceSeries.portData;
    let compounded = 1;
    for (let i = 1; i < p.length; i++) {
      if (p[i - 1] > 0) compounded *= p[i] / p[i - 1];
    }
    return (compounded - 1) * 100;
  }, [performanceSeries, drawdownSeries.length]);

  const perfOption: EChartsOption = useMemo(() => ({
    animationDuration: 600,
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: [
      { left: 8, right: 8, top: 24, height: '58%', containLabel: true },
      { left: 8, right: 8, top: '78%', bottom: 28, containLabel: true },
    ],
    // Drag/brush any window to zoom; pinch on touch. Sliders hidden — the
    // row of timeframe buttons handles explicit windows, this adds free-drag.
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], filterMode: 'none' },
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      valueFormatter: (v) => fmtPct((Number(v) - 1) * 100),
      axisPointer: { lineStyle: { color: 'rgba(255,255,255,0.2)' } },
    },
    xAxis: [
      {
        type: 'category',
        gridIndex: 0,
        boundaryGap: false,
        data: performanceSeries.labels,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
      },
      {
        type: 'category',
        gridIndex: 1,
        boundaryGap: false,
        data: performanceSeries.labels,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono },
      },
    ],
    yAxis: [
      {
        type: 'value',
        gridIndex: 0,
        scale: true,
        splitLine: { lineStyle: { color: theme.border } },
        axisLabel: {
          color: theme.muted, fontSize: 10, fontFamily: theme.fontMono,
          formatter: (v: number) => `${((v - 1) * 100).toFixed(0)}%`,
        },
      },
      {
        type: 'value',
        gridIndex: 1,
        min: -100,
        max: 0,
        splitLine: { show: false },
        axisLabel: {
          color: theme.muted, fontSize: 9, fontFamily: theme.fontMono,
          formatter: (v: number) => `${v.toFixed(0)}%`,
        },
      },
    ],
    series: [
      {
        name: 'Portfolio (indexed)',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        showSymbol: false,
        data: performanceSeries.portData,
        lineStyle: { width: 2, color: theme.primary },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(122,255,120,0.30)' },
            { offset: 1, color: 'rgba(122,255,120,0)' },
          ]),
        },
      },
      {
        name: performanceSeries.benchLabel || 'Cost basis (break-even)',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        showSymbol: false,
        data: performanceSeries.benchData,
        lineStyle: { width: 1.4, type: [4, 4], color: theme.muted },
        itemStyle: { color: theme.muted },
      },
      {
        name: 'Drawdown',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        showSymbol: false,
        data: drawdownSeries,
        lineStyle: { width: 1, color: 'rgba(255,62,62,0.55)' },
        areaStyle: { color: 'rgba(255,62,62,0.16)' },
        tooltip: { show: false },
      },
    ],
  }), [performanceSeries, drawdownSeries, theme]);

  // NOTE: ECharts/zrender cannot parse oklch(...) colors (treemap's
  // calculateBorderColor throws on them and crashes the screen), so this
  // palette must stay in hex. Values are the sRGB equivalents of the
  // previous oklch tokens.
  const CHART_COLORS = useMemo(() => ['#7aff78', '#8d92f9', '#d35bb1', '#f7ac4d', '#0090b1', '#8ec053', '#007565'], []);

// ── Allocation donut ──────────────────────────────────────────────────────

  const allocationOption: EChartsOption = useMemo(() => ({
    animationDuration: 600,
    tooltip: {
      trigger: 'item',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      formatter: (p: unknown) => {
        const d = p as { name: string; value: number; percent: number };
        return `<b>${d.name}</b><br/>${fmtD(d.value)} · ${d.percent}%`;
      },
    },
    legend: { show: false },
    series: [{
      type: 'pie',
      radius: ['58%', '82%'],
      padAngle: 2,
      itemStyle: { borderRadius: 6, borderColor: 'transparent', borderWidth: 2 },
      label: { show: false },
      emphasis: { scaleSize: 4 },
      data: stats.holdings.map((h, i) => ({
        name: h.symbol,
        value: Number(h.valueUsd.toFixed(2)),
        itemStyle: { color: CHART_COLORS[i % CHART_COLORS.length] },
      })),
    }],
  }), [stats.holdings, theme, CHART_COLORS, fmtD]);

  // ── Rebalancing suggestions ───────────────────────────────────────────────
  const rebalanceRows = useMemo(() =>
    stats.holdings.map(h => {
      const cur = weightOf(h) * 100;
      const target = RISK[h.symbol]?.target ?? RISK.DEFAULT.target;
      const drift = cur - target;
      return {
        symbol: h.symbol,
        drift,
        curFmt: `${cur.toFixed(1)}%`,
        targetFmt: `${target}%`,
        driftFmt: `${drift >= 0 ? '+' : ''}${drift.toFixed(1)} pts`,
        action: Math.abs(drift) < 1.5 ? 'Hold'
          : drift > 0 ? `Trim ${fmtDK((drift / 100) * stats.totalValue)}`
          : `Add ${fmtDK((-drift / 100) * stats.totalValue)}`,
        color: Math.abs(drift) < 1.5 ? 'text-muted-foreground' : drift > 0 ? 'text-rose-400' : 'text-emerald-400',
      };
    }).sort((a, b) => Math.abs(b.drift) - Math.abs(a.drift)),
    [stats.holdings, stats.totalValue, weightOf]);

  // ── Holdings table rows ───────────────────────────────────────────────────
  const holdingsRows = useMemo(() => {
    const dir = sortDir === 'asc' ? 1 : -1;
    const key = { symbol: 'symbol', value: 'value', day: 'day', total: 'total' }[sortCol];
    return stats.holdings
      .map(h => ({ ...h, dayPct: dayOf(h.symbol), totalPct: (h.unrealizedPnL / (h.avgCost * h.quantity || 1)) * 100 }))
      .filter(h => h.symbol.toLowerCase().includes(filterText.toLowerCase()))
      .sort((a, b) => {
        // Sort by USD-equivalent value so mixed PKR/USD books rank correctly.
        const av = key === 'day' ? a.dayPct : key === 'total' ? a.totalPct : key === 'value' ? a.valueUsd : (a[key as 'symbol'] as string);
        const bv = key === 'day' ? b.dayPct : key === 'total' ? b.totalPct : key === 'value' ? b.valueUsd : (b[key as 'symbol'] as string);
        return (av > bv ? 1 : av < bv ? -1 : 0) * dir;
      });
  }, [stats.holdings, sortCol, sortDir, filterText, dayOf]);

  const arrowFor = (col: typeof sortCol) => sortCol === col ? (sortDir === 'asc' ? ' ↑' : ' ↓') : '';
  const toggleSort = (col: typeof sortCol) => () => {
    if (sortCol === col) setSortDir(d => (d === 'desc' ? 'asc' : 'desc'));
    else { setSortCol(col); setSortDir('desc'); }
  };

  // ── Recent transactions (accurate notionals, no fabricated balance) ───────
  const recentTransactions = useMemo(() =>
    [...transactions]
      .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
      .slice(0, 8)
      .map(t => {
        const fx = (metaOf(t.symbol)?.currency ?? 'USD') === 'PKR' ? 1 / usdPkr : 1;
        const notional = t.quantity * t.price * fx;
        return {
          ...t,
          sideColor: t.type === 'BUY' ? 'text-emerald-400' : t.type === 'SELL' ? 'text-rose-400' : t.type === 'DIVIDEND' ? 'text-amber-300' : 'text-muted-foreground',
          notionalFmt: fmtD(notional),
        };
      }),
    [transactions, metaOf, usdPkr, fmtD]);

  const watchlistRows = useMemo(() =>
    Object.entries(watchlist).filter(([, v]) => v).map(([sym]) => {
      const asset = metaOf(sym);
      return {
        symbol: sym,
        price: asset?.price ?? 0,
        dayPct: asset?.changePercent ?? 0,
      };
    }).filter(w => w.price > 0),
    [watchlist, metaOf]);

  // ── Stress test (all impacts in USD-equivalent) ───────────────────────────
  const stress = useMemo(() => {
    const scen = STRESS_SCENARIOS.find(s => s.id === stressId) ?? STRESS_SCENARIOS[0];
    const rows = stats.holdings.map(h => {
      const r = RISK[h.symbol] ?? RISK.DEFAULT;
      const isMajor = ['BTC', 'ETH'].includes(h.symbol);
      const pct = (scen.mkt * (isMajor ? r.beta : r.beta) + scen.alt * (isMajor ? 0.4 : 1.1)) * severity;
      return { symbol: h.symbol, pct, dollar: h.valueUsd * (pct / 100) };
    }).sort((a, b) => a.pct - b.pct);

    const dollar = rows.reduce((a, r) => a + r.dollar, 0);
    const worst = rows[0];
    return {
      scen, rows,
      dollar,
      worstSymbol: worst?.symbol ?? '—',
      worstPct: worst?.pct ?? 0,
    };
  }, [stressId, severity, stats.holdings]);

  const stressOption: EChartsOption = useMemo(() => ({
    animationDuration: 500,
    grid: { left: 8, right: 60, top: 6, bottom: 6, containLabel: true },
    tooltip: {
      trigger: 'item',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      formatter: (p: unknown) => {
        const d = p as { name: string; value: number };
        return `<b>${d.name}</b><br/>${fmtPct(d.value)} · ${fmtD(stats.totalValue * (d.value / 100))}`;
      },
    },
    xAxis: {
      type: 'value',
      splitLine: { show: false },
      axisLabel: { show: false },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: stress.rows.map(r => r.symbol),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11, fontWeight: 600 },
    },
    series: [{
      type: 'bar',
      barWidth: 16,
      data: stress.rows.map(r => ({
        value: Number(r.pct.toFixed(2)),
        itemStyle: {
          color: new echarts.graphic.LinearGradient(1, 0, 0, 0, [
            { offset: 0, color: r.pct >= 0 ? 'rgba(52,211,153,0.85)' : 'rgba(251,113,133,0.9)' },
            { offset: 1, color: r.pct >= 0 ? 'rgba(52,211,153,0.25)' : 'rgba(251,113,133,0.3)' },
          ]),
          borderRadius: 4,
        },
        label: {
          show: true,
          position: 'right',
          formatter: (p: unknown) => fmtPct((p as { value: number }).value),
          color: r.pct >= 0 ? UP : DOWN,
          fontFamily: theme.fontMono,
          fontSize: 10.5,
        },
      })),
      markLine: {
        silent: true,
        symbol: 'none',
        data: [{ xAxis: 0 }],
        lineStyle: { color: 'rgba(255,255,255,0.25)', width: 1 },
        label: { show: false },
      },
    }],
  }), [stress, stats.totalValue, theme, fmtD]);

  // ── Correlation heatmap ───────────────────────────────────────────────────
  // Real Pearson correlation of daily returns computed from the fetched close
  // series (falls back to the static hint table only when a series is absent).
  const corrSymbols = useMemo(() => stats.holdings.map(h => h.symbol), [stats.holdings]);
  const corrData = useMemo(() => {
    // Daily returns per symbol from real history (same-length series only).
    const returns: Record<string, number[]> = {};
    for (const sym of corrSymbols) {
      const cs = history.closes[sym];
      if (cs && cs.length >= 3) {
        const r: number[] = [];
        for (let i = 1; i < cs.length; i++) {
          if (cs[i - 1] > 0) r.push(cs[i] / cs[i - 1] - 1);
        }
        if (r.length >= 2) returns[sym] = r;
      }
    }
    const pearson = (a: number[], b: number[]): number | null => {
      // Align lengths conservatively: use the overlapping tail (dates ascend together
      // for same-window fetches; misaligned series fall back to the hint table).
      const n = Math.min(a.length, b.length);
      if (n < 2) return null;
      const xa = a.slice(a.length - n), xb = b.slice(b.length - n);
      const ma = xa.reduce((s, v) => s + v, 0) / n;
      const mb = xb.reduce((s, v) => s + v, 0) / n;
      let num = 0, da = 0, db = 0;
      for (let i = 0; i < n; i++) {
        num += (xa[i] - ma) * (xb[i] - mb);
        da += (xa[i] - ma) ** 2;
        db += (xb[i] - mb) ** 2;
      }
      const den = Math.sqrt(da * db);
      return den > 0 ? Math.max(-1, Math.min(1, num / den)) : null;
    };

    const hint = (a: string, b: string) => (a === b ? 1 : (CORR[a]?.[b] ?? 0.5));
    const cells: Array<[number, number, number]> = [];
    const pairs: number[] = [];
    corrSymbols.forEach((a, i) => corrSymbols.forEach((b, j) => {
      let v: number;
      if (a === b) v = 1;
      else {
        const ra = returns[a], rb = returns[b];
        const p = ra && rb ? pearson(ra, rb) : null;
        v = p ?? hint(a, b);
      }
      cells.push([j, i, v]);
      if (j > i) pairs.push(v);
    }));
    const avg = pairs.length ? pairs.reduce((x, y) => x + y, 0) / pairs.length : 0;
    return { cells, avg };
  }, [corrSymbols, history.closes]);

  const corrOption: EChartsOption = useMemo(() => ({
    tooltip: {
      position: 'top',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      formatter: (p: unknown) => {
        const d = p as { data: [number, number, number] };
        return `<b>${corrSymbols[d.data[1]]} × ${corrSymbols[d.data[0]]}</b><br/>ρ = ${d.data[2].toFixed(2)}`;
      },
    },
    grid: { left: 44, right: 8, top: 8, bottom: 44 },
    xAxis: {
      type: 'category', data: corrSymbols,
      splitArea: { show: false },
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono },
    },
    yAxis: {
      type: 'category', data: corrSymbols,
      splitArea: { show: false },
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono },
    },
    visualMap: {
      show: false, min: 0, max: 1, calculable: false, orient: 'horizontal',
      inRange: { color: ['rgba(122,255,120,0.06)', 'rgba(122,255,120,0.55)'] },
    },
    series: [{
      type: 'heatmap',
      data: corrData.cells,
      label: {
        show: true,
        formatter: (p: unknown) => {
          const d = p as { data: [number, number, number]; dataIndex: number };
          const i = Math.floor(d.dataIndex / corrSymbols.length);
          const j = d.dataIndex % corrSymbols.length;
          return i === j ? '—' : d.data[2].toFixed(2);
        },
        color: theme.foreground,
        fontFamily: theme.fontMono,
        fontSize: 9,
      },
      itemStyle: { borderColor: 'rgba(255,255,255,0.04)', borderWidth: 2, borderRadius: 4 },
      emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.4)' } },
    }],
  }), [corrSymbols, corrData, theme]);

  // ── What-if trade ─────────────────────────────────────────────────────────
  const whatIf = useMemo(() => {
    const qty = Math.max(0, parseFloat(wiQty) || 0);
    const price = priceOf(wiSymbol);
    const fx = (metaOf(wiSymbol)?.currency ?? 'USD') === 'PKR' ? 1 / usdPkr : 1;
    const holding = stats.holdings.find(h => h.symbol === wiSymbol);
    const heldQty = holding?.quantity ?? 0;
    const delta = wiSide === 'Buy' ? qty : -Math.min(qty, heldQty);
    const cost = delta * price; // native currency
    const newCash = AVAILABLE_CASH - cost * fx; // cash is USD
    const newVal = ((holding?.quantity ?? 0) + delta) * price * fx;
    const projTotal = stats.totalValue + cost * fx;
    const newWeight = projTotal > 0 ? (newVal / projTotal) * 100 : 0;
    const oldWeight = holding ? weightOf(holding) * 100 : 0;

    const projBeta = stats.holdings.reduce((a, h) => {
      const w = h.symbol === wiSymbol ? (newVal / (projTotal || 1)) : weightOf(h);
      return a + (RISK[h.symbol]?.beta ?? RISK.DEFAULT.beta) * w;
    }, 0) + (!holding && delta > 0 ? (RISK[wiSymbol]?.beta ?? RISK.DEFAULT.beta) * (newVal / (projTotal || 1)) : 0);

    return { qty, price, fx, delta, cost, newCash, newWeight, oldWeight, newBeta: projBeta };
  }, [wiQty, wiSymbol, wiSide, stats.holdings, stats.totalValue, priceOf, weightOf, metaOf, usdPkr]);

  // ── Position sizing ───────────────────────────────────────────────────────
  const sizing = useMemo(() => {
    const entry = parseFloat(szEntry) || 0;
    const stop = parseFloat(szStop) || 0;
    const target = parseFloat(szTarget) || 0;
    const perUnit = entry - stop;
    const riskDollar = stats.totalValue * (szRisk / 100);
    const units = perUnit > 0 ? riskDollar / perUnit : 0;
    const posValue = units * entry;
    const rr = perUnit > 0 ? (target - entry) / perUnit : 0;
    return { entry, stop, target, units, posValue, rr, riskDollar };
  }, [szEntry, szStop, szTarget, szRisk, stats.totalValue]);

  // ── Monte Carlo projection ────────────────────────────────────────────────
  const monteCarlo = useMemo(() => {
    const mu = 0.45;
    const sigma = pVol / 100 || 0.6;
    const years = mcYears;
    const monthly = Math.max(0, parseFloat(mcMonthly) || 0);
    const steps = Math.max(12, years * 12);
    const proj = (z: number, tYears: number) => {
      const g = Math.exp((mu - 0.5 * sigma * sigma) * tYears + z * sigma * Math.sqrt(tYears));
      const annual = tYears > 0 ? Math.pow(g, 1 / tYears) - 1 : mu;
      const contrib = monthly * 12 * (annual !== 0 ? ((Math.pow(1 + annual, tYears) - 1) / annual) : tYears);
      return stats.totalValue * g + contrib;
    };
    const months = Array.from({ length: steps + 1 }, (_, i) => i);
    const p05 = months.map(m => proj(-1.645, m / 12));
    const p50 = months.map(m => proj(0, m / 12));
    const p95 = months.map(m => proj(1.645, m / 12));
    const bandOuter = p95.map((v, i) => Math.max(0, v - p05[i]));
    const totalContrib = monthly * 12 * years;
    return {
      months, p05, p50, p95, bandOuter,
      end: { lo: p05[steps], mid: p50[steps], hi: p95[steps] },
      totalContrib,
    };
  }, [mcYears, mcMonthly, pVol, stats.totalValue]);

  const mcOption: EChartsOption = useMemo(() => ({
    animationDuration: 600,
    grid: { left: 8, right: 8, top: 16, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      valueFormatter: (v) => fmtDK(Number(v)),
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: monteCarlo.months.map(m => (m % 12 === 0 ? `Y${m / 12}` : '')),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono, interval: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: theme.border } },
      axisLabel: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono, formatter: (v: number) => fmtDK(v) },
    },
    series: [
      {
        name: 'Floor (5th pct)',
        type: 'line', stack: 'band-outer', data: monteCarlo.p05, symbol: 'none',
        lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, silent: true, tooltip: { show: false },
      },
      {
        name: 'Optimistic band',
        type: 'line', stack: 'band-outer', data: monteCarlo.bandOuter, symbol: 'none',
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(122,255,120,0.10)' }, silent: true, tooltip: { show: false },
      },
      {
        name: 'Median path',
        type: 'line', data: monteCarlo.p50, symbol: 'none', smooth: true,
        lineStyle: { width: 2, color: theme.primary },
      },
      {
        name: 'Pessimistic (5%)',
        type: 'line', data: monteCarlo.p05, symbol: 'none', smooth: true,
        lineStyle: { width: 1, type: [3, 3], color: 'rgba(251,113,133,0.6)' },
      },
      {
        name: 'Optimistic (95%)',
        type: 'line', data: monteCarlo.p95, symbol: 'none', smooth: true,
        lineStyle: { width: 1, type: [3, 3], color: 'rgba(122,255,120,0.6)' },
      },
    ],
  }), [monteCarlo, theme, fmtD]);

  // ── Return attribution diverging bars ─────────────────────────────────────
  const attributionRows = useMemo(() =>
    stats.holdings
      .map(h => ({
        symbol: h.symbol,
        pts: (h.unrealizedPnLUsd / totalCost) * 100,
        dollar: h.unrealizedPnLUsd,
      }))
      .sort((a, b) => b.pts - a.pts),
    [stats.holdings, totalCost]);

  const attributionOption: EChartsOption = useMemo(() => ({
    animationDuration: 500,
    grid: { left: 8, right: 56, top: 6, bottom: 6, containLabel: true },
    tooltip: {
      trigger: 'item',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      formatter: (p: unknown) => {
        const d = p as { name: string; value: number; dataIndex: number };
        const row = attributionRows[d.dataIndex];
        return `<b>${d.name}</b><br/>${row.dollar >= 0 ? '+' : ''}${fmtD(row.dollar)} contribution`;
      },
    },
    xAxis: { type: 'value', splitLine: { show: false }, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false } },
    yAxis: {
      type: 'category',
      data: attributionRows.map(r => r.symbol),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11, fontWeight: 600 },
    },
    series: [{
      type: 'bar',
      barWidth: 12,
      data: attributionRows.map(r => ({
        value: Number(r.pts.toFixed(2)),
        itemStyle: {
          color: new echarts.graphic.LinearGradient(1, 0, 0, 0, [
            { offset: 0, color: r.pts >= 0 ? 'rgba(52,211,153,0.9)' : 'rgba(251,113,133,0.9)' },
            { offset: 1, color: r.pts >= 0 ? 'rgba(52,211,153,0.3)' : 'rgba(251,113,133,0.3)' },
          ]),
          borderRadius: 3,
        },
        label: {
          show: true, position: 'right',
          formatter: (p: unknown) => `${(p as { value: number }).value >= 0 ? '+' : ''}${(p as { value: number }).value.toFixed(1)} pts`,
          color: r.pts >= 0 ? UP : DOWN,
          fontFamily: theme.fontMono, fontSize: 10,
        },
      })),
      markLine: {
        silent: true, symbol: 'none', data: [{ xAxis: 0 }],
        lineStyle: { color: 'rgba(255,255,255,0.25)', width: 1 }, label: { show: false },
      },
    }],
  }), [attributionRows, theme, fmtD]);

  // ── Cost basis comparison chart ───────────────────────────────────────────
  const costBasisOption: EChartsOption = useMemo(() => ({
    animationDuration: 500,
    grid: { left: 8, right: 8, top: 20, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: theme.tooltipBg,
      borderColor: theme.tooltipBorder,
      textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      valueFormatter: (v) => fmtD(Number(v), 2),
    },
    legend: {
      top: 0, right: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 10,
      textStyle: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono },
    },
    xAxis: {
      type: 'category',
      data: stats.holdings.map(h => h.symbol),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: theme.foreground, fontFamily: theme.fontMono, fontWeight: 600, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: theme.border } },
      axisLabel: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono, formatter: (v: number) => fmtDK(v) },
    },
    series: [
      {
        name: 'Avg cost',
        type: 'bar', barWidth: 14, barGap: '20%',
        itemStyle: { color: 'rgba(251,191,36,0.65)', borderRadius: [4, 4, 0, 0] },
        data: stats.holdings.map(h => Number((h.avgCost * h.fxToUsd).toFixed(2))),
      },
      {
        name: 'Live price (USD-eq.)',
        type: 'bar', barWidth: 14,
        itemStyle: { color: 'rgba(122,255,120,0.75)', borderRadius: [4, 4, 0, 0] },
        data: stats.holdings.map(h => Number((h.currentPrice * h.fxToUsd).toFixed(2))),
      },
    ],
  }), [stats.holdings, theme]);

  // Risk headline label
  const divScore = useMemo(() => {
    const n = Math.max(stats.holdings.length, 1);
    if (stats.holdings.length === 0) return 0;
    const hhi = stats.holdings.reduce((a, h) => a + weightOf(h) * weightOf(h), 0);
    return Math.round((1 - (hhi - 1 / n) / (1 - 1 / n)) * 100);
  }, [stats.holdings, weightOf]);

  // ── Health score + Eclipse brief (deterministic decision engine) ──────────
  const healthMeta = useMemo(() => {
    const meta: Record<string, HoldingMeta> = {};
    stats.holdings.forEach(h => {
      const r = RISK[h.symbol] ?? RISK.DEFAULT;
      meta[h.symbol] = {
        name: metaOf(h.symbol)?.name ?? h.symbol,
        category: metaOf(h.symbol)?.category ?? 'Other',
        dayPct: h.dayPct,
        beta: r.beta,
        vol: r.vol,
        sharpe: r.sharpe,
        mdd: r.mdd,
        target: r.target,
        aiTag: metaOf(h.symbol)?.aiTag,
      };
    });
    return meta;
  }, [stats.holdings, metaOf]);

  const health = useMemo(
    () => computeHealthScore(stats.holdings, healthMeta),
    [stats.holdings, healthMeta]
  );
  const brief = useMemo(
    () => buildBrief(stats, stats.holdings, healthMeta),
    [stats, healthMeta]
  );
  const changes = useMemo(
    () => buildChanges(stats.holdings, healthMeta),
    [stats.holdings, healthMeta]
  );

  // ── Health gauge (ECharts) ────────────────────────────────────────────────
  const healthGaugeOption: EChartsOption = useMemo(() => ({
    animationDuration: 700,
    series: [{
      type: 'gauge',
      startAngle: 210,
      endAngle: -30,
      min: 0,
      max: 100,
      radius: '98%',
      center: ['50%', '58%'],
        progress: {
          show: true,
          width: 12,
          roundCap: true,
          itemStyle: {
            color: health.total >= 50 ? '#7aff78' : '#ff3e3e',
          },
        },
      pointer: { show: false },
      axisLine: { roundCap: true, lineStyle: { width: 12, color: [[1, 'rgba(255,255,255,0.07)']] } },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      title: { show: false },
      detail: {
        valueAnimation: true,
        offsetCenter: [0, '-2%'],
        fontSize: 30,
        fontWeight: 700,
        fontFamily: theme.fontMono,
        color: theme.foreground,
        formatter: (v: number) => `${Math.round(v)}`,
      },
      data: [{ value: health.total, name: 'Health' }],
    }],
  }), [health.total, theme]);

  // ── Risk radar (ECharts) ──────────────────────────────────────────────────
  const riskRadarScores = useMemo(() => {
    // Map raw metrics onto 0-100 where 100 = best risk posture.
    // Scales are calibrated to realistic ranges: vol 20%→100 / 90%→0,
    // drawdown -10%→100 / -60%→0, sharpe 0→0 / 2→100. Without this the
    // polygon collapses to 0 for ordinary crypto-heavy books.
    const clamp100 = (n: number) => Math.max(0, Math.min(100, Math.round(n)));
    return [
      { label: 'Diversification', v: clamp100(divScore) },
      { label: 'Low Volatility', v: clamp100(((90 - pVol) / 70) * 100) },
      { label: 'Drawdown Safety', v: clamp100(((pMdd + 60) / 50) * 100) },
      { label: 'Risk-Adj. Return', v: clamp100(pSharpe * 50) },
      { label: 'Low Correlation', v: clamp100((1 - corrData.avg) * 100) },
    ];
  }, [divScore, pVol, pMdd, pSharpe, corrData.avg]);

  const riskRadarOption: EChartsOption = useMemo(() => {
    const values = riskRadarScores.map(s => s.v);
    const clampAvg = values.reduce((a, b) => a + b, 0) / values.length;
    const betaTxt = pBeta > 1 ? 'aggressive' : pBeta < 0.8 ? 'defensive' : 'market-like';
    // Branding: green when the risk posture is healthy, red when fragile.
    const radarColor = clampAvg >= 50 ? '#7aff78' : '#ff3e3e';
    const radarGlow = clampAvg >= 50 ? 'rgba(122,255,120,' : 'rgba(255,62,62,';
    return {
      tooltip: {
        backgroundColor: theme.tooltipBg,
        borderColor: theme.tooltipBorder,
        textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
      },
      radar: {
        // Explicit polygon shape; nameGap keeps axis names off the ring
        // without clipping at panel edges.
        shape: 'polygon',
        indicator: [
          { name: 'Diversification', max: 100 },
          { name: 'Low Volatility', max: 100 },
          { name: 'Drawdown Safety', max: 100 },
          { name: 'Risk-Adj. Return', max: 100 },
          { name: 'Low Correlation', max: 100 },
        ],
        radius: '55%',
        center: ['50%', '52%'],
        splitNumber: 4,
        nameGap: 14,
        axisName: { color: theme.muted, fontSize: 10, fontFamily: theme.fontMono },
        splitLine: { lineStyle: { color: theme.border } },
        splitArea: { show: false },
        axisLine: { lineStyle: { color: theme.border } },
      },
      series: [{
        type: 'radar',
        symbol: 'circle',
        symbolSize: 5,
        data: [{
          value: values,
          name: `Risk profile (${betaTxt})`,
          lineStyle: { width: 2, color: radarColor },
          itemStyle: { color: radarColor },
          areaStyle: { color: `${radarGlow}0.20)` },
        }],
      }],
    } as EChartsOption;
  }, [riskRadarScores, pBeta, theme]);

  // ── Exposure treemap (ECharts) ────────────────────────────────────────────
  // Branding: green when the holding (or category) is up, red when down.
  const treemapOption: EChartsOption = useMemo(() => {
    const cats = new Map<string, Array<{ name: string; value: number; day: number }>>();
    stats.holdings.forEach(h => {
      const cat = metaOf(h.symbol)?.category ?? 'Other';
      const arr = cats.get(cat) ?? [];
      arr.push({ name: h.symbol, value: Number(h.valueUsd.toFixed(2)), day: h.dayPct });
      cats.set(cat, arr);
    });
    const cellColor = (day: number) =>
      day >= 0
        ? `rgba(122,255,120,${Math.min(0.85, 0.28 + Math.abs(day) * 0.12)})`
        : `rgba(255,62,62,${Math.min(0.85, 0.28 + Math.abs(day) * 0.12)})`;
    return {
      animationDuration: 600,
      tooltip: {
        backgroundColor: theme.tooltipBg,
        borderColor: theme.tooltipBorder,
        textStyle: { color: theme.foreground, fontFamily: theme.fontMono, fontSize: 11 },
        formatter: (p: unknown) => {
          const d = p as { name: string; value: number; data?: { day?: number } };
          const pct = stats.totalValue > 0 ? ((d.value / stats.totalValue) * 100).toFixed(1) : '0';
          const day = d.data?.day;
          return `<b>${d.name}</b><br/>${fmtD(d.value)} · ${pct}% of NAV${day !== undefined ? `<br/><span style="color:${day >= 0 ? '#7aff78' : '#ff3e3e'}">${day >= 0 ? '+' : ''}${day.toFixed(2)}% today</span>` : ''}`;
        },
      },
      series: [{
        type: 'treemap',
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        itemStyle: { borderColor: 'rgba(0,0,0,0.6)', borderWidth: 1.5, gapWidth: 2, borderRadius: 8 },
        upperLabel: {
          show: true, height: 22, color: '#ffffff', fontFamily: theme.fontMono, fontSize: 10, fontWeight: 700,
          textBorderColor: 'rgba(0,0,0,0.6)',
          textBorderWidth: 2,
          formatter: (p: unknown) => {
            const d = p as { name: string; value: number; children?: Array<{ day: number; value: number }> };
            const kids = d.children ?? [];
            const wday = kids.reduce((a, c) => a + c.day * c.value, 0) / (kids.reduce((a, c) => a + c.value, 0) || 1);
            return `${d.name}  ${wday >= 0 ? '+' : ''}${wday.toFixed(2)}%`;
          },
        },
        levels: [
          {
            itemStyle: { gapWidth: 4, borderColor: 'rgba(0,0,0,0.65)', borderWidth: 2, borderRadius: 10 },
          },
          {
            colorMappingBy: 'value',
            itemStyle: { borderColorSaturation: 0.55, gapWidth: 2, borderRadius: 6 },
          },
        ],
        label: {
          show: true,
          fontFamily: theme.fontMono,
          fontSize: 10.5,
          fontWeight: 700,
          color: '#ffffff',
          textBorderColor: 'rgba(0,0,0,0.6)',
          textBorderWidth: 2,
          formatter: (p: unknown) => {
            const d = p as { name: string; value: number; data?: { day?: number } };
            const pct = stats.totalValue > 0 ? Math.round((d.value / stats.totalValue) * 100) : 0;
            const day = d.data?.day;
            return `${d.name}\n${pct}%${day !== undefined ? `  ${day >= 0 ? '+' : ''}${day.toFixed(1)}%` : ''}`;
          },
        },
        data: [...cats.entries()].map(([cat, children]) => {
          const wsum = children.reduce((a, c) => a + c.value, 0);
          const wday = children.reduce((a, c) => a + c.day * c.value, 0) / (wsum || 1);
          return {
            name: cat,
            itemStyle: { color: cellColor(wday) },
            children: children.map(c => ({
              ...c,
              itemStyle: { color: cellColor(c.day) },
            })),
          };
        }),
      }],
    } as EChartsOption;
  }, [stats.holdings, stats.totalValue, metaOf, theme]);

  const bestMover = useMemo(() =>
    holdingsRows.length ? [...holdingsRows].sort((a, b) => b.dayPct - a.dayPct)[0] : null,
    [holdingsRows]);

  const riskLabel = useMemo(() => {
    if (stats.holdings.length === 0) return 'No risk data yet.';
    const maxAlloc = stats.holdings[0]?.allocation ?? 0;
    if (maxAlloc > 60) return 'High concentration — single-asset dominance.';
    if (maxAlloc > 40) return 'Moderate concentration — balanced exposure.';
    return 'Well diversified across the complex.';
  }, [stats.holdings]);

  const aiInsights = useMemo(() =>
    stats.holdings.filter(h => metaOf(h.symbol)?.aiTag).slice(0, 4)
      .map(h => ({ ticker: h.symbol, text: metaOf(h.symbol)!.aiTag! })),
    [stats.holdings, metaOf]);

  if (loadingLive || loadingPortfolio) {
    return (
      <>
        <TopLoader />
        <div className="space-y-6 p-6 md:p-10">
          <SkeletonHeader />
          <SkeletonCardGrid count={4} />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <SkeletonPanel className="lg:col-span-2 h-96" />
            <SkeletonPanel className="h-96" />
          </div>
          <SkeletonTable rows={3} />
        </div>
      </>
    );
  }

  // ─── FUND TAB STRIP (visible in both views) ────────────────────────────────
  const fundTabs = (
    <div className="flex items-center gap-2 flex-wrap">
      <button
        onClick={() => setViewMode('overview')}
        className={`flex items-center gap-2 px-4 py-2 rounded-full text-xs font-semibold border transition-all cursor-pointer shrink-0 ${
          viewMode === 'overview'
            ? 'bg-primary/15 border-primary/50 text-primary'
            : 'border-border/40 text-muted-foreground hover:text-foreground hover:border-primary/30 bg-card/40'
        }`}
      >
        <LayoutDashboard className="w-3.5 h-3.5" />
        Overview
      </button>
      {funds.map(f => {
        const Icon = FUND_ICONS[f.icon] ?? Briefcase;
        const active = viewMode === f.id;
        return (
          <button
            key={f.id}
            onClick={() => setViewMode(f.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-full text-xs font-semibold border transition-all cursor-pointer shrink-0 ${
              active
                ? 'text-foreground'
                : 'border-border/40 text-muted-foreground hover:text-foreground hover:border-primary/30 bg-card/40'
            }`}
            style={active ? { background: `${f.color}1f`, borderColor: `${f.color}80` } : { borderColor: undefined }}
          >
            <Icon className="w-3.5 h-3.5" style={{ color: f.color }} />
            {f.name}
          </button>
        );
      })}
      <button
        onClick={openCreateFundDialog}
        title="Create a new fund"
        className="flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-semibold border border-dashed border-border/50 text-muted-foreground hover:text-primary hover:border-primary/50 transition-all cursor-pointer shrink-0"
      >
        <Plus className="w-3.5 h-3.5" /> New Fund
      </button>
    </div>
  );

  return (
    <div className="space-y-8 p-6 md:p-10 font-sans bg-transparent min-h-screen text-foreground animate-in fade-in duration-500 relative overflow-x-hidden">

      {/* ─── HEADER ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 border-b border-border/40 pb-6">
        <div>
          <h1 className="text-3xl md:text-4xl font-serif font-semibold tracking-tight flex items-center gap-3 flex-wrap">
            {viewMode === 'overview'
              ? <PieChart className="h-9 w-9 text-primary" />
              : (() => { const I = FUND_ICONS[activeFund?.icon ?? 'briefcase'] ?? Briefcase; return <I className="h-9 w-9" style={{ color: activeFund?.color }} />; })()}
            {viewMode === 'overview' ? 'Portfolio Overview' : (activeFund?.name ?? 'Portfolio')}
          </h1>
          <p className="text-muted-foreground text-sm mt-2">
            {viewMode === 'overview'
              ? `Aggregated performance across ${funds.length} fund${funds.length === 1 ? '' : 's'} — click any card to open a fund.`
              : 'Holdings, performance, and AI-driven insights in real time.'}
          </p>
        </div>

        {viewMode !== 'overview' && (
          <div className="flex flex-wrap items-center gap-4">
            <select
              value={displayFx}
              onChange={e => setDisplayCurrency(e.target.value)}
              title="Display currency — all totals and charts convert instantly"
              className="bg-muted/20 border border-border/40 rounded-xl px-3 py-2.5 text-xs font-mono outline-none focus:border-primary/50 cursor-pointer text-foreground [&>option]:bg-[#1a1a1a] [&>option]:text-foreground"
            >
              {DISPLAY_CURRENCIES.map(c => (
                <option key={c.code} value={c.code}>{c.code}</option>
              ))}
            </select>
            <Button
              variant="outline"
              className="border-border/50 text-muted-foreground hover:text-foreground rounded-xl px-4 py-5 text-sm cursor-pointer flex items-center gap-2"
              onClick={() => openEditFundDialog(activeFund!)}
            >
              <SquarePen className="w-4 h-4" /> Edit Fund
            </Button>
            <Button
              className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-xl px-5 py-5 text-sm transition-all shadow-lg shadow-primary/15 flex items-center gap-2 cursor-pointer"
              onClick={() => { setTxType('BUY'); setIsAddOpen(true); }}
            >
              <Plus className="w-4 h-4" />
              Add Transaction
            </Button>
          </div>
        )}
      </div>

      {/* ─── FUND TABS ───────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[10px] uppercase tracking-wider font-mono text-muted-foreground">Funds</span>
        {fundTabs}
      </div>

      {viewMode === 'overview' && (
        <OverviewView
          funds={funds}
          usdPkr={usdPkr}
          liveAssets={liveAssets}
          onOpenFund={(id) => setViewMode(id)}
          onEditFund={openEditFundDialog}
          onDeleteFund={handleDeleteFund}
          onCreateFund={openCreateFundDialog}
          onAnalyzeTicker={onAnalyzeTicker}
          displayFx={displayFx}
          fxRates={fxRates}
          hasFx={hasFx}
          fundHistory={{ closes: fundHistRaw.closes, dates: fundHistRaw.dates }}
          fmtD={fmtD}
          fmtDK={fmtDK}
          dispLabel={DISP_LABEL}
        />
      )}
      {viewMode !== 'overview' && (<>

      {/* ─── CUSTOMIZE TOOLBAR ──────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <span className="text-[10px] uppercase tracking-wider font-mono text-muted-foreground flex items-center gap-1.5">
          <LayoutDashboard className="w-3.5 h-3.5" /> {activeFund?.name ?? 'Portfolio'}
        </span>
        <button
          onClick={() => setFundCustomizing((v) => !v)}
          className={`flex items-center gap-1.5 text-[11px] font-bold tracking-wider border rounded-lg px-3 py-1.5 transition-all cursor-pointer ${
            fundCustomizing
              ? 'text-zinc-900 dark:text-zinc-100 bg-zinc-500/30 dark:bg-zinc-400/20 border-zinc-500/60 dark:border-zinc-400/50 shadow-inner backdrop-blur-md'
              : 'text-muted-foreground hover:text-primary bg-accent/40 hover:bg-accent/70 border-border/40'
          }`}
          title="Rearrange, show/hide, and resize widgets with the mouse"
        >
          <Settings2 className="w-3.5 h-3.5" /> {fundCustomizing ? 'Done' : 'Customize'}
        </button>
      </div>

      {/* Inline customize panel — templates, drag rows to reorder, resize */}
      {fundCustomizing && (
        <div className="edit-mode-banner px-3 py-2 animate-fade-in-up flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-zinc-500 dark:bg-zinc-400 animate-pulse shrink-0" />
          <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-200">Edit mode — drag, resize, or hide widgets below · applies to every fund</p>
        </div>
      )}

      {fundCustomizing && (
        <div className={`${PANEL} p-4 animate-fade-in-up space-y-4 ring-1 ring-zinc-400/30 dark:ring-zinc-500/25`}>
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-bold uppercase tracking-wider">Page Layout — applies to every fund</p>
            <button
              onClick={resetFundLayout}
              className="text-[10px] font-bold text-muted-foreground hover:text-rose-400 uppercase tracking-wider cursor-pointer transition-colors flex items-center gap-1"
            >
              <RotateCcw className="w-3 h-3" /> Reset
            </button>
          </div>

          {/* Design templates */}
          <div>
            <p className="text-[9px] uppercase font-bold text-muted-foreground/70 tracking-wider mb-1.5">Templates</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
              {FUND_TEMPLATES.map((t) => (
                <button
                  key={t.id}
                  onClick={() => persistFundLayout(t.build())}
                  title={t.desc}
                  className={`${TILE} p-2.5 text-left hover:border-zinc-400/60 dark:hover:border-zinc-500/50 hover:bg-zinc-500/[0.06] dark:hover:bg-zinc-400/[0.04] transition-all cursor-pointer`}
                >
                  <TemplateMiniGrid rows={t.preview} />
                  <p className="text-[11px] font-bold mt-2">{t.name}</p>
                  <p className="text-[9px] text-muted-foreground leading-snug">{t.desc}</p>
                </button>
              ))}
            </div>
          </div>

          <p className="text-[10px] text-muted-foreground">
            Drag rows (or the cards themselves) to reorder · click a card to select it, then use the keyboard: arrows move, Shift+arrows resize width/height, +/− height, X hides · eye toggles visibility · S–XL sets width. You can also drag a widget&apos;s edge or corner handles directly on the page.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {fundLayout.widgets.map((w) => {
              const meta = FUND_WIDGET_META[w.id];
              return (
                <div
                  key={w.id}
                  draggable
                  onDragStart={(e) => { e.dataTransfer.effectAllowed = 'move'; setFundDrag(w.id); }}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => { e.preventDefault(); if (fundDrag) moveFundWidget(fundDrag, w.id); setFundDrag(null); }}
                  className={`${TILE} ${w.visible ? '' : 'opacity-45'} p-2.5 flex items-center gap-2 cursor-grab active:cursor-grabbing transition-all duration-150 ${fundDrag === w.id ? 'opacity-40 scale-[0.98]' : fundDrag ? 'ring-1 ring-zinc-400/50 dark:ring-zinc-400/40' : ''} ${selectedWidget === w.id ? 'ring-1 ring-zinc-500/80 dark:ring-zinc-400/70 bg-zinc-500/[0.10] dark:bg-zinc-400/[0.08]' : ''}`}
                  onClick={() => setSelectedWidget(w.id)}
                >
                  <span className={`flex items-center justify-center w-6 h-6 rounded-lg ${EDIT_GRIP} shrink-0 cursor-grab active:cursor-grabbing`} title="Drag to reorder">
                    <GripVertical className="w-3.5 h-3.5 text-zinc-200" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-bold truncate">{meta.label}</p>
                  </div>
                  <div className="flex items-center gap-0.5 shrink-0">
                    {([1, 2, 3, 4] as const).map((s) => (
                      <button
                        key={s}
                        onClick={(e) => { e.stopPropagation(); patchFundWidget(w.id, { span: s }); }}
                        title={`${SPAN_LABEL[s]} width`}
                        className={`w-5 h-5 rounded-md text-[9px] font-bold cursor-pointer transition-colors border ${
                          w.span === s
                            ? 'bg-zinc-600/80 dark:bg-zinc-300/25 text-white dark:text-zinc-100 border-zinc-600 dark:border-zinc-400/60'
                            : 'text-zinc-600 dark:text-zinc-400 border-zinc-400/30 dark:border-zinc-500/25 hover:bg-zinc-500/15 dark:hover:bg-zinc-400/10'
                        }`}
                      >
                        {SPAN_LABEL[s]}
                      </button>
                    ))}
                    {/* Height stepper */}
                    <button
                      onClick={(e) => { e.stopPropagation(); patchFundWidget(w.id, { height: Math.min(10, w.height + 1) }); }}
                      title="Taller (+40px)"
                      className="w-5 h-5 rounded-md text-[9px] font-bold cursor-pointer transition-colors border text-zinc-600 dark:text-zinc-400 border-zinc-400/30 dark:border-zinc-500/25 hover:bg-zinc-500/15 dark:hover:bg-zinc-400/10"
                    >
                      +
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); patchFundWidget(w.id, { height: Math.max(0, w.height - 1) }); }}
                      title="Shorter (−40px)"
                      className="w-5 h-5 rounded-md text-[9px] font-bold cursor-pointer transition-colors border text-zinc-600 dark:text-zinc-400 border-zinc-400/30 dark:border-zinc-500/25 hover:bg-zinc-500/15 dark:hover:bg-zinc-400/10"
                    >
                      −
                    </button>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); patchFundWidget(w.id, { visible: !w.visible }); }}
                    title={w.visible ? 'Hide' : 'Show'}
                    className={`p-1 rounded-md cursor-pointer transition-colors shrink-0 ${w.visible ? 'text-zinc-200 hover:bg-zinc-500/15 dark:hover:bg-zinc-400/10' : 'text-muted-foreground hover:text-foreground'}`}
                  >
                    {w.visible ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ─── LAYOUT-DRIVEN WIDGET FLOW ──────────────────────────────────────── */}
      <div
        className={`fund-widget-flow${fundCustomizing ? ' customizing' : ''}`}
        onClick={(e) => { if (fundCustomizing && e.target === e.currentTarget) setSelectedWidget(null); }}
      >
      {fundLayout.widgets.filter((w) => w.visible).map((w) => {
        const heightCls = w.height > 0 ? { minHeight: `${w.height * 40}px` } : undefined;
        const shellProps = {
          customizing: fundCustomizing,
          dragId: fundDrag,
          span: w.span as FundWidgetLayout['span'],
          onDragStart: (id: FundWidgetId) => setFundDrag(id),
          onDrop: (target: FundWidgetId) => { if (fundDrag) moveFundWidget(fundDrag, target); },
          onResizeStart: onWidgetResizeStart,
          onSelectWidget: setSelectedWidget,
        };
        switch (w.id) {
          case 'kpi-board':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps} heightStyle={heightCls}>
                <div className="h-full grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
        <div className={`${PANEL} p-6 relative overflow-hidden group hover:border-primary/45 transition-all`}>
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
              <Wallet className="w-4 h-4 text-primary" /> Net Asset Value
            </span>
            <span className="text-xs font-mono text-muted-foreground">{DISP_LABEL}</span>
          </div>
          <span className="text-3xl font-mono font-bold tracking-tight block">{fmtD(stats.totalValue)}</span>
          <div className={`flex items-center gap-1.5 text-xs font-semibold mt-1 ${stats.dailyChangeValue >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {stats.dailyChangeValue >= 0 ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
            {fmtD(stats.dailyChangeValue)} ({fmtPct(stats.dailyChangePercent)}) today
          </div>
          {DISP_LABEL !== 'USD' && fxAsOf && (
            <div className="text-[9.5px] text-muted-foreground/70 mt-1.5">
              1 USD = {hasFx ? fxRate.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '—'} {DISP_LABEL} · rates as of{' '}
              {new Date(fxAsOf).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
            </div>
          )}
        </div>

        <div className={`${PANEL} p-6 group hover:border-primary/45 transition-all`}>
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
              <Activity className="w-4 h-4 text-primary" /> Today&apos;s P/L
            </span>
          </div>
          <span className={`text-3xl font-mono font-bold tracking-tight block ${stats.dailyChangeValue >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {fmtD(stats.dailyChangeValue)}
          </span>
          <span className="text-xs text-muted-foreground mt-1 block">Mark-to-market, 24h window · {DISP_LABEL}-equivalent</span>
        </div>

        <div className={`${PANEL} p-6 group hover:border-primary/45 transition-all`}>
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-primary" /> Unrealized P/L
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-muted/50 border border-border/30 text-muted-foreground">All time</span>
          </div>
          <span className={`text-3xl font-mono font-bold tracking-tight block ${stats.unrealizedPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {stats.unrealizedPnL >= 0 ? '+' : '-'}{fmtD(Math.abs(stats.unrealizedPnL))}
          </span>
          <div className="text-xs mt-1 flex items-center gap-1">
            <span className="text-muted-foreground">ROI</span>
            <span className={`font-semibold ${stats.roiPercent >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtPct(stats.roiPercent)}</span>
          </div>
        </div>

        <div className={`${PANEL} p-6 group hover:border-primary/45 transition-all`}>
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-mono tracking-wider uppercase text-muted-foreground flex items-center gap-2">
              <DollarSign className="w-4 h-4 text-primary" /> Available Cash
            </span>
            <span className="text-[10px] px-2 py-0.5 rounded bg-muted/50 border border-border/30 text-muted-foreground">Deployable</span>
          </div>
          <span className="text-3xl font-mono font-bold tracking-tight block">{fmtD(AVAILABLE_CASH)}</span>
          <span className="text-xs text-muted-foreground mt-1 block">
            Realized P/L {stats.realizedPnL >= 0 ? '+' : '-'}{fmtD(Math.abs(stats.realizedPnL))} · FIFO
            {stats.dividendsUsd > 0 && (
              <> · Dividends <span className="text-amber-300 font-semibold">+{fmtD(stats.dividendsUsd)}</span></>
            )}
          </span>
        </div>
      </div>
              </FundWidgetShell>
            );
          case 'performance':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} flex flex-col h-full`}>
          <div className="p-5 border-b border-border/30 flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3 flex-wrap">
              <h3 className="text-md font-serif font-semibold">Performance</h3>
              {performanceSeries.real ? (
                <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <svg width="16" height="6"><line x1="0" y1="3" x2="16" y2="3" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 3" /></svg>
                  vs {performanceSeries.benchLabel || 'cost basis'}
                  <span className={`font-mono font-semibold ${perfDelta.port >= perfDelta.bench ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {fmtPct(perfDelta.port - perfDelta.bench)}
                  </span>
                  {twr !== null && (
                    <span className="font-mono" title="Time-weighted return over the window — the standard performance metric">
                      · TWR <span className={twr >= 0 ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>{fmtPct(twr)}</span>
                    </span>
                  )}
                </span>
              ) : (
                <span className="text-[11px] text-muted-foreground font-mono">Loading real market history…</span>
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <select
                value={benchmarkId}
                onChange={e => setBenchmarkId(e.target.value)}
                className="bg-muted/20 border border-border/30 rounded-lg px-2 py-1.5 text-[10px] font-mono outline-none focus:border-primary/50 cursor-pointer text-foreground max-w-[150px] [&>option]:bg-[#1a1a1a] [&>option]:text-foreground [&>option]:text-[11px]"
                title="Benchmark to compare portfolio performance against"
              >
                {BENCHMARKS.map(b => (
                  <option key={b.id} value={b.id}>vs {b.label}</option>
                ))}
              </select>
              <div className="flex bg-muted/20 border border-border/30 rounded-lg p-0.5">
                {(['1D', '7D', '1M', 'ALL'] as const).map(tf => (
                  <button
                    key={tf}
                    onClick={() => setTimeframe(tf)}
                    className={`px-3 py-1 text-[10px] font-mono rounded-md transition-all cursor-pointer ${
                      timeframe === tf ? 'bg-accent text-foreground font-semibold' : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            </div>
          </div>
            <div className="p-4 flex-1 min-h-[300px]">
              {performanceSeries.real ? (
                <EChart option={perfOption} height={420} />
              ) : (
                <div className="h-full min-h-[300px] flex items-center justify-center">
                  <p className="text-xs text-muted-foreground font-mono text-center">
                    Fetching real daily closes for your holdings…<br />
                    <span className="text-[10px] text-muted-foreground/70">No simulated data is shown — charts appear once market history is retrieved.</span>
                  </p>
                </div>
              )}
            </div>
                </div>
              </FundWidgetShell>
            );
          case 'allocation':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} p-5 h-full`}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-md font-serif font-semibold flex items-center gap-2">
                <PieChart className="w-4 h-4 text-primary" /> Allocation
              </h3>
              <span className="text-[11px] font-mono text-muted-foreground">
                Top: <span className="text-primary font-semibold">{stats.holdings[0]?.symbol ?? '—'} {(stats.holdings[0]?.allocation ?? 0).toFixed(0)}%</span>
              </span>
            </div>
            {stats.holdings.length > 0 ? (
              <>
                <EChart option={allocationOption} height={170} />
                <div className="mt-3 space-y-1.5 max-h-[104px] overflow-y-auto pr-1">
                  {stats.holdings.slice(0, 6).map((h, i) => (
                    <div key={h.symbol} className="flex items-center gap-2 text-xs font-mono">
                      <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }}></span>
                      <span className="font-semibold flex-1 truncate">{h.symbol}</span>
                      <span className="text-muted-foreground">{h.allocation.toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-xs text-muted-foreground font-mono text-center py-10">No active balances to chart.</p>
            )}
                </div>
              </FundWidgetShell>
            );
          case 'ai-insights':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className="rounded-2xl p-5 h-full bg-primary/[0.06] border border-primary/20">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="w-4 h-4 text-primary" />
              <h3 className="text-md font-serif font-semibold text-primary">AI Insights</h3>
            </div>
            <div className="space-y-2.5">
              {aiInsights.length > 0 ? aiInsights.map(ins => (
                <p key={ins.ticker} className="text-[12.5px] leading-relaxed text-foreground/80">
                  <span className="font-mono font-bold text-primary">{ins.ticker}</span> — {ins.text}
                </p>
              )) : (
                <p className="text-xs text-muted-foreground">No active insights — add holdings to generate signals.</p>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onAnalyzeTicker('PORTFOLIO')}
              className="mt-4 w-full border-primary/40 text-primary hover:bg-primary/10 font-mono text-xs cursor-pointer"
            >
              <Sparkles className="w-3.5 h-3.5 mr-1" />
              Discuss Portfolio With AI
            </Button>
                </div>
              </FundWidgetShell>
            );
          case 'risk-metrics':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} p-5 h-full`}>
          <h3 className="text-md font-serif font-semibold mb-4 flex items-center gap-2">
            <Shield className="w-4 h-4 text-primary" /> Risk &amp; Return Metrics
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {[
              { label: 'Beta vs BTC', value: pBeta.toFixed(2), note: pBeta > 1.2 ? 'High market sensitivity' : 'Market-like sensitivity' },
              { label: 'Volatility (ann.)', value: `${pVol.toFixed(1)}%`, note: pVol > 60 ? 'Above benchmark' : 'Moderate' },
              { label: 'Sharpe Ratio', value: pSharpe.toFixed(2), note: pSharpe > 1 ? 'Good risk-adj. return' : 'Weak risk-adjusted' },
              { label: 'Max Drawdown', value: `${pMdd.toFixed(1)}%`, note: 'Weighted historical' },
              {
                label: 'Diversification',
                value: `${divScore}/100`,
                note: `Top position ${(stats.holdings[0]?.allocation ?? 0).toFixed(0)}%`,
              },
              { label: 'Best 24h Mover', value: bestMover ? bestMover.symbol : '—', note: bestMover ? fmtPct(bestMover.dayPct) : 'No data', highlight: true },
            ].map(m => (
              <div key={m.label} className={`${TILE} p-3.5`}>
                <div className="text-[10.5px] text-muted-foreground mb-1.5">{m.label}</div>
                <div className={`font-mono text-lg font-bold ${m.highlight ? 'text-primary' : ''}`}>{m.value}</div>
                <div className="text-[10px] text-muted-foreground/70 mt-0.5">{m.note}</div>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground mt-4">{riskLabel}</p>
                </div>
              </FundWidgetShell>
            );
          case 'health':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} p-5 flex flex-col h-full`}>
          <div className="flex items-baseline justify-between mb-2 flex-wrap gap-2">
            <h3 className="text-md font-serif font-semibold flex items-center gap-2">
              <Gauge className="w-4 h-4 text-primary" /> Portfolio Health
            </h3>
            <span className="text-[11px] text-muted-foreground">
              {health.total >= 75 ? 'Strong' : health.total >= 50 ? 'Fair' : health.total > 0 ? 'Weak' : '—'}
            </span>
          </div>
          {stats.holdings.length > 0 ? (
            <>
              <EChart option={healthGaugeOption} height={130} />
              <div className="grid grid-cols-2 gap-2 mt-1">
                {[
                  { l: 'Diversification', v: health.breakdown.diversification },
                  { l: 'Risk', v: health.breakdown.risk },
                  { l: 'Momentum', v: health.breakdown.momentum },
                  { l: 'Concentration', v: health.breakdown.concentration },
                ].map(s => (
                  <div key={s.l} className="flex items-center gap-2">
                    <span className="text-[10px] text-muted-foreground flex-1">{s.l}</span>
                    <div className="h-1.5 w-16 bg-border/20 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${s.v}%`, background: s.v >= 35 ? '#7aff78' : '#ff3e3e' }} />
                    </div>
                    <span className="font-mono text-[10px] w-6 text-right">{s.v}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-xs text-muted-foreground font-mono text-center py-10">Health score unlocks with holdings.</p>
          )}
                </div>
              </FundWidgetShell>
            );
          case 'risk-radar':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} p-5 h-full`}>
          <h3 className="text-md font-serif font-semibold mb-1 flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" /> Risk Radar
          </h3>
          <p className="text-[11px] text-muted-foreground mb-2">Five dimensions of posture, higher = safer.</p>
          {stats.holdings.length > 0 ? (
            <>
              <EChart option={riskRadarOption} height={280} />
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-1">
                {riskRadarScores.map(s => (
                  <div key={s.label} className="flex items-center gap-2">
                    <span className="text-[10px] text-muted-foreground flex-1 truncate">{s.label}</span>
                    <div className="h-1 w-14 bg-border/20 rounded-full overflow-hidden shrink-0">
                      <div className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${s.v}%`, background: s.v >= 50 ? '#7aff78' : '#ff3e3e' }} />
                    </div>
                    <span className="font-mono text-[10px] w-6 text-right">{s.v}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-xs text-muted-foreground font-mono text-center py-16">Add holdings to map your risk profile.</p>
          )}
                </div>
              </FundWidgetShell>
            );
          case 'exposure-map':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} p-5 flex flex-col h-full`}>
          <div className="flex items-baseline justify-between mb-2 flex-wrap gap-2">
            <h3 className="text-md font-serif font-semibold flex items-center gap-2">
              <Grid3x3 className="w-4 h-4 text-primary" /> Exposure Map
            </h3>
            <span className="text-[11px] text-muted-foreground">Area = share of NAV, grouped by category</span>
          </div>
          <EChart option={treemapOption} height={480} className="-mx-2" />
          <div className="mt-3 pt-3 border-t border-border/20 space-y-1.5">
            <div className="text-[10px] uppercase tracking-wider font-mono text-muted-foreground mb-1">Eclipse Brief</div>
            {brief.map((line, i) => (
              <p key={i} className="text-[12px] text-foreground/80 leading-relaxed">• {line}</p>
            ))}
          </div>
                </div>
              </FundWidgetShell>
            );
          case 'changes':
            if (changes.length === 0) return null;
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} p-5`}>
          <h3 className="text-md font-serif font-semibold mb-3 flex items-center gap-2">
            <Flame className="w-4 h-4 text-primary" /> What Changed
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
            {changes.map(c => (
              <div key={c.id} className={`${TILE} p-3 flex items-start gap-2`}>
                <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${
                  c.severity === 'positive' ? 'bg-emerald-400' : c.severity === 'negative' ? 'bg-rose-400' : 'bg-amber-400'
                }`} />
                <div className="min-w-0">
                  <div className="text-xs text-foreground/90 leading-snug">{c.text}</div>
                  {c.symbol && (
                    <button
                      onClick={() => onAnalyzeTicker(c.symbol!)}
                      className="text-[10px] font-mono text-primary hover:underline mt-1 cursor-pointer"
                    >
                      analyze {c.symbol} →
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
                </div>
              </FundWidgetShell>
            );
          case 'rebalance':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} p-5`}>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h3 className="text-md font-serif font-semibold flex items-center gap-2">
            <Flame className="w-4 h-4 text-primary" /> Rebalancing Suggestions
          </h3>
          <span className="text-[11px] text-muted-foreground">Drift vs. model target allocation</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
          {rebalanceRows.map(rb => (
            <div key={rb.symbol} className={`${TILE} p-3.5 min-w-0`}>
              <div className="flex items-baseline justify-between gap-2 mb-2.5">
                <span className="font-mono text-sm font-bold">{rb.symbol}</span>
                <span className={`text-[11px] font-bold ${rb.color} text-right`}>{rb.action}</span>
              </div>
              <div className="flex gap-3 flex-wrap text-[11px]">
                <div><div className="text-muted-foreground text-[10px]">Current</div><div className="font-mono">{rb.curFmt}</div></div>
                <div><div className="text-muted-foreground text-[10px]">Target</div><div className="font-mono">{rb.targetFmt}</div></div>
                <div><div className="text-muted-foreground text-[10px]">Drift</div><div className={`font-mono ${rb.color}`}>{rb.driftFmt}</div></div>
              </div>
            </div>
          ))}
          {rebalanceRows.length === 0 && <p className="text-xs text-muted-foreground col-span-full text-center py-4">No holdings to rebalance.</p>}
        </div>
                </div>
              </FundWidgetShell>
            );
          case 'holdings':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} overflow-hidden`}>
        <div className="p-5 border-b border-border/30 flex items-center justify-between flex-wrap gap-3">
          <h3 className="text-md font-serif font-semibold flex items-center gap-2">
            <History className="w-5 h-5 text-primary" /> Active Holdings
          </h3>
          <div className="flex items-center gap-2">
            <input
              value={filterText}
              onChange={e => setFilterText(e.target.value)}
              placeholder="Filter by symbol…"
              className="bg-muted/20 border border-border/40 rounded-lg px-3 py-1.5 text-xs font-mono outline-none focus:border-primary/50 w-48"
            />
            <Button
              variant="outline"
              size="sm"
              title="Export holdings to CSV"
              onClick={() => {
                const rows: Array<Array<string | number>> = [
                  ['Symbol', 'Name', 'Quantity', 'Avg Cost (native)', 'Price (native)', 'Currency', 'Value (USD)', 'Value (DISP)', '24h %', 'Unrealized P/L (USD)', 'Allocation %'],
                  ...stats.holdings.map(h => [
                    h.symbol, metaOf(h.symbol)?.name ?? h.symbol, h.quantity,
                    h.avgCost.toFixed(4), h.currentPrice.toFixed(4), h.currency,
                    h.valueUsd.toFixed(2), convertFromUsd(h.valueUsd, hasFx ? displayFx : 'USD', fxRates).toFixed(2),
                    dayOf(h.symbol).toFixed(2), h.unrealizedPnLUsd.toFixed(2), h.allocation.toFixed(2),
                  ]),
                ];
                downloadCsv(`eclipse-holdings-${(activeFund?.name ?? 'portfolio').toLowerCase().replace(/[^a-z0-9]+/g, '-')}.csv`, rows);
              }}
              className="border-border/40 text-muted-foreground hover:text-primary hover:border-primary/40 rounded-lg font-mono text-[11px] cursor-pointer"
            >
              <History className="w-3.5 h-3.5 mr-1" /> CSV
            </Button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[760px]">
            <thead>
              <tr className="border-b border-border/30 bg-muted/15 text-[10px] uppercase font-mono text-muted-foreground tracking-wider font-semibold">
                <th className="p-4 px-6 cursor-pointer select-none hover:text-foreground" onClick={toggleSort('symbol')}>Asset{arrowFor('symbol')}</th>
                <th className="p-4">Quantity</th>
                <th className="p-4">Avg Cost</th>
                <th className="p-4">Price</th>
                <th className="p-4 cursor-pointer select-none hover:text-foreground" onClick={toggleSort('value')}>Value{arrowFor('value')}</th>
                <th className="p-4 cursor-pointer select-none hover:text-foreground" onClick={toggleSort('day')}>24h %{arrowFor('day')}</th>
                <th className="p-4 cursor-pointer select-none hover:text-foreground" onClick={toggleSort('total')}>Unrealized P/L{arrowFor('total')}</th>
                <th className="p-4"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/20 text-sm font-mono">
              {holdingsRows.length === 0 ? (
                <tr><td colSpan={8} className="p-10 text-center text-muted-foreground">
                  <div className="flex flex-col items-center gap-3">
                    <p>{filterText ? `No holdings match "${filterText}".` : 'This fund has no holdings yet.'}</p>
                    <div className="flex gap-2">
                      <Button size="sm" onClick={() => { setTxType('BUY'); setIsAddOpen(true); }}
                        className="bg-primary/15 text-primary hover:bg-primary/25 border border-primary/30 text-xs font-bold cursor-pointer">
                        <Plus className="w-3.5 h-3.5 mr-1" /> Record Transaction
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => onAnalyzeTicker('PORTFOLIO')}
                        className="border-border/40 text-xs font-mono cursor-pointer">
                        <Sparkles className="w-3.5 h-3.5 mr-1" /> Ask AI How to Start
                      </Button>
                    </div>
                  </div>
                </td></tr>
              ) : holdingsRows.map(h => {
                const up = h.dayPct >= 0;
                const expanded = expandedSymbol === h.symbol;
                return (
                  <React.Fragment key={h.symbol}>
                    <tr
                      className={`hover:bg-muted/10 transition-colors group cursor-pointer ${expanded ? 'bg-muted/10' : ''}`}
                      onClick={() => setExpandedSymbol(expanded ? null : h.symbol)}
                    >
                      <td className="p-4 px-6">
                        <div className="flex items-center gap-3">
                          <button
                            onClick={(e) => { e.stopPropagation(); toggleStar(h.symbol); }}
                            title="Toggle watchlist star"
                            className="cursor-pointer shrink-0"
                          >
                            <Star className={`w-4 h-4 ${watchlist[h.symbol] ? 'fill-primary text-primary' : 'text-muted-foreground/40 hover:text-primary/70'}`} />
                          </button>
                          <div>
                            <div className="font-bold">{h.symbol}</div>
                            <div className="text-[10px] text-muted-foreground">{metaOf(h.symbol)?.name ?? 'Crypto Asset'} · {metaOf(h.symbol)?.category ?? 'Other'}</div>
                          </div>
                        </div>
                      </td>
                      <td className="p-4 text-foreground/90">{h.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                      <td className="p-4 text-foreground/90">{fmtPrice(h.avgCost, currencyOf(h.symbol), 2)}</td>
                      <td className="p-4 text-foreground/90">{fmtPrice(h.currentPrice, currencyOf(h.symbol), 2)}</td>
                      <td className="p-4 font-bold">{fmtPrice(h.value, currencyOf(h.symbol))}</td>
                      <td className={`p-4 font-semibold ${up ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtPct(h.dayPct)}</td>
                      <td className="p-4">
                        <div className={`font-semibold ${h.unrealizedPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {h.unrealizedPnL >= 0 ? '+' : '-'}{fmtPrice(Math.abs(h.unrealizedPnL), currencyOf(h.symbol))}
                        </div>
                        <div className={`text-[10px] font-bold ${h.unrealizedPnL >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                          {fmtPct(h.totalPct)}
                        </div>
                      </td>
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end gap-1.5 opacity-60 group-hover:opacity-100 transition-opacity">
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-primary hover:bg-muted/40 cursor-pointer"
                            onClick={(e) => { e.stopPropagation(); onAnalyzeTicker(h.symbol); }}
                            title="Analyze with AI">
                            <BarChart2 className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 cursor-pointer"
                            onClick={(e) => { e.stopPropagation(); handleDeleteTransaction(h.symbol); }}
                            title="Remove all transactions for this asset">
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                          <span className="text-muted-foreground w-4 inline-flex justify-center">
                            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                          </span>
                        </div>
                      </td>
                    </tr>
                    {expanded && (
                      <tr className="bg-muted/[0.03]">
                        <td colSpan={8} className="p-4 px-6 border-b border-border/10">
                          <div className="flex items-center gap-5 flex-wrap">
                            <div>
                              <div className="text-[10px] font-mono text-muted-foreground mb-0.5">90-day real closes</div>
                              <Sparkline data={history.closes[h.symbol] ?? []} up={up} />
                            </div>
                            <p className="flex-1 text-[12.5px] text-foreground/80 min-w-[220px] font-sans">
                              {metaOf(h.symbol)?.aiTag ?? 'No active AI insight for this position.'}
                            </p>
                            <Button
                              size="sm"
                              onClick={(e) => { e.stopPropagation(); onAnalyzeTicker(h.symbol); }}
                              className="bg-primary/15 text-primary hover:bg-primary/25 border border-primary/30 text-xs font-bold cursor-pointer"
                            >
                              <Sparkles className="w-3.5 h-3.5 mr-1" /> Discuss With AI
                            </Button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
                </div>
              </FundWidgetShell>
            );
          case 'watchlist':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} p-5 h-full`}>
          <h3 className="text-md font-serif font-semibold mb-3 flex items-center gap-2">
            <Star className="w-4 h-4 fill-primary text-primary" /> Watchlist
          </h3>
          <div className="divide-y divide-border/20">
            {watchlistRows.length > 0 ? watchlistRows.map(w => (
              <div key={w.symbol} className="flex items-center justify-between py-2.5 cursor-pointer hover:bg-muted/10 rounded-lg px-2 -mx-2 transition-colors"
                onClick={() => onAnalyzeTicker(w.symbol)}>
                <div className="flex items-center gap-2">
                  <Star className="w-3 h-3 fill-primary text-primary" />
                  <span className="font-mono font-bold text-sm">{w.symbol}</span>
                  <span className="text-[10px] text-muted-foreground hidden sm:inline">{metaOf(w.symbol)?.name}</span>
                </div>
                <div className="text-right">
                  <div className="font-mono text-sm">{fmtPrice(w.price, currencyOf(w.symbol), 2)}</div>
                  <div className={`font-mono text-[11px] ${w.dayPct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtPct(w.dayPct)}</div>
                </div>
              </div>
            )) : (
              <p className="text-xs text-muted-foreground font-mono text-center py-8">
                Star holdings above to pin them here.
              </p>
            )}
          </div>
                </div>
              </FundWidgetShell>
            );
          case 'transactions':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} p-5 h-full`}>
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="text-md font-serif font-semibold flex items-center gap-2">
              <Calendar className="w-4 h-4 text-primary" /> Recent Transactions
            </h3>
            <Button
              variant="outline"
              size="sm"
              title="Export full transaction ledger to CSV"
              onClick={() => {
                const rows: Array<Array<string | number>> = [
                  ['Date', 'Type', 'Symbol', 'Quantity', 'Price (native)', 'Fee (native)', 'Notional (USD)'],
                  ...transactions.map(t => {
                    const fx = (metaOf(t.symbol)?.currency ?? 'USD') === 'PKR' ? 1 / usdPkr : 1;
                    return [t.date, t.type, t.symbol, t.quantity, t.price.toFixed(4), t.fee.toFixed(2), (t.quantity * t.price * fx).toFixed(2)];
                  }),
                ];
                downloadCsv(`eclipse-transactions-${(activeFund?.name ?? 'portfolio').toLowerCase().replace(/[^a-z0-9]+/g, '-')}.csv`, rows);
              }}
              className="border-border/40 text-muted-foreground hover:text-primary hover:border-primary/40 rounded-lg font-mono text-[11px] cursor-pointer"
            >
              <History className="w-3.5 h-3.5 mr-1" /> CSV
            </Button>
          </div>
        {/* Mobile: card list (table is unusable below md) */}
        <div className="md:hidden divide-y divide-border/20">
          {holdingsRows.length === 0 ? (
            <p className="p-8 text-center text-xs text-muted-foreground font-mono">No holdings match.</p>
          ) : holdingsRows.map(h => {
            const mUp = h.dayPct >= 0;
            return (
              <div key={h.symbol} className="p-4 cursor-pointer active:bg-muted/10" onClick={() => onAnalyzeTicker(h.symbol)}>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <Star className={`w-3.5 h-3.5 ${watchlist[h.symbol] ? 'fill-primary text-primary' : 'text-muted-foreground/40'}`}
                      onClick={(e) => { e.stopPropagation(); toggleStar(h.symbol); }} />
                    <span className="font-mono font-bold text-sm">{h.symbol}</span>
                  </div>
                  <span className={`text-xs font-semibold ${mUp ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtPct(h.dayPct)}</span>
                </div>
                <div className="flex items-baseline justify-between text-[11px] font-mono">
                  <span className="text-muted-foreground">{h.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })} × {fmtPrice(h.currentPrice, currencyOf(h.symbol))}</span>
                  <span className="font-bold">{fmtPrice(h.value, currencyOf(h.symbol))}</span>
                </div>
                <div className={`text-[10px] font-mono mt-0.5 ${h.unrealizedPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  P/L {h.unrealizedPnL >= 0 ? '+' : '-'}{fmtPrice(Math.abs(h.unrealizedPnL), currencyOf(h.symbol))} ({fmtPct(h.totalPct)})
                </div>
              </div>
            );
          })}
        </div>
        <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-left text-xs font-mono min-w-[520px]">
              <thead>
                <tr className="border-b border-border/30 text-[10px] uppercase text-muted-foreground font-semibold">
                  <th className="py-2 pr-3">Date</th><th className="pr-3">Symbol</th><th className="pr-3">Side</th>
                  <th className="pr-3">Qty</th><th className="pr-3">Price</th><th className="pr-3">Fee</th><th>Notional (USD)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/20">
                {recentTransactions.map(t => (
                  <tr key={t.id} className="hover:bg-muted/5">
                    <td className="py-2.5 pr-3 text-muted-foreground">{t.date}</td>
                    <td className="pr-3 font-bold">{t.symbol}</td>
                    <td className={`pr-3 font-bold ${t.sideColor}`}>{t.type}</td>
                    <td className="pr-3">{t.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                    <td className="pr-3">{fmtPrice(t.price, currencyOf(t.symbol), 2)}</td>
                    <td className="pr-3 text-muted-foreground">{fmtPrice(t.fee, currencyOf(t.symbol), 2)}</td>
                    <td>{t.notionalFmt}</td>
                  </tr>
                ))}
                {recentTransactions.length === 0 && (
                  <tr><td colSpan={7} className="py-6 text-center text-muted-foreground">No transactions recorded.</td></tr>
                )}
              </tbody>
            </table>
          </div>
                </div>
              </FundWidgetShell>
            );
          case 'stress':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} p-5 h-full`}>
          <div className="flex items-baseline justify-between flex-wrap gap-2">
            <h3 className="text-md font-serif font-semibold">Stress Test</h3>
            <span className="text-[11px] text-muted-foreground">Beta-adjusted shock model</span>
          </div>
          <p className="text-[11.5px] text-muted-foreground mt-1 mb-3">{stress.scen.desc}</p>

          <div className="flex gap-2 flex-wrap mb-4">
            {STRESS_SCENARIOS.map(sc => (
              <button
                key={sc.id}
                onClick={() => setStressId(sc.id)}
                className={`px-3 py-1.5 text-[11px] font-bold rounded-lg border transition-all cursor-pointer ${
                  stressId === sc.id
                    ? 'border-primary/40 bg-primary/10 text-primary'
                    : 'border-border/40 text-muted-foreground hover:text-foreground'
                }`}
              >
                {sc.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-3 mb-4">
            <span className="text-[11px] text-muted-foreground whitespace-nowrap">Severity</span>
            <input type="range" min="0.5" max="2" step="0.1" value={severity}
              onChange={e => setSeverity(parseFloat(e.target.value))}
              className="flex-1 accent-[#7aff78]" />
            <span className="font-mono text-xs text-primary w-9">{severity.toFixed(1)}×</span>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className={`${TILE} p-3`}>
              <div className="text-[10px] text-muted-foreground mb-1">Projected Value</div>
              <div className="font-mono font-bold">{fmtDK(stats.totalValue + stress.dollar)}</div>
            </div>
            <div className={`${TILE} p-3`}>
              <div className="text-[10px] text-muted-foreground mb-1">Impact</div>
              <div className={`font-mono font-bold ${stress.dollar >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {fmtD(stress.dollar, 0)}
              </div>
            </div>
            <div className={`${TILE} p-3`}>
              <div className="text-[10px] text-muted-foreground mb-1">Worst Asset</div>
              <div className="font-mono font-bold text-rose-400">
                {stress.worstSymbol} {fmtPct(stress.worstPct)}
              </div>
            </div>
          </div>

          <EChart option={stressOption} height={Math.max(140, stress.rows.length * 38 + 20)} />
                </div>
              </FundWidgetShell>
            );
          case 'correlation':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} p-5 h-full`}>
          <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
            <h3 className="text-md font-serif font-semibold">Correlation Matrix</h3>
            <span className="text-[11px] text-muted-foreground">Pearson ρ on real daily returns</span>
          </div>
          {corrSymbols.length > 1 ? (
            <>
              <EChart option={corrOption} height={Math.max(180, corrSymbols.length * 34 + 60)} />
              <p className="mt-3 pt-3 border-t border-border/20 text-[11.5px] text-muted-foreground leading-relaxed">
                Avg pairwise correlation{' '}
                <span className="font-mono font-bold text-foreground">{corrData.avg.toFixed(2)}</span>.
                {corrData.avg > 0.75
                  ? ' Holdings move largely together — diversification benefit is limited.'
                  : ' Reasonable spread of independent risk across the book.'}
              </p>
            </>
          ) : (
            <p className="text-xs text-muted-foreground font-mono text-center py-10">Add at least two assets to compute correlations.</p>
          )}
                </div>
              </FundWidgetShell>
            );
          case 'tools':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* What-If Trade */}
          <div className={`${PANEL} p-5`}>
          <h3 className="text-md font-serif font-semibold mb-4">What-If Trade</h3>

          <select
            value={wiSymbol}
            onChange={e => setWiSymbol(e.target.value)}
            className="w-full bg-muted/20 border border-border/40 rounded-lg px-3 py-2 text-xs font-mono outline-none focus:border-primary/50 mb-2 cursor-pointer [&>option]:bg-[#1a1a1a] [&>option]:text-foreground"
          >
            {liveAssets.map(a => <option key={a.symbol} value={a.symbol}>{a.symbol} — {a.name}</option>)}
          </select>

          <div className="flex gap-2 mb-3">
            {(['Buy', 'Sell'] as const).map(side => (
              <button
                key={side}
                onClick={() => setWiSide(side)}
                className={`flex-1 py-1.5 text-xs font-bold rounded-lg border transition-all cursor-pointer ${
                  wiSide === side
                    ? side === 'Buy' ? 'border-emerald-400/40 bg-emerald-400/10 text-emerald-400' : 'border-rose-400/40 bg-rose-400/10 text-rose-400'
                    : 'border-border/40 text-muted-foreground hover:text-foreground'
                }`}
              >
                {side}
              </button>
            ))}
          </div>

          <label className="text-[10px] uppercase font-mono text-muted-foreground block mb-1">Units</label>
          <input value={wiQty} onChange={e => setWiQty(e.target.value)}
            className="w-full bg-muted/20 border border-border/40 rounded-lg px-3 py-2 text-xs font-mono outline-none focus:border-primary/50 mb-4" />

          <div className="space-y-2.5">
            {[
              { l: `${wiSymbol} weight`, before: `${whatIf.oldWeight.toFixed(1)}%`, after: `${whatIf.newWeight.toFixed(1)}%`, ok: null as boolean | null },
              { l: 'Portfolio value', before: fmtDK(stats.totalValue), after: fmtDK(stats.totalValue + whatIf.cost), ok: whatIf.cost >= 0 },
              { l: 'Est. cash after', before: fmtD(AVAILABLE_CASH, 0), after: fmtD(whatIf.newCash, 0), ok: whatIf.newCash >= 0 },
            ].map(row => (
              <div key={row.l} className="flex items-baseline justify-between text-[11.5px] pb-2 border-b border-border/20">
                <span className="text-muted-foreground">{row.l}</span>
                <span className="flex items-baseline gap-2 font-mono">
                  <span className="text-muted-foreground/70">{row.before}</span>
                  <span className="text-muted-foreground/40">→</span>
                  <span className={`font-bold ${row.ok === null ? '' : row.ok ? 'text-emerald-400' : 'text-rose-400'}`}>{row.after}</span>
                </span>
              </div>
            ))}
          </div>

          <p className="mt-3 text-[11px] text-muted-foreground leading-relaxed">
            {whatIf.newCash < 0
              ? `Insufficient cash — needs ${fmtD(-whatIf.newCash, 0)} more than available.`
              : whatIf.newWeight > 40
                ? `${wiSymbol} would exceed 40% of the portfolio — concentration risk rises sharply.`
                : whatIf.delta === 0
                  ? 'No quantity held to sell at this size.'
                  : `Trade costs ${fmtD(Math.abs(whatIf.cost), 0)} and shifts ${wiSymbol} to ${whatIf.newWeight.toFixed(1)}% of NAV.`}
          </p>
        </div>

        {/* Position Sizing */}
        <div className={`${PANEL} p-5`}>
          <h3 className="text-md font-serif font-semibold mb-4">Position Sizing</h3>
          <div className="space-y-3 mb-4">
            {[
              { l: 'Entry', v: szEntry, set: setSzEntry },
              { l: 'Stop loss', v: szStop, set: setSzStop },
              { l: 'Target', v: szTarget, set: setSzTarget },
            ].map(f => (
              <div key={f.l} className="flex items-center gap-3">
                <span className="text-[11px] text-muted-foreground w-16 shrink-0">{f.l}</span>
                <input value={f.v} onChange={e => f.set(e.target.value)}
                  className="flex-1 bg-muted/20 border border-border/40 rounded-lg px-3 py-1.5 text-xs font-mono outline-none focus:border-primary/50" />
              </div>
            ))}
            <div className="flex items-center gap-3">
              <span className="text-[11px] text-muted-foreground w-16 shrink-0">Risk / trade</span>
              <input type="range" min="0.25" max="5" step="0.25" value={szRisk}
                onChange={e => setSzRisk(parseFloat(e.target.value))}
                className="flex-1 accent-[#7aff78]" />
              <span className="font-mono text-xs text-primary w-11 text-right">{szRisk.toFixed(2)}%</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            {[
              { l: 'Units', v: sizing.units > 999 ? sizing.units.toFixed(0) : sizing.units.toFixed(4), c: 'text-emerald-400' },
              { l: 'Position size', v: fmtDK(sizing.posValue), c: '' },
              { l: 'Risk amount', v: fmtD(sizing.riskDollar, 0), c: 'text-rose-400' },
              { l: 'Stop distance', v: sizing.entry > 0 ? `${(((sizing.entry - sizing.stop) / sizing.entry) * 100).toFixed(1)}%` : '—', c: '' },
              { l: 'Reward : Risk', v: `${sizing.rr.toFixed(2)} : 1`, c: sizing.rr >= 2 ? 'text-emerald-400' : sizing.rr >= 1 ? 'text-amber-400' : 'text-rose-400' },
              { l: '% of NAV', v: `${((sizing.posValue / (stats.totalValue || 1)) * 100).toFixed(1)}%`, c: sizing.posValue / (stats.totalValue || 1) > 0.25 ? 'text-rose-400' : '' },
            ].map(r => (
              <div key={r.l} className={`${TILE} p-2.5`}>
                <div className="text-[10px] text-muted-foreground mb-0.5">{r.l}</div>
                <div className={`font-mono text-sm font-bold ${r.c}`}>{r.v}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Alerts */}
        <div className={`${PANEL} p-5`}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-md font-serif font-semibold flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-primary" /> Alerts
            </h3>
            <span className="text-[10px] font-mono text-muted-foreground">{alerts.length} active</span>
          </div>

          <select
            value={alertType}
            onChange={e => setAlertType(e.target.value as Alert['type'])}
            className="w-full bg-muted/20 border border-border/40 rounded-lg px-3 py-2 text-xs font-mono outline-none focus:border-primary/50 mb-2 cursor-pointer [&>option]:bg-[#1a1a1a] [&>option]:text-foreground"
          >
            {ALERT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label} {t.value === 'DAILY_MOVE' ? '(%)' : '(USD)'}</option>)}
          </select>
          <div className="flex gap-2 mb-4">
            <input value={alertTarget} onChange={e => setAlertTarget(e.target.value)} placeholder={alertType === 'DAILY_MOVE' ? 'e.g. 5' : 'Trigger value'}
              className="flex-1 bg-muted/20 border border-border/40 rounded-lg px-3 py-1.5 text-xs font-mono outline-none focus:border-primary/50" />
            <Button size="sm" onClick={handleAddAlert}
              className="bg-primary/15 text-primary hover:bg-primary/25 border border-primary/30 text-xs font-bold cursor-pointer">
              <Plus className="w-3.5 h-3.5 mr-0.5" /> Add
            </Button>
          </div>

          <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
            {alerts.length === 0 && (
              <p className="text-xs text-muted-foreground font-mono text-center py-6">No alerts set. Define a threshold above.</p>
            )}
            {alerts.map(a => {
              const price = priceOf(a.symbol);
              const move = Math.abs(dayOf(a.symbol));
              let triggered = false;
              let status = '';
              if (a.type === 'PRICE_ABOVE') {
                triggered = price > 0 && price >= a.target;
                status = `Now ${fmtPrice(price, currencyOf(a.symbol))} · ${triggered ? 'triggered' : price > 0 ? `${(((a.target / price) - 1) * 100).toFixed(1)}% away` : 'waiting'}`;
              } else if (a.type === 'PRICE_BELOW') {
                triggered = price > 0 && price <= a.target;
                status = `Now ${fmtPrice(price, currencyOf(a.symbol))} · ${triggered ? 'triggered' : price > 0 ? `${(((1 - a.target / price)) * 100).toFixed(1)}% away` : 'waiting'}`;
              } else if (a.type === 'DAILY_MOVE') {
                triggered = move > a.target;
                status = `Today ${move.toFixed(2)}% · ${triggered ? 'triggered' : 'watching'}`;
              } else {
                status = 'Monitoring allocation';
              }
              return (
                <div key={a.id} className="flex items-center gap-2.5 bg-muted/10 border border-border/20 rounded-lg px-3 py-2">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${triggered ? 'bg-emerald-400 animate-pulse' : 'bg-muted-foreground/40'}`}></span>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs">
                      <span className="font-mono font-bold">{a.symbol}</span>{' '}
                      <span className="text-foreground/80">
                        {a.type === 'PRICE_ABOVE' ? `above ${fmtPrice(a.target, currencyOf(a.symbol), 0)}`
                          : a.type === 'PRICE_BELOW' ? `below ${fmtPrice(a.target, currencyOf(a.symbol), 0)}`
                          : `move > ${a.target}%`}
                      </span>
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">{status}</div>
                  </div>
                  <button onClick={() => handleDeleteAlert(a.id)} className="text-muted-foreground hover:text-rose-400 cursor-pointer text-base leading-none">×</button>
                </div>
              );
            })}
          </div>
        </div>
                </div>
              </FundWidgetShell>
            );
          case 'monte-carlo':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
                  <div className={`${PANEL} lg:col-span-3 p-5`}>
          <div className="flex items-baseline justify-between flex-wrap gap-3 mb-3">
            <h3 className="text-md font-serif font-semibold">Monte Carlo Projection</h3>
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground">Horizon</span>
                <input type="range" min="1" max="20" step="1" value={mcYears}
                  onChange={e => setMcYears(parseInt(e.target.value, 10))}
                  className="w-20 accent-[#7aff78]" />
                <span className="font-mono text-[11px] text-primary w-7">{mcYears}y</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-muted-foreground">Monthly add</span>
                <input value={mcMonthly} onChange={e => setMcMonthly(e.target.value)}
                  className="w-20 bg-muted/20 border border-border/40 rounded-md px-2 py-1 font-mono text-[11px] outline-none focus:border-primary/50" />
              </div>
            </div>
          </div>
          <EChart option={mcOption} height={240} />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
            {[
              { l: 'Pessimistic (5%)', v: fmtDK(monteCarlo.end.lo), c: 'text-rose-400', n: 'Worse than 95% of paths' },
              { l: 'Median (50%)', v: fmtDK(monteCarlo.end.mid), c: 'text-emerald-400', n: `+${(((monteCarlo.end.mid / (stats.totalValue + monteCarlo.totalContrib)) - 1) * 100).toFixed(0)}% over contributions` },
              { l: 'Optimistic (95%)', v: fmtDK(monteCarlo.end.hi), c: 'text-emerald-400', n: 'Top 5% of paths' },
              { l: 'Total invested', v: fmtDK(stats.totalValue + monteCarlo.totalContrib), c: '', n: `${fmtD(monteCarlo.totalContrib, 0)} added` },
            ].map(o => (
              <div key={o.l} className={`${TILE} p-3`}>
                <div className="text-[10px] text-muted-foreground mb-0.5">{o.l}</div>
                <div className={`font-mono font-bold ${o.c}`}>{o.v}</div>
                <div className="text-[9.5px] text-muted-foreground/70 mt-0.5">{o.n}</div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-muted-foreground leading-relaxed">
            Lognormal GBM paths calibrated to your weighted portfolio volatility of {pVol.toFixed(1)}%, ~45% expected annual return, contributions reinvested monthly.
          </p>
        </div>

                <div className={`${PANEL} lg:col-span-2 p-5`}>
          <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
            <h3 className="text-md font-serif font-semibold">Return Attribution</h3>
            <span className="text-[11px] text-muted-foreground">Contribution to total gain</span>
          </div>
          {attributionRows.length > 0 ? (
            <>
              <EChart option={attributionOption} height={Math.max(160, attributionRows.length * 36 + 16)} />
              <div className="mt-3 pt-3 border-t border-border/20 flex justify-between text-xs">
                <span className="text-muted-foreground">Total unrealized</span>
                <span className={`font-mono font-bold ${stats.unrealizedPnL >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {stats.unrealizedPnL >= 0 ? '+' : '-'}{fmtD(Math.abs(stats.unrealizedPnL))} ({fmtPct(stats.roiPercent)})
                </span>
              </div>
            </>
          ) : (
            <p className="text-xs text-muted-foreground font-mono text-center py-10">Attribution unlocks once you hold assets.</p>
          )}
                </div>
                </div>
              </FundWidgetShell>
            );
          case 'cost-basis':
            return (
              <FundWidgetShell key={w.id} id={w.id} {...shellProps}>
                <div className={`${PANEL} p-5 mb-6`}>
        <div className="flex items-baseline justify-between mb-4 flex-wrap gap-2">
          <h3 className="text-md font-serif font-semibold">Cost Basis &amp; DCA</h3>
          <span className="text-[11px] text-muted-foreground">Average entry vs. live market — FIFO accounting</span>
        </div>
        <EChart option={costBasisOption} height={260} />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3 mt-4">
          {stats.holdings.map(h => {
            const spread = ((h.currentPrice / h.avgCost) - 1) * 100;
            return (
              <div key={h.symbol} className={`${TILE} p-3`}>
                <div className="flex justify-between items-baseline mb-1.5">
                  <span className="font-mono font-bold text-xs">{h.symbol}</span>
                  <span className={`font-mono text-[11px] font-bold ${spread >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>{fmtPct(spread)}</span>
                </div>
                <div className="text-[10px] text-muted-foreground space-y-0.5">
                  <div>Avg <span className="font-mono text-foreground/80">{fmtPrice(h.avgCost, currencyOf(h.symbol), 2)}</span></div>
                  <div>Now <span className="font-mono text-foreground/80">{fmtPrice(h.currentPrice, currencyOf(h.symbol), 2)}</span></div>
                  <div>Break-even <span className="font-mono text-foreground/80">{fmtPrice(h.avgCost * 1.002, currencyOf(h.symbol), 2)}</span></div>
                </div>
              </div>
            );
          })}
          {stats.holdings.length === 0 && <p className="text-xs text-muted-foreground col-span-full text-center py-4">No cost basis to compare.</p>}
        </div>
                </div>
              </FundWidgetShell>
            );
          default:
            return null;
        }
      })}
      </div>
      </>)}
      {/* ─── ADD TRANSACTION MODAL (portal — escapes transform/filter ancestors) */}
      {isAddOpen && typeof document !== 'undefined' && createPortal(
        <div className="fixed inset-0 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md animate-in fade-in duration-300" style={{ zIndex: 9998 }} onMouseDown={() => setIsAddOpen(false)}>
          <div className="relative bg-card border border-border/80 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200" onMouseDown={e => e.stopPropagation()}>
            <div className="p-5 border-b border-border/40 flex items-center justify-between bg-muted/10">
              <h2 className="text-md font-serif font-semibold flex items-center gap-2.5">
                <PlusCircle className="w-5 h-5 text-primary" />
                Record Transaction
              </h2>
              <button type="button" onMouseDown={(e) => { e.stopPropagation(); setIsAddOpen(false); }} className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer p-1">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              <div className="grid grid-cols-3 gap-2">
                <Button variant="outline"
                  className={`border-border/40 font-mono transition-all rounded-xl cursor-pointer ${txType === 'BUY' ? 'bg-primary/10 text-primary border-primary/50 font-bold' : 'bg-transparent text-muted-foreground'}`}
                  onClick={() => setTxType('BUY')}>
                  Buy / Long
                </Button>
                <Button variant="outline"
                  className={`border-border/40 font-mono transition-all rounded-xl cursor-pointer ${txType === 'SELL' ? 'bg-rose-500/10 text-rose-400 border-rose-500/40 font-bold' : 'bg-transparent text-muted-foreground'}`}
                  onClick={() => setTxType('SELL')}>
                  Sell / Short
                </Button>
                <Button variant="outline"
                  className={`border-border/40 font-mono transition-all rounded-xl cursor-pointer ${txType === 'DIVIDEND' ? 'bg-amber-400/10 text-amber-300 border-amber-400/40 font-bold' : 'bg-transparent text-muted-foreground'}`}
                  onClick={() => setTxType('DIVIDEND')}>
                  Dividend
                </Button>
              </div>

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

                {showSymbolDropdown && (
                  <div className="absolute z-50 left-0 right-0 mt-1 max-h-56 overflow-y-auto bg-card border border-border/80 rounded-xl shadow-xl divide-y divide-border/20">
                    {searchingSymbols && (
                      <div className="px-4 py-2.5 text-[10px] font-mono text-muted-foreground flex items-center gap-2">
                        <span className="w-3 h-3 rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground/70 animate-spin" aria-hidden />
                        Searching JDDS…
                      </div>
                    )}
                    {filteredSymbolOptions.length === 0 && !searchingSymbols && (
                      <div className="px-4 py-2.5 text-[10px] font-mono text-muted-foreground">
                        No assets found. Try a symbol like AAPL, OGDC, BTC…
                      </div>
                    )}
                    {filteredSymbolOptions.map(asset => (
                      <div
                        key={asset.symbol + (asset.marketId ?? '')}
                        onClick={() => {
                          setTxSymbol(asset.symbol);
                          setSymbolSearchQuery(asset.symbol);
                          setTxPrice(String(asset.price));
                          if (txTotalSpent) setTxQty(String(parseFloat(txTotalSpent) / asset.price));
                          else if (txQty) setTxTotalSpent((parseFloat(txQty) * asset.price).toFixed(2));
                          setShowSymbolDropdown(false);
                        }}
                        className="flex items-center justify-between px-4 py-2.5 hover:bg-muted/30 cursor-pointer transition-colors text-xs font-mono"
                      >
                        <div className="flex flex-col min-w-0">
                          <span className="font-bold text-foreground">{asset.symbol}</span>
                          <span className="text-[10px] text-muted-foreground truncate max-w-[220px]">{asset.name}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {asset.marketId && asset.marketId !== 'TRACKED' && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-accent/60 border border-border/30 text-muted-foreground uppercase tracking-wider">
                              {asset.marketId}
                            </span>
                          )}
                          <span className="text-muted-foreground font-semibold">{fmtPrice(asset.price, asset.currency, 2)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">{txType === 'DIVIDEND' ? 'Dividend per Share ($)' : 'Price per Token ($)'}</label>
                <input type="number" step="any" value={txPrice} onChange={e => handlePriceChange(e.target.value)}
                  className="w-full bg-background border border-border/50 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono"
                  placeholder="0.00" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Quantity</label>
                  <input type="number" step="any" value={txQty} onChange={e => handleQtyChange(e.target.value)}
                    className="w-full bg-background border border-border/50 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono"
                    placeholder="0.00" />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-mono text-primary uppercase tracking-wider block">{txType === 'DIVIDEND' ? 'Total Dividend ($, auto)' : 'Total Spent ($)'}</label>
                  <input type="number" step="any" value={txTotalSpent} onChange={e => handleSpentChange(e.target.value)}
                    className="w-full bg-background border border-primary/40 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono shadow-sm shadow-primary/5"
                    placeholder="e.g. 30.00" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Trading Fee ($)</label>
                  <input type="number" value={txFee} onChange={e => setTxFee(e.target.value)}
                    className="w-full bg-background border border-border/50 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono"
                    placeholder="0.00" />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Trade Date</label>
                  <div className="relative">
                    <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
                      <Calendar className="h-4 w-4 text-muted-foreground/60" />
                    </span>
                    <input type="date" value={txDate} onChange={e => setTxDate(e.target.value)}
                      className="w-full bg-background border border-border/50 rounded-xl pl-10 pr-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono cursor-pointer" />
                  </div>
                </div>
              </div>
            </div>

            <div className="p-5 border-t border-border/40 bg-muted/10 flex justify-end gap-3">
              <Button variant="ghost" onMouseDown={(e) => { e.stopPropagation(); setIsAddOpen(false); }}
                className="text-muted-foreground hover:text-foreground cursor-pointer rounded-xl font-mono text-xs">
                Cancel
              </Button>
              <Button className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-xl px-4 font-mono text-xs shadow-md cursor-pointer"
                onMouseDown={e => e.stopPropagation()}
                onClick={handleAddTransaction}
                disabled={isUpdating || !txSymbol || !txPrice || (txType !== 'DIVIDEND' && !txQty)}>
                {isUpdating ? 'Saving...' : 'Save Transaction'}
              </Button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* ─── NEW / EDIT FUND MODAL (portal — escapes transform/filter ancestors) */}
      {isFundDialogOpen && typeof document !== 'undefined' && createPortal(
        <div className="fixed inset-0 flex items-center justify-center p-4 bg-background/80 backdrop-blur-md animate-in fade-in duration-300" style={{ zIndex: 9998 }} onMouseDown={() => setIsFundDialogOpen(false)}>
          <div className="relative bg-card border border-border/80 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200" onMouseDown={e => e.stopPropagation()}>
            <div className="p-5 border-b border-border/40 flex items-center justify-between bg-muted/10">
              <h2 className="text-md font-serif font-semibold flex items-center gap-2.5">
                <PiggyBank className="w-5 h-5 text-primary" />
                {fundEditorId ? 'Edit Fund' : 'Create New Fund'}
              </h2>
              <button type="button" onMouseDown={(e) => { e.stopPropagation(); setIsFundDialogOpen(false); }} className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer p-1">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              <div className="space-y-2">
                <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Fund Name</label>
                <input
                  value={fundName}
                  onChange={e => setFundName(e.target.value)}
                  placeholder="e.g. House Fund, College Fund…"
                  className="w-full bg-background border border-border/50 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary"
                  autoFocus
                />
              </div>

              {/* Quick-start presets (create mode only) */}
              {!fundEditorId && (
                <div className="space-y-2">
                  <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Quick Start</label>
                  <div className="flex flex-wrap gap-2">
                    {STARTER_GOAL_FUNDS
                      .filter(p => !funds.some(f => f.name === p.name))
                      .map(p => {
                        const PI = FUND_ICONS[p.icon] ?? PiggyBank;
                        return (
                          <button
                            key={p.name}
                            onClick={() => {
                              setFundName(p.name);
                              setFundIcon(p.icon);
                              setFundColor(p.color);
                              setFundGoal(p.goalUsd ? String(p.goalUsd) : '');
                            }}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border border-border/40 hover:border-primary/50 hover:bg-primary/5 transition-all cursor-pointer"
                          >
                            <PI className="w-3.5 h-3.5" style={{ color: p.color }} />
                            {p.name}
                          </button>
                        );
                      })}
                  </div>
                </div>
              )}

              <div className="space-y-2">
                <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Icon</label>
                <div className="flex flex-wrap gap-2">
                  {FUND_ICON_OPTIONS.map(key => {
                    const I = FUND_ICONS[key];
                    const active = fundIcon === key;
                    return (
                      <button
                        key={key}
                        onClick={() => setFundIcon(key)}
                        title={key}
                        className={`p-2.5 rounded-xl border transition-all cursor-pointer ${
                          active ? 'border-primary/60 bg-primary/10' : 'border-border/40 text-muted-foreground hover:text-foreground hover:border-primary/30'
                        }`}
                      >
                        <I className="w-4 h-4" style={active ? { color: fundColor } : undefined} />
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Accent Color</label>
                <div className="flex flex-wrap gap-2">
                  {FUND_COLORS.map(c => (
                    <button
                      key={c}
                      onClick={() => setFundColor(c)}
                      className={`w-8 h-8 rounded-lg border-2 transition-all cursor-pointer ${
                        fundColor === c ? 'border-foreground scale-110' : 'border-transparent hover:scale-105'
                      }`}
                      style={{ background: c }}
                      aria-label={`color ${c}`}
                    />
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-mono text-muted-foreground uppercase tracking-wider block">Goal Amount (USD, optional)</label>
                <input
                  type="number"
                  value={fundGoal}
                  onChange={e => setFundGoal(e.target.value)}
                  placeholder="e.g. 50000"
                  className="w-full bg-background border border-border/50 rounded-xl px-4 py-2.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary font-mono"
                />
              </div>
            </div>

            <div className="p-5 border-t border-border/40 bg-muted/10 flex justify-between gap-3">
              {fundEditorId && funds.length > 1 ? (
                <Button
                  variant="ghost"
                  onClick={() => { handleDeleteFund(fundEditorId); setIsFundDialogOpen(false); }}
                  className="text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 cursor-pointer rounded-xl font-mono text-xs"
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1" /> Delete Portfolio
                </Button>
              ) : <span />}
              <div className="flex gap-3">
                <Button variant="ghost" onClick={() => setIsFundDialogOpen(false)}
                  className="text-muted-foreground hover:text-foreground cursor-pointer rounded-xl font-mono text-xs">
                  Cancel
                </Button>
                <Button className="bg-primary hover:bg-primary/90 text-primary-foreground font-semibold rounded-xl px-4 font-mono text-xs shadow-md cursor-pointer"
                  onClick={handleSaveFund}
                  disabled={!fundName.trim()}>
                  {fundEditorId ? 'Save Changes' : 'Create Fund'}
                </Button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Ambient brand glow */}
      <div aria-hidden className="pointer-events-none absolute top-0 left-1/4 right-0 h-96 opacity-40"
        style={{ background: 'radial-gradient(ellipse at center, rgba(122,255,120,0.10) 0%, transparent 65%)', filter: 'blur(20px)' }} />
    </div>
  );
}
