// Hong Kong (HKEX) universe import: loads hk_stocks_master.csv into JDDS
// under the HK market, merging dividend yields from hk_div_yields.csv.
// Upserts on (marketId, symbol) — re-running never duplicates.
// Also writes Price rows (source 'csv') so the screener shows prices/caps.
//
// Symbols are zero-padded to 4 digits to match the existing HK convention
// (0001, 0288, ...); 5-digit RMB-counter codes (80016, 80700, ...) keep their
// width. Both forms resolve on Yahoo as-is via the .HK suffix.
//
// Usage: node scripts/import-hk.js
const { PrismaClient } = require('../src/generated/prisma/client');
const { PrismaBetterSqlite3 } = require('@prisma/adapter-better-sqlite3');
const path = require('path');
const fs = require('fs');

const adapter = new PrismaBetterSqlite3({ url: 'file:' + path.join(process.cwd(), 'jdds.db') });
const prisma = new PrismaClient({ adapter });

const { importPath } = require('./lib/import-paths');

const BASE = importPath('market-scraping', 'HK_Stock_Listings');
const MASTER_CSV = path.join(BASE, 'hk_stocks_master.csv');
const DIV_CSV = path.join(BASE, 'hk_div_yields.csv');

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

// "271.17B" / "2.79T" / "534.74M" -> raw dollars (or null).
function parseCap(v) {
  if (v == null) return null;
  const s = String(v).trim().replace(/,/g, '');
  if (!s) return null;
  const m = s.match(/^([\d.]+)\s*([KMBT]?)$/i);
  if (!m) return null;
  const n = parseFloat(m[1]);
  if (isNaN(n)) return null;
  const mult = { K: 1e3, M: 1e6, B: 1e9, T: 1e12 }[m[2].toUpperCase()] || 1;
  return n * mult;
}

function parseNum(v) {
  if (v == null) return null;
  const s = String(v).trim().replace(/,/g, '');
  if (!s) return null;
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

// "1" -> "0001", "288" -> "0288", "1000" -> "1000", "80016" stays "80016".
function normalizeHkSymbol(raw) {
  const s = String(raw).trim();
  if (/^\d{1,4}$/.test(s)) return s.padStart(4, '0');
  return s;
}

async function main() {
  if (!fs.existsSync(MASTER_CSV)) {
    console.error(`CSV not found: ${MASTER_CSV}`);
    process.exit(1);
  }

  await prisma.market.upsert({
    where: { id: 'HK' },
    update: { enabled: true, exchange: 'HKEX' },
    create: {
      id: 'HK',
      country: 'HK',
      exchange: 'HKEX',
      timezone: 'Asia/Hong_Kong',
      openHour: 9,
      closeHour: 16,
      isCrypto: false,
    },
  });

  // Load dividend yields lookup (raw symbol -> div_yield) to fill any blanks.
  const divYields = {};
  if (fs.existsSync(DIV_CSV)) {
    const lines = fs.readFileSync(DIV_CSV, 'utf8').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const header = splitCsvLine(lines[0], ',').map((c) => c.trim().toLowerCase());
    const iSym = header.indexOf('symbol');
    const iDiv = header.indexOf('div_yield');
    for (const line of lines.slice(1)) {
      const cells = splitCsvLine(line, ',');
      const sym = (cells[iSym] || '').trim();
      if (sym) divYields[sym] = parseNum(cells[iDiv]);
    }
    console.log(`Yield lookup loaded: ${Object.keys(divYields).length} symbols`);
  } else {
    console.log('NOTE: hk_div_yields.csv not found, using master CSV yields only.');
  }

  const text = fs.readFileSync(MASTER_CSV, 'utf8');
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const header = splitCsvLine(lines[0], ',').map((c) => c.trim().toLowerCase());
  const idx = (name) => header.indexOf(name);

  const iSymbol = idx('code');
  const iName = idx('company_name');
  const iClass = idx('class');
  const iSector = idx('sector');
  const iIndustry = idx('industry');
  const iPrice = idx('price_hkd');
  const iCap = idx('market_cap');
  const iPE = idx('p/e');
  const iEPS = idx('eps');
  const iDiv = idx('div_yield_pct');
  const iHigh = idx('52w_high');
  const iLow = idx('52w_low');
  const iBeta = idx('beta_1y');
  const iChange = idx('change_pct');
  const iVolume = idx('volume');

  let imported = 0;
  let updated = 0;
  let skipped = 0;

  for (const line of lines.slice(1)) {
    const cells = splitCsvLine(line, ',');
    const rawSymbol = (cells[iSymbol] || '').trim();
    if (!rawSymbol) { skipped++; continue; }
    const symbol = normalizeHkSymbol(rawSymbol);
    const name = (cells[iName] || symbol).trim();
    const securityType = (cells[iClass] || '').trim() || null;
    const sector = (cells[iSector] || '').trim() || null;
    const industry = (cells[iIndustry] || '').trim() || null;
    const price = parseNum(cells[iPrice]);
    const marketCap = parseCap(cells[iCap]);
    const peRatio = parseNum(cells[iPE]);
    const eps = parseNum(cells[iEPS]);
    let dividendYield = parseNum(cells[iDiv]);
    if (dividendYield == null && divYields[rawSymbol] != null) dividendYield = divYields[rawSymbol];
    const fiftyTwoWeekHigh = parseNum(cells[iHigh]);
    const fiftyTwoWeekLow = parseNum(cells[iLow]);
    const beta = parseNum(cells[iBeta]);
    const changePct = parseNum(cells[iChange]);
    const volume = parseNum(cells[iVolume]);

    const existing = await prisma.asset.findUnique({
      where: { marketId_symbol: { marketId: 'HK', symbol } },
    });

    if (existing) {
      await prisma.asset.update({
        where: { id: existing.id },
        data: {
          name,
          sector: sector ?? existing.sector,
          industry: industry ?? existing.industry,
          securityType: securityType ?? existing.securityType,
          isActive: true,
        },
      });
      updated++;
    } else {
      await prisma.asset.create({
        data: { symbol, name, marketId: 'HK', sector, industry, securityType, isActive: true },
      });
      imported++;
    }

    if (price != null) {
      const assetId = existing
        ? existing.id
        : (await prisma.asset.findUnique({ where: { marketId_symbol: { marketId: 'HK', symbol } } }))?.id;
      if (assetId) {
        await prisma.price.upsert({
          where: { assetId },
          update: {
            price, changePct: changePct ?? 0, marketCap, volume, peRatio, eps,
            dividendYield, beta, fiftyTwoWeekHigh, fiftyTwoWeekLow, source: 'csv',
          },
          create: {
            assetId, price, changePct: changePct ?? 0, marketCap, volume, peRatio, eps,
            dividendYield, beta, fiftyTwoWeekHigh, fiftyTwoWeekLow, source: 'csv',
          },
        });
      }
    }
  }

  const total = await prisma.asset.count({ where: { marketId: 'HK' } });
  const withPrice = await prisma.asset.count({ where: { marketId: 'HK', price: { isNot: null } } });
  console.log('\n=== Import complete ===');
  console.log(`Created:          ${imported}`);
  console.log(`Updated (dedup):  ${updated}`);
  console.log(`Skipped:          ${skipped}`);
  console.log(`Total HK assets:  ${total}`);
  console.log(`With price data:  ${withPrice}`);
}

main()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(() => prisma.$disconnect());
