import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  getActiveProjectId,
  projectClient,
  setActiveProjectId,
} from './project-client';

function stubStorage() {
  const map = new Map<string, string>();
  const storage = {
    getItem: (k: string) => (map.has(k) ? (map.get(k) as string) : null),
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
    key: (i: number) => Array.from(map.keys())[i] ?? null,
    get length() {
      return map.size;
    },
  };
  vi.stubGlobal('localStorage', storage);
  vi.stubGlobal('window', { localStorage: storage });
  return map;
}

describe('the active project', () => {
  beforeEach(() => {
    stubStorage();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('is null until one is chosen', () => {
    expect(getActiveProjectId()).toBeNull();
  });

  it('round-trips a project id', () => {
    setActiveProjectId('proj_abc123');
    expect(getActiveProjectId()).toBe('proj_abc123');
  });

  it('is cleared by null', () => {
    setActiveProjectId('proj_abc123');
    setActiveProjectId(null);
    expect(getActiveProjectId()).toBeNull();
  });

  it('refuses an id that is not a project id', () => {
    setActiveProjectId('not a valid id');
    expect(getActiveProjectId()).toBeNull();
  });

  it('never throws when localStorage is unavailable', () => {
    vi.stubGlobal('window', undefined);
    expect(() => setActiveProjectId('proj_abc123')).not.toThrow();
    expect(getActiveProjectId()).toBeNull();
  });
});

describe('the project client', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('lists the projects the runtime holds', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ projects: [{ id: 'proj_1', name: 'NQ momentum' }], count: 1 }),
    });
    vi.stubGlobal('fetch', fetchMock);
    const projects = await projectClient.list();
    expect(projects).toHaveLength(1);
    expect(projects[0].id).toBe('proj_1');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/harness/projects');
  });

  it('turns a runtime refusal into an honest error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ error: 'the project layer is unavailable' }),
    }));
    await expect(projectClient.list()).rejects.toThrow('the project layer is unavailable');
  });
});
