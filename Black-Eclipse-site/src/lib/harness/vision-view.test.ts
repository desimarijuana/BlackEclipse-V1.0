import { describe, expect, it } from 'vitest';
import { coerceVisionRun, primaryVisionResult } from './vision-view';

describe('vision-view', () => {
  it('returns null for an absent or empty blob', () => {
    expect(coerceVisionRun(null)).toBeNull();
    expect(coerceVisionRun(undefined)).toBeNull();
    expect(coerceVisionRun({})).toBeNull();
    expect(coerceVisionRun({ status: 'collected', results: [], failures: [] })).toBeNull();
  });

  it('coerces a collected run blob with a result', () => {
    const run = coerceVisionRun({
      type: 'vision',
      status: 'collected',
      count: 1,
      results: [
        {
          ok: true,
          mode: 'analyze',
          description: 'A grey rectangle',
          assetId: 'img_abc',
          provider: 'openai',
          model: 'gpt-4o',
          backend: 'native',
          confidence: 0.9,
          observations: [{ text: 'grey area', method: 'model', confidence: 0.9, region: { x: 0, y: 0, width: 60, height: 40 } }],
          text: [{ text: 'HELLO', confidence: 0.8, bounds: { x: 1, y: 2, width: 10, height: 5 } }],
        },
      ],
    });
    expect(run).not.toBeNull();
    expect(run?.count).toBe(1);
    const primary = primaryVisionResult(run);
    expect(primary?.assetId).toBe('img_abc');
    expect(primary?.observations?.[0].text).toBe('grey area');
    expect(primary?.observations?.[0].region?.width).toBe(60);
    expect(primary?.text?.[0].bounds?.x).toBe(1);
  });

  it('keeps failures and yields a null primary when no result succeeded', () => {
    const run = coerceVisionRun({
      status: 'collected',
      count: 0,
      results: [],
      failures: [{ mode: 'analyze', error: { errorClass: 'NO_VISION_MODEL', message: 'no model' } }],
    });
    expect(run).not.toBeNull();
    expect(primaryVisionResult(run)).toBeNull();
    expect(run?.failures?.[0].error?.errorClass).toBe('NO_VISION_MODEL');
  });

  it('ignores malformed observation shapes rather than fabricating', () => {
    const run = coerceVisionRun({
      status: 'collected',
      count: 1,
      results: [{ ok: true, observations: [{ nope: true }, { text: 'ok' }] }],
    });
    expect(run?.results[0].observations?.length).toBe(1);
    expect(run?.results[0].observations?.[0].text).toBe('ok');
  });
});
