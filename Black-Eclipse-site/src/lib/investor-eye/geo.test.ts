import { describe, it, expect } from 'vitest';
import { aggregatePoints, zoomForCount } from './geo';

describe('aggregatePoints', () => {
  it('groups nearby points into one cluster and sums weight', () => {
    const clusters = aggregatePoints(
      [
        { lon: 10.0, lat: 20.0, weight: 1, severity: 'low' as const },
        { lon: 10.1, lat: 20.1, weight: 2, severity: 'high' as const },
      ],
      'low',
    );
    expect(clusters).toHaveLength(1);
    expect(clusters[0].count).toBe(2);
    expect(clusters[0].weight).toBe(3);
    expect(clusters[0].maxSeverity).toBe('high');
  });

  it('separates distant points', () => {
    const clusters = aggregatePoints(
      [
        { lon: 10, lat: 20 },
        { lon: 100, lat: -40 },
      ],
      'low',
    );
    expect(clusters).toHaveLength(2);
  });

  it('bounds representative members', () => {
    const points = Array.from({ length: 100 }, () => ({ lon: 5.0, lat: 5.0 }));
    const clusters = aggregatePoints(points, 'low', 10);
    expect(clusters[0].count).toBe(100);
    expect(clusters[0].members).toHaveLength(10);
  });

  it('defaults weight to 1 per point', () => {
    const clusters = aggregatePoints([{ lon: 0, lat: 0 }, { lon: 0, lat: 0 }], 'high');
    expect(clusters[0].weight).toBe(2);
  });
});

describe('zoomForCount', () => {
  it('coarsens as volume grows', () => {
    expect(zoomForCount(100)).toBe('high');
    expect(zoomForCount(1000)).toBe('medium');
    expect(zoomForCount(5000)).toBe('low');
  });
});
