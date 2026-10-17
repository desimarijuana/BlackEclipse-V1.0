import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { parseResponsePayload } from '@/lib/response/contract';
import { ResponseView } from './response-view';

function render(raw: unknown): string {
  return renderToStaticMarkup(<ResponseView response={parseResponsePayload(raw)} />);
}

describe('layout primitive', () => {
  it('renders nested blocks in order', () => {
    const html = render({
      blocks: [
        {
          type: 'layout',
          layout: 'row',
          blocks: [
            { type: 'markdown', markdown: 'LEFT' },
            { type: 'markdown', markdown: 'RIGHT' },
          ],
        },
      ],
    });
    expect(html).toContain('LEFT');
    expect(html).toContain('RIGHT');
    expect(html.indexOf('LEFT')).toBeLessThan(html.indexOf('RIGHT'));
  });

  it('applies the grid column token', () => {
    const html = render({
      blocks: [{ type: 'layout', layout: 'grid', columns: 2, blocks: [{ type: 'markdown', markdown: 'X' }] }],
    });
    expect(html).toContain('grid-cols-1 sm:grid-cols-2');
  });

  it('applies a tone surface from the token vocabulary', () => {
    const html = render({
      blocks: [{ type: 'layout', layout: 'column', tone: 'warning', blocks: [{ type: 'markdown', markdown: 'W' }] }],
    });
    expect(html).toContain('border-amber-500/25');
  });
});

describe('divider primitive', () => {
  it('renders a labelled separator', () => {
    const html = render({ blocks: [{ type: 'divider', label: 'Section' }] });
    expect(html).toContain('role="separator"');
    expect(html).toContain('Section');
  });

  it('renders an unlabelled rule', () => {
    const html = render({ blocks: [{ type: 'divider' }] });
    expect(html).toContain('<hr');
  });
});
