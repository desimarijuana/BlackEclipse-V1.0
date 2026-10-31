import { describe, expect, it } from 'vitest';
import { humanMethodLine } from './computed-result-panel';

// The computed-result card names a result Eclipse worked out. Its second line is
// a METHOD ("Q1 vs Q2, same basis"), never a debug dump of the runtime's object.
describe('humanMethodLine', () => {
  it('keeps a real method line', () => {
    expect(humanMethodLine('Revenue CAGR, FY2022–FY2025, same basis')).toBe(
      'Revenue CAGR, FY2022–FY2025, same basis',
    );
  });

  it('drops a Python type dump', () => {
    expect(humanMethodLine("type <class 'dict'> · keys [\"asOf\",\"assetClass\"]")).toBeNull();
    expect(humanMethodLine("<class 'list'>")).toBeNull();
  });

  it('drops a bare serialized object', () => {
    expect(humanMethodLine('{"asOf": "2025-01-01", "assetClass": "equity"}')).toBeNull();
  });

  it('treats empty and non-string detail as no line', () => {
    expect(humanMethodLine('')).toBeNull();
    expect(humanMethodLine('   ')).toBeNull();
    expect(humanMethodLine(null)).toBeNull();
    expect(humanMethodLine(undefined)).toBeNull();
  });
});
