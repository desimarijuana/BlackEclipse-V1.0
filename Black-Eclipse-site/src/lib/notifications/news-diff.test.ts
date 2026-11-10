import { describe, expect, it } from 'vitest';
import {
  EVENT_NOTIFY_HORIZON_MINUTES,
  buildNewsNotifications,
  diffNewsNotifications,
} from './news-diff';

const alert = {
  id: 'a1',
  headline: 'Fed hikes rates by 50bp',
  alertLevel: 'critical',
  importance: 92,
  source: 'Reuters',
  ticker: null,
};

const event = {
  id: 'e1',
  title: 'US CPI',
  country: 'US',
  minutesUntil: 30,
  forecast: '3.1%',
  previous: '3.2%',
};

describe('buildNewsNotifications', () => {
  it('maps a high-alert story to a namespaced ledger entry', () => {
    const [n] = buildNewsNotifications([alert], []);
    expect(n.id).toBe('news:a1');
    expect(n.title).toBe('Fed hikes rates by 50bp');
    expect(n.body).toContain('CRITICAL');
    expect(n.body).toContain('Reuters');
    expect(n.body).toContain('score 92');
  });

  it('includes imminent releases but not distant ones', () => {
    const near = buildNewsNotifications([], [event]);
    expect(near[0].id).toBe('news-event:e1');
    expect(near[0].body).toContain('in 30m');

    const far = buildNewsNotifications([], [
      { ...event, minutesUntil: EVENT_NOTIFY_HORIZON_MINUTES + 1 },
    ]);
    expect(far).toEqual([]);
  });

  it('skips malformed rows instead of inventing entries', () => {
    expect(buildNewsNotifications([{ id: '', headline: 'x' }], [{ id: 'e', title: '' }])).toEqual([]);
  });

  it('carries the original story link, but only absolute http(s) ones', () => {
    const [linked] = buildNewsNotifications(
      [{ ...alert, url: 'https://www.reuters.com/markets/a' }],
      [],
    );
    expect(linked.url).toBe('https://www.reuters.com/markets/a');

    const [relative] = buildNewsNotifications([{ ...alert, url: '/news' }], []);
    expect(relative.url).toBeUndefined();
  });
});

describe('diffNewsNotifications', () => {
  it('seeds the seen set without replaying the current set', () => {
    const current = buildNewsNotifications([alert], [event]);
    const seed = diffNewsNotifications(current, new Set(), { seed: true });
    expect(seed.notifications).toEqual([]);
    // The seeded ids are remembered, so they are not fresh next poll.
    const again = diffNewsNotifications(current, seed.next, { seed: false });
    expect(again.notifications).toEqual([]);
  });

  it('returns only unseen entries after the seed', () => {
    const current = buildNewsNotifications([alert], []);
    const diff = diffNewsNotifications(current, new Set(['news:a1']), { seed: false });
    expect(diff.notifications).toEqual([]);

    const next = buildNewsNotifications(
      [{ ...alert, id: 'a2', headline: 'Breaking: OPEC cuts output' }],
      [],
    );
    const fresh = diffNewsNotifications(next, new Set(['news:a1']), { seed: false });
    expect(fresh.notifications.map((n) => n.id)).toEqual(['news:a2']);
  });
});
