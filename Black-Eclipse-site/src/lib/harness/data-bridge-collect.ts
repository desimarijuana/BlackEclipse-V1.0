// ─── The bounded COLLECT capability (R3-04) ─────────────────────────────────
// One page in, structured records out — the acquisition route the runtime
// exposes as the `web_scrape` tool. It is a REAL fetch through the ONE
// SSRF-hardened transport (`safeGet`: https-only, DNS-pinned, every redirect
// re-validated, streamed size cap) plus DETERMINISTIC extraction with cheerio
// (CSS-selector records or the page's own tables). No model is involved and
// nothing is guessed: a selector that matches nothing is a confirmed zero ON
// THE DELIVERED PAGE (a client-rendered page is a different story — the browser
// tools are the escalation route), and a failed fetch is UNAVAILABLE.
//
// Caps per call: 8 s timeout, 4 MB download, 4 redirects, 500 rows, 5 tables,
// 40 columns, 20 k text chars. Bulk/scheduled acquisition is a different,
// deliberately unbuilt capability — this is one page, one request, one answer.

import * as cheerio from "cheerio";
import { safeGet, validateOutboundUrl, OutboundError } from "@/lib/connectors/security";
import { OUTBOUND_USER_AGENT } from "@/lib/web-research";
import type { DataBridgeResult } from "./data-bridge-types";

const FETCH_TIMEOUT_MS = 8_000;
const MAX_BYTES = 4 * 1024 * 1024;
const MAX_REDIRECTS = 4;
const MAX_ROWS = 500;
const DEFAULT_ROWS = 100;
const MAX_TABLES = 5;
const MAX_COLS = 40;
const MAX_TEXT_CHARS = 20_000;
const MAX_CELL_CHARS = 500;

function collapse(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function cellText(value: string | null | undefined): string {
  return collapse(value ?? "").slice(0, MAX_CELL_CHARS);
}

function boundedRows(raw: unknown): number {
  const n = typeof raw === "number" && Number.isFinite(raw) ? Math.floor(raw) : DEFAULT_ROWS;
  return Math.min(MAX_ROWS, Math.max(1, n));
}

function fieldMap(raw: unknown): Record<string, string> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  return Object.fromEntries(
    Object.entries(raw as Record<string, unknown>)
      .slice(0, MAX_COLS)
      .map(([key, value]) => [String(key), String(value)]),
  );
}

export interface CollectDeps {
  /** Injectable transport for deterministic offline tests. */
  get?: typeof safeGet;
}

export async function webCollectCapability(
  params: Record<string, unknown>,
  deps?: CollectDeps,
): Promise<DataBridgeResult> {
  const url = String(params.url ?? "").trim();
  if (!url) return { status: "UNAVAILABLE", error: "url is required" };
  const check = validateOutboundUrl(url);
  if (!check.safe) {
    return {
      status: "UNAVAILABLE",
      failureClass: "blocked",
      error: `URL rejected: ${check.reason ?? "unsafe"}`,
    };
  }

  const get = deps?.get ?? safeGet;
  let res;
  try {
    res = await get({
      url,
      timeoutMs: FETCH_TIMEOUT_MS,
      maxBytes: MAX_BYTES,
      maxRedirects: MAX_REDIRECTS,
      headers: {
        "user-agent": OUTBOUND_USER_AGENT,
        accept:
          "text/html,application/xhtml+xml,application/json,application/xml,text/plain;q=0.9,*/*;q=0.5",
      },
    });
  } catch (err) {
    const code = err instanceof OutboundError ? err.code : "";
    const failureClass =
      code === "timeout"
        ? "timeout"
        : code === "too_large"
          ? "too_large"
          : code.startsWith("blocked") || code === "invalid_url"
            ? "blocked"
            : "transport_error";
    return {
      status: "UNAVAILABLE",
      failureClass,
      error: `page request failed (${code || "transport"})`,
    };
  }
  if (res.status < 200 || res.status >= 300) {
    return {
      status: "UNAVAILABLE",
      failureClass: "http_error",
      httpStatus: res.status,
      error: `HTTP ${res.status}`,
    };
  }

  const contentType = res.contentType ?? null;
  const result: DataBridgeResult = {
    status: "OK",
    url,
    finalUrl: res.url || url,
    contentType,
    retrievedAt: new Date().toISOString(),
    bytes: res.bytes,
    truncated: res.bytes >= MAX_BYTES,
  };

  const isHtml = !contentType || /html/i.test(contentType);
  if (!isHtml) {
    result.text = res.text.slice(0, MAX_TEXT_CHARS);
    result.extraction = "text";
    return result;
  }

  const $ = cheerio.load(res.text);
  result.title = cellText($("title").first().text()) || null;

  const selector = String(params.selector ?? "").trim();
  if (selector) {
    const fields = fieldMap(params.fields);
    const fieldNames = Object.keys(fields);
    const attribute = String(params.attribute ?? "").trim() || null;
    const maxRows = boundedRows(params.maxRows);
    const all = $(selector);
    const take = Math.min(all.length, maxRows);
    const rows: Array<Record<string, string>> = [];
    for (let i = 0; i < take; i += 1) {
      const scope = all.eq(i);
      const row: Record<string, string> = {};
      if (fieldNames.length) {
        for (const [field, child] of Object.entries(fields)) {
          row[field] = cellText(scope.find(child).first().text());
        }
      } else if (attribute) {
        row[attribute] = cellText(scope.attr(attribute));
      } else {
        row.text = cellText(scope.text());
      }
      rows.push(row);
    }
    result.rows = rows;
    result.columns = fieldNames.length ? fieldNames : [attribute ?? "text"];
    result.matched = all.length;
    result.extraction = "selector";
    if (all.length === 0) {
      result.note =
        "No elements matched the selector on the delivered page (a confirmed zero for THIS page). " +
        "A client-rendered page needs the browser tools instead.";
    }
    return result;
  }

  if (params.tables === false) {
    result.text = collapse($("body").text() || $.root().text()).slice(0, MAX_TEXT_CHARS);
    result.extraction = "text";
    return result;
  }

  const tables: Array<{ caption: string | null; columns: string[]; rows: string[][] }> = [];
  $("table")
    .slice(0, MAX_TABLES)
    .each((_, table) => {
      const scope = $(table);
      const columns: string[] = [];
      scope
        .find("tr")
        .first()
        .find("th,td")
        .slice(0, MAX_COLS)
        .each((__, cell) => {
          columns.push(cellText($(cell).text()));
        });
      const rows: string[][] = [];
      scope
        .find("tr")
        .slice(1, MAX_ROWS + 1)
        .each((__, tr) => {
          const cells: string[] = [];
          $(tr)
            .find("td,th")
            .slice(0, MAX_COLS)
            .each((___, cell) => {
              cells.push(cellText($(cell).text()));
            });
          if (cells.length) rows.push(cells);
        });
      tables.push({ caption: cellText(scope.find("caption").first().text()) || null, columns, rows });
    });
  result.tables = tables;
  result.tableCount = tables.length;
  result.extraction = "tables";
  if (tables.length === 0) {
    result.note = "The delivered page contained no <table> elements.";
    result.text = collapse($("body").text() || $.root().text()).slice(0, MAX_TEXT_CHARS);
  }
  return result;
}
