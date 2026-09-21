// ── Investor Eye — client-side country picking ───────────────────────────────
// The 3D globe has no per-country geometry, so country hover/click on the globe
// is resolved by a point-in-polygon test against the loaded GeoJSON. These cover
// the pure resolver and the outline extraction the globe draws.

import { describe, it, expect } from 'vitest';
import { countryIsoForPoint, countryOutlineRings, type GeoFeature } from './app-geo';

function feature(iso2: string, name: string, coords: number[][][]): GeoFeature {
  return {
    type: 'Feature',
    properties: { name, mapName: name, iso2, iso3: iso2 + 'X' },
    geometry: { type: 'Polygon', coordinates: coords },
  };
}

// A simple 10x10 square from (0,0) to (10,10).
const square = [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]];
// A square with a hole from (4,4) to (6,6) (an enclave).
const squareWithHole = [
  [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
  [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
];

describe('countryIsoForPoint', () => {
  it('resolves a point inside a polygon', () => {
    const features = [feature('AA', 'Alpha', square)];
    expect(countryIsoForPoint(features, 5, 5)).toBe('AA');
  });

  it('returns undefined for a point outside every polygon (ocean)', () => {
    const features = [feature('AA', 'Alpha', square)];
    expect(countryIsoForPoint(features, 50, 50)).toBeUndefined();
  });

  it('respects holes so an enclave is not swallowed by its neighbour', () => {
    const features = [feature('AA', 'Alpha', squareWithHole)];
    expect(countryIsoForPoint(features, 1, 1)).toBe('AA');
    // Inside the hole — not part of Alpha.
    expect(countryIsoForPoint(features, 5, 5)).toBeUndefined();
  });

  it('skips a feature whose ISO2 is the -99 sentinel', () => {
    const features = [feature('-99', 'Unknown', square)];
    expect(countryIsoForPoint(features, 5, 5)).toBeUndefined();
  });

  it('handles MultiPolygon geometry', () => {
    const multi: GeoFeature = {
      type: 'Feature',
      properties: { name: 'Multi', mapName: 'Multi', iso2: 'MP', iso3: 'MPX' },
      geometry: { type: 'MultiPolygon', coordinates: [square, [[[20, 20], [25, 20], [25, 25], [20, 25], [20, 20]]]] },
    };
    expect(countryIsoForPoint([multi], 22, 22)).toBe('MP');
  });

  it('returns undefined for a non-finite coordinate', () => {
    const features = [feature('AA', 'Alpha', square)];
    expect(countryIsoForPoint(features, NaN, 5)).toBeUndefined();
    expect(countryIsoForPoint(features, 5, Infinity)).toBeUndefined();
  });
});

describe('countryOutlineRings', () => {
  it('returns every ring of the requested country', () => {
    const features = [feature('AA', 'Alpha', squareWithHole)];
    const rings = countryOutlineRings(features, 'AA');
    expect(rings).toHaveLength(2);
    expect(rings[0][0]).toEqual([0, 0]);
  });

  it('is case-insensitive on the ISO2', () => {
    const features = [feature('AA', 'Alpha', square)];
    expect(countryOutlineRings(features, 'aa')).toHaveLength(1);
  });

  it('returns nothing for a missing country', () => {
    const features = [feature('AA', 'Alpha', square)];
    expect(countryOutlineRings(features, 'ZZ')).toEqual([]);
    expect(countryOutlineRings(features, null)).toEqual([]);
  });

  it('drops degenerate rings', () => {
    const degenerate = [[[0, 0], [1, 1]]];
    const features = [feature('AA', 'Alpha', degenerate)];
    expect(countryOutlineRings(features, 'AA')).toEqual([]);
  });
});
