import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

import { ResearchEvidencePanel } from './research-evidence-panel';
import type { ResearchCitation } from '@/lib/harness/types';

// The provenance block stays COLLAPSED by default so it reads as attached
// metadata. The always-visible header carries the status summary; opening it
// reveals Sources first.

function run(citations: ResearchCitation[], limitations: string[] = []) {
  return {
    status: 'partial',
    metadata: {
      taskType: 'research',
      status: 'partial',
      citations,
      assumptions: [],
      estimates: [],
      interpretations: [],
      limitations,
      missingEvidence: [],
      conflicts: [],
      calculations: [],
    },
  };
}

describe('ResearchEvidencePanel', () => {
  it('stays collapsed by default even when the run cited sources', () => {
    const html = renderToStaticMarkup(
      <ResearchEvidencePanel
        research={run([{
          evidenceId: 'e1',
          kind: 'filing',
          title: 'Annual report',
          sourceType: 'primary',
        }])}
      />,
    );
    // The header summary is visible; the source list is not rendered until open.
    expect(html).toContain('1 source');
    expect(html).not.toContain('Annual report');
  });

  it('keeps the limitation count visible in the collapsed header', () => {
    const html = renderToStaticMarkup(
      <ResearchEvidencePanel research={run([], ['One period was unknown.'])} />,
    );
    expect(html).toContain('1 limitation');
    expect(html).not.toContain('Annual report');
  });
});
