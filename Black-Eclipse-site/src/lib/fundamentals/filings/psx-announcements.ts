// ── PSX company announcements (Pakistan) ───────────────────────────────────
// `https://dps.psx.com.pk/company/<SYMBOL>` renders an #announcements section
// with three tables — Financial Results, Board Meetings, Others — each row
// carrying Date | Title | Document. The PDF link is an official PSX document.
//
// This is the non-US filing-list counterpart to the SEC submissions index:
// only what the exchange publishes, never a guessed date or document.

import * as cheerio from "cheerio";
import { safeGet } from "@/lib/connectors/security";
import { MONTHS_SHORT, isoDate } from "@/lib/economics/calendars/types";

const PSX_COMPANY = "https://dps.psx.com.pk/company/";
const PSX_ORIGIN = "https://dps.psx.com.pk";
const CATEGORIES = ["Financial Results", "Board Meetings", "Others"] as const;

// PSX serves the portal to browser-shaped clients; the declared SEC-style UA is
// not accepted there, so this adapter keeps the existing PSX identity.
const HEADERS = {
  "user-agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
  accept: "text/html,application/xhtml+xml",
  "x-requested-with": "XMLHttpRequest",
};

export interface PsxAnnouncement {
  /** `YYYY-MM-DD` */
  date: string;
  title: string;
  category: (typeof CATEGORIES)[number];
  documentId: string | null;
  url: string | null;
}

export function parsePsxAnnouncements(html: string): PsxAnnouncement[] {
  if (!html) return [];
  const $ = cheerio.load(html);
  const out: PsxAnnouncement[] = [];

  $("#announcements table").each((index, table) => {
    const category = CATEGORIES[index] ?? "Others";
    $(table)
      .find("tbody tr")
      .each((_row, row) => {
        const cells = $(row).find("td");
        if (cells.length < 2) return;
        const dateText = cells.eq(0).text().trim();
        const match = dateText.match(/^([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})$/);
        if (!match) return;
        const month = MONTHS_SHORT[match[1].toLowerCase().slice(0, 3)];
        const day = Number(match[2]);
        const year = Number(match[3]);
        if (month === undefined || day < 1 || day > 31) return;

        const title = cells.eq(1).text().replace(/\s+/g, " ").trim();
        if (!title) return;

        const pdf = $(row).find('a[href^="/download/document/"]').first().attr("href") ?? null;
        const imageId = $(row).find("[data-images]").first().attr("data-images") ?? null;
        const documentId =
          pdf?.match(/\/download\/document\/(\d+)\.pdf/)?.[1] ??
          imageId?.split("-")[0] ??
          null;

        out.push({
          date: isoDate(year, month, day),
          title,
          category,
          documentId,
          url: pdf ? `${PSX_ORIGIN}${pdf}` : null,
        });
      });
  });

  const seen = new Set<string>();
  return out
    .filter((item) => {
      const key = `${item.date}|${item.title}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .sort((a, b) => b.date.localeCompare(a.date));
}

export interface PsxFilingRow {
  form: string;
  filed: string;
  period: string | null;
  accession: string | null;
  document: string | null;
  description: string;
}

/** Normalize PSX announcements into the filing-list shape the UI expects. */
export function toPsxFilingRows(items: PsxAnnouncement[]): PsxFilingRow[] {
  return items.map((item) => ({
    form: item.category,
    filed: item.date,
    period: null,
    accession: item.documentId,
    document: item.url,
    description: item.title,
  }));
}

const CACHE_TTL_MS = 30 * 60 * 1000;
const cache = new Map<string, { at: number; items: PsxAnnouncement[] }>();

export async function fetchPsxAnnouncements(
  symbol: string,
  deps: { get?: typeof safeGet; now?: () => number } = {},
): Promise<PsxAnnouncement[]> {
  const ticker = symbol.trim().toUpperCase();
  if (!ticker) return [];
  const now = deps.now ?? Date.now;
  const hit = cache.get(ticker);
  if (hit && now() - hit.at < CACHE_TTL_MS) return hit.items;

  const get = deps.get ?? safeGet;
  const res = await get({
    url: `${PSX_COMPANY}${encodeURIComponent(ticker)}`,
    headers: HEADERS,
    timeoutMs: 12_000,
    maxBytes: 4 * 1024 * 1024,
  });
  if (res.status < 200 || res.status >= 300) {
    throw new Error(`PSX company page HTTP ${res.status}`);
  }
  const items = parsePsxAnnouncements(res.text);
  if (items.length === 0) throw new Error(`PSX returned no announcements for ${ticker}`);
  cache.set(ticker, { at: now(), items });
  return items;
}

export function __resetPsxAnnouncementsCache(): void {
  cache.clear();
}
