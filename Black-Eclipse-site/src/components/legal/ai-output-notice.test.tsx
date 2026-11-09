// ── Point-of-use AI/risk notice ─────────────────────────────────────────────
// The notice must ALWAYS render the short form (not dismissible) and must
// expose the full notice for the user who wants the specifics. This renders
// the real component, so a refactor that hides the text is caught.

import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AiOutputNotice } from './ai-output-notice';
import {
  AI_COMPOSER_NOTICE,
  AI_OUTPUT_LABEL,
  AI_OUTPUT_SHORT,
  RISK_DISCLOSURE_FULL,
} from '@/lib/legal/disclosure';

describe('AiOutputNotice', () => {
  it('renders the label and compact sentence under an answer', () => {
    const html = renderToStaticMarkup(<AiOutputNotice />);
    expect(html).toContain(AI_OUTPUT_LABEL);
    expect(html).toContain(AI_OUTPUT_SHORT);
    expect(html).toContain(RISK_DISCLOSURE_FULL);
    expect(html).toContain('role="note"');
  });

  it('renders the persistent composer one-liner', () => {
    const html = renderToStaticMarkup(<AiOutputNotice variant="composer" />);
    expect(html).toContain(AI_OUTPUT_LABEL);
    expect(html).toContain(AI_COMPOSER_NOTICE);
  });
});
