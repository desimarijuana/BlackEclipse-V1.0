// France universe import: loads france_stocks_master.csv into JDDS under the
// FR market. Upserts on (marketId, symbol) — re-running never duplicates.
// Also writes Price rows (source 'csv') so the screener shows prices/caps.
//
// Usage: node scripts/import-france.js [path-to-csv]
const { PrismaClient } = require('../src/generated/prisma/client');
const { PrismaBetterSqlite3 } = require('@prisma/adapter-better-sqlite3');
const path = require('path');
const fs = require('fs');

const adapter = new PrismaBetterSqlite3({ url: 'file:' + path.join(process.cwd(), 'jdds.db') });
const prisma = new PrismaClient({ adapter });

const DEFAULT_CSV = 'C:/Users/Rafay/Desktop/market-scraping/France_Stock_Listings/france_stocks_master.csv';

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

// "41.51M" / "2.46B" / "261.97K" / "151.73B" -> raw dollars (or null).
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

async function main() {
  const csvPath = process.argv[2] || DEFAULT_CSV;
  if (!fs.existsSync(csvPath)) {
    console.error(`CSV not found: ${csvPath}`);
    process.exit(1);
  }

  await prisma.market.upsert({
    where: { id: 'FR' },
    update: { enabled: true },
    create: {
      id: 'FR',
      country: 'FR',
      exchange: 'Euronext Paris',
      timezone: 'Europe/Paris',
      openHour: 9,
      closeHour: 17,
      isCrypto: false,
    },
  });

  const text = fs.readFileSync(csvPath, 'utf8');
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const header = splitCsvLine(lines[0], ',').map((c) => c.trim().toLowerCase());
  const idx = (name) => header.indexOf(name);

  const iSymbol = idx('code');
  const iName = idx('company_name');
  const iSector = idx('sector');
  const iIndustry = idx('industry');
  const iPrice = idx('price_eur');
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
    const symbol = (cells[iSymbol] || '').trim();
    if (!symbol) { skipped++; continue; }
    const name = (cells[iName] || symbol).trim();
    const sector = (cells[iSector] || '').trim() || null;
    const industry = (cells[iIndustry] || '').trim() || null;
    const price = parseNum(cells[iPrice]);
    const marketCap = parseCap(cells[iCap]);
    const peRatio = parseNum(cells[iPE]);
    const eps = parseNum(cells[iEPS]);
    const dividendYield = parseNum(cells[iDiv]);
    const fiftyTwoWeekHigh = parseNum(cells[iHigh]);
    const fiftyTwoWeekLow = parseNum(cells[iLow]);
    const beta = parseNum(cells[iBeta]);
    const changePct = parseNum(cells[iChange]);
    const volume = parseNum(cells[iVolume]);

    const existing = await prisma.asset.findUnique({
      where: { marketId_symbol: { marketId: 'FR', symbol } },
    });
    if (existing) {
      await prisma.asset.update({
        where: { id: existing.id },
        data: { name, sector: sector ?? existing.sector, industry: industry ?? existing.industry, isActive: true },
      });
      updated++;
    } else {
      await prisma.asset.create({
        data: { symbol, name, marketId: 'FR', sector, industry, isActive: true },
      });
      imported++;
    }

    if (price != null) {
      const assetId = existing ? existing.id : (await prisma.asset.findUnique({ where: { marketId_symbol: { marketId: 'FR', symbol } } }))?.id;
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

  const total = await prisma.asset.count({ where: { marketId: 'FR' } });
  const withPrice = await prisma.asset.count({ where: { marketId: 'FR', price: { isNot: null } } });
  console.log('\n=== Import complete ===');
  console.log(`Created:          ${imported}`);
  console.log(`Updated (dedup):  ${updated}`);
  console.log(`Skipped:          ${skipped}`);
  console.log(`Total FR assets:  ${total}`);
  console.log(`With price data:  ${withPrice}`);
}

main()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(() => prisma.$disconnect());
