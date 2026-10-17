import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  reportResponseTelemetry,
  setResponseTelemetryReporter,
  type ResponseTelemetryRecord,
} from './telemetry';

afterEach(() => {
  setResponseTelemetryReporter(null);
});

describe('response telemetry seam', () => {
  it('forwards records to an installed reporter', () => {
    const seen: ResponseTelemetryRecord[] = [];
    setResponseTelemetryReporter((record) => seen.push(record));
    reportResponseTelemetry({ event: 'first_block', timeToFirstBlockMs: 120 });
    reportResponseTelemetry({ event: 'interaction', blockType: 'inputs' });
    expect(seen).toEqual([
      { event: 'first_block', timeToFirstBlockMs: 120 },
      { event: 'interaction', blockType: 'inputs' },
    ]);
  });

  it('is a no-op with no reporter and never throws', () => {
    const spy = vi.spyOn(console, 'debug').mockImplementation(() => undefined);
    expect(() => reportResponseTelemetry({ event: 'partial_parse_failure', reason: 'x' })).not.toThrow();
    spy.mockRestore();
  });

  it('the uninstall handle stops reporting', () => {
    const seen: ResponseTelemetryRecord[] = [];
    const uninstall = setResponseTelemetryReporter((record) => seen.push(record));
    uninstall();
    reportResponseTelemetry({ event: 'interaction' });
    expect(seen).toEqual([]);
  });
});
