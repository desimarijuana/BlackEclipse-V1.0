import { describe, expect, it } from 'vitest';
import { parseResponsePayload } from './contract';
import { buildFigureResolver, parseFigureRef, resolveFigureValue, resolveResponseFigures } from './refs';

describe('parseFigureRef', () => {
  it('parses namespace:id#/pointer', () => {
    expect(parseFigureRef('analysis:run#/outputs/sharpe')).toEqual({
      namespace: 'analysis',
      id: 'run',
      pointer: '#/outputs/sharpe',
    });
  });
  it('parses a reference with no pointer', () => {
    expect(parseFigureRef('jdds:AAPL')).toEqual({ namespace: 'jdds', id: 'AAPL', pointer: '' });
  });
  it('rejects an unknown namespace', () => {
    expect(parseFigureRef('evil:x#/y')).toBeNull();
  });
  it('rejects a missing namespace separator or empty id', () => {
    expect(parseFigureRef('analysis')).toBeNull();
    expect(parseFigureRef('analysis:')).toBeNull();
  });
});

describe('resolveFigureValue', () => {
  const resolver = (ns: string, id: string, pointer: string) =>
    ns === 'analysis' && id === 'run' && pointer === '#/outputs/sharpe'
      ? { value: 1.42, provenance: { source: 'Worked out by Eclipse' } }
      : null;

  it('returns null for a non-reference value', () => {
    expect(resolveFigureValue(3, resolver)).toBeNull();
    expect(resolveFigureValue('text', resolver)).toBeNull();
  });
  it('resolves a hit', () => {
    expect(resolveFigureValue({ $ref: 'analysis:run#/outputs/sharpe' }, resolver)).toEqual({
      value: 1.42,
      provenance: { source: 'Worked out by Eclipse' },
    });
  });
  it('returns null for a miss or with no resolver', () => {
    expect(resolveFigureValue({ $ref: 'analysis:run#/outputs/nope' }, resolver)).toBeNull();
    expect(resolveFigureValue({ $ref: 'analysis:run#/outputs/sharpe' }, null)).toBeNull();
  });
});

describe('resolveResponseFigures', () => {
  const parsed = parseResponsePayload({
    blocks: [
      { type: 'metric_grid', metrics: [{ label: 'Sharpe', value: { $ref: 'analysis:run#/outputs/sharpe' } }] },
    ],
  });

  it('replaces a resolved reference with the source value + provenance', () => {
    const resolver = () => ({ value: 1.42, provenance: { source: 'Worked out by Eclipse' } });
    const out = resolveResponseFigures(parsed, resolver);
    const block = out.blocks[0];
    if (block.type !== 'metric_grid') throw new Error('expected metric_grid');
    expect(block.metrics[0].value).toBe(1.42);
    expect(block.metrics[0].provenance?.source).toBe('Worked out by Eclipse');
  });

  it('renders an unresolvable reference as UNAVAILABLE — never the raw reference', () => {
    const out = resolveResponseFigures(parsed, null);
    const block = out.blocks[0];
    if (block.type !== 'metric_grid') throw new Error('expected metric_grid');
    expect(block.metrics[0].unavailable).toBe(true);
    expect(block.metrics[0].value).toBe(0);
    expect(JSON.stringify(block.metrics[0])).not.toContain('$ref');
  });

  it('resolves a reference nested inside a container block', () => {
    const nested = parseResponsePayload({
      blocks: [
        {
          type: 'tabs',
          tabs: [
            { label: 'A', blocks: [{ type: 'stat_hero', stats: [{ label: 'X', value: { $ref: 'analysis:run#/outputs/sharpe' } }] }] },
          ],
        },
      ],
    });
    const resolver = () => ({ value: 2.5 });
    const out = resolveResponseFigures(nested, resolver);
    const tabBlock = out.blocks[0];
    if (tabBlock.type !== 'tabs') throw new Error('expected tabs');
    const inner = tabBlock.tabs[0].blocks[0] as { type: string; stats: { value: unknown }[] };
    expect(inner.type).toBe('stat_hero');
    expect(inner.stats[0].value).toBe(2.5);
  });

  it('resolves a `$computed` binding from the computed map', () => {
    const bound = parseResponsePayload({
      blocks: [{ type: 'metric_grid', metrics: [{ label: 'Sq', value: { $computed: 'sq' } }] }],
    });
    const out = resolveResponseFigures(bound, null, { sq: 16 });
    const block = out.blocks[0];
    if (block.type !== 'metric_grid') throw new Error('expected metric_grid');
    expect(block.metrics[0].value).toBe(16);
    expect(block.metrics[0].provenance?.source).toBe('Computed in-chat');
  });

  it('renders an unresolvable `$computed` as UNAVAILABLE — never the raw binding', () => {
    const bound = parseResponsePayload({
      blocks: [{ type: 'metric_grid', metrics: [{ label: 'Sq', value: { $computed: 'missing' } }] }],
    });
    const out = resolveResponseFigures(bound, null, {});
    const block = out.blocks[0];
    if (block.type !== 'metric_grid') throw new Error('expected metric_grid');
    expect(block.metrics[0].unavailable).toBe(true);
    expect(JSON.stringify(block.metrics[0])).not.toContain('$computed');
  });

  it('leaves a non-reference figure untouched', () => {
    const plain = parseResponsePayload({ blocks: [{ type: 'metric_grid', metrics: [{ label: 'N', value: 5 }] }] });
    const out = resolveResponseFigures(plain, null);
    const block = out.blocks[0];
    if (block.type !== 'metric_grid') throw new Error('expected metric_grid');
    expect(block.metrics[0].value).toBe(5);
    expect(block.metrics[0].unavailable).toBeUndefined();
  });
});

describe('buildFigureResolver', () => {
  const sources = {
    analysis: { outputs: { sharpe: 1.42, note: 'n/a' }, provenance: { label: 'Worked out by Eclipse', detail: 'Sharpe ratio' } },
  };

  it('resolves an analysis output by pointer', () => {
    const resolver = buildFigureResolver(sources);
    expect(resolver?.('analysis', 'run', '#/outputs/sharpe')).toEqual({
      value: 1.42,
      provenance: { source: 'Worked out by Eclipse', method: 'Sharpe ratio' },
    });
  });

  it('returns null for a non-numeric output, an unknown key, or another namespace', () => {
    const resolver = buildFigureResolver(sources);
    expect(resolver?.('analysis', 'run', '#/outputs/note')).toBeNull();
    expect(resolver?.('analysis', 'run', '#/outputs/missing')).toBeNull();
    expect(resolver?.('jdds', 'AAPL', '#/close')).toBeNull();
  });

  it('returns null when the turn has no analysis blob', () => {
    expect(buildFigureResolver({})).toBeNull();
  });
});
