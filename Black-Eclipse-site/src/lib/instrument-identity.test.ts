import { describe, expect, it } from 'vitest';
import {
  resolveInstrument,
  verifyProviderIdentity,
  toAssetClass,
  instrumentKey,
  missingContractTerms,
  type InstrumentRow,
} from './instrument-identity';
import { resolveMarketId, isKnownMarket, currencyIsoFor } from './markets';

// ── Market/venue alias resolution ───────────────────────────────────────────
describe('resolveMarketId (venue/country/market aliases)', () => {
  it('resolves venue codes to their canonical market', () => {
    expect(resolveMarketId('PSX')).toBe('PK');
    expect(resolveMarketId('LSE')).toBe('UK');
    expect(resolveMarketId('NASDAQ')).toBe('US');
    expect(resolveMarketId('XETRA')).toBe('DE');
    expect(resolveMarketId('TSX')).toBe('CA');
  });

  it('resolves market ids, country and display names', () => {
    expect(resolveMarketId('PK')).toBe('PK');
    expect(resolveMarketId('Pakistan')).toBe('PK');
    expect(resolveMarketId('United States')).toBe('US');
  });

  it('returns null for an unknown qualifier (never passes it through)', () => {
    expect(resolveMarketId('NOT_A_MARKET')).toBeNull();
    expect(resolveMarketId('')).toBeNull();
    expect(resolveMarketId(null)).toBeNull();
    expect(isKnownMarket('NOT_A_MARKET')).toBe(false);
  });

  it('knows an ISO currency for every resolved market', () => {
    expect(currencyIsoFor('PK')).toBe('PKR');
    expect(currencyIsoFor('US')).toBe('USD');
    expect(currencyIsoFor('CA')).toBe('CAD');
    // Distinct from the display symbol, which is "$" for both US and CA.
    expect(currencyIsoFor('PK')).not.toBe(currencyIsoFor('US'));
  });
});

// ── Identity resolution ─────────────────────────────────────────────────────
describe('resolveInstrument', () => {
  // The verified real-world case: FFC is both a US closed-end fund and Fauji
  // Fertilizer on the Pakistan Stock Exchange.
  const ffcRows: InstrumentRow[] = [
    {
      symbol: 'FFC',
      market: 'US',
      name: 'Flaherty & Crumrine Preferred and Income Securities Fund',
      securityType: 'Closed-end Fund',
    },
    { symbol: 'FFC', market: 'PK', name: 'Fauji Fertilizer Co. Ltd.', securityType: 'Stock' },
  ];

  it('resolves FFC on PSX to the Pakistan instrument, not the US fund', () => {
    const r = resolveInstrument('FFC', { raw: 'PSX' }, ffcRows);
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.identity.market).toBe('PK');
    expect(r.identity.currency).toBe('PKR');
    expect(r.identity.name).toContain('Fauji');
    expect(r.identity.assetClass).toBe('equity');
  });

  it('resolves FFC with no qualifier as AMBIGUOUS (never guesses)', () => {
    const r = resolveInstrument('FFC', {}, ffcRows);
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('ambiguous');
    expect(r.candidates).toEqual(expect.arrayContaining(['US', 'PK']));
  });

  it('rejects an unknown market qualifier rather than dropping it', () => {
    const r = resolveInstrument('FFC', { raw: 'MARS' }, ffcRows);
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('market_unknown');
  });

  it('reports not_found when the qualifier is valid but the ticker is absent', () => {
    const r = resolveInstrument('FFC', { raw: 'JP' }, ffcRows);
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('not_found');
  });

  it('resolves a uniquely-owned bare ticker without a qualifier', () => {
    const rows: InstrumentRow[] = [{ symbol: 'ONLYUS', market: 'US', securityType: 'Stock' }];
    const r = resolveInstrument('ONLYUS', {}, rows);
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(instrumentKey(r.identity)).toBe('US:ONLYUS');
    expect(r.identity.currency).toBe('USD');
  });
});

// ── Provider identity verification ──────────────────────────────────────────
describe('verifyProviderIdentity', () => {
  const pkIdentity = {
    market: 'PK',
    symbol: 'FFC',
    currency: 'PKR',
    assetClass: 'equity' as const,
    securityType: 'Stock',
    name: 'Fauji Fertilizer Co. Ltd.',
  };

  it('accepts a provider answer in the requested market', () => {
    expect(verifyProviderIdentity(pkIdentity, { market: 'PK', currency: 'PKR' }).ok).toBe(true);
  });

  it('rejects an answer priced in a different currency', () => {
    const r = verifyProviderIdentity(pkIdentity, { currency: 'USD' });
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('currency_mismatch');
  });

  it('rejects an answer from a different market', () => {
    const r = verifyProviderIdentity(pkIdentity, { market: 'US' });
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('venue_mismatch');
  });

  it('rejects an answer from a venue we cannot map', () => {
    const r = verifyProviderIdentity(pkIdentity, { market: 'MARS' });
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('venue_mismatch');
  });

  it('accepts absent provider metadata as unverified, not wrong', () => {
    expect(verifyProviderIdentity(pkIdentity, {}).ok).toBe(true);
  });
});

describe('toAssetClass', () => {
  it('classifies the master vocabulary', () => {
    expect(toAssetClass('Stock', 'Equity')).toBe('equity');
    expect(toAssetClass('ETF', 'ETF')).toBe('etf');
    expect(toAssetClass('Closed-end Fund', 'Closed-end Fund')).toBe('fund');
    expect(toAssetClass('Mutual Fund', 'Mutual Fund')).toBe('fund');
    expect(toAssetClass('Listed Debt', 'Listed Debt')).toBe('debt');
    expect(toAssetClass('token', 'Crypto')).toBe('crypto');
    expect(toAssetClass('Modaraba', 'Modaraba')).toBe('fund');
  });
});

// -- A5/A6: contract terms are part of derivative / fixed-income identity ----
describe('contract terms identity (A5/A6)', () => {
  const futureRows: InstrumentRow[] = [{ symbol: 'ES', market: 'US', securityType: 'Future' }];
  const bondRows: InstrumentRow[] = [{ symbol: 'TFC6', market: 'PK', securityType: 'Listed Debt' }];

  it('classifies futures and debt', () => {
    expect(toAssetClass('Future', null)).toBe('derivative');
    expect(toAssetClass('Listed Debt', 'Listed Debt')).toBe('debt');
  });

  it('refuses a derivative without expiry', () => {
    const r = resolveInstrument('ES', { raw: 'US' }, futureRows);
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('terms_missing');
  });

  it('resolves a derivative once expiry is supplied', () => {
    const r = resolveInstrument('ES', { raw: 'US' }, futureRows, { expiry: '2026-12-18', contractMonth: '2026-12' });
    expect(r.ok).toBe(true);
  });

  it('refuses fixed income without maturity', () => {
    const r = resolveInstrument('TFC6', { raw: 'PK' }, bondRows);
    expect(r.ok).toBe(false);
    if (r.ok) return;
    expect(r.reason).toBe('terms_missing');
  });

  it('reports which terms are missing', () => {
    expect(missingContractTerms('derivative', {})).toEqual(['expiry']);
    expect(missingContractTerms('debt', { maturity: '2030-01-01' })).toEqual([]);
    expect(missingContractTerms('equity', {})).toEqual([]);
  });
});
