import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { EdgeReportView } from './edge-report-view';
import type { EdgeReport } from '@/lib/backtest/backtest-client';

const report: EdgeReport = {
  status: 'OK',
  experimentId: 'exp_1',
  verdict: {
    available: true,
    grade: 'B',
    score: 72,
    components: {
      risk: { score: 70, basis: 'drawdown + tail', detail: 'max drawdown 12%' },
    },
    flags: [{ code: 'OVERFIT_TELL', severity: 'warning', message: 'few trades' }],
    flagCounts: { critical: 0, warning: 1, info: 0 },
    summary: 'Decent evidence with one caution.',
  },
  markdown: '# Report\n\nSome numbers.',
  warnings: [],
  charts: [],
};

describe('EdgeReportView', () => {
  it('renders the grade, the axes, the flags and the document', () => {
    const html = renderToStaticMarkup(<EdgeReportView report={report} />);
    expect(html).toContain('B');
    expect(html).toContain('risk');
    expect(html).toContain('OVERFIT_TELL');
    expect(html).toContain('Flags to clear');
    expect(html).toContain('Full report document');
    expect(html).toContain('not investment advice');
  });

  it('renders a chart error instead of pretending a figure exists', () => {
    const html = renderToStaticMarkup(
      <EdgeReportView
        report={{
          ...report,
          charts: [
            {
              name: 'equity',
              title: 'Equity',
              artifactId: null,
              error: { code: 'CHART_UNAVAILABLE', reason: 'matplotlib missing' },
            },
          ],
        }}
      />,
    );
    expect(html).toContain('CHART_UNAVAILABLE');
    expect(html).toContain('matplotlib missing');
  });
});
