import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

import { CodeVerificationPanel } from './code-verification-panel';

// The card exists to show EVIDENCE. Two regressions this file locks:
//   1. a "0 check(s)" header claims a check that never happened;
//   2. a collapsed failure hides the one thing the user needs to see.

function render(verification: unknown): string {
  return renderToStaticMarkup(<CodeVerificationPanel verification={verification} />);
}

describe('CodeVerificationPanel evidence display', () => {
  it('never prints a check count when no check was recorded', () => {
    const html = render({
      runId: 'r1',
      records: [],
      truncated: false,
      repair: null,
      artifacts: [],
      reviews: [],
      claims: [{
        sentence: 'All checks pass.',
        kind: 'tests_pass',
        matchedClasses: [],
        supported: false,
        evidenceExecutionId: null,
        evidenceDigest: null,
      }],
    });
    expect(html).toContain('Proof it works');
    expect(html).not.toContain('0 check');
    // The evidence itself is visible, not hidden behind a second click.
    expect(html).toContain('All checks pass.');
  });

  it('opens on a failed check instead of hiding it', () => {
    const html = render({
      runId: 'r1',
      truncated: false,
      repair: null,
      claims: [],
      artifacts: [],
      reviews: [],
      records: [{
        commandExecutionId: 'c1',
        commandClass: 'unit_test',
        exitCode: 1,
        durationMs: 1200,
        outputDigest: 'abc123',
        argv: [],
        startedAt: '2026-01-01T00:00:00Z',
        workspaceId: null,
      }],
    });
    expect(html).toContain('Did not pass');
  });
});
