// India universe import: loads india_stocks_master.csv into JDDS under the
// IN market, merging dividend yields from india_div_yields.csv when the master
// CSV has blanks. Upserts on (marketId, symbol) — re-running never duplicates.
// Also writes Price rows (source 'csv') so the screener shows prices/caps.
//
// Columns: symbol,company_name,price_INR,market_cap,currency,listed_on,
//          sector,industry,P/E,EPS,div_yield_pct,52w_high,52w_low,beta_1y,
//          change_pct,volume,analyst_rating,total_debt_INR,total_assets_INR
//
// Usage: node scripts/import-india.js [path-to-master-csv] [path-to-div-csv]
const { PrismaClient } = require('../src/generated/prisma/client');
const { PrismaBetterSqlite3 } = require('@prisma/adapter-better-sqlite3');
const path = require('path');
const fs = require('fs');

const adapter = new PrismaBetterSqlite3({ url: 'file:' + path.join(process.cwd(), 'jdds.db') });
const prisma = new PrismaClient({ adapter });

const DEFAULT_BASE = 'C:/Users/Rafay/Desktop/market-scraping/India_Stock_Listings';
const DEFAULT_MASTER = path.join(DEFAULT_BASE, 'india_stocks_master.csv');
const DEFAULT_DIV = path.join(DEFAULT_BASE, 'india_div_yields.csv');

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

// "1.00M" / "75.18M" / "5.09B" / "185.57B" -> raw rupees (or null).
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
  if (!s || s === 'NA' || s === 'N/A') return null;
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

async function main() {
  const masterCsv = process.argv[2] || DEFAULT_MASTER;
  const divCsv = process.argv[3] || DEFAULT_DIV;
  if (!fs.existsSync(masterCsv)) {
    console.error(`CSV not found: ${masterCsv}`);
    process.exit(1);
  }

  await prisma.market.upsert({
    where: { id: 'IN' },
    update: { enabled: true, exchange: 'NSE/BSE' },
    create: {
      id: 'IN',
      country: 'IN',
      exchange: 'NSE/BSE',
      timezone: 'Asia/Kolkata',
      openHour: 9,
      closeHour: 15,
      isCrypto: false,
    },
  });

  // Load dividend yields lookup (symbol -> div_yield) to fill any blanks.
  const divYields = {};
  if (fs.existsSync(divCsv)) {
    const lines = fs.readFileSync(divCsv, 'utf8').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
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
    console.log('NOTE: div yields CSV not found, using master CSV yields only.');
  }

  const text = fs.readFileSync(masterCsv, 'utf8');
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const header = splitCsvLine(lines[0], ',').map((c) => c.trim().toLowerCase());
  const idx = (name) => header.indexOf(name);

  const iSymbol = idx('symbol');
  const iName = idx('company_name');
  const iSector = idx('sector');
  const iIndustry = idx('industry');
  const iPrice = idx('price_inr');
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
    let dividendYield = parseNum(cells[iDiv]);
    if (dividendYield == null && divYields[symbol] != null) dividendYield = divYields[symbol];
    const fiftyTwoWeekHigh = parseNum(cells[iHigh]);
    const fiftyTwoWeekLow = parseNum(cells[iLow]);
    const beta = parseNum(cells[iBeta]);
    const changePct = parseNum(cells[iChange]);
    const volume = parseNum(cells[iVolume]);

    const existing = await prisma.asset.findUnique({
      where: { marketId_symbol: { marketId: 'IN', symbol } },
    });
    if (existing) {
      await prisma.asset.update({
        where: { id: existing.id },
        data: { name, sector: sector ?? existing.sector, industry: industry ?? existing.industry, isActive: true },
      });
      updated++;
    } else {
      await prisma.asset.create({
        data: { symbol, name, marketId: 'IN', sector, industry, isActive: true },
      });
      imported++;
    }

    if (price != null) {
      const assetId = existing
        ? existing.id
        : (await prisma.asset.findUnique({ where: { marketId_symbol: { marketId: 'IN', symbol } } }))?.id;
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

  const total = await prisma.asset.count({ where: { marketId: 'IN' } });
  const withPrice = await prisma.asset.count({ where: { marketId: 'IN', price: { isNot: null } } });
  console.log('\n=== Import complete ===');
  console.log(`Created:          ${imported}`);
  console.log(`Updated (dedup):  ${updated}`);
  console.log(`Skipped:          ${skipped}`);
  console.log(`Total IN assets:  ${total}`);
  console.log(`With price data:  ${withPrice}`);
}

main()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(() => prisma.$disconnect());
