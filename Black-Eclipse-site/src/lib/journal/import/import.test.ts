import { describe, it, expect } from 'vitest';
import { parseImportText, detectFormat, buildTemplate, IMPORT_FORMATS } from './index';
import { parseCsv } from './csv';

describe('detectFormat', () => {
  it('detects MT4', () => {
    expect(detectFormat(['Ticket', 'Open Time', 'Type', 'Size', 'Item', 'Price', 'S/L', 'T/P', 'Close Time', 'Price', 'Commission', 'Taxes', 'Swap', 'Profit'])).toBe('mt4');
  });
  it('detects MT5', () => {
    expect(detectFormat(['Ticket', 'Time', 'Type', 'Volume', 'Symbol', 'Price', 'S/L', 'T/P', 'Time', 'Price', 'Commission', 'Swap', 'Profit'])).toBe('mt5');
  });
  it('detects Binance', () => {
    expect(detectFormat(['Symbol', 'Side', 'Price', 'Qty', 'Realized PnL', 'Time'])).toBe('binance');
  });
  it('detects Coinbase', () => {
    expect(detectFormat(['trade_id', 'product_id', 'side', 'size', 'price', 'created_at'])).toBe('coinbase');
  });
  it('detects generic', () => {
    expect(detectFormat(['symbol', 'direction', 'entry', 'exit'])).toBe('generic');
  });
});

describe('parseImportText', () => {
  it('parses generic format', () => {
    const text = 'symbol,direction,entry,exit,stopLoss,takeProfit,quantity,entryTime,exitTime\nXAUUSD,LONG,2650.5,2662.0,2648.0,2680.0,1,2026-09-01 09:30,2026-09-01 10:00';
    const { rows, format } = parseImportText(text);
    expect(format).toBe('generic');
    expect(rows.length).toBe(1);
    expect(rows[0].symbol).toBe('XAUUSD');
    expect(rows[0].direction).toBe('LONG');
    expect(rows[0].entry).toBe(2650.5);
  });

  it('parses MT4 format', () => {
    const text = 'Ticket,Open Time,Type,Size,Item,Price,S/L,T/P,Close Time,Price,Commission,Taxes,Swap,Profit\n123456,2026.09.01 09:30,buy,1.00,xauusd,2650.50,2648.00,2680.00,2026.09.01 10:00,2662.00,0.00,0.00,0.00,11.50';
    const { rows, format } = parseImportText(text);
    expect(format).toBe('mt4');
    expect(rows.length).toBe(1);
    expect(rows[0].symbol).toBe('XAUUSD');
    expect(rows[0].direction).toBe('LONG');
    expect(rows[0].entry).toBe(2650.5);
    expect(rows[0].exit).toBe(2662);
  });

  it('parses Binance format', () => {
    const text = 'Symbol,Side,Price,Qty,Realized PnL,Time\nBTCUSDT,BUY,64000.0,0.1,120.5,2026-09-01 09:30:00';
    const { rows, format } = parseImportText(text);
    expect(format).toBe('binance');
    expect(rows.length).toBe(1);
    expect(rows[0].symbol).toBe('BTCUSDT');
    expect(rows[0].direction).toBe('LONG');
  });

  it('skips invalid rows', () => {
    const text = 'symbol,direction,entry,exit,entryTime,exitTime\nXAUUSD,LONG,2650.5,2662.0,2026-09-01 09:30,2026-09-01 10:00\nBAD,SHORT,100,,2026-09-01 09:30,2026-09-01 10:00';
    const { rows, skipped } = parseImportText(text);
    expect(rows.length).toBe(1);
    expect(skipped).toBe(1);
  });
});

describe('buildTemplate', () => {
  it('builds a template for each format', () => {
    for (const f of IMPORT_FORMATS) {
      const tpl = buildTemplate(f.id);
      expect(tpl).toContain(f.templateHeader);
      expect(tpl).toContain(f.templateRow);
    }
  });
});

describe('parseCsv', () => {
  it('handles quoted fields', () => {
    const rows = parseCsv('a,b\n"hello, world",2');
    expect(rows[0].a).toBe('hello, world');
    expect(rows[0].b).toBe('2');
  });
});
