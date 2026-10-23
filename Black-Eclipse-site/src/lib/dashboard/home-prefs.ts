'use client';

import { useCallback, useEffect, useState } from 'react';

export type HomeLens = 'investor' | 'trader' | 'both';

export interface HomePrefs {
  lens: HomeLens;
  name: string;
  hiddenSections: string[];
  sectionOrder: string[];
}

const KEY = 'be_home_prefs_v1';

const DEFAULTS: HomePrefs = { lens: 'both', name: '', hiddenSections: [], sectionOrder: [] };

function read(): HomePrefs {
  if (typeof window === 'undefined') return DEFAULTS;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<HomePrefs>;
    return {
      lens: parsed.lens === 'investor' || parsed.lens === 'trader' || parsed.lens === 'both' ? parsed.lens : 'both',
      name: typeof parsed.name === 'string' ? parsed.name : '',
      hiddenSections: Array.isArray(parsed.hiddenSections) ? parsed.hiddenSections.filter((id): id is string => typeof id === 'string') : [],
      sectionOrder: Array.isArray(parsed.sectionOrder) ? parsed.sectionOrder.filter((id): id is string => typeof id === 'string') : [],
    };
  } catch {
    return DEFAULTS;
  }
}

function write(prefs: HomePrefs): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
}

export function useHomePrefs() {
  const [prefs, setPrefs] = useState<HomePrefs>(DEFAULTS);

  useEffect(() => {
    setPrefs(read());
  }, []);

  const setLens = useCallback((lens: HomeLens) => {
    setPrefs((prev) => {
      const next = { ...prev, lens };
      write(next);
      return next;
    });
  }, []);

  const setName = useCallback((name: string) => {
    const trimmed = name.trim().slice(0, 40);
    setPrefs((prev) => {
      const next = { ...prev, name: trimmed };
      write(next);
      return next;
    });
  }, []);

  const toggleSection = useCallback((id: string) => {
    setPrefs((prev) => {
      const hidden = prev.hiddenSections.includes(id)
        ? prev.hiddenSections.filter((item) => item !== id)
        : [...prev.hiddenSections, id];
      const next = { ...prev, hiddenSections: hidden };
      write(next);
      return next;
    });
  }, []);

  const moveSection = useCallback((id: string, direction: -1 | 1, defaults: string[]) => {
    setPrefs((prev) => {
      const order = (prev.sectionOrder.length > 0 ? prev.sectionOrder : defaults).filter((item) => defaults.includes(item));
      for (const item of defaults) if (!order.includes(item)) order.push(item);
      const index = order.indexOf(id);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= order.length) return prev;
      const nextOrder = [...order];
      [nextOrder[index], nextOrder[target]] = [nextOrder[target], nextOrder[index]];
      const next = { ...prev, sectionOrder: nextOrder };
      write(next);
      return next;
    });
  }, []);

  return { prefs, setLens, setName, toggleSection, moveSection };
}

export function greetingFor(date = new Date()): string {
  const hour = date.getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}
