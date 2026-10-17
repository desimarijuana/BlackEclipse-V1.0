import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { parseResponsePayload } from '@/lib/response/contract';
import { buildFigureResolver } from '@/lib/response/refs';
import { ResponseRuntimeProvider } from './figure-context';
import { ResponseView } from './response-view';

const response = parseResponsePayload({
  blocks: [
    {
      type: 'metric_grid',
      title: 'Risk',
      metrics: [{ label: 'Sharpe', value: { $ref: 'analysis:run#/outputs/sharpe' } }],
    },
  ],
});

const sources = {
  analysis: { outputs: { sharpe: 1.42 }, provenance: { label: 'Worked out by Eclipse', detail: 'Sharpe ratio' } },
};

describe('figure references render through ResponseView', () => {
  it('shows the resolved source value with a provenance chip', () => {
    const html = renderToStaticMarkup(
      <ResponseRuntimeProvider value={{ figureResolver: buildFigureResolver(sources) }}>
        <ResponseView response={response} />
      </ResponseRuntimeProvider>,
    );
    expect(html).toContain('1.42');
    expect(html).toContain('Worked out by Eclipse');
  });

  it('shows UNAVAILABLE (never the raw reference) when it cannot resolve', () => {
    const html = renderToStaticMarkup(
      <ResponseRuntimeProvider value={{ figureResolver: null }}>
        <ResponseView response={response} />
      </ResponseRuntimeProvider>,
    );
    expect(html).toContain('UNAVAILABLE');
    expect(html).not.toContain('$ref');
    expect(html).not.toContain('analysis:run');
  });
});
