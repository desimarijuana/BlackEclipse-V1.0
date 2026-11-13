import { describe, expect, it } from 'vitest';
import { rmsFromTimeDomain, rmsToLevel, smoothLevel, spectralCentroid } from './meter';

function buffer(values: number[]): Uint8Array {
  return Uint8Array.from(values);
}

describe('rmsFromTimeDomain', () => {
  it('is zero for a centred (silent) buffer', () => {
    expect(rmsFromTimeDomain(buffer([128, 128, 128, 128]))).toBe(0);
  });

  it('is near one for a full-scale square wave', () => {
    // 8-bit samples are asymmetric (−128..127 over 128), so 255 is ≈0.992.
    expect(rmsFromTimeDomain(buffer([255, 0, 255, 0]))).toBeCloseTo(0.996, 2);
  });

  it('handles an empty buffer', () => {
    expect(rmsFromTimeDomain(buffer([]))).toBe(0);
  });
});

describe('rmsToLevel', () => {
  it('treats the noise floor as silence', () => {
    expect(rmsToLevel(0)).toBe(0);
    expect(rmsToLevel(0.004)).toBe(0);
  });

  it('lifts quiet speech into a usable range', () => {
    const quiet = rmsToLevel(0.03);
    expect(quiet).toBeGreaterThan(0.15);
    expect(quiet).toBeLessThan(rmsToLevel(0.12));
  });

  it('saturates at 1 and rejects non-finite input', () => {
    expect(rmsToLevel(1)).toBe(1);
    expect(rmsToLevel(Number.NaN)).toBe(0);
    expect(rmsToLevel(Infinity)).toBe(0);
  });
});

describe('smoothLevel', () => {
  it('attacks faster than it releases', () => {
    const up = smoothLevel(0, 1, 0.5, 0.12);
    const down = smoothLevel(1, 0, 0.5, 0.12);
    expect(up).toBeCloseTo(0.5, 5);
    expect(down).toBeCloseTo(0.88, 5);
  });

  it('clamps and survives NaN input', () => {
    expect(smoothLevel(0.5, 2)).toBeLessThanOrEqual(1);
    expect(smoothLevel(0.5, -2)).toBeGreaterThanOrEqual(0);
    expect(smoothLevel(0.5, Number.NaN)).toBe(0.5);
  });
});

describe('spectralCentroid', () => {
  it('is low for bass-heavy energy and high for treble-heavy energy', () => {
    const bins = 64;
    const bass = new Uint8Array(bins);
    bass[2] = 255;
    const treble = new Uint8Array(bins);
    treble[58] = 255;
    expect(spectralCentroid(bass, 44100)).toBeLessThan(spectralCentroid(treble, 44100));
  });

  it('is zero for an empty spectrum', () => {
    expect(spectralCentroid(new Uint8Array(32), 44100)).toBe(0);
    expect(spectralCentroid(new Uint8Array(0), 44100)).toBe(0);
  });

  it('stays inside 0..1', () => {
    const bins = new Uint8Array(64).fill(255);
    const value = spectralCentroid(bins, 44100);
    expect(value).toBeGreaterThanOrEqual(0);
    expect(value).toBeLessThanOrEqual(1);
  });
});
