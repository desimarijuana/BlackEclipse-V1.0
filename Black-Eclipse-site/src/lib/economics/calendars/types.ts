// Shared shape for every official release schedule adapter (FOMC, BLS, BEA,
// ECB, BoE, BoJ). Adapters only ever return dates the institution itself
// published; an unparseable page yields an empty list, never a guess.

export interface OfficialEvent {
  /** `YYYY-MM-DD` — the release/decision day. */
  date: string;
  /** Human-readable release time with its timezone, when published. */
  time: string | null;
  title: string;
  country: string;
  importance: "high" | "medium";
  /** False when the institution marks the date provisional/tentative. */
  confirmed: boolean;
  url: string;
}

export const MONTHS: Record<string, number> = {
  january: 0,
  february: 1,
  march: 2,
  april: 3,
  may: 4,
  june: 5,
  july: 6,
  august: 7,
  september: 8,
  october: 9,
  november: 10,
  december: 11,
};

export const MONTHS_SHORT: Record<string, number> = {
  jan: 0,
  feb: 1,
  mar: 2,
  apr: 3,
  may: 4,
  jun: 5,
  jul: 6,
  aug: 7,
  sep: 8,
  sept: 8,
  oct: 9,
  nov: 10,
  dec: 11,
};

export function isoDate(year: number, month: number, day: number): string {
  return `${String(year).padStart(4, "0")}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** Sort + drop duplicate dates for the same title. */
export function dedupe(events: OfficialEvent[]): OfficialEvent[] {
  const seen = new Set<string>();
  return events
    .filter((e) => {
      const key = `${e.title}|${e.date}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => a.date.localeCompare(b.date));
}

export interface CalendarAdapter {
  id: string;
  fetch: () => Promise<OfficialEvent[]>;
}
