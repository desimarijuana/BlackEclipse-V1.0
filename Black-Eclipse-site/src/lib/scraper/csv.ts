// CSV parsing for the market universe + price imports (shared with the
// /api/scraper/import route and the universe import script).

export interface CsvRow {
  symbol: string;
  name?: string;
  price?: number;
  changePct?: number;
  volume?: number;
  marketCap?: number;
  securityType?: string;
  assetClass?: string;
  sector?: string;
  industry?: string;
  exchange?: string;
  issuer?: string;
  cik?: string;
  isin?: string;
  cusip?: string;
  figi?: string;
  currency?: string;
  country?: string;
  website?: string;
  status?: string;
}

const HEADER_ALIASES: Record<string, keyof CsvRow> = {
  symbol: "symbol", ticker: "symbol", code: "symbol",
  name: "name", company: "name",
  price: "price", last: "price", close: "price", "last price": "price",
  change: "changePct", changepct: "changePct", "change pct": "changePct", "chg%": "changePct",
  volume: "volume", vol: "volume",
  marketcap: "marketCap", "market cap": "marketCap", mktcap: "marketCap",
  securitytype: "securityType", "security type": "securityType", type: "securityType",
  assetclass: "assetClass", "asset class": "assetClass",
  sector: "sector", industry: "industry",
  exchange: "exchange", issuer: "issuer",
  cik: "cik", isin: "isin", cusip: "cusip", figi: "figi",
  currency: "currency", country: "country",
  website: "website", status: "status",
};

function parseNumber(raw: string): number | undefined {
  const cleaned = String(raw ?? "").trim().replace(/[$,]/g, "");
  if (!cleaned) return undefined;
  const n = parseFloat(cleaned);
  return isNaN(n) ? undefined : n;
}

function detectDelimiter(firstLine: string): string {
  if (firstLine.includes("\t")) return "\t";
  return ",";
}

function normalizeHeader(h: string): string {
  return h.trim().toLowerCase().replace(/\s+/g, " ");
}

/**
 * Split a CSV line into cells, honoring double-quoted fields that may contain
 * the delimiter (e.g. `"TrueShares Technology, AI & Deep Learning ETF"`).
 */
function splitCsvLine(line: string, delimiter: string): string[] {
  const cells: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        cur += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === delimiter) {
      cells.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  cells.push(cur);
  return cells;
}

export function parseCsv(text: string): CsvRow[] {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) return [];

  const delimiter = detectDelimiter(lines[0]);

  // Try to detect a header row (known column names).
  const firstCells = splitCsvLine(lines[0], delimiter).map((c) => normalizeHeader(c));
  const hasHeader = firstCells.some((c) => HEADER_ALIASES[c] !== undefined);

  const dataLines = hasHeader ? lines.slice(1) : lines;

  const rows: CsvRow[] = [];
  for (const line of dataLines) {
    const cells = splitCsvLine(line, delimiter).map((c) => c.trim());
    const row: CsvRow = { symbol: "" };
    if (hasHeader) {
      cells.forEach((cell, idx) => {
        const key = HEADER_ALIASES[firstCells[idx]];
        if (!key || cell === "") return;
        const target = row as unknown as Record<string, string | number | undefined>;
        if (key === "price" || key === "changePct" || key === "volume" || key === "marketCap") {
          const n = parseNumber(cell);
          if (n !== undefined) target[key] = n;
        } else {
          target[key] = cell;
        }
      });
    } else {
      // Headerless fallback: symbol, name, price, changePct, volume, marketCap
      row.symbol = cells[0] || "";
      if (cells[1]) row.name = cells[1];
      const price = parseNumber(cells[2] ?? "");
      if (price !== undefined) row.price = price;
      const changePct = parseNumber(cells[3] ?? "");
      if (changePct !== undefined) row.changePct = changePct;
      const volume = parseNumber(cells[4] ?? "");
      if (volume !== undefined) row.volume = volume;
      const marketCap = parseNumber(cells[5] ?? "");
      if (marketCap !== undefined) row.marketCap = marketCap;
    }
    if (row.symbol) rows.push(row);
  }
  return rows;
}
