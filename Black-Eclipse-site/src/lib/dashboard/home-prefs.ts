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
      // Picking a lens applies that workflow's default card order; a custom
      // arrangement from the previous lens would otherwise mask the change.
      const next = { ...prev, lens, sectionOrder: [] };
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

export type TimeOfDay = 'morning' | 'afternoon' | 'evening' | 'night';

/**
 * Local-wall-clock part of day. Boundaries are intentionally user-facing:
 * morning 05:00–11:59, afternoon 12:00–16:59, evening 17:00–21:59, night
 * 22:00–04:59. Computed from the *browser's* clock, never the server's, so a
 * user in another time zone is not told it is evening at noon.
 */
export function timeOfDayFor(date = new Date()): TimeOfDay {
  const hour = date.getHours();
  if (hour >= 5 && hour < 12) return 'morning';
  if (hour >= 12 && hour < 17) return 'afternoon';
  if (hour >= 17 && hour < 22) return 'evening';
  return 'night';
}

const GREETING: Record<TimeOfDay, string> = {
  morning: 'Good morning',
  afternoon: 'Good afternoon',
  evening: 'Good evening',
  night: 'Good night',
};

export function greetingFor(date = new Date()): string {
  return GREETING[timeOfDayFor(date)];
}

/**
 * Live greeting for the Dashboard header.
 *
 * The greeting used to be computed once during render, so a keep-alive tab
 * left open all day kept saying "Good morning" (or "Good evening") until a
 * manual refresh. This ticks once a minute against the browser clock and
 * re-derives both the greeting and the day label, so the header stays truthful
 * across noon, sunset and midnight.
 */
export function useGreeting(): { greeting: string; timeOfDay: TimeOfDay; today: string } {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    setNow(new Date());
    const id = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  return {
    greeting: greetingFor(now),
    timeOfDay: timeOfDayFor(now),
    today: now.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' }),
  };
}
