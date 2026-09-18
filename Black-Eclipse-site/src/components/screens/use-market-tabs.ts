'use client';

import { useState, useEffect, useMemo } from 'react';

// ── Forex & Commodities tabs ────────────────────────────────────────────────
// Extracted from market-overview.tsx (memory/simplicity standing goal): each
// block owns its fetch, filter state, and memoized filtered list. The screen
// passes in the active tab and keeps only the rendering.

export type ForexPair = {
  symbol: string;
  name: string;
  base: string;
  quote: string;
  price: number;
  changePct: number;
  found: boolean;
};

export type CommodityItem = {
  symbol: string;
  name: string;
  unit: string;
  price: number;
  changePct: number;
  found: boolean;
};

export function useForex(active: boolean, setLoadingTab: (v: boolean) => void) {
  const [forexPairs, setForexPairs] = useState<ForexPair[]>([]);
  const [forexSearch, setForexSearch] = useState('');
  const [forexChange, setForexChange] = useState('All');
  const [forexCurrency, setForexCurrency] = useState('All');
  const [forexSortField, setForexSortField] = useState<keyof ForexPair>('symbol');
  const [forexSortOrder, setForexSortOrder] = useState<'asc' | 'desc'>('asc');
  const [loadingForex, setLoadingForex] = useState(false);

  useEffect(() => {
    if (!active) return;
    // Already loaded — switching between the overview card and the dedicated
    // table must be instant, not refetch the (slow) bridge.
    if (forexPairs.length > 0) { setLoadingTab(false); return; }
    let cancelled = false;
    (async () => {
      setLoadingForex(true);
      try {
        const res = await fetch('/api/forex');
        const data = await res.json();
        if (!cancelled && data && Array.isArray(data.pairs)) {
          setForexPairs(data.pairs);
        }
      } catch (err) {
        console.error('Failed to load forex pairs', err);
      } finally {
        if (!cancelled) setLoadingForex(false);
        setLoadingTab(false);
      }
    })();
    return () => { cancelled = true; };
  }, [active, forexPairs.length, setLoadingTab]);

  const toggleForexSort = (field: keyof ForexPair) => {
    if (forexSortField === field) {
      setForexSortOrder(forexSortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setForexSortField(field);
      setForexSortOrder('asc');
    }
  };

  const filteredForex = useMemo(() => {
    let list = forexPairs;
    if (forexSearch.trim()) {
      const q = forexSearch.trim().toLowerCase();
      list = list.filter(p => p.symbol.toLowerCase().includes(q) || p.name.toLowerCase().includes(q) || p.base.toLowerCase().includes(q) || p.quote.toLowerCase().includes(q));
    }
    // Preference filters: change direction, base currency, quote currency.
    if (forexChange === 'Gainers') list = list.filter(p => p.found && p.changePct > 0);
    else if (forexChange === 'Losers') list = list.filter(p => p.found && p.changePct < 0);
    else if (forexChange === 'Flat') list = list.filter(p => !p.found || p.changePct === 0);
    if (forexCurrency !== 'All') {
      list = list.filter(p => p.base === forexCurrency || p.quote === forexCurrency);
    }
    const dir = forexSortOrder === 'asc' ? 1 : -1;
    return [...list].sort((a, b) => {
      const av = a[forexSortField];
      const bv = b[forexSortField];
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [forexPairs, forexSearch, forexChange, forexCurrency, forexSortField, forexSortOrder]);

  return {
    forexPairs, forexSearch, setForexSearch, forexChange, setForexChange,
    forexCurrency, setForexCurrency, forexSortField, forexSortOrder,
    loadingForex, toggleForexSort, filteredForex,
  };
}

// Category membership for the commodities filter. `energy` here is the METALS
// group (the legacy variable name is preserved for diff clarity; the mapping
// below is the contract).
const COMMODITY_METALS = ['GC=F', 'SI=F', 'HG=F', 'PL=F', 'PA=F', 'ALI=F'];
const COMMODITY_AGRI = ['ZW=F', 'ZC=F', 'ZS=F', 'KC=F', 'CC=F', 'SB=F', 'CT=F', 'LE=F'];

export function useCommodities(active: boolean, setLoadingTab: (v: boolean) => void) {
  const [commodities, setCommodities] = useState<CommodityItem[]>([]);
  const [commoditySearch, setCommoditySearch] = useState('');
  const [commodityChange, setCommodityChange] = useState('All');
  const [commodityCategory, setCommodityCategory] = useState('All');
  const [loadingCommodities, setLoadingCommodities] = useState(false);

  useEffect(() => {
    if (!active) return;
    // Already loaded — switching between the overview card and the dedicated
    // table must be instant, not refetch the (slow) bridge.
    if (commodities.length > 0) { setLoadingTab(false); return; }
    let cancelled = false;
    (async () => {
      setLoadingCommodities(true);
      try {
        const res = await fetch('/api/commodities');
        const data = await res.json();
        if (!cancelled && data && Array.isArray(data.commodities)) {
          setCommodities(data.commodities);
        }
      } catch (err) {
        console.error('Failed to load commodities', err);
      } finally {
        if (!cancelled) setLoadingCommodities(false);
        setLoadingTab(false);
      }
    })();
    return () => { cancelled = true; };
  }, [active, commodities.length, setLoadingTab]);

  const filteredCommodities = useMemo(() => {
    let list = commodities;
    if (commoditySearch.trim()) {
      const q = commoditySearch.trim().toLowerCase();
      list = list.filter(c => c.name.toLowerCase().includes(q) || c.symbol.toLowerCase().includes(q));
    }
    // Preference filters: change direction + category (energy/metals/agriculture).
    if (commodityChange === 'Gainers') list = list.filter(c => c.found && c.changePct > 0);
    else if (commodityChange === 'Losers') list = list.filter(c => c.found && c.changePct < 0);
    else if (commodityChange === 'Flat') list = list.filter(c => !c.found || c.changePct === 0);
    if (commodityCategory !== 'All') {
      list = list.filter(c =>
        commodityCategory === 'Energy'
          ? ['CL=F', 'BZ=F', 'NG=F'].includes(c.symbol)
          : commodityCategory === 'Metals'
            ? COMMODITY_METALS.includes(c.symbol)
            : COMMODITY_AGRI.includes(c.symbol)
      );
    }
    return list;
  }, [commodities, commoditySearch, commodityChange, commodityCategory]);

  return {
    commodities, commoditySearch, setCommoditySearch, commodityChange,
    setCommodityChange, commodityCategory, setCommodityCategory,
    loadingCommodities, filteredCommodities,
  };
}
