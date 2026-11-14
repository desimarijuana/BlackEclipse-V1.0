// Import the Black Eclipse crypto universe (assets + prices) into JDDS under the
// CRYPTO market, with duplicate detection and category enrichment.
//
// Primary source:  crypto_universe_*.jsonl  (1500 coins, per-coin metric rows)
//   metrics: price_usd, price_change_24h, market_cap, volume_24h, ath,
//            ath_change_percentage, atl, atl_change_percentage,
//            circulating_supply, total_supply, max_supply, fdv
// Enrichment:  market_data_*.jsonl  (categories / asset_type / chain per coin)
//
// Each coin's sector/industry is derived from its CoinGecko categories, mapped to
// the screener's category buckets (Layer 1, Layer 2, DeFi, Meme Coins, Gaming,
// AI / Data, DePIN, Privacy, Payment, Exchange Tokens, Stablecoins, RWA, etc).
//
// Usage: node scripts/import-crypto.js [universe-file] [marketdata-file]
const { PrismaClient } = require('../src/generated/prisma/client');
const { PrismaBetterSqlite3 } = require('@prisma/adapter-better-sqlite3');
const path = require('path');
const fs = require('fs');

const { importPath } = require('./lib/import-paths');

// The timestamp in the sample filename is only a default; pass a path to override.
const DEFAULT_MARKETDATA_DIR = importPath('eclipse-crypto-data', 'data', 'output');
const DEFAULT_UNIVERSE = path.join(DEFAULT_MARKETDATA_DIR, 'crypto_universe_20260814_223934.jsonl');

const adapter = new PrismaBetterSqlite3({ url: 'file:' + path.join(process.cwd(), 'jdds.db') });
const prisma = new PrismaClient({ adapter });

// ─── Category bucketing ─────────────────────────────────────────────────────
// Map a raw CoinGecko category -> a screener bucket (sector) + a refined label
// (industry). Falls back to 'Other' when unknown. Priority order matters.
const BUCKETS = [
  { sector: 'Layer 1', match: [/^Layer 1 \(L1\)$/, /Smart Contract Platform/, /Layer 0 \(L0\)$/], label: null },
  { sector: 'Layer 2', match: [/^Layer 2 \(L2\)$/, /Rollup/, /Optimistic Rollup/, /Zero Knowledge Rollups/, /Polygon Ecosystem/, /zkSync Ecosystem/, /Arbitrum Ecosystem/, /Optimism Ecosystem/, /Base Ecosystem/, /Base Native/, /MegaETH Ecosystem/, /Linea Ecosystem/, /Scroll Ecosystem/, /Hyperliquid Ecosystem/, /Mantle Ecosystem/, /Morph L2 Ecosystem/], label: null },
  { sector: 'DeFi', match: [/Decentralized Finance \(DeFi\)/, /Decentralized Exchange \(DEX\)/, /Automated Market Maker \(AMM\)/, /Lending\/Borrowing/, /Yield Farming/, /Yield Aggregator/, /Liquid Staking/, /Restaking/, /Perpetuals/, /Derivatives/, /Options/, /Prediction Markets/, /LSDFi/, /Index Coop Defi Index/], label: null },
  { sector: 'Stablecoins', match: [/Stablecoin/, /Fiat-backed Stablecoin/, /Crypto-backed Stablecoin/, /USD Stablecoin/, /EUR Stablecoin/, /Yield-Bearing Stablecoin/], label: null },
  { sector: 'Meme Coins', match: [/^Meme$/, /Meme Coins/, /Solana Meme/, /Base Meme/, /TON Meme/, /GMCI Meme Index/, /Cat-Themed/, /Dog-Themed/, /Frog-Themed/, /Parody Meme/, /4chan-Themed/, /Celebrity-Themed/, /Pump\.fun/], label: null },
  { sector: 'Gaming', match: [/Gaming \(GameFi\)/, /Play To Earn/, /Tap to Earn/, /Gaming Blockchains/, /Gaming Marketplace/, /Gaming Utility Token/, /Arcade Games/, /NFT/, /Metaverse/], label: null },
  { sector: 'AI / Data', match: [/Artificial Intelligence \(AI\)/, /AI Agents/, /AI Framework/, /AI Applications/, /DeFAI/, /AI Agent Launchpad/, /Data Availability/, /Analytics/, /Big Data/, /Bittensor/], label: null },
  { sector: 'DePIN', match: [/DePIN/, /Storage/, /Internet of Things \(IOT\)/, /Computing/, /Distributed Computing/, /Data Storage/], label: null },
  { sector: 'Privacy', match: [/Privacy/, /Privacy Coins/, /Zero Knowledge \(ZK\)/, /Privacy Infrastructure/, /Masternodes/], label: null },
  { sector: 'Payment', match: [/Payment Solutions/, /Payment Tokens/, /Cross-border/, /Remittance/, /Payments/], label: null },
  { sector: 'Exchange Tokens', match: [/Exchange-based Tokens/, /Centralized Exchange \(CEX\) Token/, /DEX Token/], label: null },
  { sector: 'Real World Assets', match: [/Real World Assets \(RWA\)/, /Tokenized Assets/, /Tokenized Stock/, /Tokenized Treasuries/, /Tokenized Credit/, /Tokenized Exchange-Traded/, /RWA Protocol/, /Ondo Tokenized/, /Tokenized Exchange-Traded Funds \(ETFs\)/], label: null },
  { sector: 'Infrastructure', match: [/Infrastructure/, /Cross-chain Communication/, /Interoperability/, /Chain Abstraction/, /Oracle/, /Indexing/, /Launchpad/, /Wallets/, /Governance/, /SocialFi/, /Media/], label: null },
];

function classify(categories) {
  if (!categories || !categories.length) return { sector: 'Other', industry: 'Other' };
  for (const b of BUCKETS) {
    for (const rx of b.match) {
      if (categories.some((c) => rx.test(c))) {
        // Pick a more specific industry label when available.
        const specific = categories.find((c) => /Layer 1 \(L1\)/.test(c) || /Layer 2 \(L2\)/.test(c) || /Stablecoin/.test(c) || /Gaming \(GameFi\)/.test(c) || /Artificial Intelligence \(AI\)/.test(c));
        return { sector: b.sector, industry: specific || b.sector };
      }
    }
  }
  return { sector: 'Other', industry: 'Other' };
}

// Read a JSONL file into a map keyed by asset_id.
function readJsonlMap(file) {
  const map = {};
  if (!fs.existsSync(file)) { console.warn('Missing file:', file); return map; }
  const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/).filter(Boolean);
  for (const l of lines) {
    try {
      const o = JSON.parse(l);
      map[o.asset_id] = map[o.asset_id] || { metrics: {}, meta: null };
      if (o.metric) map[o.asset_id].metrics[o.metric] = o.value;
      else if (o.categories || o.asset_type || o.chain || o.market_cap_rank != null) {
        map[o.asset_id].meta = o; // the asset metadata row
      }
    } catch (e) { /* skip malformed */ }
  }
  return map;
}

// Read every market_data_*.jsonl in a directory, merging categories/type/chain
// per asset (multiple enrichment runs may cover different coins).
function readAllMarketData(dir) {
  const map = {};
  if (!fs.existsSync(dir)) { console.warn('Missing dir:', dir); return map; }
  const files = fs.readdirSync(dir).filter((f) => /^market_data_.*\.jsonl$/.test(f));
  for (const file of files) {
    const lines = fs.readFileSync(path.join(dir, file), 'utf8').split(/\r?\n/).filter(Boolean);
    for (const l of lines) {
      try {
        const o = JSON.parse(l);
        if (o.asset_id && (o.categories || o.asset_type || o.chain)) {
          map[o.asset_id] = map[o.asset_id] || { categories: null, asset_type: null, chain: null };
          if (o.categories) map[o.asset_id].categories = o.categories;
          if (o.asset_type) map[o.asset_id].asset_type = o.asset_type;
          if (o.chain) map[o.asset_id].chain = o.chain;
        }
      } catch (e) { /* skip malformed */ }
    }
  }
  return map;
}

function num(v) {
  if (v == null || Number.isNaN(Number(v))) return null;
  return Number(v);
}

async function main() {
  const universeFile = process.argv[2] || DEFAULT_UNIVERSE;
  const marketDataDir = process.argv[3] || DEFAULT_MARKETDATA_DIR;

  // Ensure the CRYPTO market exists.
  await prisma.market.upsert({
    where: { id: 'CRYPTO' },
    update: { enabled: true },
    create: {
      id: 'CRYPTO',
      country: 'CRYPTO',
      exchange: 'Global',
      timezone: 'UTC',
      openHour: 0,
      closeHour: 24,
      isCrypto: true,
    },
  });

  const universe = readJsonlMap(universeFile);
  const marketData = readAllMarketData(marketDataDir);
  const coinIds = Object.keys(universe).filter((id) => Object.keys(universe[id].metrics).length > 0);
  // Process highest market-cap rank first so that, for symbols shared by
  // multiple coins, the most significant coin owns the symbol in JDDS.
  coinIds.sort((a, b) => {
    const ra = num(universe[a].metrics.market_cap_rank ?? universe[a].meta?.market_cap_rank);
    const rb = num(universe[b].metrics.market_cap_rank ?? universe[b].meta?.market_cap_rank);
    return (ra ?? 1e9) - (rb ?? 1e9);
  });
  console.log(`Universe coins with metrics: ${coinIds.length}`);

  let created = 0, updated = 0, skipped = 0;
  const bySector = {};
  const tx = await prisma.$transaction(async (p) => {
    for (const id of coinIds) {
      const m = universe[id].metrics;
      const symbol = (m.symbol || universe[id].meta?.symbol || id).toUpperCase();
      if (!symbol || !m.price_usd) { skipped++; continue; }
      const name = m.name || universe[id].meta?.name || symbol;

      // Enrich with categories/type/chain from market data.
      const md = marketData[id];
      const categories = md?.categories || null;
      const asset_type = md?.asset_type || null;
      const chain = md?.chain || null;
      const { sector, industry } = classify(categories);

      const price = num(m.price_usd);
      const changePct = num(m.price_change_24h) || 0;
      const marketCap = num(m.market_cap);
      const volume = num(m.volume_24h);
      const fdv = num(m.fdv);
      const circulatingSupply = num(m.circulating_supply);
      const totalSupply = num(m.total_supply);
      const maxSupply = num(m.max_supply);
      const ath = num(m.ath);
      const atl = num(m.atl);
      const athChangePct = num(m.ath_change_percentage);
      const rank = num(m.market_cap_rank || universe[id].meta?.market_cap_rank);

      const existing = await p.asset.findUnique({
        where: { marketId_symbol: { marketId: 'CRYPTO', symbol } },
      });

      if (existing) {
        await p.asset.update({
          where: { id: existing.id },
          data: {
            name,
            sector: sector ?? existing.sector,
            industry: industry ?? existing.industry,
            country: 'CRYPTO',
            securityType: asset_type || existing.securityType,
            isActive: true,
          },
        });
        updated++;
      } else {
        await p.asset.create({
          data: {
            symbol,
            name,
            marketId: 'CRYPTO',
            sector,
            industry,
            country: 'CRYPTO',
            securityType: asset_type || null,
            assetClass: 'Crypto',
            isActive: true,
          },
        });
        created++;
      }

      const asset = await p.asset.findUnique({
        where: { marketId_symbol: { marketId: 'CRYPTO', symbol } },
      });
      if (asset) {
        await p.price.upsert({
          where: { assetId: asset.id },
          update: {
            price,
            changePct: changePct ?? 0,
            marketCap,
            volume,
            rank,
            fdv,
            circulatingSupply,
            totalSupply,
            maxSupply,
            ath,
            atl,
            athChangePct,
            source: 'csv',
          },
          create: {
            assetId: asset.id,
            price,
            changePct: changePct ?? 0,
            marketCap,
            volume,
            rank,
            fdv,
            circulatingSupply,
            totalSupply,
            maxSupply,
            ath,
            atl,
            athChangePct,
            source: 'csv',
          },
        });
      }

      bySector[sector] = (bySector[sector] || 0) + 1;
    }
  });

  const total = await prisma.asset.count({ where: { marketId: 'CRYPTO' } });
  const withPrice = await prisma.asset.count({ where: { marketId: 'CRYPTO', price: { isNot: null } } });

  console.log('\n=== Crypto import complete ===');
  console.log(`Coins processed:  ${coinIds.length}`);
  console.log(`Created:          ${created}`);
  console.log(`Updated:          ${updated}`);
  console.log(`Skipped:          ${skipped}`);
  console.log(`Total CRYPTO assets: ${total}`);
  console.log(`With price:       ${withPrice}`);
  console.log('\nBy sector:');
  for (const [s, c] of Object.entries(bySector).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${s}: ${c}`);
  }
}

main()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(() => prisma.$disconnect());
