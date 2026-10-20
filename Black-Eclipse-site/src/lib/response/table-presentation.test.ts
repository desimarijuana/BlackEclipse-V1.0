import { describe, expect, it } from 'vitest';
import {
  formatNumericCell,
  isLossColumn,
  numericCellValue,
  resolveColumnAlign,
} from './table-presentation';

describe('numericCellValue', () => {
  it('reads raw numbers and formatted financial strings', () => {
    expect(numericCellValue(42)).toBe(42);
    expect(numericCellValue('$1,234.50')).toBe(1234.5);
    expect(numericCellValue('(2,500)')).toBe(-2500);
    expect(numericCellValue('-12%')).toBe(-12);
    expect(numericCellValue('1.2K')).toBe(1.2);
  });

  it('does not treat labels, empty cells or booleans as numbers', () => {
    expect(numericCellValue('AAPL')).toBeNull();
    expect(numericCellValue('UNAVAILABLE')).toBeNull();
    expect(numericCellValue(null)).toBeNull();
    expect(numericCellValue(true)).toBeNull();
    expect(numericCellValue(Number.NaN)).toBeNull();
  });
});

describe('formatNumericCell', () => {
  it('locale-formats raw numbers only', () => {
    expect(formatNumericCell(1234.5)).toBe(
      (1234.5).toLocaleString(undefined, { maximumFractionDigits: 4 }),
    );
    expect(formatNumericCell('$1,234.50')).toBeNull();
  });

  it('leaves non-finite values to the empty-state path', () => {
    expect(formatNumericCell(Number.POSITIVE_INFINITY)).toBeNull();
  });
});

describe('resolveColumnAlign', () => {
  const rows = [
    { asset: 'BTC', loss: -1200, mixed: 'n/a' },
    { asset: 'ETH', loss: '(300)', mixed: 4 },
  ];

  it('honours an explicit alignment', () => {
    expect(resolveColumnAlign({ align: 'center' }, rows, 'loss')).toBe('center');
  });

  it('right-aligns a numeric column and left-aligns text', () => {
    expect(resolveColumnAlign({}, rows, 'loss')).toBe('right');
    expect(resolveColumnAlign({}, rows, 'asset')).toBe('left');
  });

  it('does not right-align a mostly-text column', () => {
    expect(resolveColumnAlign({}, rows, 'mixed')).toBe('left');
  });

  it('is left when there are no populated cells', () => {
    expect(resolveColumnAlign({}, [{ a: null }], 'a')).toBe('left');
  });
});

describe('isLossColumn', () => {
  it('recognises loss and P&L labels', () => {
    expect(isLossColumn('Realised loss')).toBe(true);
    expect(isLossColumn('P&L')).toBe(true);
    expect(isLossColumn('Drawdown')).toBe(true);
    expect(isLossColumn('Weight')).toBe(false);
  });
});
