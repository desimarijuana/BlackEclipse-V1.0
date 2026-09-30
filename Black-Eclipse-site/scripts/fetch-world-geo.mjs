// ── Fetch + slim the Natural Earth world map ────────────────────────────────
// Downloads the public-domain Natural Earth 1:110m admin-0 country boundaries
// and writes a slimmed GeoJSON to `public/geo/world.geo.json` for Investor Eye.
//
// Why a build-time asset instead of a runtime fetch or a hard-coded blob:
//   - zero runtime configuration (works offline once vendored),
//   - the browser only downloads ~300 KB instead of the full 840 KB source,
//   - React components never embed a geographic dataset.
//
// Natural Earth is public domain (no attribution required) — see
// https://www.naturalearthdata.com/about/terms-of-use/.
//
// ⚠️  The committed `world.geo.json` is NOT a byte-for-byte copy of the upstream
// default. It has been deliberately post-processed:
//   1. Point-of-view on disputed territory: the whole of Jammu & Kashmir (incl.
//      the Kashmir Valley, Jammu and Ladakh) is rendered as Pakistan, while
//      Aksai Chin remains with China.
//   2. The Gaza Strip is added to Palestine (`PS` becomes a MultiPolygon of West
//      Bank + Gaza) and subtracted from Israel's coarse polygon — at 110m Gaza
//      would otherwise render as an unclaimed blank.
// Re-running this script regenerates the *default* Natural Earth view and will
// silently revert both. Re-apply them after regenerating — see
// docs/investor-eye-architecture.md §2.1.
//
// Usage: `node scripts/fetch-world-geo.mjs`

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SOURCE =
  'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, '..', 'public', 'geo', 'world.geo.json');

// Coordinate precision. 110m geometry is coarse enough that 2 decimals
// (~1 km) is visually lossless while cutting the payload by >50%.
const PRECISION = 2;

function roundCoord(coord) {
  if (typeof coord[0] === 'number') {
    return [
      Number(coord[0].toFixed(PRECISION)),
      Number(coord[1].toFixed(PRECISION)),
    ];
  }
  return coord.map(roundCoord);
}

function roundGeometry(geometry) {
  if (!geometry) return geometry;
  return { type: geometry.type, coordinates: roundCoord(geometry.coordinates) };
}

async function main() {
  console.log(`[world-geo] fetching ${SOURCE}`);
  const res = await fetch(SOURCE, {
    headers: { Accept: 'application/geo+json, application/json' },
    signal: AbortSignal.timeout(60_000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} from Natural Earth`);
  const raw = await res.json();
  if (raw?.type !== 'FeatureCollection' || !Array.isArray(raw.features)) {
    throw new Error('Unexpected payload — expected a GeoJSON FeatureCollection');
  }

  const features = raw.features
    .map((f) => {
      const p = f.properties ?? {};
      // Keep only the fields Investor Eye matches/display on. `mapName` is the
      // Natural Earth display name used to join a GeoJSON feature to a country
      // entity; ISO codes are the primary key.
      const props = {
        name: p.NAME ?? p.ADMIN ?? p.name ?? 'Unknown',
        mapName: p.ADMIN ?? p.NAME ?? 'Unknown',
        iso2: p.ISO_A2 ?? p.iso_a2 ?? '-99',
        iso3: p.ISO_A3 ?? p.iso_a3 ?? '-99',
      };
      // A few ISO_A2 values are '-99' in the source; fall back to ISO_A3.
      if (props.iso2 === '-99' && props.iso3 !== '-99') props.iso2 = props.iso3;
      return {
        type: 'Feature',
        properties: props,
        geometry: roundGeometry(f.geometry),
      };
    })
    .filter((f) => f.geometry);

  const out = { type: 'FeatureCollection', features };

  await fs.mkdir(path.dirname(OUT), { recursive: true });
  await fs.writeFile(OUT, JSON.stringify(out), 'utf8');
  const { size } = await fs.stat(OUT);
  console.log(`[world-geo] wrote ${features.length} features → ${OUT} (${(size / 1024).toFixed(0)} KB)`);
}

main().catch((err) => {
  console.error('[world-geo] failed:', err);
  process.exit(1);
});
