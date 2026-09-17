export const NAV_HISTORY_LIMIT = 20;

export interface NavigationHistoryOptions<T> {
  cap?: number;
  isKnown?: (tab: T) => boolean;
}

export function recordVisit<T>(history: T[], tab: T, options: NavigationHistoryOptions<T> = {}): T[] {
  const cap = Math.max(1, Math.floor(options.cap ?? NAV_HISTORY_LIMIT));
  if (options.isKnown && !options.isKnown(tab)) return history;
  if (history.length > 0 && history[history.length - 1] === tab) return history;
  const next = [...history, tab];
  return next.length > cap ? next.slice(next.length - cap) : next;
}

export function backTarget<T>(history: T[]): { tab: T; history: T[] } | null {
  if (history.length < 2) return null;
  const index = history.length - 2;
  return { tab: history[index], history: history.slice(0, index + 1) };
}
