import { afterEach, describe, expect, it, vi } from 'vitest';
import { getInstitutionPreset, runInstitution } from '@/lib/harness/team-client';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Institution preset client', () => {
  it('asks the runtime for a filled team graph with the objective in the query', async () => {
    const fetchMock = vi.fn(async (
      _url: RequestInfo | URL,
      _init?: RequestInit,
    ) => jsonResponse({
      preset: { id: 'institution', name: 'Institution', version: 1, stages: [], roles: [], rules: '' },
      team: { id: 'institution-committee', name: 'Investment Committee', members: [], subtasks: [] },
      bots: [],
    }));
    vi.stubGlobal('fetch', fetchMock);

    await getInstitutionPreset({
      objective: 'Evaluate NVDA',
      universe: 'NVDA',
      constraints: ['max 5% single name'],
    });

    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain('/api/team/presets/institution?');
    expect(url).toContain('objective=Evaluate+NVDA');
    expect(url).toContain('universe=NVDA');
    expect(url).toContain('constraints=max+5%25+single+name');
  });

  it('starts the committee through the preset run route', async () => {
    const fetchMock = vi.fn(async (
      _url: RequestInfo | URL,
      _init?: RequestInit,
    ) => jsonResponse({
      teamRun: { id: 'teamrun_1', status: 'RUNNING' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const run = await runInstitution({ objective: 'Evaluate NVDA' });

    expect(run.id).toBe('teamrun_1');
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe('/api/team/presets/institution/run');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toMatchObject({ objective: 'Evaluate NVDA' });
  });
});
