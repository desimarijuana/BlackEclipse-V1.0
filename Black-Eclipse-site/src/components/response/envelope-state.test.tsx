import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { parseResponsePayload } from '@/lib/response/contract';
import { ResponseView } from './response-view';

function render(raw: unknown): string {
  return renderToStaticMarkup(<ResponseView response={parseResponsePayload(raw)} />);
}

describe('envelope state → computed → figure binding', () => {
  it('renders inputs and a figure bound to a computed value (default state)', () => {
    const html = render({
      state: [{ id: 'qty', label: 'Quantity', value: 4, min: 0, max: 100, kind: 'number' }],
      computed: [{ id: 'sq', expression: 'qty * qty' }],
      blocks: [
        { type: 'inputs' },
        { type: 'metric_grid', metrics: [{ label: 'Squared', value: { $computed: 'sq' } }] },
      ],
    });
    expect(html).toContain('Quantity');
    // The computed figure shows the default-state result (4 * 4 = 16).
    expect(html).toContain('16');
    expect(html).not.toContain('$computed');
  });

  it('renders UNAVAILABLE when a computed id does not resolve', () => {
    const html = render({
      state: [{ id: 'qty', value: 4 }],
      computed: [],
      blocks: [{ type: 'metric_grid', metrics: [{ label: 'Missing', value: { $computed: 'nope' } }] }],
    });
    expect(html).toContain('UNAVAILABLE');
    expect(html).not.toContain('$computed');
  });
});
