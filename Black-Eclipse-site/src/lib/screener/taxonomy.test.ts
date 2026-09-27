import { describe, it, expect } from 'vitest';
import {
  UNCLASSIFIED, normalizeSector, normalizeIndustry,
  rawSectorVariants, rawIndustryVariants,
} from './taxonomy';

describe('screener taxonomy normalization', () => {
  it('collapses sector synonyms to one canonical label', () => {
    expect(normalizeSector('Financials')).toBe('Financial Services');
    expect(normalizeSector('Financial Services')).toBe('Financial Services');
    expect(normalizeSector('Consumer Discretionary')).toBe('Consumer Cyclical');
    expect(normalizeSector('Consumer Staples')).toBe('Consumer Defensive');
    expect(normalizeSector('Payment')).toBe('Payments');
    expect(normalizeSector('Meme')).toBe('Meme Coins');
  });

  it('passes unknown sectors through unchanged', () => {
    expect(normalizeSector('Technology')).toBe('Technology');
    expect(normalizeSector('Non-Energy Minerals')).toBe('Non-Energy Minerals');
  });

  it('maps null/undefined to Unclassified', () => {
    expect(normalizeSector(null)).toBe(UNCLASSIFIED);
    expect(normalizeSector(undefined)).toBe(UNCLASSIFIED);
    expect(normalizeIndustry(null)).toBe(UNCLASSIFIED);
  });

  it('collapses crypto industry variants', () => {
    expect(normalizeIndustry('Layer 1 (L1)')).toBe('Layer 1');
    expect(normalizeIndustry('Gaming (GameFi)')).toBe('Gaming');
    expect(normalizeIndustry('Fiat-backed Stablecoin')).toBe('Stablecoins');
    expect(normalizeIndustry('Stablecoin Issuer')).toBe('Stablecoins');
  });

  it('rawSectorVariants returns every stored synonym for a canonical label', () => {
    expect(rawSectorVariants('Financial Services').sort()).toEqual(['Financial Services', 'Financials']);
    expect(rawSectorVariants('Technology')).toEqual(['Technology']);
    expect(rawSectorVariants(UNCLASSIFIED)).toEqual([]);
  });

  it('rawIndustryVariants returns every stored synonym for a canonical label', () => {
    expect(rawIndustryVariants('Stablecoins').sort())
      .toEqual(['Fiat-backed Stablecoin', 'Stablecoin Issuer', 'Stablecoins', 'Yield-Bearing Stablecoin']);
    expect(rawIndustryVariants('Layer 1').sort()).toEqual(['Layer 1', 'Layer 1 (L1)']);
    expect(rawIndustryVariants(UNCLASSIFIED)).toEqual([]);
  });
});
