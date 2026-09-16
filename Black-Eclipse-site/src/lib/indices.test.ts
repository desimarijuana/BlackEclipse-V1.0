import { describe, it, expect } from 'vitest';
import { resolveIndex, isPsxIndex, searchIndices, INDEX_DEFS, indexCurrency } from './indices';
import { parsePsxHistorical, parsePsxEod, psxTicker } from './scraper/fetchers/psx-index';
import { getInstrumentByAlias } from './search/registry';

// ── resolveIndex ─────────────────────────────────────────────────────────────
// The core defect this module fixes: the UI used to hand the data path bare
// TradingView ids (`SPX`, `DJI`, `NIFTY`) that Yahoo has no instrument for.
// Resolution must map those to the real, fetchable ticker.

describe('resolveIndex', () => {
  it('maps the bare TradingView ids the old registry shipped', () => {
    expect(resolveIndex('SPX')?.symbol).toBe('^GSPC');
    expect(resolveIndex('DJI')?.symbol).toBe('^DJI');
    expect(resolveIndex('NDX')?.symbol).toBe('^NDX');
    expect(resolveIndex('RUT')?.symbol).toBe('^RUT');
  });

  it('is case- and caret-insensitive', () => {
    for (const raw of ['spx', '^SPX', ' ^spx ', '^GSPC', 'gspc']) {
      expect(resolveIndex(raw)?.symbol).toBe('^GSPC');
    }
  });

  it('resolves the world benchmarks the user asked for', () => {
    expect(resolveIndex('^GSPC')?.name).toBe('S&P 500');
    expect(resolveIndex('^DJI')?.name).toBe('Dow Jones Industrial Average');
    expect(resolveIndex('^FTSE')?.name).toBe('FTSE 100');
    expect(resolveIndex('^NSEI')?.name).toBe('Nifty 50');
    expect(resolveIndex('NIFTY')?.symbol).toBe('^NSEI');
    expect(resolveIndex('KSE100')?.symbol).toBe('^KSE100');
  });

  it('routes PSX benchmarks to their own provider', () => {
    expect(isPsxIndex('^KSE100')).toBe(true);
    expect(isPsxIndex('KSE30')).toBe(true);
    expect(isPsxIndex('KMI30')).toBe(true);
    // Yahoo-backed indices must NOT be sent to the PSX endpoint.
    expect(isPsxIndex('^GSPC')).toBe(false);
    expect(isPsxIndex('^NSEI')).toBe(false);
  });

  it('reports the index currency so a bare index is not shown in USD', () => {
    expect(indexCurrency('^FTSE')).toBe('GBP');
    expect(indexCurrency('^NSEI')).toBe('INR');
    expect(indexCurrency('^KSE100')).toBe('PKR');
    expect(indexCurrency('^GSPC')).toBe('USD');
  });

  it('does not hijack tickers that collide with real listed instruments', () => {
    // `DAX` is the Global X DAX Germany ETF, `STI` is Solidion Technology,
    // `SSE` is SSE plc, `000001` is a Shanghai-listed stock. Charting those
    // must keep meaning the instrument, not the index.
    expect(resolveIndex('DAX')).toBeUndefined();
    expect(resolveIndex('STI')).toBeUndefined();
    expect(resolveIndex('SSE')).toBeUndefined();
    expect(resolveIndex('000001')).toBeUndefined();
    expect(resolveIndex('TSX')).toBeUndefined();
    expect(resolveIndex('IPC')).toBeUndefined();
    // …but the explicit canonical tickers still work.
    expect(resolveIndex('^GDAXI')?.name).toBe('DAX');
    expect(resolveIndex('^STI')?.name).toBe('Straits Times');
  });

  it('returns undefined for non-indices and empty input', () => {
    expect(resolveIndex('AAPL')).toBeUndefined();
    expect(resolveIndex('')).toBeUndefined();
    expect(resolveIndex(null)).toBeUndefined();
    expect(resolveIndex(undefined)).toBeUndefined();
  });

  it('never maps two indices to the same canonical symbol', () => {
    const symbols = INDEX_DEFS.map(d => d.symbol);
    expect(new Set(symbols).size).toBe(symbols.length);
  });
});

// ── searchIndices ────────────────────────────────────────────────────────────

describe('searchIndices', () => {
  it('finds indices by name', () => {
    expect(searchIndices('nifty')[0]?.symbol).toBe('^NSEI');
    expect(searchIndices('ftse')[0]?.symbol).toBe('^FTSE');
    expect(searchIndices('dow')[0]?.symbol).toBe('^DJI');
  });

  it('finds indices by the aliases that are unsafe to resolve implicitly', () => {
    // "DAX" must surface the index in autocomplete even though resolving the
    // bare ticker would select the ETF instead.
    expect(searchIndices('dax').some(d => d.symbol === '^GDAXI')).toBe(true);
    expect(searchIndices('kse100')[0]?.symbol).toBe('^KSE100');
  });

  it('returns nothing for an empty query', () => {
    expect(searchIndices('')).toEqual([]);
    expect(searchIndices('   ')).toEqual([]);
  });

  it('respects the limit', () => {
    expect(searchIndices('a', 3).length).toBeLessThanOrEqual(3);
  });
});

// ── Search registry integration ──────────────────────────────────────────────
// The palette must hand the chart a ticker the data path can actually fetch.

describe('search registry index entries', () => {
  it('registers S&P 500 with the canonical Yahoo ticker, not "SPX"', () => {
    const spx = getInstrumentByAlias('S&P 500');
    expect(spx?.assetClass).toBe('index');
    // The destination symbol is what reaches /api/price-history.
    expect(spx?.destination.params?.symbol).toBe('^GSPC');
  });

  it('registers the indices the user listed, reachable by their common names', () => {
    const cases: Array<[string, string]> = [
      ['dow jones', '^DJI'],
      ['ftse 100', '^FTSE'],
      ['nifty 50', '^NSEI'],
      ['kse 100', '^KSE100'],
      ['nikkei', '^N225'],
      ['dax', '^GDAXI'],
    ];
    for (const [alias, ticker] of cases) {
      expect(getInstrumentByAlias(alias)?.destination.params?.symbol).toBe(ticker);
    }
  });

  it('registers every definition in INDEX_DEFS', () => {
    for (const def of INDEX_DEFS) {
      const hit = getInstrumentByAlias(def.name);
      expect(hit?.destination.params?.symbol).toBe(def.symbol);
    }
  });
});

// ── PSX historical parsing ───────────────────────────────────────────────────
// PSX is the only source for KSE-100 (Yahoo dropped it). The HTML table shape is
// the fragile part, so the parser is pinned here.

describe('parsePsxHistorical', () => {
  // Real response fragment (header row + one data row), trimmed.
  const HTML = `
    <table><thead><tr>
      <th>DATE</th><th>OPEN</th><th>HIGH</th><th>LOW</th><th>CLOSE</th><th>VOLUME</th>
    </tr></thead><tbody>
      <tr>
        <td>Sep 16, 2026</td><td>169,151.90</td><td>169,382.01</td>
        <td>167,849.70</td><td>168,021.80</td><td>127,596,823</td>
      </tr>
      <tr>
        <td>Sep 15, 2026</td><td>169,301.32</td><td>169,988.12</td>
        <td>169,189.30</td><td>169,392.33</td><td>140,866,614</td>
      </tr>
    </tbody></table>`;

  it('parses date, OHLC and volume in the correct field order', () => {
    const bars = parsePsxHistorical(HTML);
    expect(bars).toHaveLength(2);
    const [first] = bars;
    expect(first.date).toBe('2026-09-16');
    expect(first.open).toBe(169151.9);
    expect(first.high).toBe(169382.01);
    expect(first.low).toBe(167849.7);
    expect(first.close).toBe(168021.8);
    expect(first.volume).toBe(127596823);
  });

  it('ignores the header row and any row without a valid close', () => {
    const bars = parsePsxHistorical(`
      <tr><td>DATE</td><td>OPEN</td><td>HIGH</td><td>LOW</td><td>CLOSE</td><td>VOLUME</td></tr>
      <tr><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>
      <tr><td>Sep 16, 2026</td><td>1</td><td>2</td><td>0.5</td><td>1.5</td><td>100</td></tr>`);
    expect(bars).toHaveLength(1);
    expect(bars[0].close).toBe(1.5);
  });

  it('returns an empty array for a non-table response', () => {
    expect(parsePsxHistorical('<html><body>No data</body></html>')).toEqual([]);
  });
});

describe('psxTicker', () => {
  it('strips the caret the Yahoo-style ticker carries', () => {
    expect(psxTicker('^KSE100')).toBe('KSE100');
    expect(psxTicker('^KMI30')).toBe('KMI30');
    expect(psxTicker('kse30')).toBe('KSE30');
  });
});

// ── PSX latest quote (chart footer / live price) ─────────────────────────────

describe('parsePsxEod', () => {
  // Real shape: [epochSeconds, close, volume, open], newest first.
  const PAYLOAD = {
    status: 1,
    data: [
      [1789556400, 168021.8, 127596823, 169151.896],
      [1789470000, 169392.32, 140866614, 169301.3153],
    ],
  };

  it('reads the latest close and derives change vs the previous session', () => {
    const q = parsePsxEod(PAYLOAD, 'KSE100')!;
    expect(q).not.toBeNull();
    expect(q.price).toBe(168021.8);
    expect(q.previousClose).toBe(169392.32);
    expect(q.changePct).toBeCloseTo(-0.8092, 3);
    expect(q.volume).toBe(127596823);
    expect(q.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('reports 0% change when there is only one session', () => {
    const q = parsePsxEod({ data: [[1789556400, 100, 5, 99]] }, 'X')!;
    expect(q.changePct).toBe(0);
    expect(q.previousClose).toBe(100);
  });

  it('returns null for empty or malformed payloads', () => {
    expect(parsePsxEod({ data: [] }, 'X')).toBeNull();
    expect(parsePsxEod({}, 'X')).toBeNull();
    expect(parsePsxEod(null, 'X')).toBeNull();
    // A zero/negative close is not a usable quote.
    expect(parsePsxEod({ data: [[1, 0, 0, 0]] }, 'X')).toBeNull();
  });
});
