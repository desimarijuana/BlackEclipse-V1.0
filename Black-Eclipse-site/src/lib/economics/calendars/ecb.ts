// ── ECB Governing Council monetary-policy meeting calendar ──────────────────
// The ECB publishes the schedule as a definition list: `<dt>dd/mm/yyyy</dt>`
// followed by a `<dd>` description. Only monetary-policy meeting days count;
// "Day 1" is excluded so the decision day (Day 2, press conference) is the
// event date.

import * as cheerio from "cheerio";
import { safeGet } from "@/lib/connectors/security";
import { OUTBOUND_USER_AGENT } from "@/lib/web-research";
import { isoDate, dedupe, type OfficialEvent } from "./types";

const ECB_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html";

export function parseEcbSchedule(html: string, url = ECB_URL): OfficialEvent[] {
  const $ = cheerio.load(html);
  const events: OfficialEvent[] = [];

  $("dl dt").each((_i, dt) => {
    const dateText = $(dt).text().trim();
    const match = dateText.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (!match) return;
    const day = Number(match[1]);
    const month = Number(match[2]) - 1;
    const year = Number(match[3]);
    if (day < 1 || day > 31 || month < 0 || month > 11) return;

    const description = $(dt).next("dd").first().text().replace(/\s+/g, " ").trim();
    if (/non-monetary/i.test(description)) return;
    if (!/(^|\s)monetary policy meeting/i.test(description)) return;
    // Day 1 is the first sitting; the decision/press conference is Day 2.
    if (/\(day 1\)/i.test(description)) return;

    events.push({
      date: isoDate(year, month, day),
      time: "14:15 CET",
      title: "ECB Interest Rate Decision",
      country: "EU",
      importance: "high",
      confirmed: true,
      url,
    });
  });

  return dedupe(events);
}

const CACHE_TTL_MS = 12 * 60 * 60 * 1000;
let cache: { at: number; events: OfficialEvent[] } | null = null;

export async function fetchEcbSchedule(now: () => number = Date.now): Promise<OfficialEvent[]> {
  if (cache && now() - cache.at < CACHE_TTL_MS) return cache.events;
  const res = await safeGet({
    url: ECB_URL,
    headers: { "user-agent": OUTBOUND_USER_AGENT },
    timeoutMs: 10_000,
    maxBytes: 4 * 1024 * 1024,
  });
  if (res.status < 200 || res.status >= 300) throw new Error(`ECB HTTP ${res.status}`);
  const events = parseEcbSchedule(res.text);
  if (events.length === 0) throw new Error("ECB calendar had no parseable monetary-policy dates");
  cache = { at: now(), events };
  return events;
}

export function __resetEcbCache(): void {
  cache = null;
}
