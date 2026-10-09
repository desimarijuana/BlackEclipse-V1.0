import { describe, it, expect, afterAll } from 'vitest';
import { prisma } from '@/lib/db';
import {
  createThesis,
  getThesis,
  updateThesis,
  addEvidence,
  listRevisions,
  deleteThesis,
} from './store';

// Real-DB integration test for the thesis store (no mocks). It self-skips when
// the Thesis tables are absent (e.g. a fresh checkout whose committed jdds.db
// seed predates them and has not yet run `prisma db push`), so it never breaks
// the default suite. It uses a unique symbol and deletes everything it creates.
let ready = false;
try {
  await prisma.thesis.count();
  ready = true;
} catch {
  ready = false;
}

const SYM = `ZZTEST${Date.now().toString(36).toUpperCase()}`;

describe.skipIf(!ready)('thesis store (integration)', () => {
  afterAll(async () => {
    await prisma.thesis.deleteMany({ where: { symbol: SYM } });
  });

  it('creates a v1 thesis and records an immutable origin revision', async () => {
    const t = await createThesis({
      symbol: SYM,
      marketId: 'US',
      title: 'Integration thesis',
      hypothesis: 'ORIGINAL hypothesis text',
      assumptions: ['margin expansion'],
    });
    expect(t.version).toBe(1);
    const revs = await listRevisions(t.id);
    expect(revs).toHaveLength(1);
    expect(revs[0].snapshot.hypothesis).toBe('ORIGINAL hypothesis text');
    await deleteThesis(t.id);
  });

  it('appends a revision on update and preserves the prior hypothesis', async () => {
    const t = await createThesis({
      symbol: SYM, marketId: 'US', title: 'T', hypothesis: 'V1 hypothesis',
    });
    const updated = await updateThesis(t.id, { hypothesis: 'V2 changed', note: 'revised' });
    expect(updated!.version).toBe(2);
    expect(updated!.hypothesis).toBe('V2 changed');
    const revs = await listRevisions(t.id);
    expect(revs).toHaveLength(2);
    // The revision with version 1 still holds the ORIGINAL text.
    const v1 = revs.find((r) => r.version === 1)!;
    expect(v1.snapshot.hypothesis).toBe('V1 hypothesis');
    await deleteThesis(t.id);
  });

  it('records evidence and reports it back', async () => {
    const t = await createThesis({
      symbol: SYM, marketId: 'US', title: 'T', hypothesis: 'h', assumptions: ['margin expansion'],
    });
    const added = await addEvidence(t.id, { stance: 'supporting', summary: 'margin expansion confirmed' });
    expect(added!.stance).toBe('supporting');
    const full = await getThesis(t.id);
    expect(full!.evidence).toHaveLength(1);
    await deleteThesis(t.id);
  });
});
