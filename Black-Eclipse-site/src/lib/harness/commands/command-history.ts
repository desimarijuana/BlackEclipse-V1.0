'use client';

// ─── Command usage memory (client) ────────────────────────────────────────────
// Recent commands and pinned commands are a UI convenience, never an authority.
// They live in localStorage so they survive a reload, and in a module cache so
// the palette re-renders without a storage read on every keystroke. Every access
// is guarded: SSR and the node test runner have no localStorage, and the store
// still works in memory there.
//
// This is deliberately separate from the server audit stream: the audit is the
// record of what ran, this is only what the user wants quick access to.

import { useSyncExternalStore } from "react";

export interface CommandHistoryEntry {
  /** Canonical command name, no leading slash. */
  name: string;
  /** Unix ms of the most recent use. */
  at: number;
}

const HISTORY_KEY = "be.command.history.v1";
const FAVORITES_KEY = "be.command.favorites.v1";
const MAX_HISTORY = 50;
const MAX_FAVORITES = 24;

const EMPTY_HISTORY: readonly CommandHistoryEntry[] = Object.freeze([]);
const EMPTY_FAVORITES: readonly string[] = Object.freeze([]);

const listeners = new Set<() => void>();
let historyCache: readonly CommandHistoryEntry[] | null = null;
let favoritesCache: readonly string[] | null = null;

function storage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    return window.localStorage;
  } catch {
    return null;
  }
}

function readJson<T>(key: string, fallback: T): T {
  const store = storage();
  if (!store) return fallback;
  try {
    const raw = store.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(key, JSON.stringify(value));
  } catch {
    /* quota/privacy mode — the in-memory cache still works */
  }
}

function emit(): void {
  for (const listener of listeners) listener();
}

function normalizeName(name: string): string {
  return String(name ?? "").trim().replace(/^\//, "").toLowerCase();
}

function sanitizeHistory(value: unknown): CommandHistoryEntry[] {
  if (!Array.isArray(value)) return [];
  const out: CommandHistoryEntry[] = [];
  const seen = new Set<string>();
  for (const row of value) {
    if (!row || typeof row !== "object") continue;
    const name = normalizeName(String((row as { name?: unknown }).name ?? ""));
    const at = Number((row as { at?: unknown }).at);
    if (!name || !Number.isFinite(at) || seen.has(name)) continue;
    seen.add(name);
    out.push({ name, at });
    if (out.length >= MAX_HISTORY) break;
  }
  return out;
}

function sanitizeFavorites(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of value) {
    const name = normalizeName(String(raw ?? ""));
    if (!name || seen.has(name)) continue;
    seen.add(name);
    out.push(name);
    if (out.length >= MAX_FAVORITES) break;
  }
  return out;
}

/** Recent commands, newest first, de-duplicated by command name. */
export function getCommandHistory(): readonly CommandHistoryEntry[] {
  if (historyCache === null) {
    historyCache = sanitizeHistory(readJson<unknown>(HISTORY_KEY, []));
  }
  return historyCache;
}

/** Pinned command names, in the order the user pinned them. */
export function getCommandFavorites(): readonly string[] {
  if (favoritesCache === null) {
    favoritesCache = sanitizeFavorites(readJson<unknown>(FAVORITES_KEY, []));
  }
  return favoritesCache;
}

/**
 * Record one command submission. Recording the same command repeatedly moves it
 * to the front rather than filling the list with duplicates.
 */
export function recordCommandRun(name: string): void {
  const token = normalizeName(name);
  if (!token) return;
  const now = Date.now();
  const current = getCommandHistory();
  const next = [
    { name: token, at: now },
    ...current.filter((entry) => entry.name !== token),
  ].slice(0, MAX_HISTORY);
  historyCache = next;
  writeJson(HISTORY_KEY, next);
  emit();
}

/** Pin or unpin a command. */
export function toggleCommandFavorite(name: string): void {
  const token = normalizeName(name);
  if (!token) return;
  const current = getCommandFavorites();
  const exists = current.includes(token);
  const next = exists
    ? current.filter((entry) => entry !== token)
    : [...current, token].slice(0, MAX_FAVORITES);
  favoritesCache = next;
  writeJson(FAVORITES_KEY, next);
  emit();
}

export function clearCommandHistory(): void {
  historyCache = EMPTY_HISTORY;
  writeJson(HISTORY_KEY, []);
  emit();
}

export function subscribeCommandMemory(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Reactive view for the palette; server snapshot is always empty. */
export function useCommandMemory(): {
  history: readonly CommandHistoryEntry[];
  favorites: readonly string[];
} {
  const history = useSyncExternalStore(
    subscribeCommandMemory,
    getCommandHistory,
    () => EMPTY_HISTORY,
  );
  const favorites = useSyncExternalStore(
    subscribeCommandMemory,
    getCommandFavorites,
    () => EMPTY_FAVORITES,
  );
  return { history, favorites };
}

/** Test-only: drop the module cache so each test starts from a clean slate. */
export function resetCommandMemoryForTests(): void {
  historyCache = null;
  favoritesCache = null;
  listeners.clear();
}

/** The most recent unique command names, newest first. */
export function recentCommandNames(limit = 5): string[] {
  return getCommandHistory()
    .slice(0, Math.max(0, limit))
    .map((entry) => entry.name);
}
