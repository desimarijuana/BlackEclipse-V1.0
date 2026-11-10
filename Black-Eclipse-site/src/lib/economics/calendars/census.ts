// ── Census Advance Monthly Retail Trade schedule ────────────────────────────
// `census.gov/retail/release_schedule.html` publishes a simple table:
// Data Month | Release Date at 8:30 am. The release date is explicit.

import * as cheerio from "cheerio";
import { safeGet } from "@/lib/connectors/security";
import { OUTBOUND_USER_AGENT } from "@/lib/web-research";
import { MONTHS, isoDate, dedupe, type OfficialEvent } from "./types";

const CENSUS_RETAIL_URL = "https://www.census.gov/retail/release_schedule.html";

export function parseCensusRetailSchedule(html: string, url = CENSUS_RETAIL_URL): OfficialEvent[] {
  const $ = cheerio.load(html);
  const events: OfficialEvent[] = [];

  $("table").each((_, table) => {
    const header = $(table).find("tr").first().text().replace(/\s+/g, " ").trim();
    if (!/data month/i.test(header) || !/release date/i.test(header)) return;

    $(table)
      .find("tr")
      .each((_row, row) => {
        const cells = $(row).find("td");
        if (cells.length < 2) return;
        const dateText = cells.eq(1).text().replace(/\s+/g, " ").trim();
        const match = dateText.match(/^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$/);
        if (!match) return;
        const month = MONTHS[match[1].toLowerCase()];
        const day = Number(match[2]);
        const year = Number(match[3]);
        if (month === undefined || day < 1 || day > 31) return;

        events.push({
          date: isoDate(year, month, day),
          time: "08:30 AM ET",
          title: "US Advance Retail Sales",
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

export async function fetchCensusRetailSchedule(now: () => number = Date.now): Promise<OfficialEvent[]> {
  if (cache && now() - cache.at < CACHE_TTL_MS) return cache.events;
  const res = await safeGet({
    url: CENSUS_RETAIL_URL,
    headers: { "user-agent": OUTBOUND_USER_AGENT },
    timeoutMs: 10_000,
    maxBytes: 3 * 1024 * 1024,
  });
  if (res.status < 200 || res.status >= 300) throw new Error(`Census HTTP ${res.status}`);
  const events = parseCensusRetailSchedule(res.text);
  if (events.length === 0) throw new Error("Census retail schedule had no parseable rows");
  cache = { at: now(), events };
  return events;
}

export function __resetCensusCache(): void {
  cache = null;
}
