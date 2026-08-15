// Import PSX asset categories (ETF, REIT, Closed-end Fund, Modaraba) into JDDS
// under the PK market. These update the existing equities' asset_class/securityType
// so users can filter by category (Stock / ETF / REIT / Closed-end Fund / Modaraba).
const { PrismaClient } = require('../src/generated/prisma/client');
const { PrismaBetterSqlite3 } = require('@prisma/adapter-better-sqlite3');
const path = require('path');
const fs = require('fs');

const adapter = new PrismaBetterSqlite3({ url: 'file:' + path.join(process.cwd(), 'jdds.db') });
const prisma = new PrismaClient({ adapter });

const DIR = 'C:/Users/Rafay/Desktop/Eclipse-PSX-Universe/normalized';
const FILES = [
  { file: '02_psx_etfs.csv', assetClass: 'ETF' },
  { file: '03_psx_reits.csv', assetClass: 'REIT' },
  { file: '04_psx_closed_end_funds.csv', assetClass: 'Closed-end Fund' },
  { file: '05_psx_modarabas.csv', assetClass: 'Modaraba' },
  { file: '06_psx_listed_debt.csv', assetClass: 'Listed Debt', nameCol: 'security_name' },
  { file: '07_mufap_mutual_funds.csv', assetClass: 'Mutual Fund', nameCol: 'name', symbolCol: 'fundID', skipDupHeader: true },
  { file: '08_national_savings_schemes.csv', assetClass: 'National Savings Scheme', nameCol: 'name', genSymbol: true },
];

function splitCsvLine(line, delimiter) {
  const cells = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"') { if (line[i + 1] === '"') { cur += '"'; i++; } else { inQuotes = false; } }
      else { cur += ch; }
    } else if (ch === '"') { inQuotes = true; }
    else if (ch === delimiter) { cells.push(cur); cur = ''; }
    else { cur += ch; }
  }
  cells.push(cur);
  return cells;
}

async function main() {
  const marketId = 'PK';
  let totalUpdated = 0;

  for (const { file, assetClass, nameCol, symbolCol, genSymbol, skipDupHeader } of FILES) {
    const csvPath = path.join(DIR, file);
    if (!fs.existsSync(csvPath)) { console.warn('Missing file:', file); continue; }
    const text = fs.readFileSync(csvPath, 'utf8');
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const headerLine = lines[0].replace(/^\uFEFF/, '');
    const header = splitCsvLine(headerLine, ',').map((c) => c.trim().toLowerCase());
    const iSymbol = header.indexOf((symbolCol || 'symbol').toLowerCase());
    const iName = header.indexOf((nameCol || 'name').toLowerCase());

    let updated = 0;
    let dataLines = lines.slice(1);
    if (skipDupHeader) {
      // Skip a repeated header row if present.
      const firstCells = splitCsvLine(dataLines[0], ',').map((c) => c.trim().toLowerCase());
      if (firstCells.some((c) => c === header[0] || c === 'name')) dataLines = dataLines.slice(1);
    }
    let genIdx = 0;
    for (let i = 0; i < dataLines.length; i++) {
      const cells = splitCsvLine(dataLines[i], ',');
      let symbol = (cells[iSymbol] || '').trim();
      let name = (cells[iName] || '').trim();
      if (genSymbol) {
        // No symbol for national savings schemes; generate a stable one from the name.
        if (!name) continue;
        const slug = name.replace(/[^a-zA-Z0-9]/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '').toUpperCase().slice(0, 24);
        symbol = slug || `NSS_${genIdx++}`;
      }
      if (!symbol) { genIdx++; continue; }
      if (!name) name = symbol;
      const existing = await prisma.asset.findUnique({ where: { marketId_symbol: { marketId, symbol } } });
      if (existing) {
        await prisma.asset.update({
          where: { id: existing.id },
          data: { name, assetClass, securityType: assetClass, isActive: true },
        });
      } else {
        await prisma.asset.create({ data: { symbol, name, marketId, assetClass, securityType: assetClass, isActive: true } });
      }
      updated++;
    }
    console.log(`[${file}] ${assetClass}: updated/created ${updated}`);
    totalUpdated += updated;
  }

  const total = await prisma.asset.count({ where: { marketId } });
  const byClass = await prisma.asset.findMany({ where: { marketId }, select: { assetClass: true }, distinct: ['assetClass'] });
  console.log('\n=== PSX Categories complete ===');
  console.log('Total updated/created:', totalUpdated);
  console.log('Total PK assets:', total);
  console.log('Asset classes:', byClass.map(c => c.assetClass).filter(Boolean).join(', '));
}

main().catch((e) => { console.error(e); process.exit(1); }).finally(() => prisma.$disconnect());
