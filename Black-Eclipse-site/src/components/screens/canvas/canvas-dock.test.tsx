import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

import { CanvasHeaderCard } from './canvas-dock';
import type { CanvasContent, CanvasContentKind } from '@/lib/canvas/content';

// The dock opens from "Open in Canvas". Its header is ONE surface card: a
// rounded icon tile + the surface label, not a thin toolbar with a kind badge.

function view(kind: CanvasContentKind): CanvasContent {
  return {
    id: 'view-1',
    kind,
    title: 'Eclipse response',
    markdown: '# Hello',
    code: kind === 'code' ? { text: 'const x = 1;' } : undefined,
    editable: false,
  };
}

function render(kind: CanvasContentKind): string {
  return renderToStaticMarkup(<CanvasHeaderCard content={view(kind)} onClose={() => {}} />);
}

describe('Canvas dock header', () => {
  it('labels a prose answer as Writing', () => {
    const html = render('markdown');
    expect(html).toContain('Writing');
    expect(html).not.toContain('Document');
  });

  it('uses the card shape (rounded surface + icon tile)', () => {
    const html = render('markdown');
    expect(html).toContain('rounded-2xl');
    expect(html).toContain('rounded-xl');
    expect(html).toContain('h-11');
    expect(html).toContain('w-11');
  });

  it('labels code and report surfaces honestly', () => {
    expect(render('code')).toContain('Code');
    expect(render('report')).toContain('Report');
  });

  it('renders the empty Canvas state without a surface label', () => {
    const html = renderToStaticMarkup(<CanvasHeaderCard content={null} onClose={() => {}} />);
    expect(html).toContain('Canvas');
    expect(html).not.toContain('Save to edit');
  });
});
