// ── BEA release schedule (GDP + PCE) ────────────────────────────────────────
// `bea.gov/news/schedule` renders one table per year; each row carries an
// explicit month/day (`td.scheduled-date .release-date`) and time. We keep only
// the GDP and Personal Income & Outlays releases, which is what the macro
// calendar needs; everything else on the page is intentionally ignored.

import * as cheerio from "cheerio";
import { safeGet } from "@/lib/connectors/security";
import { OUTBOUND_USER_AGENT } from "@/lib/web-research";
import { MONTHS, isoDate, dedupe, type OfficialEvent } from "./types";

const BEA_URL = "https://www.bea.gov/news/schedule";

function titleFor(release: string): string | null {
  if (/gross domestic product/i.test(release)) return "US GDP Release";
  if (/personal income and outlays/i.test(release)) return "US PCE Inflation";
  return null;
}

export function parseBeaSchedule(html: string, url = BEA_URL): OfficialEvent[] {
  const $ = cheerio.load(html);
  const events: OfficialEvent[] = [];

  $("#release-schedule-table").each((_, table) => {
    const yearText = $(table).find("thead th").first().text();
    const yearMatch = yearText.match(/(\d{4})/);
    if (!yearMatch) return;
    const year = Number(yearMatch[1]);

    $(table)
      .find("tbody tr")
      .each((_row, row) => {
        const dateText = $(row).find(".release-date").first().text().trim();
        const dateMatch = dateText.match(/^([A-Za-z]+)\s+(\d{1,2})$/);
        if (!dateMatch) return;
        const month = MONTHS[dateMatch[1].toLowerCase()];
        const day = Number(dateMatch[2]);
        if (month === undefined || day < 1 || day > 31) return;

        const release = $(row).find(".release-title").first().text().replace(/\s+/g, " ").trim();
        const title = titleFor(release);
        if (!title) return;

        const timeText = $(row).find(".scheduled-date small").first().text().trim();
        events.push({
          date: isoDate(year, month, day),
          time: timeText ? `${timeText} ET` : null,
          title,
          country: "US",
          importance: "high",
          confirmed: true,
          url,
        });
      });
  });

  return dedupe(events);
}

const CACHE_TTL_MS = 12 * 60 * 60 * 1000;
let cache: { at: number; events: OfficialEvent[] } | null = null;

export async function fetchBeaSchedules(now: () => number = Date.now): Promise<OfficialEvent[]> {
  if (cache && now() - cache.at < CACHE_TTL_MS) return cache.events;
  const res = await safeGet({
    url: BEA_URL,
    headers: { "user-agent": OUTBOUND_USER_AGENT },
    timeoutMs: 10_000,
    maxBytes: 3 * 1024 * 1024,
  });
  if (res.status < 200 || res.status >= 300) throw new Error(`BEA HTTP ${res.status}`);
  const events = parseBeaSchedule(res.text);
  if (events.length === 0) throw new Error("BEA schedule had no parseable GDP/PCE rows");
  cache = { at: now(), events };
  return events;
}

export function __resetBeaCache(): void {
  cache = null;
}
