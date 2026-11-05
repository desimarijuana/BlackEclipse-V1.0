import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ComputedResultPanel, humanMethodLine } from './computed-result-panel';

function render(result: unknown): string {
  return renderToStaticMarkup(createElement(ComputedResultPanel, { result }));
}

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

describe('ComputedResultPanel empty states', () => {
  const provenance = { kind: 'computed', label: 'Worked out by Eclipse', detail: 'Sharpe' };

  it('renders nothing when the number has no provenance record', () => {
    const html = render({
      status: 'ok',
      provenance: null,
      outputs: { sharpe: 1.42 },
      artifacts: [],
      figure: null,
    });
    expect(html).toBe('');
  });

  it('renders nothing when there is no content to show', () => {
    const html = render({
      status: 'ok',
      provenance,
      outputs: {},
      artifacts: [],
      figure: null,
    });
    expect(html).toBe('');
  });

  it('still renders a computed result that has data', () => {
    const html = render({
      status: 'ok',
      provenance,
      outputs: { sharpe: 1.42 },
      artifacts: [],
      figure: null,
    });
    expect(html).toContain('Worked out by Eclipse');
    expect(html).toContain('1.42');
  });
});
