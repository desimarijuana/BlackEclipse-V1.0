// Remove the imported US market universe (all 141k assets) and re-seed with the
// small built-in dummy universe (MARKET_SEEDS) so the screener shows clean data.
const { PrismaClient } = require('../src/generated/prisma/client');
const { PrismaBetterSqlite3 } = require('@prisma/adapter-better-sqlite3');
const path = require('path');
const adapter = new PrismaBetterSqlite3({ url: 'file:' + path.join(process.cwd(), 'jdds.db') });
const p = new PrismaClient({ adapter });

const DUMMY_US = [
  { symbol: 'AAPL', name: 'Apple Inc.', sector: 'Technology', industry: 'Consumer Electronics' },
  { symbol: 'MSFT', name: 'Microsoft Corp.', sector: 'Technology', industry: 'Software - Infrastructure' },
  { symbol: 'NVDA', name: 'NVIDIA Corp.', sector: 'Technology', industry: 'Semiconductors' },
  { symbol: 'TSLA', name: 'Tesla Inc.', sector: 'Consumer Discretionary', industry: 'Auto Manufacturers' },
  { symbol: 'AMZN', name: 'Amazon.com Inc.', sector: 'Consumer Discretionary', industry: 'Internet Retail' },
  { symbol: 'META', name: 'Meta Platforms', sector: 'Communication Services', industry: 'Internet Content' },
  { symbol: 'GOOGL', name: 'Alphabet Inc.', sector: 'Communication Services', industry: 'Internet Content' },
  { symbol: 'BRK.B', name: 'Berkshire Hathaway', sector: 'Financials', industry: 'Insurance' },
  { symbol: 'LLY', name: 'Eli Lilly', sector: 'Healthcare', industry: 'Drug Manufacturers' },
  { symbol: 'AVGO', name: 'Broadcom', sector: 'Technology', industry: 'Semiconductors' },
  { symbol: 'JPM', name: 'JPMorgan Chase & Co.', sector: 'Financials', industry: 'Diversified Banks' },
  { symbol: 'V', name: 'Visa Inc.', sector: 'Financials', industry: 'Credit Services' },
  { symbol: 'JNJ', name: 'Johnson & Johnson', sector: 'Healthcare', industry: 'Drug Manufacturers' },
  { symbol: 'XOM', name: 'Exxon Mobil', sector: 'Energy', industry: 'Oil & Gas' },
  { symbol: 'WMT', name: 'Walmart', sector: 'Consumer Staples', industry: 'Discount Stores' },
  { symbol: 'MA', name: 'Mastercard', sector: 'Financials', industry: 'Credit Services' },
  { symbol: 'PG', name: 'Procter & Gamble', sector: 'Consumer Staples', industry: 'Household Products' },
  { symbol: 'UNH', name: 'UnitedHealth Group', sector: 'Healthcare', industry: 'Healthcare Plans' },
  { symbol: 'HD', name: 'Home Depot', sector: 'Consumer Discretionary', industry: 'Home Improvement' },
  { symbol: 'ORCL', name: 'Oracle', sector: 'Technology', industry: 'Software - Infrastructure' },
  { symbol: 'COST', name: 'Costco Wholesale', sector: 'Consumer Staples', industry: 'Discount Stores' },
  { symbol: 'MRK', name: 'Merck & Co.', sector: 'Healthcare', industry: 'Drug Manufacturers' },
  { symbol: 'ABBV', name: 'AbbVie', sector: 'Healthcare', industry: 'Drug Manufacturers' },
  { symbol: 'BAC', name: 'Bank of America', sector: 'Financials', industry: 'Diversified Banks' },
  { symbol: 'KO', name: 'Coca-Cola', sector: 'Consumer Staples', industry: 'Beverages' },
  { symbol: 'PEP', name: 'PepsiCo', sector: 'Consumer Staples', industry: 'Beverages' },
  { symbol: 'CSCO', name: 'Cisco Systems', sector: 'Technology', industry: 'Communication Equipment' },
  { symbol: 'MCD', name: "McDonald's", sector: 'Consumer Discretionary', industry: 'Restaurants' },
  { symbol: 'AMD', name: 'Advanced Micro Devices', sector: 'Technology', industry: 'Semiconductors' },
  { symbol: 'CRM', name: 'Salesforce', sector: 'Technology', industry: 'Software - Application' },
  { symbol: 'ADBE', name: 'Adobe', sector: 'Technology', industry: 'Software - Infrastructure' },
  { symbol: 'NFLX', name: 'Netflix', sector: 'Communication Services', industry: 'Entertainment' },
  { symbol: 'TMO', name: 'Thermo Fisher Scientific', sector: 'Healthcare', industry: 'Diagnostics' },
  { symbol: 'ACN', name: 'Accenture', sector: 'Technology', industry: 'Information Technology Services' },
  { symbol: 'CVX', name: 'Chevron', sector: 'Energy', industry: 'Oil & Gas' },
  { symbol: 'DIS', name: 'Walt Disney', sector: 'Communication Services', industry: 'Entertainment' },
  { symbol: 'WFC', name: 'Wells Fargo', sector: 'Financials', industry: 'Diversified Banks' },
  { symbol: 'ABT', name: 'Abbott Laboratories', sector: 'Healthcare', industry: 'Medical Devices' },
  { symbol: 'DHR', name: 'Danaher', sector: 'Healthcare', industry: 'Diagnostics' },
  { symbol: 'INTC', name: 'Intel', sector: 'Technology', industry: 'Semiconductors' },
  { symbol: 'CMCSA', name: 'Comcast', sector: 'Communication Services', industry: 'Entertainment' },
  { symbol: 'PFE', name: 'Pfizer', sector: 'Healthcare', industry: 'Drug Manufacturers' },
  { symbol: 'VZ', name: 'Verizon', sector: 'Communication Services', industry: 'Telecom' },
  { symbol: 'T', name: 'AT&T', sector: 'Communication Services', industry: 'Telecom' },
  { symbol: 'QCOM', name: 'Qualcomm', sector: 'Technology', industry: 'Semiconductors' },
  { symbol: 'NKE', name: 'Nike', sector: 'Consumer Discretionary', industry: 'Apparel' },
  { symbol: 'TXN', name: 'Texas Instruments', sector: 'Technology', industry: 'Semiconductors' },
  { symbol: 'CAT', name: 'Caterpillar', sector: 'Industrials', industry: 'Farm Machinery' },
  { symbol: 'GE', name: 'GE Aerospace', sector: 'Industrials', industry: 'Aerospace & Defense' },
];

async function main() {
  const marketId = 'US';

  // 1. Remove all US assets (cascades to their prices).
  const deleted = await p.asset.deleteMany({ where: { marketId } });
  console.log('Deleted US assets:', deleted.count);

  // 2. Ensure the US market exists.
  await p.market.upsert({
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

  // 3. Seed the small dummy universe.
  for (const s of DUMMY_US) {
    await p.asset.upsert({
      where: { marketId_symbol: { marketId, symbol: s.symbol } },
      update: { name: s.name, sector: s.sector, industry: s.industry, isActive: true },
      create: { symbol: s.symbol, name: s.name, sector: s.sector, industry: s.industry, marketId },
    });
  }

  const total = await p.asset.count({ where: { marketId } });
  console.log('Seeded dummy US assets:', total);
}

main()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(() => p.$disconnect());
