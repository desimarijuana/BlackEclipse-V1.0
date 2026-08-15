// Universe import: loads the manually scraped US market universe CSVs into JDDS
// under the US market. Auto-discovers every `blackeclipse_*.csv` in the folder,
// so you can drop in new lists (equities, ETFs, mutual funds, other securities,
// etc.) and re-run — no code changes needed.
//
// Dedup: every row is upserted on the (marketId, symbol) unique key, so
// re-running this script never creates duplicates — it updates in place.
//
// Usage: node scripts/import-universe.js [path-to-universe-dir]
const { PrismaClient } = require('../src/generated/prisma/client');
const { PrismaBetterSqlite3 } = require('@prisma/adapter-better-sqlite3');
const path = require('path');
const fs = require('fs');

// Minimal CSV parser (mirrors src/lib/scraper/csv.ts) honoring quoted fields.
const HEADER_ALIASES = {
  symbol: 'symbol', ticker: 'symbol', code: 'symbol',
  name: 'name', company: 'name',
  securitytype: 'securityType', 'security type': 'securityType', 'security_type': 'securityType', type: 'securityType',
  assetclass: 'assetClass', 'asset class': 'assetClass', 'asset_class': 'assetClass',
  sector: 'sector', industry: 'industry',
};
function splitCsvLine(line, delimiter) {
  const cells = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++; } else { inQuotes = false; }
      } else { cur += ch; }
    } else if (ch === '"') { inQuotes = true; }
    else if (ch === delimiter) { cells.push(cur); cur = ''; }
    else { cur += ch; }
  }
  cells.push(cur);
  return cells;
}
function parseCsv(text) {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return [];
  const delimiter = lines[0].includes('\t') ? '\t' : ',';
  const firstCells = splitCsvLine(lines[0], delimiter).map((c) => c.trim().toLowerCase().replace(/\s+/g, ' '));
  const hasHeader = firstCells.some((c) => HEADER_ALIASES[c] !== undefined);
  const dataLines = hasHeader ? lines.slice(1) : lines;
  const rows = [];
  for (const line of dataLines) {
    const cells = splitCsvLine(line, delimiter).map((c) => c.trim());
    const row = { symbol: '' };
    if (hasHeader) {
      cells.forEach((cell, idx) => {
        const key = HEADER_ALIASES[firstCells[idx]];
        if (!key || cell === '') return;
        row[key] = cell;
      });
    } else {
      row.symbol = cells[0] || '';
      if (cells[1]) row.name = cells[1];
    }
    if (row.symbol) rows.push(row);
  }
  return rows;
}

const adapter = new PrismaBetterSqlite3({ url: 'file:' + path.join(process.cwd(), 'jdds.db') });
const prisma = new PrismaClient({ adapter });

const DEFAULT_DIR = 'C:/Users/Rafay/Desktop/blackeclipse_market_universe';

// Auto-discover all universe CSVs in the folder (any blackeclipse_*.csv).
function discoverFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => /^blackeclipse_.*\.csv$/i.test(f))
    .sort();
}

async function main() {
  const dir = process.argv[2] || DEFAULT_DIR;
  const marketId = 'US';

  // Ensure the US market exists.
  await prisma.market.upsert({
    where: { id: marketId },
    update: { enabled: true },
    create: {
      id: marketId,
      country: 'US',
      exchange: 'NYSE/NASDAQ',
      timezone: 'America/New_York',
      openHour: 9,
      closeHour: 16,
      isCrypto: false,
    },
  });

  let totalRows = 0;
  let imported = 0;
  let updated = 0;
  let skipped = 0;

  const files = discoverFiles(dir);
  if (files.length === 0) {
    console.warn(`No blackeclipse_*.csv files found in: ${dir}`);
    return;
  }
  console.log(`Found ${files.length} universe file(s) in ${dir}\n`);

  for (const file of files) {
    const filePath = path.join(dir, file);
    if (!fs.existsSync(filePath)) {
      console.warn(`[skip] missing file: ${filePath}`);
      continue;
    }
    const text = fs.readFileSync(filePath, 'utf8');
    const rows = parseCsv(text);
    totalRows += rows.length;
    console.log(`[${file}] parsed ${rows.length} rows`);

    for (const row of rows) {
      if (!row.symbol) {
        skipped++;
        continue;
      }
      const existing = await prisma.asset.findUnique({
        where: { marketId_symbol: { marketId, symbol: row.symbol } },
      });
      if (existing) {
        // Update in place — never duplicate.
        await prisma.asset.update({
          where: { id: existing.id },
          data: {
            name: row.name || existing.name,
            sector: row.sector ?? existing.sector,
            industry: row.industry ?? existing.industry,
            securityType: row.securityType ?? existing.securityType,
            assetClass: row.assetClass ?? existing.assetClass,
            isActive: true,
          },
        });
        updated++;
      } else {
        await prisma.asset.create({
          data: {
            symbol: row.symbol,
            name: row.name || row.symbol,
            marketId,
            sector: row.sector,
            industry: row.industry,
            securityType: row.securityType,
            assetClass: row.assetClass,
            isActive: true,
          },
        });
        imported++;
      }
    }
  }

  const total = await prisma.asset.count({ where: { marketId } });
  console.log('\n=== Import complete ===');
  console.log(`Rows parsed:      ${totalRows}`);
  console.log(`Created:          ${imported}`);
  console.log(`Updated (dedup):  ${updated}`);
  console.log(`Skipped:          ${skipped}`);
  console.log(`Total US assets:  ${total}`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
