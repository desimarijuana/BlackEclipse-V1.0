// ─── ArtifactView tests (Phase 15/18) ───────────────────────────────────────
// The vitest environment is `node` (no DOM), so — like the video/response
// panels — the component is rendered with `react-dom/server`. What matters
// here is the LINK contract: the bytes come from the Artifact Center route
// (derived server-side by id), an image renders inline, and NO link renders
// when the catalog has no entry (a broken link would pretend retrievability).

import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

import { ArtifactView, entryFor, indexArtifacts } from './artifact-view';
import type { Artifact } from '@/lib/harness/clients/artifacts-browser';
import type { ComputedArtifact } from '@/lib/harness/analysis-types';

const SHA = 'a'.repeat(64);

const artifact: ComputedArtifact = {
  name: 'drawdown.png',
  path: '/tmp/drawdown.png',
  sha256: SHA,
  bytes: 42,
  mediaType: 'image/png',
};

const record: Artifact = {
  id: 'art_1',
  name: 'drawdown.png',
  mimeType: 'image/png',
  checksum: SHA,
} as Artifact;

describe('ArtifactView', () => {
  it('indexes by id, checksum and name, and resolves a checksum match first', () => {
    const index = indexArtifacts([record]);
    expect(index['art_1']).toBe(record);
    expect(index[`sha:${SHA}`]).toBe(record);
    expect(index['name:drawdown.png']).toBe(record);
    expect(entryFor(index, artifact)).toBe(record);
    // A renamed file still resolves by its checksum.
    expect(entryFor(index, { ...artifact, name: 'renamed.png' })).toBe(record);
    // Nothing in the catalog ⇒ null (the fallback renders).
    expect(entryFor(index, { ...artifact, sha256: 'b'.repeat(64), name: 'other.png' })).toBeNull();
  });

  it('renders a produced image inline through the Artifact Center route', () => {
    const html = renderToStaticMarkup(<ArtifactView artifact={artifact} entry={record} />);
    expect(html).toContain('src="/api/artifacts/art_1/download"');
    expect(html).toContain('drawdown.png');
    expect(html).toContain('<figure');
  });

  it('offers a download for a non-image artifact', () => {
    const csv = { ...artifact, name: 'report.csv', mediaType: 'text/csv' };
    const csvRecord = { ...record, id: 'art_2', name: 'report.csv', mimeType: 'text/csv' } as Artifact;
    const html = renderToStaticMarkup(<ArtifactView artifact={csv} entry={csvRecord} />);
    expect(html).toContain('href="/api/artifacts/art_2/download"');
    expect(html).toContain('Download');
    expect(html).not.toContain('<img');
  });

  it('shows an honest fallback with NO link when the catalog has no entry', () => {
    const html = renderToStaticMarkup(<ArtifactView artifact={artifact} entry={null} />);
    expect(html).toContain('drawdown.png');
    expect(html).toContain(SHA.slice(0, 12));
    expect(html).not.toContain('/api/artifacts');
    expect(html).not.toContain('<img');
  });
});
