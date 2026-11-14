// Shared source-data paths for the one-off bulk importers.
//
// WHY: the scraped CSVs/JSONL that populate JDDS are not part of the repository
// (they are third-party market data, and a snapshot can carry a real journal).
// The importers used to default to an absolute path on one developer's machine,
// which leaked a personal directory into the public tree and was useless to
// everyone else. Point `BE_IMPORT_ROOT` at a directory that mirrors the layout
// below; the default is `./data/imports` under the app directory.
//
// Layout (see each importer's header for the exact files):
//   data/imports/market-scraping/<Market>_Stock_Listings/...
//   data/imports/eclipse-crypto-data/data/output/...
//   data/imports/Eclipse-PSX-Universe/normalized/...
//   data/imports/black_eclipse_assets/divided/...
//   data/imports/blackeclipse_market_universe/...
const path = require("path");

function importRoot() {
  return process.env.BE_IMPORT_ROOT || path.join(process.cwd(), "data", "imports");
}

function importPath(...parts) {
  return path.join(importRoot(), ...parts);
}

module.exports = { importRoot, importPath };
