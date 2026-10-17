import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ResponseFence } from './response-fence';

describe('ResponseFence while streaming', () => {
  it('renders a closed block immediately and keeps the composing note for the open tail', () => {
    const html = renderToStaticMarkup(
      <ResponseFence
        streaming
        source={'{"blocks":[{"type":"markdown","markdown":"First early paragraph."},{"type":"card'}
      />,
    );
    expect(html).toContain('First early paragraph.');
    expect(html).toContain('Composing structured response');
  });

  it('shows only the placeholder when no block has closed', () => {
    const html = renderToStaticMarkup(<ResponseFence streaming source={'{"blocks":[{"type":"mark'} />);
    expect(html).toContain('Composing structured response');
    expect(html).not.toContain('First early paragraph.');
  });

  it('renders the full answer once the envelope is complete', () => {
    const html = renderToStaticMarkup(
      <ResponseFence streaming source={'{"blocks":[{"type":"markdown","markdown":"Complete."}]}'} />,
    );
    expect(html).toContain('Complete.');
  });
});
