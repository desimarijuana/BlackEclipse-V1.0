// ── Point-of-use AI/risk notice ─────────────────────────────────────────────
// The notice must ALWAYS render the short form (not dismissible) and must
// expose the full notice for the user who wants the specifics. This renders
// the real component, so a refactor that hides the text is caught.

import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AiOutputNotice } from './ai-output-notice';
import { AI_COMPOSER_NOTICE, AI_OUTPUT_LABEL } from '@/lib/legal/disclosure';

describe('AiOutputNotice', () => {
  it('does not repeat the notice under every settled answer', () => {
    const html = renderToStaticMarkup(<AiOutputNotice />);
    expect(html).toBe('');
  });

  it('renders the persistent composer one-liner', () => {
    const html = renderToStaticMarkup(<AiOutputNotice variant="composer" />);
    expect(html).toContain(AI_OUTPUT_LABEL);
    expect(html).toContain(AI_COMPOSER_NOTICE);
  });
});
