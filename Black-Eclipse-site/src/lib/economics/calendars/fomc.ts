// ── Official FOMC meeting calendar ──────────────────────────────────────────
// The Federal Reserve publishes its meeting schedule at
//   https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
// This module reads that page and returns the real meeting dates — never a
// synthetic "spread over the next 30 days" placeholder. An asterisk in the
// Fed's own date cell marks a tentative meeting and is preserved as
// `confirmed: false`.
//
// The parser is deliberately small and fixture-testable: the Fed's markup is a
// per-year `panel` whose rows carry `.fomc-meeting__month` and
// `.fomc-meeting__date`. Anything we cannot parse is skipped, not guessed.

import * as cheerio from "cheerio";
import { safeGet } from "@/lib/connectors/security";
import { OUTBOUND_USER_AGENT } from "@/lib/web-research";

const FOMC_CALENDAR_URL =
  "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm";

const MONTHS: Record<string, number> = {
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

export interface FomcMeeting {
  /** Decision day, `YYYY-MM-DD`. FOMC statements are released at 2pm ET. */
  date: string;
  time: string;
  title: string;
  country: "US";
  confirmed: boolean;
  source: "official";
  url: string;
}

function isoDate(year: number, month: number, day: number): string {
  const y = String(year).padStart(4, "0");
  const m = String(month + 1).padStart(2, "0");
  const d = String(day).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/**
 * Parse the Fed's calendar HTML. Exported for tests. `now` is not used to
 * filter — callers decide the window — so historical fixtures stay stable.
 */
export function parseFomcCalendar(
  html: string,
  url = FOMC_CALENDAR_URL,
): FomcMeeting[] {
  const $ = cheerio.load(html);
  const meetings: FomcMeeting[] = [];

  $(".panel").each((_, panel) => {
    const heading = $(panel).find("h4").first().text();
    const yearMatch = heading.match(/(\d{4})\s+FOMC/i);
    if (!yearMatch) return;
    const year = Number(yearMatch[1]);

    $(panel)
      .find(".fomc-meeting")
      .each((_row, row) => {
        const monthText = $(row)
          .find(".fomc-meeting__month")
          .first()
          .text()
          .trim()
          .toLowerCase();
        const month = MONTHS[monthText];
        if (month === undefined) return;

        const rawDate = $(row).find(".fomc-meeting__date").first().text().trim();
        // "27-28", "17-18*", "30-1", "22 (notation vote)". Keep only the
        // leading day/range; a notation vote or conference call is not a
        // two-day policy meeting and must not become a rate-decision event.
        const cleaned = rawDate.replace(/\*/g, "").trim();
        if (/notation|conference|call|vote/i.test(cleaned)) return;
        if (!/^\d{1,2}(?:\s*[-–]\s*\d{1,2})?$/.test(cleaned)) return;
        const range = cleaned.match(/^(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?/);
        if (!range) return;

        const startDay = Number(range[1]);
        const endDay = range[2] ? Number(range[2]) : startDay;
        let decisionMonth = month;
        let decisionYear = year;

        // A range like "30-1" crosses into the following month.
        if (endDay < startDay) {
          decisionMonth += 1;
          if (decisionMonth > 11) {
            decisionMonth = 0;
            decisionYear += 1;
          }
        }
        if (
          !Number.isInteger(startDay) ||
          !Number.isInteger(endDay) ||
          startDay < 1 ||
          startDay > 31 ||
          endDay < 1 ||
          endDay > 31
        ) {
          return;
        }

        meetings.push({
          date: isoDate(decisionYear, decisionMonth, endDay),
          time: "14:00 ET",
          title: "FOMC Interest Rate Decision",
          country: "US",
          confirmed: !rawDate.includes("*"),
          source: "official",
          url,
        });
      });
  });

  // Deduplicate identical dates (the page can repeat a panel for anchors).
  const seen = new Set<string>();
  return meetings
    .filter((m) => {
      if (seen.has(m.date)) return false;
      seen.add(m.date);
      return true;
    })
    .sort((a, b) => a.date.localeCompare(b.date));
}

const CACHE_TTL_MS = 12 * 60 * 60 * 1000;
let cache: { at: number; meetings: FomcMeeting[] } | null = null;

/**
 * Fetch and parse the live Fed calendar. Throws when the official page is
 * unreachable or unparseable — callers must degrade to "no confirmed date",
 * never invent one.
 */
export async function fetchFomcSchedule(
  deps: { get?: typeof safeGet; now?: () => number } = {},
): Promise<FomcMeeting[]> {
  const now = deps.now ?? Date.now;
  if (cache && now() - cache.at < CACHE_TTL_MS) return cache.meetings;

  const get = deps.get ?? safeGet;
  const res = await get({
    url: FOMC_CALENDAR_URL,
    headers: { "user-agent": OUTBOUND_USER_AGENT },
    timeoutMs: 10_000,
    maxBytes: 4 * 1024 * 1024,
  });
  if (res.status < 200 || res.status >= 300) {
    throw new Error(`FOMC calendar HTTP ${res.status}`);
  }
  const meetings = parseFomcCalendar(res.text, FOMC_CALENDAR_URL);
  if (meetings.length === 0) {
    throw new Error("FOMC calendar page contained no parseable meeting dates");
  }
  cache = { at: now(), meetings };
  return meetings;
}

/** Test-only: reset the module cache. */
export function __resetFomcCache(): void {
  cache = null;
}
