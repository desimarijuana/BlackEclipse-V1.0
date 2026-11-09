// ── Bank of England MPC announcement dates ──────────────────────────────────
// `bankofengland.co.uk/monetary-policy/upcoming-mpc-dates` groups dates under
// `<h2>YYYY confirmed dates</h2>` followed by a table. Each row's first cell is
// "Thursday 5 February" (no year) — the year comes from the heading.

import * as cheerio from "cheerio";
import { safeGet } from "@/lib/connectors/security";
import { OUTBOUND_USER_AGENT } from "@/lib/web-research";
import { MONTHS, isoDate, dedupe, type OfficialEvent } from "./types";

const BOE_URL = "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates";

export function parseBoeSchedule(html: string, url = BOE_URL): OfficialEvent[] {
  const $ = cheerio.load(html);
  const events: OfficialEvent[] = [];

  $("h2").each((_i, heading) => {
    const headingText = $(heading).text().replace(/\s+/g, " ").trim();
    const yearMatch = headingText.match(/(\d{4})\b/);
    if (!yearMatch) return;
    const year = Number(yearMatch[1]);
    const confirmed = !/provisional|tentative|to be confirmed/i.test(headingText);
    const table = $(heading).next("table");
    if (table.length === 0) return;

    table.find("tbody tr").each((_r, row) => {
      const cells = $(row).find("td");
      if (cells.length === 0) return;
      const dateText = cells.eq(0).text().replace(/\s+/g, " ").trim();
      const match = dateText.match(/(\d{1,2})\s+([A-Za-z]+)/);
      if (!match) return;
      const day = Number(match[1]);
      const month = MONTHS[match[2].toLowerCase()];
      if (month === undefined || day < 1 || day > 31) return;

      events.push({
        date: isoDate(year, month, day),
        time: "12:00 UK",
        title: "BoE Bank Rate Decision",
        country: "UK",
        importance: "high",
        confirmed,
        url,
      });
    });
  });

  return dedupe(events);
}

const CACHE_TTL_MS = 12 * 60 * 60 * 1000;
let cache: { at: number; events: OfficialEvent[] } | null = null;

export async function fetchBoeSchedule(now: () => number = Date.now): Promise<OfficialEvent[]> {
  if (cache && now() - cache.at < CACHE_TTL_MS) return cache.events;
  const res = await safeGet({
    url: BOE_URL,
    headers: { "user-agent": OUTBOUND_USER_AGENT },
    timeoutMs: 10_000,
    maxBytes: 4 * 1024 * 1024,
  });
  if (res.status < 200 || res.status >= 300) throw new Error(`BoE HTTP ${res.status}`);
  const events = parseBoeSchedule(res.text);
  if (events.length === 0) throw new Error("BoE page had no parseable MPC dates");
  cache = { at: now(), events };
  return events;
}

export function __resetBoeCache(): void {
  cache = null;
}
