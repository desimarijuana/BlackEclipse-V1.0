import { describe, it, expect } from 'vitest';
import { encodeFigure, decodeFigure, figureUrl, appUrl } from './share';

describe('figure deep-link', () => {
  it('round-trips a model3d block through the hash', () => {
    const block = { type: 'model3d', title: 'Gear drive', parts: [{ id: 'a', kind: 'box', label: 'base' }] };
    const decoded = decodeFigure(encodeFigure(block));
    expect(decoded?.blocks[0]?.type).toBe('model3d');
  });

  it('encodes a URL-safe hash (no +, / or =)', () => {
    const hash = encodeFigure({ type: 'model3d', parts: [{ id: 'a', kind: 'box' }] });
    expect(hash).not.toMatch(/[+/=]/);
  });

  it('builds an absolute /figure URL and returns null for junk', () => {
    expect(figureUrl({ type: 'model3d', parts: [] }, 'https://blackeclipse/')).toContain('https://blackeclipse/figure#');
    expect(decodeFigure('%%%%not-base64%%%%')).toBeNull();
    expect(decodeFigure('')).toBeNull();
  });
});

describe('interactive app deep-link', () => {
  it('round-trips an interactive block through /app-view', () => {
    const block = { type: 'interactive', title: 'Bike', html: '<p>ok</p>' };
    const decoded = decodeFigure(encodeFigure(block));
    expect(decoded?.blocks[0]?.type).toBe('interactive');
    expect(appUrl(block, 'https://blackeclipse/')).toContain('https://blackeclipse/app-view#');
  });
});
