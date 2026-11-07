import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import VisualEditor from './visual-editor';

const ENVELOPE = JSON.stringify({
  schemaVersion: '1.0',
  title: 'Quarterly Review',
  blocks: [
    { type: 'callout', tone: 'info', title: 'Two bets', markdown: 'Body' },
    { type: 'markdown', markdown: '## Detail\n\nText.' },
  ],
});

describe('Canvas visual editor', () => {
  it('shows one editable card per block instead of one raw JSON blob', () => {
    const html = renderToStaticMarkup(<VisualEditor content={ENVELOPE} defaultMode="blocks" onChange={() => {}} />);
    expect(html).toContain('Blocks');
    expect(html).toContain('Source JSON');
    expect(html).toContain('callout');
    expect(html).toContain('Two bets');
    expect(html).toContain('markdown');
    expect(html).toContain('Add block');
    // The block cards carry their own Edit action.
    expect(html).toContain('Edit');
  });

  it('keeps the structured preview and never silently drops invalid JSON', () => {
    const html = renderToStaticMarkup(<VisualEditor content={'{ not json'} onChange={() => {}} />);
    expect(html).toContain('Source JSON');
    expect(html).toContain('invalid JSON');
  });
});
