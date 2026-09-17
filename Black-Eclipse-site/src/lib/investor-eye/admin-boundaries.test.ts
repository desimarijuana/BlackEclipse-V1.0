import { describe, it, expect } from 'vitest';
import {
  pointInRing, pointInParts, geometryParts, countryAtPoint, loadBoundaries,
} from './admin-boundaries';

// A 2x2 square (0,0)-(2,2) with a 1x1 hole at (0.5,0.5)-(1.5,1.5).
const RING: number[][] = [[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]];
const HOLE: number[][] = [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5], [0.5, 0.5]];

describe('pointInRing', () => {
  it('detects inside and outside', () => {
    expect(pointInRing(1, 1, RING)).toBe(true);
    expect(pointInRing(3, 1, RING)).toBe(false);
    expect(pointInRing(-0.1, 1, RING)).toBe(false);
  });
});

describe('pointInParts', () => {
  it('treats an interior hole as outside the polygon', () => {
    expect(pointInParts(0.2, 0.2, [[RING, HOLE]])).toBe(true);
    // The centre of the hole belongs to the enclave, not the surrounding shape.
    expect(pointInParts(1, 1, [[RING, HOLE]])).toBe(false);
  });

  it('returns false for an empty part list', () => {
    expect(pointInParts(1, 1, [])).toBe(false);
    expect(pointInParts(1, 1, [[]])).toBe(false);
  });
});

describe('geometryParts', () => {
  it('normalizes Polygon and MultiPolygon without mixing nesting', () => {
    expect(geometryParts({ type: 'Polygon', coordinates: [RING] })).toHaveLength(1);
    expect(geometryParts({ type: 'MultiPolygon', coordinates: [[RING], [RING]] })).toHaveLength(2);
    expect(geometryParts({ type: 'Point', coordinates: [0, 0] })).toHaveLength(0);
  });
});

describe('countryAtPoint against the shipped boundaries', () => {
  it('loads the repo boundary asset', () => {
    expect(loadBoundaries().length).toBeGreaterThan(100);
  });

  it('resolves a point deep inside a large country (centroid matching cannot)', () => {
    // Eastern Siberia — thousands of km from Russia's centroid.
    expect(countryAtPoint(115, 62)).toBe('RU');
    // The Australian interior.
    expect(countryAtPoint(133, -24)).toBe('AU');
    // The Brazilian interior.
    expect(countryAtPoint(-55, -12)).toBe('BR');
  });

  it('returns undefined for a point in international waters', () => {
    // South Atlantic, far from any land.
    expect(countryAtPoint(-25, -55)).toBeUndefined();
    expect(countryAtPoint(-140, -40)).toBeUndefined();
  });

  it('rejects a non-finite coordinate instead of guessing', () => {
    expect(countryAtPoint(Number.NaN, 10)).toBeUndefined();
  });

  it('accepts an injected boundary list so tests need no file access', () => {
    const fake = [{ iso2: 'ZZ', parts: [[RING]] }];
    expect(countryAtPoint(1, 1, fake)).toBe('ZZ');
    expect(countryAtPoint(5, 5, fake)).toBeUndefined();
  });
});
