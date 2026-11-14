// Import the Black Eclipse stock universe (assets + prices) into JDDS under the
// US market, with duplicate detection.
//
// CSV columns: Ticker,Company,Type,Sector,Industry,Country,Market Cap,P/E,Price,Change %
//
// Dedup: every row is upserted on the (marketId, symbol) unique key, so re-running
// never creates duplicates — it updates in place. A duplicate report is printed.
//
// Usage: node scripts/import-stocks.js [path-to-csv]
const { PrismaClient } = require('../src/generated/prisma/client');
const { PrismaBetterSqlite3 } = require('@prisma/adapter-better-sqlite3');
const path = require('path');
const fs = require('fs');

const { importPath } = require('./lib/import-paths');

const DEFAULT_CSV = importPath('black_eclipse_assets', 'divided', '01_ByType_Stock.csv');

// Proper CSV parser honoring double-quoted fields (may contain commas).
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

// Parse a market cap string like "5.26T", "980.90B", "999.7M", "994,557" into a number.
function parseCap(raw) {
  if (raw == null) return null;
  const s = String(raw).trim().replace(/,/g, '');
  if (!s || s === 'NA' || s === 'N/A') return null;
  const m = s.match(/^([\d.]+)\s*([TBMK])?$/i);
  if (!m) return null;
  const n = parseFloat(m[1]);
  if (isNaN(n)) return null;
  const mult = { T: 1e12, B: 1e9, M: 1e6, K: 1e3 }[m[2] ? m[2].toUpperCase() : ''];
  return mult ? n * mult : n;
}

function parseNum(raw) {
  if (raw == null) return null;
  const s = String(raw).trim().replace(/[$,%]/g, '');
  if (!s || s === 'NA' || s === 'N/A' || s === 'Infinity') return null;
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

const adapter = new PrismaBetterSqlite3({ url: 'file:' + path.join(process.cwd(), 'jdds.db') });
const prisma = new PrismaClient({ adapter });

async function main() {
  const csvPath = process.argv[2] || DEFAULT_CSV;
  const marketId = 'US';

  if (!fs.existsSync(csvPath)) {
    console.error(`CSV not found: ${csvPath}`);
    process.exit(1);
  }

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

  const text = fs.readFileSync(csvPath, 'utf8');
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) { console.error('Empty CSV'); process.exit(1); }

  const header = splitCsvLine(lines[0], ',').map((c) => c.trim().toLowerCase());
  const col = (name) => header.indexOf(name);

  const iTicker = col('ticker');
  const iCompany = col('company');
  const iType = col('type');
  const iSector = col('sector');
  const iIndustry = col('industry');
  const iCountry = col('country');
  const iCap = col('market cap');
  const iPrice = col('price');
  const iChange = col('change %');
  const iPE = col('p/e');

  let created = 0;
  let updated = 0;
  let skipped = 0;
  const seen = new Map(); // symbol -> count, for duplicate detection within file

  for (let i = 1; i < lines.length; i++) {
    const cells = splitCsvLine(lines[i], ',');
    const symbol = (cells[iTicker] || '').trim();
    if (!symbol) { skipped++; continue; }

    // Duplicate detection within the source file.
    seen.set(symbol, (seen.get(symbol) || 0) + 1);

    const name = (cells[iCompany] || symbol).trim();
    const securityType = (cells[iType] || '').trim() || null;
    const sector = (cells[iSector] || '').trim() || null;
    const industry = (cells[iIndustry] || '').trim() || null;
    const country = (cells[iCountry] || '').trim() || null;
    const marketCap = parseCap(cells[iCap]);
    const price = parseNum(cells[iPrice]);
    const changePct = parseNum(cells[iChange]);
    const peRatio = parseNum(cells[iPE]);

    const existing = await prisma.asset.findUnique({
      where: { marketId_symbol: { marketId, symbol } },
    });

    if (existing) {
      await prisma.asset.update({
        where: { id: existing.id },
        data: {
          name,
          sector: sector ?? existing.sector,
          industry: industry ?? existing.industry,
          country: country ?? existing.country,
          securityType: securityType ?? existing.securityType,
          isActive: true,
        },
      });
      updated++;
    } else {
      await prisma.asset.create({
        data: {
          symbol,
          name,
          marketId,
          sector,
          industry,
          country,
          securityType,
          assetClass: 'Equity',
          isActive: true,
        },
      });
      created++;
    }

    // Upsert price (only when a price is present).
    if (price != null && price > 0) {
      const asset = await prisma.asset.findUnique({
        where: { marketId_symbol: { marketId, symbol } },
      });
      if (asset) {
        await prisma.price.upsert({
          where: { assetId: asset.id },
          update: { price, changePct: changePct ?? 0, marketCap, peRatio, source: 'csv' },
          create: { assetId: asset.id, price, changePct: changePct ?? 0, marketCap, peRatio, source: 'csv' },
        });
      }
    }
  }

  // Duplicate report.
  const dupes = [...seen.entries()].filter(([, c]) => c > 1);
  const total = await prisma.asset.count({ where: { marketId } });
  const withPrice = await prisma.asset.count({ where: { marketId, price: { isNot: null } } });

  console.log('\n=== Import complete ===');
  console.log(`Source rows:      ${lines.length - 1}`);
  console.log(`Created:          ${created}`);
  console.log(`Updated (dedup):  ${updated}`);
  console.log(`Skipped:          ${skipped}`);
  console.log(`Total US assets:  ${total}`);
  console.log(`With price:       ${withPrice}`);
  console.log(`Duplicate symbols in file: ${dupes.length}`);
  if (dupes.length) {
    console.log(dupes.map(([s, c]) => `  ${s} x${c}`).join('\n'));
  }
}

main()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(() => prisma.$disconnect());
