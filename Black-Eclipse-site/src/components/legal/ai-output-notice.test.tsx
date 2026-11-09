// ── Point-of-use AI/risk notice ─────────────────────────────────────────────
// The notice must render the SHORT responsibility clause under an answer (not
// the whole paragraph, which causes banner blindness) and must always expose
// the full notice behind the expander. The composer form is the persistent
// one-liner. This renders the real component, so a refactor that hides the text
// is caught.

import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AiOutputNotice } from './ai-output-notice';
import {
  AI_COMPOSER_NOTICE,
  AI_OUTPUT_INLINE,
  AI_OUTPUT_LABEL,
  RISK_DISCLOSURE_FULL,
} from '@/lib/legal/disclosure';

describe('AiOutputNotice', () => {
  it('renders a short responsibility clause (and the full notice) under an answer', () => {
    const html = renderToStaticMarkup(<AiOutputNotice />);
    expect(html).toContain(AI_OUTPUT_LABEL);
    expect(html).toContain(AI_OUTPUT_INLINE);
    expect(html).toContain(RISK_DISCLOSURE_FULL);
    expect(html).toContain('role="note"');
    expect(html.indexOf(RISK_DISCLOSURE_FULL)).toBeGreaterThan(html.indexOf('Full notice'));
  });

  it('renders the persistent composer one-liner', () => {
    const html = renderToStaticMarkup(<AiOutputNotice variant="composer" />);
    expect(html).toContain(AI_OUTPUT_LABEL);
    expect(html).toContain(AI_COMPOSER_NOTICE);
  });
});
