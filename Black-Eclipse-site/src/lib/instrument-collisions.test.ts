import { describe, expect, it } from 'vitest';
import fixtures from './instrument-collisions.json';
import { resolveInstrument, type InstrumentRow } from './instrument-identity';
import { resolveMarketId } from './markets';

// Every entry in this fixture is a REAL collision from the JDdS instrument
// master (see instrument-collisions.json). The point of this test is that the
// identity rule generalizes across countries and asset classes: for ANY ticker
// that maps to more than one market, an unqualified lookup is ambiguous, and a
// qualified lookup resolves to exactly the requested market.

const { crossMarket, crossClass } = fixtures as {
  crossMarket: Record<string, string[]>;
  crossClass: Record<string, string[]>;
};

describe('instrument collision fixtures (generated from the master)', () => {
  const symbols = Object.keys(crossMarket);

  it('has a substantial, real collision set (not a hand-picked few)', () => {
    // If this ever collapses, the generator or the master changed — investigate.
    expect(symbols.length).toBeGreaterThan(500);
  });

  it('every unqualified colliding ticker is AMBIGUOUS', () => {
    const failures: string[] = [];
    for (const symbol of symbols.slice(0, 400)) {
      const markets = crossMarket[symbol];
      if (markets.length < 2) continue;
      const rows: InstrumentRow[] = markets.map((m) => ({ symbol, market: m }));
      const r = resolveInstrument(symbol, {}, rows);
      if (r.ok || r.reason !== 'ambiguous') failures.push(`${symbol} -> ${JSON.stringify(r)}`);
    }
    expect(failures).toEqual([]);
  });

  it('every qualified colliding ticker resolves to exactly that market', () => {
    const failures: string[] = [];
    for (const symbol of symbols.slice(0, 400)) {
      const markets = crossMarket[symbol];
      if (markets.length < 2) continue;
      const rows: InstrumentRow[] = markets.map((m) => ({ symbol, market: m }));
      for (const market of markets) {
        const r = resolveInstrument(symbol, { raw: market }, rows);
        if (!r.ok || r.identity.market !== market) {
          failures.push(`${symbol}/${market} -> ${JSON.stringify(r)}`);
        }
      }
    }
    expect(failures).toEqual([]);
  });

  it('a venue code from the cross-market set resolves to its market (PSX is PK)', () => {
    // The FFC example, expressed as the general rule.
    expect(resolveMarketId('PSX')).toBe('PK');
  });

  it('cross-asset-class tickers are still ambiguous without a market', () => {
    const failures: string[] = [];
    for (const [symbol, types] of Object.entries(crossClass).slice(0, 200)) {
      if (types.length < 2) continue;
      // Same ticker, same market, two asset classes = two instruments.
      const rows: InstrumentRow[] = types.map((t) => ({ symbol, market: 'US', securityType: t }));
      const r = resolveInstrument(symbol, {}, rows);
      if (r.ok) failures.push(`${symbol} -> ${JSON.stringify(r)}`);
    }
    expect(failures).toEqual([]);
  });
});
