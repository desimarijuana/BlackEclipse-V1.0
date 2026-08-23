// Regional market universes: creates the Market rows + assets for the markets
// that have no universe yet (SG/MY/AU/FR/NL/CA/BR/MX/SA/AE/ZA/EG/RU/ID/TH/VN).
//
// Symbols were verified against scripts/yfinance_bridge.py — every symbol in
// here resolves on Yahoo (NG + PK are Yahoo data gaps, so they are skipped).
//
// Usage: node scripts/import-regions.js
// Re-running is safe: assets upsert on (marketId, symbol).
const { PrismaClient } = require('../src/generated/prisma/client');
const { PrismaBetterSqlite3 } = require('@prisma/adapter-better-sqlite3');
const path = require('path');

const adapter = new PrismaBetterSqlite3({ url: 'file:' + path.join(process.cwd(), 'jdds.db') });
const prisma = new PrismaClient({ adapter });

const REGIONS = [
  {
    market: { id: 'SG', country: 'SG', exchange: 'SGX', timezone: 'Asia/Singapore', openHour: 9, closeHour: 17, isCrypto: false },
    symbols: [
      ['D05', 'DBS Group Holdings'], ['O39', 'Oversea-Chinese Banking Corp'], ['U11', 'United Overseas Bank'],
      ['Z74', 'Singtel'], ['C6L', 'Singapore Airlines'], ['A17U', 'CapitaLand Integrated Commercial Trust'],
      ['U96', 'Sembcorp Industries'], ['F34', 'Wilmar International'], ['BS6', 'Yangzijiang Shipbuilding'],
      ['S63', 'ST Engineering'], ['558', 'UOL Group'],
    ],
  },
  {
    market: { id: 'MY', country: 'MY', exchange: 'Bursa Malaysia', timezone: 'Asia/Kuala_Lumpur', openHour: 9, closeHour: 17, isCrypto: false },
    symbols: [
      ['1155', 'Malayan Banking (Maybank)'], ['1295', 'Public Bank'], ['5183', 'Petronas Chemicals Group'],
      ['1023', 'CIMB Group Holdings'], ['5347', 'Tenaga Nasional'], ['4863', 'IOI Corporation'],
      ['3816', 'MISC Berhad'], ['4707', 'Nestle Malaysia'], ['1961', 'IHH Healthcare'],
    ],
  },
  {
    market: { id: 'AU', country: 'AU', exchange: 'ASX', timezone: 'Australia/Sydney', openHour: 10, closeHour: 16, isCrypto: false },
    symbols: [
      ['CBA', 'Commonwealth Bank of Australia'], ['BHP', 'BHP Group'], ['CSL', 'CSL Limited'],
      ['WBC', 'Westpac Banking Corp'], ['NAB', 'National Australia Bank'], ['WES', 'Wesfarmers'],
      ['TLS', 'Telstra Group'], ['MQG', 'Macquarie Group'], ['RIO', 'Rio Tinto'], ['GMG', 'Goodman Group'],
    ],
  },
  {
    market: { id: 'FR', country: 'FR', exchange: 'Euronext Paris', timezone: 'Europe/Paris', openHour: 9, closeHour: 17, isCrypto: false },
    symbols: [
      ['MC', 'LVMH Moet Hennessy'], ['OR', 'L\'Oreal'], ['SAN', 'Sanofi'], ['AI', 'Air Liquide'],
      ['TTE', 'TotalEnergies'], ['BNP', 'BNP Paribas'], ['ACA', 'Credit Agricole'], ['SU', 'Schneider Electric'],
      ['VIE', 'Veolia Environnement'], ['KER', 'Kering'],
    ],
  },
  {
    market: { id: 'NL', country: 'NL', exchange: 'Euronext Amsterdam', timezone: 'Europe/Amsterdam', openHour: 9, closeHour: 17, isCrypto: false },
    symbols: [
      ['ASML', 'ASML Holding'], ['SHELL', 'Shell plc'], ['INGA', 'ING Groep'], ['PHIA', 'Philips'],
      ['UNA', 'Unilever'], ['AD', 'Ahold Delhaize'], ['WKL', 'Wolters Kluwer'], ['HEIA', 'Heineken'],
    ],
  },
  {
    market: { id: 'CA', country: 'CA', exchange: 'TSX', timezone: 'America/Toronto', openHour: 9, closeHour: 16, isCrypto: false },
    symbols: [
      ['SHOP', 'Shopify'], ['RY', 'Royal Bank of Canada'], ['TD', 'Toronto-Dominion Bank'], ['ENB', 'Enbridge'],
      ['CNQ', 'Canadian Natural Resources'], ['BNS', 'Bank of Nova Scotia'], ['CP', 'Canadian Pacific Kansas City'],
      ['MFC', 'Manulife Financial'], ['SU', 'Suncor Energy'], ['TRP', 'TC Energy'],
    ],
  },
  {
    market: { id: 'BR', country: 'BR', exchange: 'B3', timezone: 'America/Sao_Paulo', openHour: 10, closeHour: 17, isCrypto: false },
    symbols: [
      ['PETR4', 'Petrobras PN'], ['VALE3', 'Vale ON'], ['ITUB4', 'Itau Unibanco PN'], ['BBDC4', 'Bradesco PN'],
      ['ABEV3', 'Ambev ON'], ['WEGE3', 'WEG ON'], ['BBAS3', 'Banco do Brasil ON'], ['B3SA3', 'B3 ON'],
      ['HAPV3', 'Hapvida ON'],
    ],
  },
  {
    market: { id: 'MX', country: 'MX', exchange: 'BMV', timezone: 'America/Mexico_City', openHour: 9, closeHour: 16, isCrypto: false },
    symbols: [
      ['WALMEX', 'Walmex'], ['FEMSAUBD', 'Femsa UBD'], ['TLEVISACPO', 'Grupo Televisa CPO'], ['GFNORTEO', 'Banorte O'],
      ['CEMEXCPO', 'Cemex CPO'], ['BBAJIOO', 'Banregio O'], ['AC', 'Arca Continental'], ['KIMBERA', 'Kimberly-Clark de Mexico A'],
      ['BIMBOA', 'Grupo Bimbo A'], ['GMEXICOB', 'Grupo Mexico B'],
    ],
  },
  {
    market: { id: 'SA', country: 'SA', exchange: 'Tadawul', timezone: 'Asia/Riyadh', openHour: 10, closeHour: 15, isCrypto: false },
    symbols: [
      ['2222', 'Saudi Aramco'], ['1120', 'Al Rajhi Bank'], ['2010', 'SABIC'], ['1180', 'Alinma Bank'],
      ['7010', 'Saudi Telecom Co'], ['2280', 'Saudi Arabian Mining (Maaden)'], ['1010', 'Riyad Bank'],
      ['4280', 'Saudi Awwal Bank (SAB)'],
    ],
  },
  {
    market: { id: 'AE', country: 'AE', exchange: 'ADX/DFM', timezone: 'Asia/Dubai', openHour: 10, closeHour: 15, isCrypto: false },
    symbols: [
      ['EMAAR', 'Emaar Properties'], ['DU', 'Emirates Integrated Telecommunications (du)'],
      ['AIRARABIA', 'Air Arabia'], ['AMANAT', 'Amanat Holdings'], ['EMIRATESNBD', 'Emirates NBD'],
    ],
  },
  {
    market: { id: 'ZA', country: 'ZA', exchange: 'JSE', timezone: 'Africa/Johannesburg', openHour: 9, closeHour: 17, isCrypto: false },
    symbols: [
      ['NPN', 'Naspers'], ['FSR', 'FirstRand'], ['SBK', 'Standard Bank Group'], ['BTI', 'British American Tobacco'],
      ['AGL', 'Anglo American Platinum'], ['CPI', 'Capitec Bank'], ['SOL', 'Sasol'], ['GLN', 'Glencore'], ['GFI', 'Gold Fields'],
    ],
  },
  {
    market: { id: 'EG', country: 'EG', exchange: 'EGX', timezone: 'Africa/Cairo', openHour: 10, closeHour: 15, isCrypto: false },
    symbols: [
      ['COMI', 'Commercial International Bank'], ['EAST', 'Eastern Company'], ['AMOC', 'Alexandria Mineral Oils'],
      ['JUFO', 'Juhayna Food Industries'], ['EKHO', 'Emaar Misr'], ['SWDY', 'Elsewedy Electric'],
      ['HRHO', 'Heliopolis Housing'], ['ORWE', 'Orascom Construction'],
    ],
  },
  {
    market: { id: 'RU', country: 'RU', exchange: 'MOEX', timezone: 'Europe/Moscow', openHour: 10, closeHour: 18, isCrypto: false },
    symbols: [
      ['SBER', 'Sberbank'], ['GAZP', 'Gazprom'], ['LKOH', 'Lukoil'], ['NVTK', 'Novatek'],
      ['MGNT', 'Magnit'], ['TATN', 'Tatneft'], ['ROSN', 'Rosneft'],
    ],
  },
  {
    market: { id: 'ID', country: 'ID', exchange: 'IDX', timezone: 'Asia/Jakarta', openHour: 9, closeHour: 15, isCrypto: false },
    symbols: [
      ['BBCA', 'Bank Central Asia'], ['BBRI', 'Bank Rakyat Indonesia'], ['TLKM', 'Telkom Indonesia'],
      ['ASII', 'Astra International'], ['BMRI', 'Bank Mandiri'], ['GGRM', 'Gudang Garam'],
      ['UNVR', 'Unilever Indonesia'], ['ICBP', 'Indofood CBP'],
    ],
  },
  {
    market: { id: 'TH', country: 'TH', exchange: 'SET', timezone: 'Asia/Bangkok', openHour: 10, closeHour: 16, isCrypto: false },
    symbols: [
      ['PTT', 'PTT Public Company'], ['SCB', 'Siam Commercial Bank'], ['KBANK', 'Kasikornbank'],
      ['ADVANC', 'Advanced Info Service'], ['CPALL', 'CP All'], ['AOT', 'Airports of Thailand'],
      ['BBL', 'Bangkok Bank'], ['CPF', 'Charoen Pokphand Foods'],
    ],
  },
  {
    market: { id: 'VN', country: 'VN', exchange: 'HOSE', timezone: 'Asia/Ho_Chi_Minh', openHour: 9, closeHour: 15, isCrypto: false },
    symbols: [
      ['VIC', 'Vingroup'], ['VNM', 'Vinamilk'], ['VHM', 'Vinhomes'], ['FPT', 'FPT Corporation'],
      ['VCB', 'Vietcombank'], ['HPG', 'Hoa Phat Group'], ['MSN', 'Masan Group'], ['GAS', 'PV Gas'],
    ],
  },
];

async function main() {
  let created = 0;
  for (const region of REGIONS) {
    const { market, symbols } = region;
    await prisma.market.upsert({
      where: { id: market.id },
      update: { enabled: true },
      create: market,
    });
    for (const [symbol, name] of symbols) {
      await prisma.asset.upsert({
        where: { marketId_symbol: { marketId: market.id, symbol } },
        update: { name, isActive: true },
        create: { symbol, name, marketId: market.id, isActive: true },
      });
      created++;
    }
    console.log(`  ${market.id}: ${symbols.length} assets`);
  }
  console.log(`\nDone. Created/verified ${created} assets across ${REGIONS.length} markets.`);
}

main()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(() => prisma.$disconnect());
