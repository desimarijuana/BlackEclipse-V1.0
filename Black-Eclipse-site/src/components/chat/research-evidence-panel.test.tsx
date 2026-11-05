import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

import { ResearchEvidencePanel } from './research-evidence-panel';
import type { ResearchCitation } from '@/lib/harness/types';

// The sources are the useful part of the provenance block, so a run that cited
// them opens on the source list by default. A run with no citation stays quiet.

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
  it('opens on the sources when the run cited them', () => {
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
    expect(html).toContain('Sources');
    expect(html).toContain('Annual report');
  });

  it('stays collapsed when there is no source to show', () => {
    const html = renderToStaticMarkup(
      <ResearchEvidencePanel research={run([], ['One period was unknown.'])} />,
    );
    expect(html).toContain('1 limitation');
    expect(html).not.toContain('Annual report');
  });
});
