// Import PSX (Pakistan Stock Exchange) equities into JDDS under the PK market.
// CSV columns: symbol,name,sector,asset_class,exchange
// Dedup: upsert on (marketId, symbol) so re-running never creates duplicates.
const { PrismaClient } = require('../src/generated/prisma/client');
const { PrismaBetterSqlite3 } = require('@prisma/adapter-better-sqlite3');
const path = require('path');
const fs = require('fs');

const { importPath } = require('./lib/import-paths');

const DEFAULT_CSV = importPath('Eclipse-PSX-Universe', 'normalized', '01_psx_equities.csv');

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

const adapter = new PrismaBetterSqlite3({ url: 'file:' + path.join(process.cwd(), 'jdds.db') });
const prisma = new PrismaClient({ adapter });

async function main() {
  const csvPath = process.argv[2] || DEFAULT_CSV;
  const marketId = 'PK';

  if (!fs.existsSync(csvPath)) { console.error('CSV not found:', csvPath); process.exit(1); }

  // Ensure the PK market exists.
  await prisma.market.upsert({
    where: { id: marketId },
    update: { enabled: true },
    create: {
      id: marketId,
      country: 'PK',
      exchange: 'PSX',
      timezone: 'Asia/Karachi',
      openHour: 9,
      closeHour: 15,
      isCrypto: false,
    },
  });

  const text = fs.readFileSync(csvPath, 'utf8');
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) { console.error('Empty CSV'); process.exit(1); }

  // Handle BOM on first header line.
  const headerLine = lines[0].replace(/^\uFEFF/, '');
  const header = splitCsvLine(headerLine, ',').map((c) => c.trim().toLowerCase());
  const iSymbol = header.indexOf('symbol');
  const iName = header.indexOf('name');
  const iSector = header.indexOf('sector');

  let created = 0;
  let updated = 0;
  let skipped = 0;
  const seen = new Map();

  for (let i = 1; i < lines.length; i++) {
    const cells = splitCsvLine(lines[i], ',');
    const symbol = (cells[iSymbol] || '').trim();
    if (!symbol) { skipped++; continue; }
    seen.set(symbol, (seen.get(symbol) || 0) + 1);

    const name = (cells[iName] || symbol).trim();
    const sector = (cells[iSector] || '').trim() || null;
    const securityType = 'Stock';
    const assetClass = 'Equity';

    const existing = await prisma.asset.findUnique({
      where: { marketId_symbol: { marketId, symbol } },
    });

    if (existing) {
      await prisma.asset.update({
        where: { id: existing.id },
        data: { name, sector: sector ?? existing.sector, securityType: securityType ?? existing.securityType, assetClass: assetClass ?? existing.assetClass, isActive: true },
      });
      updated++;
    } else {
      await prisma.asset.create({
        data: { symbol, name, marketId, sector, securityType, assetClass, isActive: true },
      });
      created++;
    }
  }

  const dupes = [...seen.entries()].filter(([, c]) => c > 1);
  const total = await prisma.asset.count({ where: { marketId } });

  console.log('\n=== PSX Import complete ===');
  console.log(`Source rows:      ${lines.length - 1}`);
  console.log(`Created:          ${created}`);
  console.log(`Updated (dedup):  ${updated}`);
  console.log(`Skipped:          ${skipped}`);
  console.log(`Total PK assets:  ${total}`);
  console.log(`Duplicate symbols: ${dupes.length}`);
  if (dupes.length) console.log(dupes.map(([s, c]) => `  ${s} x${c}`).join('\n'));
}

main().catch((e) => { console.error(e); process.exit(1); }).finally(() => prisma.$disconnect());
