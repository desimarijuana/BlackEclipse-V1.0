import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ClockWidget, clockDisplay, normalizeClockConfig } from './clock-widget';
import type { WidgetPlacement } from '@/lib/workspace/types';

const NOW = new Date('2026-01-02T03:04:05Z');

function config(overrides: Record<string, unknown> = {}) {
  return normalizeClockConfig({ timezone: 'UTC', ...overrides });
}

describe('clockDisplay', () => {
  it('formats a 24-hour time in a pinned timezone', () => {
    const display = clockDisplay(NOW, config());
    expect(display.time).toBe('03:04:05');
    expect(display.date).toContain('2026');
    expect(display.zone).toBe('UTC');
    expect(display.error).toBeNull();
  });

  it('honours 12-hour and second/date toggles', () => {
    const twelve = clockDisplay(NOW, config({ format: '12h' }));
    expect(twelve.time.toLowerCase()).toContain('am');
    const compact = clockDisplay(NOW, config({ showSeconds: false, showDate: false }));
    expect(compact.time).toBe('03:04');
    expect(compact.date).toBe('');
  });

  it('fails honestly for an invalid timezone', () => {
    const display = clockDisplay(NOW, config({ timezone: 'Mars/Olympus' }));
    expect(display.time).toBe('--:--');
    expect(display.error).toContain('UNAVAILABLE');
  });
});

describe('ClockWidget', () => {
  it('renders the UNAVAILABLE state instead of a fabricated time', () => {
    const placement = {
      id: 'w1',
      widgetId: 'clock',
      height: null,
      config: { timezone: 'Mars/Olympus' },
    } as WidgetPlacement;
    const html = renderToStaticMarkup(<ClockWidget placement={placement} />);
    expect(html).toContain('UNAVAILABLE');
    expect(html).toContain('Mars/Olympus');
  });
});
